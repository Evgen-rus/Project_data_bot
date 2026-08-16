import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram.filters import Command
from datetime import datetime
import pytz
import asyncio

import src.config as config
from src import rich_report


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
        await self.deliver_secondary_report(
            chat_id=message.chat.id,
            result=result,
            notify_empty=True,
        )

    async def deliver_secondary_report(self, chat_id, result, notify_empty=False):
        """Отправляет дополнительный отчёт в указанный чат.

        rich — таблицы через sendRichMessage: основной отчёт и два предупреждения.
        legacy — прежний текст через sendMessage.
        """
        if not result.get('success'):
            if notify_empty:
                await self.bot.send_message(chat_id=chat_id, text=f"Ошибка: {result['error']}")
            else:
                logger.error("Secondary report failed: %s", result.get('error'))
            return False

        message_format = rich_report.get_message_format(config.REPORTS_MESSAGE_FORMAT)

        try:
            if message_format == "legacy":
                sent = await self._send_legacy_secondary_report(chat_id, result)
            else:
                sent = await self._send_rich_secondary_report(
                    chat_id, result, notify_empty=notify_empty
                )
        except Exception as e:
            logger.error("Error sending secondary report: %s", e)
            if notify_empty:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"Ошибка отправки отчёта: {e}",
                )
                return False
            raise

        await self._send_report_warnings(chat_id, result, message_format)
        return sent

    async def _send_legacy_secondary_report(self, chat_id, result):
        """Старый формат: один текст со всеми проектами через sendMessage."""
        text = config.MESSAGES['SECONDARY_REPORT'].format(
            date=result['date'],
            projects_data=result['projects_data']
        )
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            return True
        except Exception as e:
            logger.error(f"Error with Markdown formatting: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text=text.replace('*', '').replace('_', '').replace('`', '')
            )
            return True

    async def _send_rich_secondary_report(self, chat_id, result, notify_empty=False):
        """Rich-формат: одна таблица на чат через sendRichMessage."""
        grouped = rich_report.group_projects_by_chat(
            result.get('projects') or [],
            default_chat_id=chat_id,
        )
        report_date = result.get('report_date')
        if report_date is None:
            report_date = datetime.now(pytz.timezone(config.REPORT_TIME['TIMEZONE'])).date()

        if not grouped:
            logger.info("Rich report skipped: no projects with data for today")
            if notify_empty:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text="Нет проектов с данными за сегодня",
                )
            return False

        bot_token = self.bot.token
        for dest_chat_id, projects in grouped.items():
            rows = [rich_report.project_to_row(project) for project in projects]
            for text in rich_report.build_rich_report_messages(report_date, rows):
                await asyncio.to_thread(
                    rich_report.send_rich_telegram_message,
                    bot_token,
                    dest_chat_id,
                    text,
                )
        return True

    async def _send_report_warnings(self, chat_id, result, message_format):
        """Предупреждения: rich — две отдельные таблицы, legacy — старый текст."""
        if message_format == "legacy":
            if result.get('disable_warning'):
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=result['disable_warning'],
                    parse_mode="Markdown",
                )
            if result.get('reduce_warning'):
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=result['reduce_warning'],
                    parse_mode="Markdown",
                )
            return

        bot_token = self.bot.token
        disable_grouped = rich_report.group_projects_by_chat(
            result.get('projects_to_disable') or [],
            default_chat_id=chat_id,
            require_today_data=False,
        )
        reduce_grouped = rich_report.group_projects_by_chat(
            result.get('projects_to_reduce') or [],
            default_chat_id=chat_id,
            require_today_data=False,
        )

        for dest_chat_id, projects in disable_grouped.items():
            rows = rich_report.disable_projects_to_rows(projects)
            for text in rich_report.build_disable_warning_messages(rows):
                await asyncio.to_thread(
                    rich_report.send_rich_telegram_message,
                    bot_token,
                    dest_chat_id,
                    text,
                )

        for dest_chat_id, projects in reduce_grouped.items():
            rows = rich_report.reduce_projects_to_rows(projects)
            for text in rich_report.build_reduce_warning_messages(rows):
                await asyncio.to_thread(
                    rich_report.send_rich_telegram_message,
                    bot_token,
                    dest_chat_id,
                    text,
                )

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

                result_secondary = self.data_processor.generate_secondary_report()
                await self.deliver_secondary_report(
                    chat_id=config.GROUP_CHAT_ID,
                    result=result_secondary,
                    notify_empty=False,
                )

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