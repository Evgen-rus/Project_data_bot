import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram.filters import Command
from datetime import datetime, timedelta
import pytz
import asyncio

import src.config as config
from src.data_processor import DataProcessor

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token, data_processor):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.data_processor = data_processor
        
        # Регистрация обработчиков
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_secondary, Command("secondary"))
        self.dp.message.register(self.cmd_test, Command("test"))
        self.dp.callback_query.register(self.callback_handler)  # Для обработки нажатий

        # Основная клавиатура
        self.inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Отчет", callback_data="secondary")]
        ])

        # Добавляем время последней отправки отчетов
        self.last_report_date = None

        # Добавляем обработчик всех сообщений
        @self.dp.message()
        async def message_handler(message: Message):
            logger.info(f"Message from chat: {message.chat.id}")
            logger.info(f"Chat type: {message.chat.type}")
            logger.info(f"Full message info: {message.dict()}")

    async def cmd_start(self, message: Message):
        """Обработчик команды /start"""
        await message.answer(
            "Выберите тип отчета:",
            reply_markup=self.inline_kb
        )

    async def callback_handler(self, callback: CallbackQuery):
        """Обработчик нажатий на inline-кнопки"""
        if callback.data == "secondary":
            await self.cmd_secondary(callback.message)
        await callback.answer()

    # Удалены команды /daily, /period, /project как неактуальные

    async def cmd_test(self, message: Message):
        """Тестовая команда для получения ID чата"""
        chat_id = message.chat.id
        
        # Добавляем тестовую отправку в группу
        try:
            await self.bot.send_message(
                chat_id=config.GROUP_CHAT_ID,
                text=f"Тестовое сообщение в группу\nChat ID группы: {config.GROUP_CHAT_ID}"
            )
            await message.reply(f"Тестовое сообщение отправлено в группу\nID текущего чата: {chat_id}")
        except Exception as e:
            await message.reply(f"Ошибка отправки: {e}\nID текущего чата: {chat_id}")

    async def cmd_secondary(self, message: Message):
        """Обработчик команды /secondary"""
        result = self.data_processor.generate_secondary_report()
        
        if result['success']:
            try:
                text = config.MESSAGES['SECONDARY_REPORT'].format(
                    date=result['date'],
                    projects_data=result['projects_data']
                )
                await message.answer(text, parse_mode="Markdown")
                
                # Отправляем предупреждение о проектах для отключения, если есть
                if result.get('disable_warning'):
                    await message.answer(result['disable_warning'], parse_mode="Markdown")
                    
                # Отправляем предупреждение о проектах для уменьшения лимитов, если есть
                if result.get('reduce_warning'):
                    await message.answer(result['reduce_warning'], parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error with Markdown formatting: {e}")
                # Если ошибка форматирования - отправляем без разметки
                text = text.replace('*', '').replace('_', '').replace('`', '')
                await message.answer(text)
        else:
            await message.answer(f"Ошибка: {result['error']}")

    async def set_commands(self):
        """Установка команд бота в меню"""
        commands = [
            BotCommand(command="start", description="🔄 Открыть главное меню"),
            BotCommand(command="secondary", description="📊 Отчет за сегодня"),
            BotCommand(command="test", description="🧪 Тестовое сообщение")
        ]
        await self.bot.set_my_commands(commands)

    async def check_and_send_reports(self):
        """Проверяет необходимость отправки отчетов из второй таблицы"""
        now = datetime.now(pytz.timezone(config.REPORT_TIME['TIMEZONE']))
        current_date = now.date()

        if (now.hour == config.REPORT_TIME['HOUR'] and 
            now.minute == config.REPORT_TIME['MINUTE'] and
            (self.last_report_date is None or self.last_report_date < current_date)):
            
            try:
                logger.info(f"Attempting to send secondary report at {now}")
                
                # Отчет по второй таблице
                result_secondary = self.data_processor.generate_secondary_report()
                if result_secondary['success']:
                    text_secondary = config.MESSAGES['SECONDARY_REPORT'].format(
                        date=result_secondary['date'],
                        projects_data=result_secondary['projects_data']
                    )
                    try:
                        await self.bot.send_message(
                            chat_id=config.GROUP_CHAT_ID,
                            text=text_secondary,
                            parse_mode="Markdown"
                        )
                        logger.info("Secondary report sent successfully")
                        
                        # Отправляем предупреждение о проектах для отключения, если есть
                        if result_secondary.get('disable_warning'):
                            await self.bot.send_message(
                                chat_id=config.GROUP_CHAT_ID,
                                text=result_secondary['disable_warning'],
                                parse_mode="Markdown"
                            )
                            
                        # Отправляем предупреждение о проектах для уменьшения лимитов, если есть
                        if result_secondary.get('reduce_warning'):
                            await self.bot.send_message(
                                chat_id=config.GROUP_CHAT_ID,
                                text=result_secondary['reduce_warning'],
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.error(f"Error sending secondary report: {e}")
                        # Пробуем отправить без форматирования
                        await self.bot.send_message(
                            chat_id=config.GROUP_CHAT_ID,
                            text=text_secondary.replace('*', '').replace('_', '').replace('`', '')
                        )
                        logger.info("Secondary report sent without formatting")

                self.last_report_date = current_date
                logger.info(f"Secondary report sent successfully at {now}")
                
            except Exception as e:
                logger.error(f"Error sending secondary report: {e}")

    async def start(self):
        """Запуск бота"""
        logger.info("Bot started...")
        try:
            await self.set_commands()
            
            # Запускаем периодическую проверку в отдельной задаче
            asyncio.create_task(self.check_reports_periodically())
            logger.info("Periodic check task started")
            
            # Запускаем поллинг
            await self.dp.start_polling(self.bot)
        finally:
            await self.bot.session.close()

    async def check_reports_periodically(self):
        """Периодическая проверка необходимости отправки отчетов"""
        while True:
            await self.check_and_send_reports()
            # Проверяем каждые 55 секунд
            await asyncio.sleep(55) 