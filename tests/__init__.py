import os

# Необязательные заглушки, если тесты запускают без .env
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("GROUP_CHAT_ID", "-100")
