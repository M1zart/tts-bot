import asyncio
import base64
import logging

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
    ATTEMPTS_PER_MODEL = 3
    last = "неизвестная ошибка"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
        for model in models:
            url = API_URL.format(model=model)
            for attempt in range(ATTEMPTS_PER_MODEL):
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
                        # Перегрузка и лимиты временные: повтор, затем следующая модель.
                        # Остальные 4xx (ключ, формат, нет доступа к модели): повтор не поможет, пробуем следующую
                        if resp.status not in (408, 429) and resp.status < 500:
                            break
                # пауза растет: 3, 6 секунд; после последней попытки сразу следующая модель
                if attempt < ATTEMPTS_PER_MODEL - 1:
                    await asyncio.sleep(3 * (attempt + 1))
    logger.error("Gemini transcribe failed: %s", last)
    raise TranscribeError(f"Gemini не расшифровал аудио: {last}")
