import re

from config import MAX_CHUNK_CHARS


def split_into_sentences(text: str) -> list[str]:
    """Грубое разбиение на предложения, сохраняя разделители."""
    # Разбиваем по концу предложения с учётом пробела/переноса после
    parts = re.split(r"(?<=[.!?…])\s+", text)
    return [p for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Режет текст на куски не длиннее max_chars символов,
    стараясь не разрывать предложения и абзацы.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""

    # Сначала по абзацам
    paragraphs = text.split("\n")

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) > max_chars:
            # Абзац сам слишком длинный — режем по предложениям
            sentences = split_into_sentences(paragraph)
            for sentence in sentences:
                if len(sentence) > max_chars:
                    # Совсем длинное предложение — режем жёстко по символам
                    for i in range(0, len(sentence), max_chars):
                        piece = sentence[i:i + max_chars]
                        if len(current) + len(piece) + 1 <= max_chars:
                            current = (current + " " + piece).strip()
                        else:
                            if current:
                                chunks.append(current)
                            current = piece
                else:
                    if len(current) + len(sentence) + 1 <= max_chars:
                        current = (current + " " + sentence).strip()
                    else:
                        if current:
                            chunks.append(current)
                        current = sentence
        else:
            if len(current) + len(paragraph) + 1 <= max_chars:
                current = (current + "\n" + paragraph).strip()
            else:
                if current:
                    chunks.append(current)
                current = paragraph

    if current:
        chunks.append(current)

    return chunks
