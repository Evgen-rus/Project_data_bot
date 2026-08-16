from dotenv import load_dotenv
import os

load_dotenv()  # загружаем данные из .env

# Telegram Bot Settings
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# Google Sheets (только вторая таблица)
SECONDARY_SPREADSHEET_ID = os.getenv("SECONDARY_SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

# Минимальная структура для формата даты, используемого во втором отчете
SHEET_STRUCTURE = {
    'DATE_FORMAT_OUT': '%d.%m.%Y'
}

# Время ежедневного отчёта по Москве.
# Само расписание живёт в crontab (строка 40 13 * * *), бот по таймеру больше не шлёт.
REPORT_TIME = {
    'HOUR': 13,
    'MINUTE': 40,
    'TIMEZONE': 'Europe/Moscow'
}

# Формат Telegram-отчёта:
# "rich" — одна Rich Markdown-таблица на чат через sendRichMessage
# "legacy" — старый текст через sendMessage (откат)
# Допустимые значения: legacy | rich
REPORTS_MESSAGE_FORMAT = "rich"

SHEET_SETTINGS = {
    'SECONDARY': {
        'SPREADSHEET_ID': SECONDARY_SPREADSHEET_ID,
        'NAME': "[учет данных] 2025",
        'STRUCTURE': {
            'RANGE': 'A1:ZZ227',
            'PROJECT_COLUMN': 'A',  # Название проекта
            'STATUS_COLUMN': 'B',   # Статус (TRUE/FALSE)
            'VOLUME_COLUMN': 'C',   # Объем общий
            'REMAINING_COLUMN': 'D', # Остаток тарифа
            'TOTAL_ISSUED_COLUMN': 'E', # Выдано итого
            'DATA_START_COLUMN': 'G',   # Начало данных по датам
            'DATE_ROW': 1,
        }
    }
}

MESSAGES = {
    'SECONDARY_REPORT': r"""🔍 \[LR конкуренты] Ежедневный отчет поступления данных за {date}:

{projects_data}""",

    'SECONDARY_PROJECT_FORMAT': """
Проект: *{name}*
Тариф: {total_issued}/{total_volume}
Выдано за сегодня: {today_data}
Остаток: {tariff_remaining}
""",

    'PROJECTS_TO_DISABLE': """
🚨 *ВНИМАНИЕ! Тарифы исчерпаны:*

{projects_list}

*Необходимо отключить указанные проекты!*
""",

    'PROJECTS_TO_REDUCE': """
⚠️ *ВНИМАНИЕ! Остаток меньше чем на день:*

{projects_list}

*Необходимо уменьшить лимиты для указанных проектов!*
"""
}

