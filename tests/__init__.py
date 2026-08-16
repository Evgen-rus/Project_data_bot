import os

# Значения только для тестов: чтобы импорт config не падал без .env
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ADMIN_CHAT_ID", "1")
os.environ.setdefault("GROUP_CHAT_ID", "-100")
os.environ.setdefault("SECONDARY_SPREADSHEET_ID", "sheet")
os.environ.setdefault("CREDENTIALS_FILE", "/tmp/nonexistent.json")
