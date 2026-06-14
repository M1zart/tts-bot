# Telegram TTS Bot

Бот озвучивает текст голосом через Google Cloud Text-to-Speech.

## Команды

- `/start` — приветствие и краткая справка
- `/voice` — выбрать голос (инлайн-кнопки)
- `/speed 1.25` — установить скорость речи (0.5–2.0)
- `/settings` — показать текущие настройки

## Использование

Просто перешли или напиши боту любой текст — он вернёт voice/audio сообщение.
Длинные тексты автоматически режутся на чанки и склеиваются в один файл.

## Переменные окружения (для Railway)

- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather
- `GOOGLE_CREDENTIALS_JSON` — содержимое JSON-ключа service account целиком (как одна строка)
- `DB_PATH` — путь к SQLite файлу (опционально, по умолчанию `user_settings.db`)

## Важно про FFmpeg

`pydub` требует наличие `ffmpeg` в системе для склейки MP3-чанков.
На Railway добавь через `nixpacks.toml`:

```toml
[phases.setup]
nixPkgs = ["ffmpeg"]
```

## Деплой на Railway

1. Залей проект в GitHub репозиторий
2. На Railway: New Project → Deploy from GitHub repo
3. Добавь переменные окружения (Settings → Variables)
4. Railway автоматически подхватит `Procfile` и запустит worker
