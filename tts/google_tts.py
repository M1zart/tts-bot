import asyncio
import json

from google.cloud import texttospeech
from google.oauth2 import service_account

from config import GOOGLE_CREDENTIALS_JSON, AVAILABLE_VOICES
from tts.chunker import chunk_text


def _build_client() -> texttospeech.TextToSpeechClient:
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return texttospeech.TextToSpeechClient(credentials=credentials)


_client = None


def get_client() -> texttospeech.TextToSpeechClient:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _synthesize_chunk_sync(text: str, voice_name: str, speed: float) -> bytes:
    client = get_client()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="ru-RU",
        name=voice_name,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speed,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


async def synthesize_text(text: str, voice_key: str, speed: float) -> bytes:
    """
    Разбивает текст на чанки, синтезирует каждый асинхронно,
    возвращает склеенный MP3 как bytes.
    """
    from audio.merge import merge_mp3_chunks

    voice_name = AVAILABLE_VOICES[voice_key]["name"]
    chunks = chunk_text(text)

    if not chunks:
        raise ValueError("Текст пустой после обработки")

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _synthesize_chunk_sync, chunk, voice_name, speed)
        for chunk in chunks
    ]
    audio_chunks = await asyncio.gather(*tasks)

    if len(audio_chunks) == 1:
        return audio_chunks[0]

    return merge_mp3_chunks(list(audio_chunks))
