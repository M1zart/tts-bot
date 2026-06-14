import sqlite3
from contextlib import contextmanager

from config import DB_PATH, DEFAULT_VOICE_KEY, DEFAULT_SPEED


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                voice_key TEXT NOT NULL DEFAULT '{DEFAULT_VOICE_KEY}',
                speed REAL NOT NULL DEFAULT {DEFAULT_SPEED}
            )
            """
        )


def get_user_settings(user_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT voice_key, speed FROM user_settings WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO user_settings (user_id, voice_key, speed) VALUES (?, ?, ?)",
                (user_id, DEFAULT_VOICE_KEY, DEFAULT_SPEED),
            )
            return {"voice_key": DEFAULT_VOICE_KEY, "speed": DEFAULT_SPEED}
        return {"voice_key": row[0], "speed": row[1]}


def set_user_voice(user_id: int, voice_key: str):
    get_user_settings(user_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE user_settings SET voice_key = ? WHERE user_id = ?",
            (voice_key, user_id),
        )


def set_user_speed(user_id: int, speed: float):
    get_user_settings(user_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE user_settings SET speed = ? WHERE user_id = ?",
            (speed, user_id),
        )
