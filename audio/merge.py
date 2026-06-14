import io

from pydub import AudioSegment


def merge_mp3_chunks(mp3_chunks: list[bytes]) -> bytes:
    """Склеивает несколько MP3 байт-строк в одну."""
    combined = AudioSegment.empty()

    for chunk in mp3_chunks:
        segment = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
        combined += segment

    out = io.BytesIO()
    combined.export(out, format="mp3")
    return out.getvalue()
