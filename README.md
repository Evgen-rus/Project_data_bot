# Data Report Bot

Telegram-бот читает Google Sheets и присылает ежедневный отчёт по проектам: сколько выдано сегодня, тариф и остаток. Если тариф кончился или остатка меньше чем на день — отдельным сообщением.

## Как работает

- **По расписанию:** cron каждый день в **13:40 МСК** запускает `send_secondary_report.py` и шлёт отчёт в группу (`GROUP_CHAT_ID`).
- **Вручную:** команда `/secondary` или кнопка «📊 Отчет» — в любой момент, в тот чат, откуда вызвали.
- Формат по умолчанию — Rich-таблица (`REPORTS_MESSAGE_FORMAT = "rich"`). Откат на старый текст: `"legacy"`.

## Установка

Python 3.9 или выше.

```bash
pip install -r requirements.txt
```

Создайте `.env` в корне проекта:

```
BOT_TOKEN=ваш_токен_бота
GROUP_CHAT_ID=id_группы
SECONDARY_SPREADSHEET_ID=id_таблицы
CREDENTIALS_FILE=путь_к_credentials.json
```

Google Sheets: включите API, создайте Service Account, скачайте `credentials.json` в папку `credentials/`.

## Запуск бота

```bash
python main.py
```

На сервере бот крутится как systemd-служба `project_data_bot` (команды и кнопки). Отчёт по времени отправляет cron, не сам бот.

### Команды

1. `/start` — главное меню
2. `/secondary` — отчёт за сегодня

### Cron

```cron
CRON_TZ=Europe/Moscow
40 13 * * * cd /opt/Project_data_bot && /opt/Project_data_bot/venv/bin/python send_secondary_report.py >/dev/null 2>&1
```

Лог одноразовой отправки: `send_secondary_report.log`.

## Структура проекта

```
Project_data_bot/
├── src/
│   ├── config.py          # Настройки и .env
│   ├── data_processor.py  # Чтение Google Sheets
│   ├── rich_report.py     # Rich-таблицы и sendRichMessage
│   └── telegram_bot.py    # Команды бота
├── tests/                 # Проверки на mocks, без реального Bot API
├── send_secondary_report.py  # Отправка отчёта из cron
├── main.py
├── requirements.txt
└── .env
```

## Обслуживание

1. Бот отвечает на `/start` и `/secondary`
2. В 13:40 МСК отчёт приходит в группу
3. Данные в листе `[учет данных] 2025` актуальны

### Если что-то не так

- Бот молчит: служба запущена? токен верный?
- Нет доступа к таблице: `credentials.json` и права Service Account
- Отчёт не пришёл в группу: `crontab -l`, `send_secondary_report.log`, `GROUP_CHAT_ID`

Перезапуск бота:

```bash
sudo systemctl restart project_data_bot
```
