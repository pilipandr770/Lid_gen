"""
Модуль для отримання та парсингу RSS стрічок автомобільних сайтів.
"""
import os
import hashlib
import feedparser
import urllib.request
from typing import List, Dict, Optional
from pathlib import Path

# User-Agent для обходу блокування
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

data_dir = os.getenv("DATA_DIR", ".")
if data_dir == "/data" and not os.path.exists("/data"):
    data_dir = "."  # Якщо /data не існує (локальний запуск), використовуємо поточну папку
SEEN_ARTICLES_FILE = os.path.join(data_dir, "seen_articles.txt")


def load_seen_articles() -> set:
    """Завантажує список вже оброблених статей."""
    if not os.path.exists(SEEN_ARTICLES_FILE):
        return set()
    with open(SEEN_ARTICLES_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_seen_article(article_id: str):
    """Зберігає ID статті як оброблену."""
    with open(SEEN_ARTICLES_FILE, "a", encoding="utf-8") as f:
        f.write(f"{article_id}\n")


def get_article_id(entry: dict) -> str:
    """Генерує унікальний ID для статті."""
    # Використовуємо link або title для створення хешу
    unique_str = entry.get("link", "") or entry.get("title", "")
    return hashlib.md5(unique_str.encode()).hexdigest()


def fetch_rss_feeds(feed_urls: List[str]) -> List[Dict]:
    """
    Отримує статті з RSS стрічок.
    Повертає список нових (ще не оброблених) статей.
    """
    seen = load_seen_articles()
    new_articles = []
    
    for url in feed_urls:
        try:
            # Завантажуємо RSS з User-Agent
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            response = urllib.request.urlopen(request, timeout=10)
            feed_content = response.read()
            feed = feedparser.parse(feed_content)
            
            for entry in feed.entries[:10]:  # Беремо тільки останні 10 з кожного джерела
                article_id = get_article_id(entry)
                
                if article_id in seen:
                    continue
                
                # Витягуємо основні дані
                article = {
                    "id": article_id,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "source": feed.feed.get("title", url),
                    "published": entry.get("published", ""),
                }
                
                # Фільтруємо порожні
                if article["title"] and article["summary"]:
                    new_articles.append(article)
                    
        except Exception as e:
            print(f"[RSS ERROR] Помилка при читанні {url}: {e}")
            continue
    
    return new_articles


def mark_article_as_processed(article_id: str):
    """Позначає статтю як оброблену."""
    save_seen_article(article_id)
