import asyncio
import base64
import logging
import time

import aiohttp

from config import GEMINI_API_KEY, GEMINI_TRANSCRIBE_MODEL, GEMINI_FALLBACK_MODELS

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = (
    "Расшифруй это аудио дословно, на языке оригинала (русский или украинский). "
    "Ничего не исправляй, не пересказывай и не добавляй. "
    "Верни только текст расшифровки, без пояснений и таймкодов."
)

# Inline-запрос у Gemini ограничен по размеру: base64 раздувает файл на треть
MAX_AUDIO_BYTES = 14 * 1024 * 1024


class TranscribeError(Exception):
    pass


def normalize_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if "ogg" in mime or "opus" in mime:
        return "audio/ogg"
    if mime in ("audio/mpeg", "audio/mp3"):
        return "audio/mp3"
    if mime in ("audio/x-m4a", "audio/m4a", "audio/mp4", "video/mp4"):
        return "audio/mp4" if mime != "video/mp4" else "video/mp4"
    return mime or "audio/ogg"


COOLDOWN_SECONDS = 90
ROUNDS = 2
ROUND_PAUSE = 5
_COOLDOWN: dict[str, float] = {}


async def transcribe(audio: bytes, mime: str) -> str:
    if not GEMINI_API_KEY:
        raise TranscribeError("GEMINI_API_KEY не задан в переменных Railway")
    if len(audio) > MAX_AUDIO_BYTES:
        raise TranscribeError("Файл слишком большой, пришли аудио до 14 МБ")

    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": normalize_mime(mime), "data": base64.b64encode(audio).decode()}},
                {"text": PROMPT},
            ]
        }],
        "generationConfig": {"temperature": 0},
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    models = [GEMINI_TRANSCRIBE_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_TRANSCRIBE_MODEL]
    last = "неизвестная ошибка"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
        for round_no in range(ROUNDS):
            now = time.monotonic()
            # модели, которые только что упали, пропускаем; если упали все, пробуем все
            active = [m for m in models if _COOLDOWN.get(m, 0) <= now] or models
            for model in active:
                url = API_URL.format(model=model)
                async with session.post(url, json=body, headers=headers) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status == 200:
                        parts = (((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
                        text = "".join(p.get("text", "") for p in parts).strip()
                        if text:
                            if model != GEMINI_TRANSCRIBE_MODEL:
                                logger.info("Transcribed with fallback model %s", model)
                            return text
                        last = f"{model}: пустой ответ"
                    else:
                        msg = ((data or {}).get("error") or {}).get("message", "")
                        last = f"{model}: HTTP {resp.status}: {msg[:200]}"
                        logger.warning("Gemini %s", last)
                        # перегрузка и лимиты: сразу следующая модель, упавшую не трогаем COOLDOWN_SECONDS
                        if resp.status in (408, 429) or resp.status >= 500:
                            _COOLDOWN[model] = time.monotonic() + COOLDOWN_SECONDS
            if round_no < ROUNDS - 1:
                await asyncio.sleep(ROUND_PAUSE)
    logger.error("Gemini transcribe failed: %s", last)
    raise TranscribeError(f"Gemini не расшифровал аудио: {last}")
