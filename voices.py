"""Рубрика «100 голосов iGaming»: диалог в боте. Расшифровка идет здесь (Gemini),
раскладка по вопросам и запись в Notion делает сервис PostBot через закрытый API."""
import asyncio
import logging

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
    """Пересланное голосовое: собираем пачку, через 1.5 с задаем вопрос про роль."""
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
        s = {"chat_id": chat_id, "voices": [], "step": "role", "role": None, "number": None,
             "exp": "", "other_qs": [], "busy": False, "task": None, "info": None}
        sessions[user_id] = s
    s["voices"].append((file_id, mime))
    if s["task"]:
        s["task"].cancel()
    s["task"] = context.application.create_task(announce(context.bot, s))


async def announce(bot, s):
    try:
        await asyncio.sleep(1.5)
        if s["step"] == "role":
            info = await api("GET", "info", timeout=30)
            s["info"] = info
            rows = [[InlineKeyboardButton(r["title"], callback_data="vo:r:" + r["key"])] for r in info["roles"]]
            rows.append([InlineKeyboardButton(info.get("other", "Другое"), callback_data="vo:r:other")])
            rows.append([InlineKeyboardButton("Только расшифровка", callback_data="vo:r:plain")])
            rows.append([CANCEL_BTN])
            await bot.send_message(s["chat_id"], f"Принял {len(s['voices'])} {word(len(s['voices']))}. Чей голос?",
                                   reply_markup=kb(rows))
        else:
            await bot.send_message(s["chat_id"], f"Добавил. Всего голосовых: {len(s['voices'])}.",
                                   reply_markup=kb([[DONE_BTN, CANCEL_BTN]]))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("voice announce failed")
        await bot.send_message(s["chat_id"], f"Не получилось связаться с PostBot: {e}")


async def ask_number(bot, s):
    s["step"] = "number"
    nxt = (s.get("info") or {}).get("next", 1)
    await bot.send_message(
        s["chat_id"], "Номер голоса? Нажми кнопку или напиши число.",
        reply_markup=kb([[InlineKeyboardButton(f"Голос #{nxt}", callback_data=f"vo:n:{nxt}")], [CANCEL_BTN]]),
    )


async def ask_exp(bot, s):
    s["step"] = "exp"
    await bot.send_message(
        s["chat_id"], "Стаж героя? Напиши текстом (например, «12 лет в индустрии») или пропусти.",
        reply_markup=kb([[InlineKeyboardButton("Пропустить", callback_data="vo:skip")], [CANCEL_BTN]]),
    )


def role_title(s) -> str:
    if s["role"] == "other":
        return (s.get("info") or {}).get("other", "Другое")
    for r in (s.get("info") or {}).get("roles", []):
        if r["key"] == s["role"]:
            return r["title"]
    return s["role"] or ""


async def ask_ready(bot, s):
    s["step"] = "ready"
    exp = f", {s['exp']}" if s["exp"] else ""
    await bot.send_message(
        s["chat_id"],
        f"Голос #{s['number']}: {role_title(s)}{exp}\nГолосовых: {len(s['voices'])}. "
        f"Можно досылать еще. Нажми «Готово», когда все.",
        reply_markup=kb([[DONE_BTN, CANCEL_BTN]]),
    )


async def handle_session_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Текст в чате, пока открыта сессия: номер, стаж или вопросы для роли «Другое». True = текст использован."""
    s = sessions.get(update.effective_user.id)
    if not s or s["busy"] or s["step"] not in ("number", "exp", "otherq"):
        return False
    text = (update.message.text or "").strip()
    bot = context.bot
    if s["step"] == "number":
        if not text.isdigit() or len(text) > 4:
            await update.message.reply_text("Нужно число, например 7.")
            return True
        s["number"] = int(text)
        await ask_exp(bot, s)
        return True
    if s["step"] == "exp":
        s["exp"] = text[:80]
        await ask_ready(bot, s)
        return True
    need = int((s.get("info") or {}).get("roleQuestions", 3))
    qs = [q.strip().lstrip("0123456789.) ").strip() for q in text.split("\n")]
    qs = [q for q in qs if q]
    if len(qs) != need:
        await update.message.reply_text(f"Нужно ровно {need} вопроса, каждый с новой строки.")
        return True
    s["other_qs"] = qs
    await ask_number(bot, s)
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
    if kind == "r" and s["step"] == "role":
        if arg == "plain":
            await process_plain(bot, user_id, s)
            return
        s["role"] = arg
        if arg == "other":
            s["step"] = "otherq"
            need = int((s.get("info") or {}).get("roleQuestions", 3))
            await bot.send_message(
                s["chat_id"], f"Пришли {need} вопроса для этого героя одним сообщением, каждый с новой строки.",
                reply_markup=kb([[CANCEL_BTN]]),
            )
            return
        await ask_number(bot, s)
        return
    if kind == "n" and s["step"] == "number":
        s["number"] = int(arg)
        await ask_exp(bot, s)
        return
    if kind == "skip" and s["step"] == "exp":
        s["exp"] = ""
        await ask_ready(bot, s)
        return
    if kind == "go":
        if s["step"] != "ready":
            await bot.send_message(s["chat_id"], "Сначала выбери роль, номер и стаж.")
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
        await bot.send_message(s["chat_id"], f"Не получилось: {e}\n\nСессия сохранена, выбери роль заново.",
                               reply_markup=kb([[CANCEL_BTN]]))
    except Exception as e:
        s["busy"] = False
        logger.exception("plain transcribe failed")
        await bot.send_message(s["chat_id"], f"Не получилось: {e}")


async def process(bot, user_id, s):
    s["busy"] = True
    try:
        parts = await transcribe_all(
            bot, s, f"Обрабатываю {len(s['voices'])} {word(len(s['voices']))}, это займет пару минут…")
        transcript = "\n\n".join(f"[Голосовое {i}]\n{text}" for i, text in parts)
        await api("POST", "submit", {
            "role": s["role"], "otherQs": s["other_qs"], "number": s["number"],
            "exp": s["exp"], "transcript": transcript,
        })
        sessions.pop(user_id, None)
        await bot.send_message(s["chat_id"], f"Голос #{s['number']} готов, открой вкладку «Голос» в приложении PostBot.")
    except Exception as e:
        s["busy"] = False
        logger.exception("voice process failed")
        await bot.send_message(
            s["chat_id"], f"Не получилось: {str(e)[:400]}\n\nСессия сохранена, нажми «Готово» еще раз.",
            reply_markup=kb([[DONE_BTN, CANCEL_BTN]]),
        )
