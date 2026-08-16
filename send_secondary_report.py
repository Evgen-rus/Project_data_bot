"""Одноразовая отправка ежедневного отчёта.

Запускается из cron каждый день в 13:40 по Москве.
Бот при этом остаётся запущенным: /secondary и кнопка работают в любой момент.
"""

import asyncio
import logging

from src.data_processor import DataProcessor
from src.telegram_bot import TelegramBot
from src import config

logger = logging.getLogger(__name__)


def setup_logging():
    """Пишем в файл, потому что cron обычно глушит stdout/stderr."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("send_secondary_report.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


async def send_report(data_processor=None, bot=None):
    """Собирает отчёт и отправляет его в GROUP_CHAT_ID."""
    close_bot = False
    if data_processor is None:
        data_processor = DataProcessor()
    if bot is None:
        bot = TelegramBot(config.BOT_TOKEN, data_processor)
        close_bot = True

    try:
        result = data_processor.generate_secondary_report()
        logger.info("Отчёт собран, success=%s", result.get("success"))
        await bot.deliver_secondary_report(
            chat_id=config.GROUP_CHAT_ID,
            result=result,
            notify_empty=False,
        )
        logger.info("Отчёт отправлен в чат %s", config.GROUP_CHAT_ID)
    finally:
        if close_bot:
            await bot.bot.session.close()


def main():
    setup_logging()
    asyncio.run(send_report())


if __name__ == "__main__":
    main()
