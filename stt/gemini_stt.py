import asyncio
import base64
import logging

import aiohttp

from config import GEMINI_API_KEY, GEMINI_TRANSCRIBE_MODEL

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
    url = API_URL.format(model=GEMINI_TRANSCRIBE_MODEL)
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    last = "неизвестная ошибка"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
        for attempt in range(3):
            async with session.post(url, json=body, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 200:
                    parts = (((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                    last = "пустой ответ"
                else:
                    msg = ((data or {}).get("error") or {}).get("message", "")
                    last = f"HTTP {resp.status}: {msg[:200]}"
                    # 4xx кроме 408/429: повтор не поможет
                    if resp.status < 500 and resp.status not in (408, 429):
                        break
            await asyncio.sleep(2 * (attempt + 1))
    logger.error("Gemini transcribe failed: %s", last)
    raise TranscribeError(f"Gemini не расшифровал аудио: {last}")
