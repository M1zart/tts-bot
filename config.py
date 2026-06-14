import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Google credentials передаются как JSON-строка в переменной окружения
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]

# Лимит символов на один TTS-запрос для Google Cloud TTS (безопасный запас от лимита 5000 байт)
MAX_CHUNK_CHARS = 1500

DB_PATH = os.environ.get("DB_PATH", "user_settings.db")

# Доступные голоса (русские, бесплатный тир: Standard и Wavenet)
AVAILABLE_VOICES = {
    "wavenet_d": {"name": "ru-RU-Wavenet-D", "label": "Wavenet D (муж.)"},
    "wavenet_e": {"name": "ru-RU-Wavenet-E", "label": "Wavenet E (жен.)"},
    "wavenet_b": {"name": "ru-RU-Wavenet-B", "label": "Wavenet B (муж.)"},
    "wavenet_c": {"name": "ru-RU-Wavenet-C", "label": "Wavenet C (жен.)"},
    "standard_d": {"name": "ru-RU-Standard-D", "label": "Standard D (муж.)"},
    "standard_e": {"name": "ru-RU-Standard-E", "label": "Standard E (жен.)"},
}

DEFAULT_VOICE_KEY = "wavenet_d"
DEFAULT_SPEED = 1.0
MIN_SPEED = 0.5
MAX_SPEED = 2.0
