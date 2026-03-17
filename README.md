# nostressbyruleva_bot — Инструкция по запуску

## Структура папок

```
nostress_bot/
├── bot.py
├── requirements.txt
├── Procfile
└── docs/
    ├── Политика_обработки_ПД.pdf
    ├── Согласие_на_обработку_ПД.pdf
    ├── Согласие_на_рассылку.pdf
    └── Как_обрабатывать_свои_эмоции.pdf
```

## Деплой на Railway (бесплатно)

### Шаг 1 — Создай репозиторий на GitHub
1. Зайди на github.com → New repository → название "nostress-bot"
2. Создай папку `docs` и загрузи туда все 4 PDF-файла
3. Загрузи `bot.py`, `requirements.txt`, `Procfile`

### Шаг 2 — Разверни на Railway
1. Зайди на railway.app → New Project → Deploy from GitHub repo
2. Выбери репозиторий nostress-bot
3. В разделе Variables добавь переменные:
   - `BOT_TOKEN` = твой токен от BotFather
   - `ADMIN_CHAT_ID` = твой Telegram chat ID (см. ниже)

### Как узнать свой ADMIN_CHAT_ID
1. Напиши боту @userinfobot в Telegram
2. Он ответит твоим chat ID
3. Скопируй число и вставь в переменную ADMIN_CHAT_ID на Railway

### Шаг 3 — Запуск
Railway автоматически установит зависимости и запустит бота.
Проверь: напиши /start в своём боте @nostressbyruleva_bot

## Где хранятся лиды
Файл `leads.csv` создаётся автоматически рядом с bot.py.
На Railway его можно скачать через раздел Files, или настроить 
отправку на почту (сообщи — добавим).
