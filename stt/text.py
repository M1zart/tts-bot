from typing import List

TG_MESSAGE_LIMIT = 4000


def split_for_telegram(text: str, limit: int = TG_MESSAGE_LIMIT):
    """Режет длинную расшифровку на сообщения, стараясь резать по абзацам и предложениям."""
    parts = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(". ", 0, limit) + 1, text.rfind(" ", 0, limit))
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts
