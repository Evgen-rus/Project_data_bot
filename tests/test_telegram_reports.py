import os
import sys
import unittest
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytz

# Подставляем значения до импорта config, чтобы тесты не падали без .env
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ADMIN_CHAT_ID", "1")
os.environ.setdefault("GROUP_CHAT_ID", "-100")
os.environ.setdefault("SECONDARY_SPREADSHEET_ID", "sheet")
os.environ.setdefault("CREDENTIALS_FILE", "/tmp/nonexistent.json")

# Google-клиент в тестах не нужен — подменяем модули, чтобы импорт не требовал пакетов
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())
sys.modules.setdefault("googleapiclient", MagicMock())
sys.modules.setdefault("googleapiclient.discovery", MagicMock())

from src.data_processor import DataProcessor, parse_sheet_int, column_to_index
from src.telegram_bot import TelegramBot
import src.config as config


REPORT_DATE = date(2026, 8, 16)


def make_processor(rows):
    """Собирает DataProcessor без Google-credentials, с готовыми строками листа."""
    processor = DataProcessor.__new__(DataProcessor)
    processor.moscow_tz = __import__("pytz").timezone("Europe/Moscow")
    processor.get_sheet_data = lambda sheet_type="SECONDARY": rows
    return processor


def make_sheet_rows(today_values_by_name):
    today_header = REPORT_DATE.strftime("%d.%m.%y")
    headers = ["Проект", "Статус", "Объем", "D", "Остаток", "Выдано", today_header]
    rows = [headers]
    for name, today_value, remaining, issued, volume in today_values_by_name:
        # C=объём, D не используется, E=остаток, F=выдано, далее дата
        rows.append(
            [name, "TRUE", str(volume), "", str(remaining), str(issued), str(today_value)]
        )
    return rows


class DataProcessorReportTests(unittest.TestCase):
    def test_returns_structured_projects_for_rich_table(self):
        moscow = pytz.timezone("Europe/Moscow")
        fixed_now = moscow.localize(datetime(2026, 8, 16, 13, 40))
        processor = make_processor(
            make_sheet_rows(
                [
                    ("[LR1] Alpha", 3, 90, 10, 100),
                    ("[LR2] Beta", 0, 180, 20, 200),
                ]
            )
        )
        with patch("src.data_processor.datetime") as datetime_mock:
            datetime_mock.now.return_value = fixed_now
            result = processor.generate_secondary_report()

        self.assertTrue(result["success"])
        self.assertEqual(result["report_date"], REPORT_DATE)
        self.assertEqual(len(result["projects"]), 2)
        self.assertEqual(result["projects"][0]["name"], "[LR1] Alpha")
        self.assertEqual(result["projects"][0]["today_data"], 3)
        self.assertEqual(result["projects"][0]["tariff_remaining"], 90)
        self.assertEqual(result["projects"][0]["total_issued"], 10)
        self.assertEqual(result["projects"][1]["today_data"], 0)

    def test_reads_remaining_from_e_even_if_d_is_empty(self):
        moscow = pytz.timezone("Europe/Moscow")
        fixed_now = moscow.localize(datetime(2026, 8, 16, 13, 40))
        processor = make_processor(make_sheet_rows([("[LR1] Alpha", 3, 995, 5, 1000)]))
        with patch("src.data_processor.datetime") as datetime_mock:
            datetime_mock.now.return_value = fixed_now
            result = processor.generate_secondary_report()

        self.assertEqual(result["projects"][0]["tariff_remaining"], 995)
        self.assertEqual(result["projects"][0]["total_volume"], 1000)
        self.assertEqual(result["projects"][0]["total_issued"], 5)

    def test_returns_warning_project_lists(self):
        moscow = pytz.timezone("Europe/Moscow")
        fixed_now = moscow.localize(datetime(2026, 8, 16, 13, 40))
        processor = make_processor(
            make_sheet_rows(
                [
                    ("[LR9] Dead", 0, 0, 100, 100),
                    ("[LR8] Low", 10, 5, 95, 100),
                ]
            )
        )
        with patch("src.data_processor.datetime") as datetime_mock:
            datetime_mock.now.return_value = fixed_now
            result = processor.generate_secondary_report()

        self.assertEqual(
            result["projects_to_disable"],
            [{"name": "[LR9] Dead", "remaining": 0, "today_data": 0}],
        )
        self.assertEqual(
            result["projects_to_reduce"],
            [{"name": "[LR8] Low", "remaining": 5, "today_data": 10}],
        )


class TelegramDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.processor = MagicMock()
        self.bot = TelegramBot("123456:TESTTOKEN", self.processor)

    async def asyncTearDown(self):
        await self.bot.bot.session.close()

    def _success_result(
        self,
        projects,
        disable_warning="",
        reduce_warning="",
        projects_to_disable=None,
        projects_to_reduce=None,
    ):
        return {
            "success": True,
            "date": "16.08.2026",
            "report_date": REPORT_DATE,
            "projects": projects,
            "projects_data": "legacy-text",
            "projects_to_disable": projects_to_disable or [],
            "projects_to_reduce": projects_to_reduce or [],
            "disable_warning": disable_warning,
            "reduce_warning": reduce_warning,
        }

    async def test_rich_groups_projects_into_one_message_per_chat(self):
        result = self._success_result(
            [
                {
                    "name": "[LR1] Alpha",
                    "today_data": 3,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 90,
                    "telegram_chat_id": 100,
                },
                {
                    "name": "[LR2] Beta",
                    "today_data": 7,
                    "total_issued": 20,
                    "total_volume": 200,
                    "tariff_remaining": 180,
                    "telegram_chat_id": 200,
                },
                {
                    "name": "[LR3] Gamma",
                    "today_data": 1,
                    "total_issued": 1,
                    "total_volume": 10,
                    "tariff_remaining": 9,
                    "telegram_chat_id": 100,
                },
            ]
        )
        calls = []

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "rich"), patch(
            "src.rich_report.send_rich_telegram_message",
            side_effect=lambda *args: calls.append(args),
        ), patch.object(self.bot.bot, "send_message", new_callable=AsyncMock) as send_message:
            await self.bot.deliver_secondary_report(chat_id=-100, result=result)

        self.assertEqual(2, len(calls))
        send_message.assert_not_called()
        messages_by_chat = {call[1]: call[2] for call in calls}
        self.assertIn(r"\[LR1\] Alpha", messages_by_chat[100])
        self.assertIn(r"\[LR3\] Gamma", messages_by_chat[100])
        self.assertNotIn(r"\[LR2\] Beta", messages_by_chat[100])
        self.assertIn(r"\[LR2\] Beta", messages_by_chat[200])
        self.assertEqual(1, messages_by_chat[100].count("## Отчёт"))

    async def test_rich_skips_zero_today_and_does_not_call_send_message(self):
        result = self._success_result(
            [
                {
                    "name": "[LR1] Alpha",
                    "today_data": 0,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 90,
                }
            ]
        )

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "rich"), patch(
            "src.rich_report.send_rich_telegram_message"
        ) as send_rich, patch.object(
            self.bot.bot, "send_message", new_callable=AsyncMock
        ) as send_message:
            await self.bot.deliver_secondary_report(
                chat_id=-100, result=result, notify_empty=False
            )

        send_rich.assert_not_called()
        send_message.assert_not_called()

    async def test_legacy_keeps_send_message(self):
        result = self._success_result(
            [
                {
                    "name": "[LR1] Alpha",
                    "today_data": 3,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 90,
                }
            ]
        )

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "legacy"), patch(
            "src.rich_report.send_rich_telegram_message"
        ) as send_rich, patch.object(
            self.bot.bot, "send_message", new_callable=AsyncMock
        ) as send_message:
            await self.bot.deliver_secondary_report(chat_id=-100, result=result)

        send_rich.assert_not_called()
        send_message.assert_called_once()
        self.assertEqual(-100, send_message.call_args.kwargs["chat_id"])
        self.assertIn("legacy-text", send_message.call_args.kwargs["text"])

    async def test_rich_warnings_go_as_tables(self):
        result = self._success_result(
            [
                {
                    "name": "[LR1] Alpha",
                    "today_data": 3,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 90,
                }
            ],
            projects_to_disable=[
                {"name": "[LR9] Dead", "remaining": 0, "today_data": 0},
            ],
            projects_to_reduce=[
                {"name": "[LR8] Low", "remaining": 2, "today_data": 5},
            ],
        )
        calls = []

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "rich"), patch(
            "src.rich_report.send_rich_telegram_message",
            side_effect=lambda *args: calls.append(args),
        ), patch.object(self.bot.bot, "send_message", new_callable=AsyncMock) as send_message:
            await self.bot.deliver_secondary_report(chat_id=-100, result=result)

        send_message.assert_not_called()
        self.assertEqual(3, len(calls))
        titles = [call[2].split("\n", 1)[0] for call in calls]
        self.assertEqual(
            titles,
            [
                "## Отчёт · 16.08",
                "## Внимание · тарифы исчерпаны",
                "## Внимание · остаток меньше чем на день",
            ],
        )
        self.assertIn("| Остаток | 0 |", calls[1][2])
        self.assertNotIn("Сегодня", calls[1][2])
        self.assertIn("| Остаток | 2 |", calls[2][2])
        self.assertNotIn("Сегодня", calls[2][2])

    async def test_rich_disable_warning_sent_when_today_is_zero(self):
        result = self._success_result(
            [
                {
                    "name": "[LR9] Dead",
                    "today_data": 0,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 0,
                }
            ],
            projects_to_disable=[
                {"name": "[LR9] Dead", "remaining": 0, "today_data": 0},
            ],
        )
        calls = []

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "rich"), patch(
            "src.rich_report.send_rich_telegram_message",
            side_effect=lambda *args: calls.append(args),
        ), patch.object(self.bot.bot, "send_message", new_callable=AsyncMock) as send_message:
            await self.bot.deliver_secondary_report(
                chat_id=-100, result=result, notify_empty=False
            )

        send_message.assert_not_called()
        self.assertEqual(1, len(calls))
        self.assertIn("## Внимание · тарифы исчерпаны", calls[0][2])
        self.assertIn(r"\[LR9\] Dead", calls[0][2])

    async def test_legacy_warnings_keep_send_message(self):
        result = self._success_result(
            [
                {
                    "name": "[LR1] Alpha",
                    "today_data": 3,
                    "total_issued": 10,
                    "total_volume": 100,
                    "tariff_remaining": 90,
                }
            ],
            disable_warning="disable-me",
        )

        with patch.object(config, "REPORTS_MESSAGE_FORMAT", "legacy"), patch(
            "src.rich_report.send_rich_telegram_message"
        ) as send_rich, patch.object(
            self.bot.bot, "send_message", new_callable=AsyncMock
        ) as send_message:
            await self.bot.deliver_secondary_report(chat_id=-100, result=result)

        send_rich.assert_not_called()
        texts = [call.kwargs["text"] for call in send_message.call_args_list]
        self.assertIn("legacy-text", texts[0])
        self.assertEqual("disable-me", texts[1])

    def test_bot_does_not_schedule_reports_internally(self):
        self.assertFalse(hasattr(TelegramBot, "check_reports_periodically"))
        self.assertFalse(hasattr(TelegramBot, "check_and_send_reports"))
        self.assertFalse(hasattr(TelegramBot, "cmd_test"))


class CronSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_sends_to_group_chat_without_polling(self):
        from send_secondary_report import send_report

        processor = MagicMock()
        processor.generate_secondary_report.return_value = {
            "success": True,
            "projects": [],
        }
        bot = MagicMock()
        bot.deliver_secondary_report = AsyncMock()
        bot.bot.session.close = AsyncMock()

        with patch.object(config, "GROUP_CHAT_ID", -100):
            await send_report(data_processor=processor, bot=bot)

        bot.deliver_secondary_report.assert_awaited_once_with(
            chat_id=-100,
            result=processor.generate_secondary_report.return_value,
            notify_empty=False,
        )
        bot.dp.start_polling.assert_not_called()
        bot.bot.session.close.assert_not_awaited()


class SheetParseTests(unittest.TestCase):
    def test_column_letters(self):
        self.assertEqual(column_to_index("A"), 0)
        self.assertEqual(column_to_index("E"), 4)
        self.assertEqual(column_to_index("F"), 5)

    def test_parse_sheet_int_reads_own_cell(self):
        row = ["name", "TRUE", "1000", "", "995", "5"]
        self.assertEqual(parse_sheet_int(row, 2), 1000)
        self.assertEqual(parse_sheet_int(row, 4), 995)
        self.assertEqual(parse_sheet_int(row, 5), 5)
        self.assertEqual(parse_sheet_int(row, 3), 0)

    def test_parse_optional_int_does_not_crash_on_empty(self):
        self.assertIsNone(config.parse_optional_int(None))
        self.assertIsNone(config.parse_optional_int(""))
        self.assertIsNone(config.parse_optional_int("  "))
        self.assertEqual(config.parse_optional_int("-100"), -100)


if __name__ == "__main__":
    unittest.main()
