import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Переход на уровень выше и доступ к credentials.json
credentials_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    '..', 
    'credentials', 
    'sheets-data-bot-b8f4cc6634fc.json'
)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

class GoogleSheetsService:
    def __init__(self):
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Аутентификация в Google Sheets API используя сервисный аккаунт."""
        try:
            self.creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.creds)
        except Exception as e:
            print(f"Ошибка аутентификации: {e}")
            raise

    def test_connection(self):
        """Тестирует соединение с Google Sheets API."""
        try:
            # Получаем список листов таблицы в тестовом режиме
            spreadsheet = self.service.spreadsheets().get(spreadsheetId='1viekt1aegnrJ2A6IhDxxC_n0jyggXl6jBjM-BCxU6aU').execute()
            sheets = spreadsheet.get('sheets', [])
            if sheets:
                print("Соединение с Google Sheets успешно установлено.")
            else:
                print("Не удалось найти листы в таблице.")
        except Exception as e:
            print(f"Ошибка соединения: {e}")


def main():
    """Основная функция для инициализации сервиса и проверки подключения."""
    print("Инициализируем Google Sheets Service...")
    service = GoogleSheetsService()
    service.test_connection()


if __name__ == '__main__':
    main()

