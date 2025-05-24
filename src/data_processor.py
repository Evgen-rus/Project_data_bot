from datetime import datetime, timedelta
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import src.config as config
import logging

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        """Инициализация обработчика данных"""
        self.spreadsheet_id = config.SPREADSHEET_ID
        self.credentials = service_account.Credentials.from_service_account_file(
            config.CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.moscow_tz = pytz.timezone(config.REPORT_TIME['TIMEZONE'])

    def get_sheet_data(self, sheet_type='MAIN'):
        """Получение данных из таблицы"""
        try:
            settings = config.SHEET_SETTINGS[sheet_type]
            range_name = f"'{settings['NAME']}'!{settings['STRUCTURE']['RANGE']}"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=settings['SPREADSHEET_ID'],
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.warning(f"No data found in {sheet_type} sheet")
                return []
            
            return values
            
        except Exception as e:
            logger.error(f"Error getting sheet data: {e}")
            return []

    def get_deposit_amount(self, data):
        """Получение суммы депозита из строки с текстом 'Остаток депозита'"""
        try:
            # Ищем строку с текстом "Остаток депозита"
            for row in data:
                if len(row) > 0 and row[0].strip() == 'Остаток депозита':
                    logger.info(f"Найдена строка депозита: {row}")
                    
                    # Проверяем наличие колонки C
                    if len(row) <= 2:
                        logger.error("Колонка C не найдена в строке депозита")
                        return 0
                        
                    deposit_value = row[2]
                    logger.info(f"Значение депозита: {deposit_value}")
                    
                    # Преобразуем в число (учитываем отрицательные значения и пробелы)
                    # Заменяем все виды пробелов и убираем их
                    cleaned_value = (deposit_value
                                   .replace('\xa0', '')  # неразрывный пробел
                                   .replace(' ', '')     # обычный пробел
                                   .replace('\u202f', '') # узкий неразрывный пробел
                                   .strip())
                    
                    logger.info(f"Очищенное значение: {cleaned_value}")
                    deposit = float(cleaned_value)
                    logger.info(f"Итоговая сумма депозита: {deposit:,.2f}₽")
                    
                    return deposit
                    
            logger.error("Строка 'Остаток депозита' не найдена")
            return 0
            
        except (ValueError, IndexError) as e:
            logger.error(f"Ошибка при получении депозита: {str(e)}")
            return 0

    def find_column_index(self, data, target_date):
        """Поиск индекса столбца по дате"""
        try:
            if not data or len(data) < config.SHEET_STRUCTURE['DATE_ROW']:
                logger.error("No data or date row not found")
                return None
            
            date_row = data[config.SHEET_STRUCTURE['DATE_ROW'] - 1]
            target_date_str = target_date.strftime('%d.%m.%y')  # формат 01.11.24
            
            logger.info(f"Looking for date: {target_date_str}")
            
            # Пропускаем первые 3 столбца (Наименование, Фаза, Итого)
            start_column = 3
            actual_dates = date_row[start_column:]
            
            # Ищем точное совпадение, пропуская недельные итоги
            for i, cell in enumerate(actual_dates):
                cell = cell.strip()
                # Пропускаем ячейки с диапазонами дат (недельные итоги)
                if ' ' in cell or 'нед.' in cell:
                    continue
                if cell == target_date_str:
                    actual_index = i + start_column
                    logger.info(f"Found date at index {actual_index}: {cell}")
                    return actual_index
                    
            logger.warning(f"Date not found: {target_date_str}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding column index: {e}")
            return None

    def generate_daily_report(self):
        """Генерация ежедневного отчета"""
        try:
            data = self.get_sheet_data('MAIN')
            if not data:
                return {'success': False, 'error': 'No data in sheet'}

            # Получаем вчерашнюю дату
            yesterday = datetime.now(self.moscow_tz) - timedelta(days=1)
            date_str = yesterday.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT'])

            # Ищем колонку с нужной датой
            date_to_find = yesterday.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_IN'])
            yesterday_idx = self.find_column_index(data, yesterday)
            
            if yesterday_idx is None:
                return {'success': False, 'error': config.ERROR_MESSAGES['no_data']}

            # Проверяем статус верификации
            verify_row = data[config.SHEET_STRUCTURE['VERIFY_ROW'] - 1]
            is_verified = len(verify_row) > yesterday_idx and verify_row[yesterday_idx] == 'TRUE'

            # Подсчет записей
            total_records = 0
            for row in data[config.SHEET_STRUCTURE['DATA_START_ROW'] - 1:237]:
                if len(row) > yesterday_idx and row[yesterday_idx]:
                    try:
                        value = row[yesterday_idx].strip()
                        if value and value.isdigit():
                            total_records += int(value)
                    except (ValueError, IndexError):
                        continue

            # Получаем значение депозита
            deposit_cell = data[241][2] if len(data) > 241 and len(data[241]) > 2 else '0'
            # Очищаем значение от пробелов и спецсимволов
            deposit_value = deposit_cell.replace('\xa0', '').replace(' ', '') if deposit_cell else '0'
            deposit = int(float(deposit_value))

            return {
                'success': True,
                'date': date_str,
                'records': total_records,
                'deposit': deposit,
                'verified': is_verified
            }

        except Exception as e:
            logger.error(f"Error generating daily report: {e}")
            return {'success': False, 'error': str(e)}

    def parse_date_range(self, date_range):
        """Парсинг диапазона дат из строки формата DD.MM-DD.MM"""
        try:
            start_str, end_str = date_range.split('-')
            current_year = datetime.now(self.moscow_tz).year
            
            # Добавляем год к датам
            if len(start_str.split('.')) == 2:
                start_str = f"{start_str}.{current_year}"
            if len(end_str.split('.')) == 2:
                end_str = f"{end_str}.{current_year}"
                
            start_date = datetime.strptime(start_str.strip(), '%d.%m.%Y')
            end_date = datetime.strptime(end_str.strip(), '%d.%m.%Y')
            return start_date, end_date
        except Exception:
            return None, None

    def generate_period_report(self, date_range):
        """Генерация отчета за период"""
        try:
            start_date, end_date = self.parse_date_range(date_range)
            if not start_date or not end_date:
                return {'success': False, 'error': 'Invalid date range'}

            data = self.get_sheet_data()
            if not data:
                return {'success': False, 'error': 'No data in sheet'}

            total_records = 0
            current_date = start_date

            logger.info(f"\nОтчет за период {start_date.strftime('%d.%m.%y')} - {end_date.strftime('%d.%m.%y')}:")
            logger.info("-" * 40)

            warning = ""
            while current_date <= end_date:
                date_idx = self.find_column_index(data, current_date)
                if date_idx is not None:
                    daily_total = 0
                    for row in data[config.SHEET_STRUCTURE['DATA_START_ROW'] - 1:237]:
                        if len(row) > date_idx:
                            try:
                                project_name = row[0]  # Название проекта
                                value = row[date_idx].strip().replace(' ', '')
                                if value and value.isdigit():
                                    count = int(value)
                                    daily_total += count
                                    logger.info(f"{current_date.strftime('%d.%m.%y')} - {project_name}: {count}")
                            except (ValueError, IndexError):
                                continue
                    logger.info(f"Итого за {current_date.strftime('%d.%m.%y')}: {daily_total}")
                    logger.info("-" * 20)
                    total_records += daily_total

                current_date += timedelta(days=1)

            logger.info("-" * 40)
            logger.info(f"Всего записей за период: {total_records}")

            if total_records == 0:
                warning = config.ERROR_MESSAGES['no_data_period']

            return {
                'success': True,
                'total_records': total_records,
                'start_date': start_date.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
                'end_date': end_date.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
                'warning': warning  # Добавляем warning в результат
            }

        except Exception as e:
            logger.error(f"Error generating period report: {e}")
            return {'success': False, 'error': str(e)}

    def generate_project_report(self, project_tag, date_range):
        """Генерация отчета по конкретному проекту"""
        start_date, end_date = self.parse_date_range(date_range)
        if not start_date or not end_date:
            return {
                'success': False,
                'error': config.ERROR_MESSAGES['invalid_date_format']
            }

        data = self.get_sheet_data()
        if not data:
            return {
                'success': False,
                'error': config.ERROR_MESSAGES['sheet_error']
            }

        # Находим строку с нужным проектом
        project_row = None
        for row in data[config.SHEET_STRUCTURE['DATA_START_ROW'] - 1:]:
            if row and row[0].startswith(project_tag):
                project_row = row
                break

        if not project_row:
            return {
                'success': False,
                'error': config.ERROR_MESSAGES['invalid_project_tag']
            }

        total_records = 0
        current_date = start_date
        
        warning = ""
        while current_date <= end_date:
            col_idx = self.find_column_index(data, current_date)
            if col_idx is not None and len(project_row) > col_idx:
                try:
                    value = project_row[col_idx].replace(' ', '')
                    if value.isdigit():
                        total_records += int(value)
                except (ValueError, IndexError):
                    continue
            current_date += timedelta(days=1)

        if total_records == 0:
            warning = config.ERROR_MESSAGES['no_data_period']

        return {
            'success': True,
            'project_name': project_row[0],
            'total_records': total_records,
            'start_date': start_date.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
            'end_date': end_date.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
            'warning': warning  # Добавляем warning в результат
        } 

    def generate_secondary_report(self):
        """Генерация отчета по второй таблице"""
        try:
            data = self.get_sheet_data('SECONDARY')
            logger.info(f"Получены данные из второй таблицы: {len(data) if data else 0} строк")
            
            if not data:
                return {'success': False, 'error': 'No data in secondary sheet'}

            # Получаем заголовки для определения индекса вчерашней даты
            headers = data[0]
            yesterday = datetime.now(self.moscow_tz) - timedelta(days=1)
            yesterday_str = yesterday.strftime('%d.%m.%y')
            
            # Ищем индекс колонки с вчерашней датой
            yesterday_col_idx = None
            for idx, header in enumerate(headers):
                if yesterday_str in header:
                    yesterday_col_idx = idx
                    break

            if yesterday_col_idx is None:
                logger.error(f"Не найдена колонка с датой {yesterday_str}")
                return {'success': False, 'error': f'Не найдены данные за {yesterday_str}'}

            active_projects = []
            for row in data[1:]:  # Пропускаем заголовок
                if len(row) > 1 and row[1] == 'TRUE':  # Проверяем статус
                    try:
                        # Очищаем значения от пробелов
                        project_data = {
                            'name': row[0],
                            'total_volume': int(float(row[2].replace('\xa0', '').replace(' ', ''))) if row[2] else 0,
                            'tariff_remaining': int(float(row[4].replace('\xa0', '').replace(' ', ''))) if row[3] else 0,
                            'total_issued': int(float(row[5].replace('\xa0', '').replace(' ', ''))) if row[4] else 0,
                            'yesterday_data': int(float(row[yesterday_col_idx].replace('\xa0', '').replace(' ', ''))) if len(row) > yesterday_col_idx and row[yesterday_col_idx] else 0
                        }
                        active_projects.append(project_data)
                    except (ValueError, IndexError) as e:
                        logger.error(f"Ошибка обработки строки {row}: {e}")
                        continue

            if not active_projects:
                return {'success': False, 'error': 'Нет активных проектов'}

            projects_text = ""
            for project in active_projects:
                projects_text += config.MESSAGES['SECONDARY_PROJECT_FORMAT'].format(**project)

            return {
                'success': True,
                'date': yesterday.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
                'projects_data': projects_text
            }
        except Exception as e:
            logger.error(f"Error generating secondary report: {e}")
            return {'success': False, 'error': str(e)} 