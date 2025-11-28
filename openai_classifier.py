from typing import Tuple, Dict, List
import json
import os
import time
from openai import OpenAI
from config import settings

client = OpenAI(api_key=settings.openai_api_key)

# Директорія для batch файлів
data_dir = os.getenv("DATA_DIR", ".")
BATCH_INPUT_FILE = os.path.join(data_dir, "batch_input.jsonl")
BATCH_OUTPUT_FILE = os.path.join(data_dir, "batch_output.jsonl")
BATCH_STATUS_FILE = os.path.join(data_dir, "batch_status.json")

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


# ============ BATCH API (50% дешевше) ============

def create_batch_request(custom_id: str, text: str, author_display: str, 
                         is_verified_or_admin: bool, interest_keywords: list) -> dict:
    """Створює один запит для batch файлу."""
    kw = ", ".join(interest_keywords) if interest_keywords else "(без ключових слів)"
    user_hint = f"Ключові слова інтересу: {kw}. Автор: {author_display}. Ознака адміна/верифікації: {is_verified_or_admin}."
    
    prompt = f"""Текст коментаря:
{text}

Додаткова інформація:
{user_hint}
"""
    
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 500
        }
    }


def save_batch_requests(requests: List[dict]) -> str:
    """Зберігає запити у JSONL файл для batch обробки."""
    with open(BATCH_INPUT_FILE, "w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")
    return BATCH_INPUT_FILE


def submit_batch() -> str:
    """Відправляє batch на обробку. Повертає batch_id."""
    # Завантажуємо файл
    with open(BATCH_INPUT_FILE, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")
    
    # Створюємо batch
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"  # 50% знижка!
    )
    
    # Зберігаємо статус
    status = {
        "batch_id": batch.id,
        "file_id": batch_file.id,
        "status": batch.status,
        "created_at": time.time()
    }
    with open(BATCH_STATUS_FILE, "w") as f:
        json.dump(status, f)
    
    print(f"[BATCH] ✅ Batch створено: {batch.id}")
    return batch.id


def check_batch_status() -> dict:
    """Перевіряє статус batch запиту."""
    if not os.path.exists(BATCH_STATUS_FILE):
        return {"status": "no_batch"}
    
    with open(BATCH_STATUS_FILE, "r") as f:
        status = json.load(f)
    
    # Перевіряємо актуальний статус
    try:
        batch = client.batches.retrieve(status["batch_id"])
        status["status"] = batch.status
        status["output_file_id"] = getattr(batch, "output_file_id", None)
        
        with open(BATCH_STATUS_FILE, "w") as f:
            json.dump(status, f)
        
        return status
    except Exception as e:
        return {"status": "error", "error": str(e)}


def download_batch_results() -> Dict[str, dict]:
    """Завантажує результати batch. Повертає {custom_id: result}."""
    status = check_batch_status()
    
    if status.get("status") != "completed":
        print(f"[BATCH] Статус: {status.get('status')}, очікуємо...")
        return {}
    
    output_file_id = status.get("output_file_id")
    if not output_file_id:
        print("[BATCH] Немає output_file_id")
        return {}
    
    # Завантажуємо результати
    content = client.files.content(output_file_id)
    
    with open(BATCH_OUTPUT_FILE, "wb") as f:
        f.write(content.read())
    
    # Парсимо результати
    results = {}
    with open(BATCH_OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            custom_id = data.get("custom_id")
            
            try:
                response_body = data.get("response", {}).get("body", {})
                content = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Парсимо JSON з відповіді
                import re
                match = re.search(r'\{.*\}', content, re.S)
                if match:
                    result = json.loads(match.group(0))
                else:
                    result = {"role": "other", "confidence": 0.5, "reason": "Не вдалося розпарсити"}
                
                results[custom_id] = result
            except Exception as e:
                results[custom_id] = {"role": "other", "confidence": 0.5, "reason": f"Помилка: {e}"}
    
    print(f"[BATCH] ✅ Завантажено {len(results)} результатів")
    
    # Очищуємо статус
    if os.path.exists(BATCH_STATUS_FILE):
        os.remove(BATCH_STATUS_FILE)
    
    return results


def has_pending_batch() -> bool:
    """Перевіряє чи є активний batch."""
    if not os.path.exists(BATCH_STATUS_FILE):
        return False
    
    status = check_batch_status()
    return status.get("status") in ["validating", "in_progress", "finalizing"]