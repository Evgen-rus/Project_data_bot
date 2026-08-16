from datetime import datetime
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import src.config as config
import logging

logger = logging.getLogger(__name__)


def column_to_index(letter):
    """Буква колонки Google Sheets → индекс списка. A=0, B=1, ..."""
    return ord(letter.strip().upper()) - ord('A')


def parse_sheet_int(row, index, default=0):
    """Читает число из своей ячейки. Пусто, нет колонки или мусор → default."""
    if index >= len(row):
        return default
    raw = row[index]
    if raw is None:
        return default
    text = str(raw).replace('\xa0', '').replace(' ', '').strip()
    if text == '':
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


class DataProcessor:
    def __init__(self):
        """Инициализация обработчика данных"""
        self.credentials = service_account.Credentials.from_service_account_file(
            config.CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.moscow_tz = pytz.timezone(config.REPORT_TIME['TIMEZONE'])

    def get_sheet_data(self, sheet_type='SECONDARY'):
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
    
    def generate_secondary_report(self):
        """Генерация отчета по второй таблице"""
        try:
            data = self.get_sheet_data('SECONDARY')
            logger.info(f"Получены данные из второй таблицы: {len(data) if data else 0} строк")
            
            if not data:
                return {'success': False, 'error': 'No data in secondary sheet'}

            # Получаем заголовки для определения индекса сегодняшней даты
            headers = data[0]
            today = datetime.now(self.moscow_tz)
            today_str = today.strftime('%d.%m.%y')
            
            # Ищем индекс колонки с сегодняшней датой
            today_col_idx = None
            for idx, header in enumerate(headers):
                if today_str in header:
                    today_col_idx = idx
                    break

            if today_col_idx is None:
                logger.error(f"Не найдена колонка с датой {today_str}")
                return {'success': False, 'error': f'Не найдены данные за {today_str}'}

            structure = config.SHEET_SETTINGS['SECONDARY']['STRUCTURE']
            idx_project = column_to_index(structure['PROJECT_COLUMN'])
            idx_status = column_to_index(structure['STATUS_COLUMN'])
            idx_volume = column_to_index(structure['VOLUME_COLUMN'])
            idx_remaining = column_to_index(structure['REMAINING_COLUMN'])
            idx_issued = column_to_index(structure['TOTAL_ISSUED_COLUMN'])

            active_projects = []
            projects_to_disable = []  # Список проектов для отключения
            projects_to_reduce = []   # Список проектов для уменьшения лимитов
            
            for row in data[1:]:  # Пропускаем заголовок
                if len(row) <= idx_status or row[idx_status] != 'TRUE':
                    continue
                try:
                    project_data = {
                        'name': row[idx_project] if len(row) > idx_project else '',
                        'total_volume': parse_sheet_int(row, idx_volume),
                        'tariff_remaining': parse_sheet_int(row, idx_remaining),
                        'total_issued': parse_sheet_int(row, idx_issued),
                        'today_data': parse_sheet_int(row, today_col_idx),
                    }
                    active_projects.append(project_data)

                    # Проверяем остаток тарифа
                    if project_data['tariff_remaining'] <= 0:
                        projects_to_disable.append({
                            'name': project_data['name'],
                            'remaining': project_data['tariff_remaining'],
                            'today_data': project_data['today_data'],
                        })
                    elif project_data['tariff_remaining'] <= project_data['today_data']:
                        projects_to_reduce.append({
                            'name': project_data['name'],
                            'remaining': project_data['tariff_remaining'],
                            'today_data': project_data['today_data'],
                        })

                except (ValueError, IndexError) as e:
                    logger.error(f"Ошибка обработки строки {row}: {e}")
                    continue

            if not active_projects:
                return {'success': False, 'error': 'Нет активных проектов'}

            projects_text = ""
            for project in active_projects:
                projects_text += config.MESSAGES['SECONDARY_PROJECT_FORMAT'].format(**project)
                
            # Формируем сообщение о проектах для отключения
            disable_warning = ""
            if projects_to_disable:
                disable_warning = config.MESSAGES['PROJECTS_TO_DISABLE'].format(
                    projects_list='\n'.join([
                        f"*{project['name']}* - остаток: {project['remaining']}"
                        for project in projects_to_disable
                    ])
                )
                
            # Формируем сообщение о проектах для уменьшения лимитов
            reduce_warning = ""
            if projects_to_reduce:
                reduce_warning = config.MESSAGES['PROJECTS_TO_REDUCE'].format(
                    projects_list='\n'.join([f"*{project['name']}* - остаток: {project['remaining']}" for project in projects_to_reduce])
                )

            return {
                'success': True,
                'date': today.strftime(config.SHEET_STRUCTURE['DATE_FORMAT_OUT']),
                'report_date': today.date(),
                'projects': active_projects,
                'projects_data': projects_text,
                'projects_to_disable': projects_to_disable,
                'projects_to_reduce': projects_to_reduce,
                'disable_warning': disable_warning,
                'reduce_warning': reduce_warning
            }
        except Exception as e:
            logger.error(f"Error generating secondary report: {e}")
            return {'success': False, 'error': str(e)} 