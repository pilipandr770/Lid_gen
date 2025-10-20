# LeadHarvester (Telegram comments → Leads)

Комплаєнтний збирач лідів із **публічних** коментарів Telegram (пов'язані чати каналів).  
**Не** маскується під людину, **не** пише повідомлення автоматично, **не** обходить детекцію.

## Можливості
- Telethon входить користувацьким акаунтом (офіційний API).
- Читає коментарі у зв'язаних чатах каналів зі списку `TARGET_CHANNELS`.
- Класифікує автора коментаря (promoter/admin vs potential_client) за допомогою OpenAI.
- Зберігає ліди у SQLite `leads.sqlite` + `leads_export.csv`.

## Швидкий старт

### 1. Підготовка середовища
```powershell
# Створити віртуальне середовище
python -m venv .venv

# Активувати віртуальне середовище
.\.venv\Scripts\Activate.ps1

# Встановити залежності
pip install -r requirements.txt
```

### 2. Налаштування
1. Створи застосунок на https://my.telegram.org та отримай `TELEGRAM_API_ID` і `TELEGRAM_API_HASH`.
2. Скопіюй `.env.example` у `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Відредагуй `.env` файл і заповни:
   - `TELEGRAM_API_ID` та `TELEGRAM_API_HASH` з my.telegram.org
   - `TELEGRAM_PHONE` - твій номер телефону
   - `OPENAI_API_KEY` - ключ від OpenAI
   - `TARGET_CHANNELS` - канали для моніторингу (через кому)
   - `INTEREST_KEYWORDS` - ключові слова інтересу

### 3. Запуск
```powershell
# Перший запуск (логін через SMS/код з Telegram)
python app.py --once

# Регулярний моніторинг (цикл кожні 5 хвилин)
python app.py --stream
```

## Структура файлів
```
leadharvester/
├── app.py                 # Головний файл запуску
├── config.py             # Конфігурація та налаштування
├── telegram_client.py    # Робота з Telegram API
├── openai_classifier.py  # Класифікація через OpenAI
├── storage.py           # База даних SQLite
├── requirements.txt     # Залежності Python
├── .env.example        # Приклад конфігурації
└── README.md          # Ця документація
```

## Результати
- `leads.sqlite` - база даних з лідами
- `leads_export.csv` - експорт у CSV формат
- Структура ліда: user_id, username, display_name, channel, message_link, role_label, confidence, reason, message_text, created_at

## Комплаєнс / GDPR
- Збираємо **мінімум публічних даних**: id, username, display_name, фрагмент повідомлення.
- Підстава: *legitimate interest* (B2B-лідогенерація).  
- Зберігати **обмежений строк**, обробляти запити на видалення.  
- У первинному зверненні до контакту — прозоро пояснити джерело (посилання на публічний коментар) і дати **opt-out**.

## Ліміти й поради
- Не додавай автопостинг чи "людську імітацію" — це може порушувати умови Telegram.  
- Краще робити ручний outreach, або генерувати чернетки.  
- Розширення: 
  - фільтри за мовою/регіоном, 
  - whitelist/blacklist слів, 
  - інтеграція з Notion/CRM, 
  - UI на Flask для перегляду лідів, 
  - Windows Task Scheduler/pm2 для автозапуску.

## Усунення проблем

### Помилки авторизації Telegram
- Переконайся, що `TELEGRAM_API_ID` і `TELEGRAM_API_HASH` правильні
- Перевір формат номера телефону (`+380123456789`)
- Видали `tg_session.session` і спробуй знову

### Помилки OpenAI
- Перевір валідність `OPENAI_API_KEY`
- Переконайся, що у тебе є кредити на акаунті OpenAI

### Канали без коментарів
- Не всі канали мають пов'язані чати для коментарів
- Перевір, чи канал публічний і чи дозволені коментарі