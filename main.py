import asyncio
import logging
from src.telegram_bot import TelegramBot
from src.data_processor import DataProcessor
from src import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    data_processor = DataProcessor()
    bot = TelegramBot(config.BOT_TOKEN, data_processor)
    
    try:
        await bot.start()
    except Exception as e:
        logging.error(f"Error running bot: {e}")

if __name__ == '__main__':
    asyncio.run(main()) 