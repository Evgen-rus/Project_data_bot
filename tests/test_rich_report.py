import unittest
from datetime import date
from unittest.mock import patch

from src.rich_report import (
    RICH_TABLE_MAX_DATA_ROWS,
    build_rich_report_messages,
    escape_rich_table_cell,
    format_disable_warning_message,
    format_reduce_warning_message,
    format_rich_report_message,
    get_message_format,
    group_projects_by_chat,
    has_today_data,
    send_rich_telegram_message,
)


REPORT_DATE = date(2026, 8, 16)


def project(
    name,
    today_data,
    total_issued=5,
    total_volume=1000,
    tariff_remaining=995,
    telegram_chat_id=None,
):
    return {
        "name": name,
        "today_data": today_data,
        "total_issued": total_issued,
        "total_volume": total_volume,
        "tariff_remaining": tariff_remaining,
        "telegram_chat_id": telegram_chat_id,
    }


class FormatTests(unittest.TestCase):
    def test_vertical_table_for_one_project(self):
        message = format_rich_report_message(
            REPORT_DATE,
            [("[LR221] Название", 5, 5, 1000, 995)],
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Отчёт · 16.08",
                    "",
                    r"| Проект | \[LR221\] Название |",
                    "|:--|:--|",
                    "| Сегодня | 5 |",
                    "| Тариф | 5/1000 |",
                    "| Остаток | 995 |",
                ]
            ),
        )

    def test_horizontal_table_for_several_projects(self):
        message = format_rich_report_message(
            REPORT_DATE,
            [
                ("[LR1] Проект А", 3, 10, 100, 90),
                ("[LR2] Проект Б", 7, 20, 200, 180),
            ],
        )

        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Отчёт · 16.08",
                    "",
                    "| Проект | Сегодня | Тариф | Остаток |",
                    "|:--|--:|--:|--:|",
                    r"| \[LR1\] Проект А | 3 | 10 / 100 | 90 |",
                    r"| \[LR2\] Проект Б | 7 | 20 / 200 | 180 |",
                ]
            ),
        )

    def test_escapes_table_cell_boundaries_and_line_breaks(self):
        escaped = escape_rich_table_cell("A | B\\C\nD_*[]")
        self.assertNotIn("\n", escaped)
        self.assertIn("\\|", escaped)
        self.assertIn("\\\\", escaped)
        self.assertIn("\\_", escaped)

    def test_escapes_project_name_in_table(self):
        message = format_rich_report_message(
            REPORT_DATE,
            [("[LR1] A | B\\C\nD_*[]", 3, 1, 2, None)],
        )
        self.assertNotIn("\nD", message)
        self.assertIn("\\|", message)
        self.assertIn("\\\\", message)
        self.assertIn("\\_", message)


class WarningFormatTests(unittest.TestCase):
    def test_disable_vertical_table_for_one_project(self):
        message = format_disable_warning_message([("[LR1] Alpha", 0)])
        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Внимание · тарифы исчерпаны",
                    "",
                    r"| Проект | \[LR1\] Alpha |",
                    "|:--|:--|",
                    "| Остаток | 0 |",
                ]
            ),
        )

    def test_disable_horizontal_table_for_several_projects(self):
        message = format_disable_warning_message(
            [("[LR1] Alpha", 0), ("[LR2] Beta", -5)]
        )
        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Внимание · тарифы исчерпаны",
                    "",
                    "| Проект | Остаток |",
                    "|:--|--:|",
                    r"| \[LR1\] Alpha | 0 |",
                    r"| \[LR2\] Beta | -5 |",
                ]
            ),
        )

    def test_reduce_vertical_table_for_one_project(self):
        message = format_reduce_warning_message([("[LR1] Alpha", 5)])
        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Внимание · остаток меньше чем на день",
                    "",
                    r"| Проект | \[LR1\] Alpha |",
                    "|:--|:--|",
                    "| Остаток | 5 |",
                ]
            ),
        )

    def test_reduce_horizontal_table_for_several_projects(self):
        message = format_reduce_warning_message(
            [("[LR1] Alpha", 5), ("[LR2] Beta", 3)]
        )
        self.assertEqual(
            message,
            "\n".join(
                [
                    "## Внимание · остаток меньше чем на день",
                    "",
                    "| Проект | Остаток |",
                    "|:--|--:|",
                    r"| \[LR1\] Alpha | 5 |",
                    r"| \[LR2\] Beta | 3 |",
                ]
            ),
        )


