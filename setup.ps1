# LeadHarvester - швидке встановлення
Write-Host "🚀 LeadHarvester - встановлення залежностей..." -ForegroundColor Green

# Перевірка наявності Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Знайдено: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python не знайдено. Встанови Python з python.org" -ForegroundColor Red
    exit 1
}

# Створення віртуального середовища
Write-Host "`n📦 Створення віртуального середовища..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "⚠️  Віртуальне середовище вже існує" -ForegroundColor Yellow
} else {
    python -m venv .venv
    Write-Host "✅ Віртуальне середовище створено" -ForegroundColor Green
}

# Активація віртуального середовища
Write-Host "`n🔧 Активація віртуального середовища..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# Встановлення залежностей
Write-Host "`n📚 Встановлення залежностей..." -ForegroundColor Yellow
pip install -r requirements.txt

# Копіювання .env файлу
Write-Host "`n⚙️  Підготовка конфігурації..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "⚠️  .env файл вже існує" -ForegroundColor Yellow
} else {
    Copy-Item ".env.example" ".env"
    Write-Host "✅ .env файл створено з шаблону" -ForegroundColor Green
}

Write-Host "`n🎉 Встановлення завершено!" -ForegroundColor Green
Write-Host "`n📝 Наступні кроки:" -ForegroundColor Cyan
Write-Host "1. Відредагуй файл .env (заповни API ключі)" -ForegroundColor White
Write-Host "2. Запусти: python app.py --once" -ForegroundColor White
Write-Host "`n📖 Детальна інструкція в README.md" -ForegroundColor Gray