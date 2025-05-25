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
        self.dp.message.register(self.cmd_daily, Command("daily"))
        self.dp.message.register(self.cmd_period, Command("period"))
        self.dp.message.register(self.cmd_project, Command("project"))
        self.dp.message.register(self.cmd_test, Command("test"))
        self.dp.message.register(self.cmd_secondary, Command("secondary"))
        self.dp.callback_query.register(self.callback_handler)  # Для обработки нажатий

        # Основная клавиатура
        self.inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Отчет за вчера", callback_data="daily")],
            [InlineKeyboardButton(text="📊 Доп. отчет", callback_data="secondary")],
            [
                InlineKeyboardButton(text="📅 Отчет за период", callback_data="show_periods"),
                InlineKeyboardButton(text="📂 Отчет по проекту", callback_data="show_projects")
            ]
        ])

        # Клавиатура с периодами
        self.periods_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="За неделю", callback_data="period_week")],
            [InlineKeyboardButton(text="За месяц", callback_data="period_month")],
            [InlineKeyboardButton(text="За всё время", callback_data="period_all")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
        ])

        # Клавиатура с проектами
        self.projects_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="[П1] Проект 1", callback_data="project_П1")],
            [InlineKeyboardButton(text="[П37] Проект 37", callback_data="project_П37")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_main")]
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
        if callback.data == "daily":
            await self.cmd_daily(callback.message)
        elif callback.data == "secondary":
            await self.cmd_secondary(callback.message)
        elif callback.data == "show_periods":
            # Показываем инструкцию по вводу периода
            text = (
                "📅 *Отчет за период*\n\n"
                "Введите команду в формате:\n"
                "`/period 14.10-20.10`\n\n"
                "Доступные данные: с 14.10.2024"
            )
            await callback.message.edit_text(text, parse_mode="Markdown")

        elif callback.data == "show_projects":
            # Показываем инструкцию по вводу проекта и периода
            text = (
                "📂 *Отчет по проекту*\n\n"
                "Введите команду в формате:\n"
                "`/project [П1] 14.10-20.10`\n\n"
                "Доступные данные: с 14.10.2024"
            )
            await callback.message.edit_text(text, parse_mode="Markdown")

        elif callback.data == "back_to_main":
            await callback.message.edit_text(
                "Выберите тип отчета:",
                reply_markup=self.inline_kb
            )

        await callback.answer()

    async def cmd_daily(self, message: Message):
        """Обработчик команды /daily"""
        result = self.data_processor.generate_daily_report()
        
        if result['success']:
            verified_status = "✅ Проверено" if result['verified'] else "❌ Не проверено"
            text = config.MESSAGES['DAILY_REPORT'].format(
                date=result['date'],
                records=result['records'],
                deposit=result.get('deposit', 0),
                verified=verified_status
            )
            await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer(result['error'])

    async def cmd_period(self, message: Message, period_str=None):
        """Отправка отчета за период"""
        if not period_str:
            args = message.text.split()[1:]
            if not args:
                await message.reply(
                    "❌ Пожалуйста, укажите период в формате: /period 01.11-30.11",
                    parse_mode="Markdown"
                )
                return
            period_str = args[0]

        result = self.data_processor.generate_period_report(period_str)
        if result['success']:
            text = config.MESSAGES['PERIOD_REPORT'].format(
                start_date=result['start_date'],
                end_date=result['end_date'],
                total_records=result['total_records'],
                warning=result.get('warning', '')
            )
        else:
            text = f"❌ Ошибка: {result['error']}"
        
        await message.reply(text, parse_mode="Markdown")

    async def cmd_project(self, message: Message, project=None, period=None):
        """Отправка отчета по проекту"""
        if not project or not period:
            args = message.text.split()[1:]
            if len(args) < 2:
                await message.reply(
                    "❌ Пожалуйста, укажите проект и период в формате: "
                    "/project [П1] 01.11-30.11",
                    parse_mode="Markdown"
                )
                return
            project = args[0]
            period = args[1]

        result = self.data_processor.generate_project_report(project, period)
        if result['success']:
            text = config.MESSAGES['PROJECT_REPORT'].format(
                project=result['project_name'],
                start_date=result['start_date'],
                end_date=result['end_date'],
                records=result['total_records'],
                warning=result.get('warning', '')
            )
        else:
            text = f"❌ Ошибка: {result['error']}"
        
        await message.reply(text, parse_mode="Markdown")

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
            BotCommand(command="daily", description="📊 Отчет за вчера"),
            BotCommand(command="period", description="📅 Отчет за период"),
            BotCommand(command="project", description="📂 Отчет по проекту"),
            BotCommand(command="secondary", description="📊 Дополнительный отчет")
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