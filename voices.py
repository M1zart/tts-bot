"""Рубрика «100 голосов iGaming»: диалог в боте. Расшифровка идет здесь (Gemini),
раскладка по вопросам и запись в Notion делает сервис PostBot через закрытый API."""
import asyncio
import logging
import re

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import POSTBOT_URL, VOICE_API_SECRET
from stt.gemini_stt import transcribe, TranscribeError
from stt.text import split_for_telegram

logger = logging.getLogger(__name__)

# user_id -> сессия (в памяти: после перезапуска бота открывается заново)
sessions: dict = {}

CANCEL_BTN = InlineKeyboardButton("Отмена", callback_data="vo:x")
DONE_BTN = InlineKeyboardButton("Готово", callback_data="vo:go")


def configured() -> bool:
    return bool(POSTBOT_URL and VOICE_API_SECRET)


def kb(rows):
    return InlineKeyboardMarkup(rows)


def word(n: int) -> str:
    return "голосовое" if n % 10 == 1 and n % 100 != 11 else "голосовых"


async def api(method: str, path: str, payload=None, timeout=300):
    url = POSTBOT_URL.rstrip("/") + "/api/voice-api/" + path
    headers = {"Authorization": f"Bearer {VOICE_API_SECRET}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
        async with http.request(method, url, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200 or not data.get("ok"):
                raise RuntimeError((data or {}).get("error") or f"HTTP {resp.status}")
            return data


async def download(bot, file_id: str) -> bytes:
    f = await bot.get_file(file_id)
    return bytes(await f.download_as_bytearray())


async def intake(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, mime: str):
    """Пересланное голосовое: собираем пачку, через 1.5 с просим написать роль и стаж."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    s = sessions.get(user_id)
    if s and s["busy"]:
        await update.message.reply_text("Сейчас обрабатываю предыдущую пачку, подожди минуту.")
        return
    if not configured():
        await update.message.reply_text(
            "Рубрика голосов не настроена: задай POSTBOT_URL и VOICE_API_SECRET в переменных Railway."
        )
        return
    if not s:
        s = {"chat_id": chat_id, "voices": [], "step": "role", "role": None, "role_title": "", "number": None,
             "exp": "", "other_qs": [], "busy": False, "task": None, "info": None}
        sessions[user_id] = s
    s["voices"].append((file_id, mime))
    if s["task"]:
        s["task"].cancel()
    s["task"] = context.application.create_task(announce(context.bot, s))


def err_text(e: Exception) -> str:
    """У таймаутов и обрывов связи текст ошибки пустой: показываем хотя бы тип."""
    msg = str(e).strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def select_name(title: str) -> str:
    """Notion не принимает запятые в названиях select: так же считает PostBot."""
    return " ".join((title or "").replace(",", " ").split())


EXP_RE = re.compile(
    r"((?:более|больше|свыше|over|more than)?\s*\d+\s*\+?\s*(?:лет|года|год|годов|years?|yrs?)\b[^,;\n]*|\b\d+\s*\+)", re.I)
TAIL_NUM_RE = re.compile(r"\s(\d{1,2})\s*$")
NUM_RE = re.compile(r"[#№]\s*(\d{1,4})")


def parse_hero(text: str):
    """Из одной строки вида «Head of Risk, 12 лет» достает роль, стаж и необязательный номер (#7 или №7)."""
    text = (text or "").strip()
    number = None
    m = NUM_RE.search(text)
    if m:
        number = int(m.group(1))
        text = (text[:m.start()] + " " + text[m.end():]).strip()
    exp = ""
    m = EXP_RE.search(text)
    if m:
        exp = m.group(1).strip(" .,-—–")
        text = (text[:m.start()] + " " + text[m.end():])
    if not exp:
        m = TAIL_NUM_RE.search(text)
        if m:
            exp = m.group(1) + " лет"
            text = text[:m.start()]
    role = re.sub(r"\s+", " ", text).strip(" ,;-—–.\n")
    role = re.sub(r"\b(стаж|опыт)\s*[:\-]?$", "", role, flags=re.I).strip(" ,;-—–.")
    return role, exp[:80], number


def match_roles(role_text: str, roles: list) -> list:
    low = (role_text or "").lower()
    exact = [r for r in roles if low == r["title"].lower()]
    if exact:
        return exact
    out = []
    for r in roles:
        keys = [a.lower() for a in r.get("aliases", [])] + [r["title"].lower()]
        if any(k and k in low for k in keys):
            out.append(r)
    return out


def nth(n: int) -> str:
    return f"{n}-й"


async def announce(bot, s):
    try:
        await asyncio.sleep(1.5)
        if s["step"] == "role":
            s["info"] = await api("GET", "info", timeout=30)
            await bot.send_message(
                s["chat_id"],
                f"Принял {len(s['voices'])} {word(len(s['voices']))}. Напиши, чей голос: роль и стаж одним сообщением, "
                f"например «Head of Risk, 12 лет». Номер бот поставит сам, если нужен другой, допиши «№7».",
                reply_markup=kb([[InlineKeyboardButton("Только расшифровка", callback_data="vo:r:plain")], [CANCEL_BTN]]),
            )
        elif s["step"] == "ready":
            await bot.send_message(s["chat_id"], f"Добавил. Всего голосовых: {len(s['voices'])}.",
                                   reply_markup=kb([[DONE_BTN, CANCEL_BTN]]))
        else:
            await bot.send_message(s["chat_id"], f"Добавил. Всего голосовых: {len(s['voices'])}.")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("voice announce failed")
        await bot.send_message(s["chat_id"], f"Не получилось связаться с PostBot: {err_text(e)}")


def role_title(s) -> str:
    return s.get("role_title") or ""


def role_count(s) -> int:
    """Сколько голосов этой роли уже есть в Notion."""
    counts = (s.get("info") or {}).get("counts") or {}
    return int(counts.get(select_name(role_title(s)), 0))


async def ask_ready(bot, s):
    s["step"] = "ready"
    if s["number"] is None:
        s["number"] = int((s.get("info") or {}).get("next", 1))
    exp = f", {s['exp']}" if s["exp"] else ""
    k = role_count(s) + 1
    note = "Первый голос этой роли." if k == 1 else f"Это {nth(k)} голос этой роли, до него уже {k - 1}."
    if s["role"] == "other":
        note += " Роли нет в списке: вопросы по роли бот восстановит из ответов."
    await bot.send_message(
        s["chat_id"],
        f"Голос #{s['number']}: {role_title(s)}{exp}\n{note}\nГолосовых: {len(s['voices'])}. "
        f"Можно досылать еще. Если что-то не так, напиши роль и стаж заново. Нажми «Готово», когда все.",
        reply_markup=kb([[DONE_BTN, CANCEL_BTN]]),
    )


async def after_role(bot, s):
    """Роль определена. Для роли вне списка вопросы не нужны: PostBot восстановит их из самих ответов."""
    await ask_ready(bot, s)


async def handle_session_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Текст в чате, пока открыта сессия: роль и стаж или вопросы для новой роли. True = текст использован."""
    s = sessions.get(update.effective_user.id)
    if not s or s["busy"] or s["step"] not in ("role", "ready", "pick"):
        return False
    text = (update.message.text or "").strip()
    bot = context.bot
    # role / ready / pick: считаем, что человек пишет роль и стаж (заново тоже можно)
    if not s.get("info"):
        try:
            s["info"] = await api("GET", "info", timeout=30)
        except Exception as e:
            await update.message.reply_text(f"Не получилось связаться с PostBot: {err_text(e)}")
            return True
    role_text, exp, number = parse_hero(text)
    if not role_text:
        await update.message.reply_text("Не вижу роли. Напиши, например: Head of Risk, 12 лет.")
        return True
    s["exp"] = exp
    s["number"] = number
    s["other_qs"] = []
    roles = (s.get("info") or {}).get("roles", [])
    found = match_roles(role_text, roles)
    if len(found) == 1:
        s["role"], s["role_title"] = found[0]["key"], found[0]["title"]
        await after_role(bot, s)
    elif len(found) > 1:
        s["step"] = "pick"
        rows = [[InlineKeyboardButton(r["title"], callback_data="vo:r:" + r["key"])] for r in found]
        rows.append([CANCEL_BTN])
        await bot.send_message(s["chat_id"], "Подходит несколько ролей, какая?", reply_markup=kb(rows))
    else:
        s["role"], s["role_title"] = "other", role_text[:60]
        await after_role(bot, s)
    return True


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    s = sessions.get(user_id)
    if not s:
        await query.answer("Сессия не открыта: перешли голосовые заново")
        return
    if s["busy"]:
        await query.answer("Обрабатываю, подожди")
        return
    await query.answer()
    parts = query.data.split(":")
    kind = parts[1]
    arg = parts[2] if len(parts) > 2 else None
    bot = context.bot

    if kind == "x":
        if s["task"]:
            s["task"].cancel()
        sessions.pop(user_id, None)
        await bot.send_message(s["chat_id"], "Отменено, голосовые не сохранены.")
        return
    if kind == "r" and arg == "plain" and s["step"] in ("role", "pick"):
        await process_plain(bot, user_id, s)
        return
    if kind == "r" and s["step"] == "pick":
        for r in (s.get("info") or {}).get("roles", []):
            if r["key"] == arg:
                s["role"], s["role_title"] = r["key"], r["title"]
                await after_role(bot, s)
                return
        return
    if kind == "go":
        if s["step"] != "ready":
            await bot.send_message(s["chat_id"], "Сначала напиши роль и стаж героя.")
            return
        await process(bot, user_id, s)


async def transcribe_all(bot, s, status_text: str):
    await bot.send_message(s["chat_id"], status_text)
    parts = []
    for i, (file_id, mime) in enumerate(s["voices"], 1):
        try:
            audio = await download(bot, file_id)
        except Exception as e:
            raise RuntimeError(f"Голосовое {i}: не скачалось ({e}). Бот скачивает файлы до 20 МБ") from e
        text = await transcribe(audio, mime)
        parts.append((i, text))
    return parts


async def process_plain(bot, user_id, s):
    s["busy"] = True
    try:
        parts = await transcribe_all(bot, s, f"Расшифровываю {len(s['voices'])} {word(len(s['voices']))}…")
        for i, text in parts:
            head = f"[Голосовое {i}]\n" if len(parts) > 1 else ""
            for chunk in split_for_telegram(head + text):
                await bot.send_message(s["chat_id"], chunk)
        sessions.pop(user_id, None)
    except (TranscribeError, RuntimeError) as e:
        s["busy"] = False
        await bot.send_message(s["chat_id"], f"Не получилось: {err_text(e)}\n\nСессия сохранена, нажми «Только расшифровка» еще раз.",
                               reply_markup=kb([[InlineKeyboardButton("Только расшифровка", callback_data="vo:r:plain")], [CANCEL_BTN]]))
    except Exception as e:
        s["busy"] = False
        logger.exception("plain transcribe failed")
        await bot.send_message(s["chat_id"], f"Не получилось: {err_text(e)}")


async def process(bot, user_id, s):
    s["busy"] = True
    try:
        parts = await transcribe_all(
            bot, s, f"Обрабатываю {len(s['voices'])} {word(len(s['voices']))}, это займет пару минут…")
        transcript = "\n\n".join(f"[Голосовое {i}]\n{text}" for i, text in parts)
        await api("POST", "submit", {
            "role": s["role"], "otherQs": s["other_qs"], "number": s["number"],
            "exp": s["exp"], "transcript": transcript,
            "roleTitle": s["role_title"] if s["role"] == "other" else "",
        })
        sessions.pop(user_id, None)
        await bot.send_message(s["chat_id"], f"Голос #{s['number']} готов, открой вкладку «Голос» в приложении PostBot.")
    except Exception as e:
        s["busy"] = False
        logger.exception("voice process failed")
        await bot.send_message(
            s["chat_id"], f"Не получилось: {err_text(e)[:400]}\n\nСессия сохранена, нажми «Готово» еще раз.",
            reply_markup=kb([[DONE_BTN, CANCEL_BTN]]),
        )
