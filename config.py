import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Google credentials передаются как JSON-строка в переменной окружения
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]

# Расшифровка голосовых через Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_TRANSCRIBE_MODEL = os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.8-flash")
# Запасные модели через запятую: на них бот переключается, если основная перегружена (503) или упирается в лимит (429)
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite").split(",")
    if m.strip()
]

# Рубрика «100 голосов»: сервис PostBot (адрес без / в конце) и общий секрет его закрытого API
POSTBOT_URL = os.environ.get("POSTBOT_URL", "")
VOICE_API_SECRET = os.environ.get("VOICE_API_SECRET", "")

# Лимит символов на один TTS-запрос для Google Cloud TTS (безопасный запас от лимита 5000 байт)
MAX_CHUNK_CHARS = 1500

DB_PATH = os.environ.get("DB_PATH", "user_settings.db")

# Секретный ключ для HTTP API расширения — защита от посторонних запросов
API_SECRET = os.environ.get("API_SECRET", "")

# Порт для HTTP сервера (Railway передаёт PORT автоматически)
PORT = int(os.environ.get("PORT", "8080"))

# Telegram chat_id владельца — куда отправлять аудио из HTTP API
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")

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
