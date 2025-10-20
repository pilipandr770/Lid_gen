from typing import Tuple, Dict
from openai import OpenAI
from config import settings

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """Ти — асистент для класифікації коментарів у Telegram.
Мета: знайти потенційних клієнтів (людей, які цікавляться заданою темою) та відсіяти промо/адмін-повідомлення.
Відповідай коротким JSON з полями:
role: "promoter" | "potential_client" | "other"
confidence: число 0..1
reason: коротке пояснення українською
Увага: "promoter" якщо повідомлення рекламує, просуває, модерує або виглядає як офіційний представник/адмін/бот.
"potential_client" якщо людина задає питання, шукає рішення або явно цікавиться темою.
"""

def classify_comment(
    text: str,
    author_display: str,
    is_verified_or_admin: bool,
    interest_keywords: list[str]
) -> Dict:
    kw = ", ".join(interest_keywords) if interest_keywords else "(без ключових слів)"
    user_hint = f"Ключові слова інтересу: {kw}. Автор: {author_display}. Ознака адміна/верифікації: {is_verified_or_admin}."

    # Використаємо легку модель для економії
    prompt = f"""Текст коментаря:
{text}

Додаткова інформація:
{user_hint}
"""

    try:
        # Використовуємо стандартний API ChatCompletion
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=500
        )
        
        out = response.choices[0].message.content.strip()
        
        # Витягнемо JSON
        import json, re
        try:
            # Витяг JSON-об'єкта
            match = re.search(r'\{.*\}', out, re.S)
            if match:
                data = json.loads(match.group(0))
            else:
                # fallback на простий аналіз
                data = {"role":"other","confidence":0.5,"reason":"Не вдалося надійно розпізнати."}
        except Exception:
            data = {"role":"other","confidence":0.5,"reason":"Парсинг відповіді не вдався."}
    
    except Exception as e:
        print(f"[ERROR] OpenAI API помилка: {e}")
        data = {"role":"other","confidence":0.5,"reason":f"API помилка: {str(e)}"}

    # Гарантії полів
    role = data.get("role","other")
    if role not in ("promoter","potential_client","other"):
        role = "other"
    conf = float(data.get("confidence", 0.5))
    reason = str(data.get("reason",""))
    return {"role": role, "confidence": conf, "reason": reason}