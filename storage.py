import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

import os

# Якщо задана змінна DATA_DIR, використовуємо її, інакше поточна папка
data_dir = os.getenv("DATA_DIR")
if data_dir and data_dir != "/data":  # /data тільки для Render
    DB_PATH = Path(data_dir) / "leads.sqlite"
else:
    DB_PATH = Path(".") / "leads.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    display_name TEXT,
    channel TEXT,
    message_id INTEGER,
    message_text TEXT,
    role_label TEXT,          -- 'promoter' | 'potential_client' | 'other'
    confidence REAL,
    reason TEXT,
    message_link TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_channel ON leads(channel);

CREATE TABLE IF NOT EXISTS checked_messages (
    message_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_checked_channel ON checked_messages(channel_id);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def insert_lead(row: Dict[str, Any]) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (user_id, username, display_name, channel, message_id, message_text,
                           role_label, confidence, reason, message_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row.get("user_id"),
        row.get("username"),
        row.get("display_name"),
        row.get("channel"),
        row.get("message_id"),
        row.get("message_text"),
        row.get("role_label"),
        row.get("confidence"),
        row.get("reason"),
        row.get("message_link"),
    ))
    conn.commit()
    conn.close()

def export_csv(path: str = "leads_export.csv") -> str:
    import csv
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, display_name, channel, message_link, role_label, confidence, reason, message_text, created_at FROM leads ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id","username","display_name","channel","message_link","role_label","confidence","reason","message_text","created_at"])
        writer.writerows(rows)
    return path


def is_message_checked(message_id: int) -> bool:
    """Перевіряє чи повідомлення вже було оброблено."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM checked_messages WHERE message_id = ?", (message_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None


def mark_message_checked(message_id: int, channel_id: int) -> None:
    """Позначає повідомлення як оброблене."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO checked_messages (message_id, channel_id) VALUES (?, ?)",
        (message_id, channel_id)
    )
    conn.commit()
    conn.close()


def get_checked_messages_count() -> int:
    """Повертає кількість перевірених повідомлень."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM checked_messages")
    result = cur.fetchone()[0]
    conn.close()
    return result


def cleanup_old_checked_messages(days: int = 14) -> int:
    """Видаляє старі записи про перевірені повідомлення (старше N днів)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM checked_messages WHERE checked_at < datetime('now', ?)",
        (f'-{days} days',)
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted