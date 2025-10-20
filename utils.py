"""
Додаткові утиліти для аналізу та експорту лідів.
"""
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta

DB_PATH = Path("leads.sqlite")

def get_stats() -> Dict[str, Any]:
    """Отримати статистику по лідах."""
    if not DB_PATH.exists():
        return {"error": "База даних не знайдена"}
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    stats = {}
    
    # Загальна кількість лідів
    cur.execute("SELECT COUNT(*) FROM leads")
    stats["total_leads"] = cur.fetchone()[0]
    
    # Статистика по каналах
    cur.execute("SELECT channel, COUNT(*) FROM leads GROUP BY channel")
    stats["by_channel"] = dict(cur.fetchall())
    
    # Статистика по ролях
    cur.execute("SELECT role_label, COUNT(*) FROM leads GROUP BY role_label")
    stats["by_role"] = dict(cur.fetchall())
    
    # Середня впевненість
    cur.execute("SELECT AVG(confidence) FROM leads WHERE role_label = 'potential_client'")
    avg_conf = cur.fetchone()[0]
    stats["avg_confidence"] = round(avg_conf, 2) if avg_conf else 0
    
    # Ліди за останні дні
    cur.execute("""
        SELECT DATE(created_at) as day, COUNT(*) 
        FROM leads 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY day DESC
    """)
    stats["last_7_days"] = dict(cur.fetchall())
    
    # Топ причини класифікації
    cur.execute("""
        SELECT reason, COUNT(*) as cnt
        FROM leads 
        WHERE role_label = 'potential_client'
        GROUP BY reason
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stats["top_reasons"] = dict(cur.fetchall())
    
    conn.close()
    return stats

def export_filtered_leads(
    min_confidence: float = 0.7,
    channel: str = None,
    days_back: int = 7,
    output_file: str = "filtered_leads.csv"
) -> str:
    """Експорт відфільтрованих лідів."""
    import csv
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    query = """
        SELECT user_id, username, display_name, channel, message_link, 
               role_label, confidence, reason, message_text, created_at
        FROM leads 
        WHERE role_label = 'potential_client' 
        AND confidence >= ?
        AND created_at >= datetime('now', '-{} days')
    """.format(days_back)
    
    params = [min_confidence]
    
    if channel:
        query += " AND channel = ?"
        params.append(channel)
    
    query += " ORDER BY confidence DESC, created_at DESC"
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id", "username", "display_name", "channel", "message_link",
            "role_label", "confidence", "reason", "message_text", "created_at"
        ])
        writer.writerows(rows)
    
    return output_file

def generate_outreach_templates(leads_csv: str = "filtered_leads.csv") -> str:
    """Генерує шаблони для звернення до лідів."""
    import csv
    
    templates = []
    
    with open(leads_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            username = row["username"] or row["display_name"]
            channel = row["channel"]
            reason = row["reason"]
            
            template = f"""
Привіт, {username}! 👋

Помітив твій коментар в {channel}, де ти {reason.lower()}.

Я займаюся [опиши свою послугу/продукт], можливо, це буде цікаво для тебе.

Джерело: {row['message_link']}

Якщо не цікавить - просто ігноруй це повідомлення 🙂

---
""".strip()
            
            templates.append({
                "user": username,
                "channel": channel,
                "template": template
            })
    
    # Зберегти у файл
    output_file = "outreach_templates.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for t in templates:
            f.write(f"=== {t['user']} ({t['channel']}) ===\n")
            f.write(t['template'])
            f.write("\n\n" + "="*50 + "\n\n")
    
    return output_file

def cleanup_old_leads(days_to_keep: int = 30) -> int:
    """Видалити старі ліди для GDPR compliance."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM leads 
        WHERE created_at < datetime('now', '-{} days')
    """.format(days_to_keep))
    
    deleted_count = cur.rowcount
    conn.commit()
    conn.close()
    
    return deleted_count

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Утиліти для роботи з лідами")
    parser.add_argument("--stats", action="store_true", help="Показати статистику")
    parser.add_argument("--export", action="store_true", help="Експорт відфільтрованих лідів")
    parser.add_argument("--templates", action="store_true", help="Генерувати шаблони звернень")
    parser.add_argument("--cleanup", type=int, help="Видалити ліди старші за N днів")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Мінімальна впевненість")
    parser.add_argument("--channel", help="Фільтр по каналу")
    parser.add_argument("--days", type=int, default=7, help="Кількість днів назад")
    
    args = parser.parse_args()
    
    if args.stats:
        stats = get_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    if args.export:
        file = export_filtered_leads(
            min_confidence=args.min_confidence,
            channel=args.channel,
            days_back=args.days
        )
        print(f"Експортовано у {file}")
    
    if args.templates:
        file = generate_outreach_templates()
        print(f"Шаблони збережено у {file}")
    
    if args.cleanup:
        deleted = cleanup_old_leads(args.cleanup)
        print(f"Видалено {deleted} старих лідів")