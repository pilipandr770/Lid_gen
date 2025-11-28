"""
Модуль для генерації контенту через OpenAI API.
Створює корисні статті для автолюбителів на основі RSS новин.
"""
import os
from openai import OpenAI
from typing import Optional, Dict

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Ти — досвідчений автомобільний експерт та копірайтер. Твоє завдання — створювати корисний контент для українських автолюбителів.

ВАЖЛИВІ ПРАВИЛА:
1. Пиши ТІЛЬКИ українською мовою
2. ПРОПУСКАЙ і відмовляйся обробляти (відповідай SKIP):
   - Політичні новини (війна, уряд, політики, санкції, законопроекти)
   - Прямі рекламні матеріали зі знижками та акціями конкретних дилерів
   - Кримінальні новини (аварії зі смертями, ДТП з жертвами)
   - Новини про аукціони та продаж конкретних авто
   - Фотогалереї без тексту
3. ОБРОБЛЯЙ ВСЕ ІНШЕ, включаючи:
   - Огляди нових моделей авто → перероби у корисний огляд для покупця
   - Порівняння авто → зроби практичне порівняння
   - Тести та тест-драйви → виділи важливі характеристики
   - Технічні новини → поясни простою мовою
   - Електромобілі та гібриди → розкажи про переваги/недоліки
   - Ретро-авто та класика → цікаві факти для читачів

ФОРМАТ ВІДПОВІДІ:
- Заголовок: короткий, цікавий, з емодзі на початку
- Текст: 150-250 слів, розбитий на абзаци
- Наприкінці: заклик до дії або питання до читачів
- Додай 3-5 релевантних хештегів

Якщо стаття НЕ підходить — відповідай ТІЛЬКИ словом: SKIP"""

def generate_article(source_article: Dict) -> Optional[str]:
    """
    Генерує унікальну статтю на основі джерела.
    Повертає None якщо стаття не підходить (політика/реклама).
    """
    try:
        user_prompt = f"""Ось стаття з автомобільного сайту. Створи на її основі корисний пост для Telegram каналу:

ЗАГОЛОВОК: {source_article['title']}

ЗМІСТ: {source_article['summary'][:1500]}

ДЖЕРЕЛО: {source_article['source']}

Якщо це політика, реклама або кримінал — напиши тільки SKIP."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        result = response.choices[0].message.content.strip()
        
        # Перевіряємо чи це SKIP
        if result.upper().startswith("SKIP"):
            print(f"[CONTENT] Пропущено (не підходить): {source_article['title'][:50]}...")
            return None
        
        return result
        
    except Exception as e:
        print(f"[CONTENT ERROR] Помилка генерації: {e}")
        return None


def generate_article_from_topic(topic: str) -> Optional[str]:
    """
    Генерує статтю на задану тему (без джерела).
    Корисно для створення оригінального контенту.
    """
    try:
        user_prompt = f"Напиши корисну статтю для автолюбителів на тему: {topic}"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"[CONTENT ERROR] Помилка генерації: {e}")
        return None