class FilterAndGroupTests(unittest.TestCase):
    def test_skips_zero_and_empty_today_values(self):
        self.assertFalse(has_today_data(0))
        self.assertFalse(has_today_data("0"))
        self.assertFalse(has_today_data(""))
        self.assertFalse(has_today_data(None))
        self.assertTrue(has_today_data(5))

        grouped = group_projects_by_chat(
            [
                project("[LR1] Alpha", 0, telegram_chat_id=100),
                project("[LR2] Beta", "", telegram_chat_id=100),
                project("[LR3] Gamma", 12, telegram_chat_id=100),
            ],
            default_chat_id=999,
        )

        self.assertEqual(list(grouped.keys()), [100])
        self.assertEqual([item["name"] for item in grouped[100]], ["[LR3] Gamma"])

    def test_groups_non_adjacent_projects_by_chat(self):
        grouped = group_projects_by_chat(
            [
                project("[LR1] Alpha", 63, telegram_chat_id=100),
                project("[LR2] Beta", 41, telegram_chat_id=200),
                project("[LR3] Gamma", 12, telegram_chat_id=100),
            ],
            default_chat_id=999,
        )

        self.assertEqual(list(grouped.keys()), [100, 200])
        self.assertEqual(
            [item["name"] for item in grouped[100]],
            ["[LR1] Alpha", "[LR3] Gamma"],
        )
        self.assertEqual([item["name"] for item in grouped[200]], ["[LR2] Beta"])

    def test_uses_default_chat_when_project_has_no_chat_id(self):
        grouped = group_projects_by_chat(
            [
                project("[LR1] Alpha", 3),
                project("[LR2] Beta", 7),
            ],
            default_chat_id=-100,
        )

        self.assertEqual(list(grouped.keys()), [-100])
        self.assertEqual(len(grouped[-100]), 2)

    def test_warning_group_keeps_zero_today_projects(self):
        grouped = group_projects_by_chat(
            [project("[LR1] Alpha", 0, telegram_chat_id=100)],
            default_chat_id=999,
            require_today_data=False,
        )
        self.assertEqual([item["name"] for item in grouped[100]], ["[LR1] Alpha"])


class SplitTests(unittest.TestCase):
    def test_splits_when_too_many_data_rows(self):
        rows = [(f"P{index}", 1, 1, 10, 9) for index in range(RICH_TABLE_MAX_DATA_ROWS + 2)]
        messages = build_rich_report_messages(REPORT_DATE, rows)

        self.assertEqual(2, len(messages))
        self.assertEqual(1, messages[0].count("## Отчёт"))
        self.assertEqual(1, messages[1].count("## Отчёт"))
        self.assertIn("| P0 |", messages[0])
        self.assertIn(f"| P{RICH_TABLE_MAX_DATA_ROWS} |", messages[1])

    def test_splits_when_message_exceeds_byte_limit(self):
        long_name = "A" * 20000
        messages = build_rich_report_messages(
            REPORT_DATE,
            [
                (long_name + "1", 1, 1, 10, 9),
                (long_name + "2", 2, 2, 20, 18),
            ],
        )

        self.assertEqual(2, len(messages))
        self.assertIn(long_name + "1", messages[0])
        self.assertNotIn(long_name + "2", messages[0])
        self.assertIn(long_name + "2", messages[1])


class SenderTests(unittest.TestCase):
    def test_rich_sender_uses_send_rich_message_payload(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True, "result": {"message_id": 1}}

        with patch("src.rich_report.requests.post", return_value=FakeResponse()) as post:
            send_rich_telegram_message("token", 100, "## Отчёт · 16.08")

        post.assert_called_once_with(
            "https://api.telegram.org/bottoken/sendRichMessage",
            json={"chat_id": 100, "rich_message": {"markdown": "## Отчёт · 16.08"}},
            timeout=15,
        )

    def test_unknown_format_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "REPORTS_MESSAGE_FORMAT"):
            get_message_format("unsupported")


if __name__ == "__main__":
    unittest.main()
