def merge_mp3_chunks(mp3_chunks: list[bytes]) -> bytes:
    """
    Склеивает несколько MP3 байт-строк простой конкатенацией.
    Для constant-bitrate MP3 (как у Google TTS) это работает надёжно
    в большинстве плееров, включая Telegram.
    """
    if len(mp3_chunks) == 1:
        return mp3_chunks[0]

    return b"".join(mp3_chunks)
