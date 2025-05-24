from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import os

load_dotenv()  # загружаем данные из .env

# Telegram Bot Settings
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# Google Sheets Settings
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SECONDARY_SPREADSHEET_ID = os.getenv("SECONDARY_SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
SHEET_NAME = "[учет данных] 2025"

# Sheet structure
SHEET_STRUCTURE = {
    'RANGE': 'A1:ZZ1000',
    'PROJECT_COLUMN': 'A',
    'PHASE_COLUMN': 'B',
    'TOTAL_COLUMN': 'C',
    'DEPOSIT_CELL': 'C242',
    'DATE_ROW': 1,
    'VERIFY_ROW': 2,
    'DATA_START_ROW': 3,
    'DATE_FORMAT_IN': '%d.%m.%y',  # Формат в таблице (01.11.24)
    'DATE_FORMAT_OUT': '%d.%m.%Y',  # Формат для отображения (01.11.2024)
}

# Time settings
REPORT_TIME = {
    'HOUR': 9,
    'MINUTE': 0,
    'TIMEZONE': 'Europe/Moscow'
}

# Message templates
MESSAGES = {
    'DAILY_REPORT': """📊 *Отчет за {date}*

Всего записей: {records}
Остаток депозита: {deposit}₽

Статус проверки: {verified}""",

    'NO_DATA': """⚠️ *Внимание!*
За вчерашний день данные не поступили.
Проверьте источник данных.""",

    'PERIOD_REPORT': """📅 *Отчет за период {start_date} - {end_date}*

Всего записей: {total_records}
{warning}""",

    'PROJECT_REPORT': """📂 *Отчет по проекту {project}*
За период: {start_date} - {end_date}
Всего записей: {records}
{warning}""",

    'NO_CHECKMARK': """⚠️ *Внимание!*
Данные за {date} присутствуют, но не отмечены как проверенные."""
}

# Error messages
ERROR_MESSAGES = {
    'not_authorized': "У вас нет прав для выполнения этой команды.",
    'invalid_date_format': "Неверный формат даты. Используйте формат ДД.ММ.ГГГГ",
    'invalid_project_tag': "❌ Пожалуйста, укажите проект и период в формате: /project [П1] 01.11-30.11",
    'no_data': "Данные не найдены за указанный период.",
    'sheet_error': "Ошибка при получении данных из таблицы.",
    'no_data_period': "⚠️ За указанный период данных нет. Данные доступны с 14.10.2024"
}

# Column types to skip
SKIP_COLUMNS = [
    'нед. выгр. всего',
    'Итого:',
    'Фаза проекта'
]

# Helper functions
def get_yesterday_date():
    moscow_tz = pytz.timezone(REPORT_TIME['TIMEZONE'])
    moscow_now = datetime.now(moscow_tz)
    return (moscow_now - timedelta(days=1)).strftime(SHEET_STRUCTURE['DATE_FORMAT_OUT'])

def format_date(date_str):
    """Convert date string to required format"""
    return datetime.strptime(date_str, '%d.%m.%Y').strftime(SHEET_STRUCTURE['DATE_FORMAT_OUT'])

# Обновляем SHEET_SETTINGS
SHEET_SETTINGS = {
    'MAIN': {
        'SPREADSHEET_ID': SPREADSHEET_ID,
        'NAME': "[учет данных] 2025",
        'STRUCTURE': SHEET_STRUCTURE
    },
    'SECONDARY': {
        'SPREADSHEET_ID': SECONDARY_SPREADSHEET_ID,
        'NAME': "[учет данных] 2025",
        'STRUCTURE': {
            'RANGE': 'A1:ZZ1000',
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

MESSAGES.update({
    'SECONDARY_REPORT': r"""🔍 \[LR конкуренты] Ежедневный отчет поступления данных за {date}:

{projects_data}""",

    'SECONDARY_PROJECT_FORMAT': """
*{name}*
Объем общий тариф: {total_volume}
Выдано за вчера: {yesterday_data}
Выдано итого: {total_issued}
Остаток тарифа: {tariff_remaining}
"""
})

