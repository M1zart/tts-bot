import os
import subprocess
import tempfile


def merge_mp3_chunks(mp3_chunks: list[bytes]) -> bytes:
    """Склеивает несколько MP3 байт-строк в одну через ffmpeg concat."""
    if len(mp3_chunks) == 1:
        return mp3_chunks[0]

    with tempfile.TemporaryDirectory() as tmpdir:
        file_paths = []
        for i, chunk in enumerate(mp3_chunks):
            path = os.path.join(tmpdir, f"chunk_{i}.mp3")
            with open(path, "wb") as f:
                f.write(chunk)
            file_paths.append(path)

        list_path = os.path.join(tmpdir, "list.txt")
        with open(list_path, "w") as f:
            for path in file_paths:
                f.write(f"file '{path}'\n")

        output_path = os.path.join(tmpdir, "output.mp3")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        with open(output_path, "rb") as f:
            return f.read()
