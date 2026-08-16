"""Rich Markdown-отчёт для Telegram sendRichMessage.

Формат скопирован с проекта Load_leads_to_google_sheets:
вертикальная таблица для одного проекта, общая таблица для нескольких.
"""

from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

import requests

# Лимиты официального Rich Message API
RICH_MESSAGE_MAX_BYTES = 32768
RICH_TABLE_MAX_DATA_ROWS = 498

VALID_MESSAGE_FORMATS = {"legacy", "rich"}

# Одна строка отчёта: имя, сегодня, использовано, лимит, остаток
ReportRow = Tuple[str, int, Optional[int], Optional[int], Optional[int]]


def get_message_format(message_format: str) -> str:
    """Проверяет переключатель формата. Неизвестное значение — ошибка, не молчаливый fallback."""
    if message_format not in VALID_MESSAGE_FORMATS:
        raise ValueError(
            "REPORTS_MESSAGE_FORMAT должен быть одним из: legacy, rich; "
            f"получено: {message_format!r}"
        )
    return message_format


def escape_rich_table_cell(value: object) -> str:
    """Экранирует спецсимволы Markdown внутри ячейки таблицы."""
    text = str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = text.replace("\\", "\\\\")
    for character in ("|", "`", "*", "_", "~", "[", "]", "<", ">", "$", "#"):
        text = text.replace(character, f"\\{character}")
    return text


def has_today_data(today_data: object) -> bool:
    """True, если за сегодня есть число больше 0. Пусто и 0 в отчёт не входят."""
    if today_data is None:
        return False
    text = str(today_data).strip()
    if text == "":
        return False
    try:
        return int(float(text.replace("\xa0", "").replace(" ", ""))) > 0
    except (TypeError, ValueError):
        return False


def project_to_row(project: dict) -> ReportRow:
    """Превращает словарь проекта из data_processor в строку Rich-таблицы."""
    return (
        project["name"],
        int(project["today_data"]),
        project.get("total_issued"),
        project.get("total_volume"),
        project.get("tariff_remaining"),
    )


def group_projects_by_chat(
    projects: Iterable[dict],
    default_chat_id: int,
    require_today_data: bool = True,
) -> Dict[int, List[dict]]:
    """Собирает проекты по telegram_chat_id.

    Если у проекта нет своего chat_id, берём default_chat_id
    (в этом боте это GROUP_CHAT_ID или чат, откуда вызвали /secondary).
    Порядок проектов внутри чата сохраняется.

    require_today_data=True — как в основном отчёте: пустые и 0 за сегодня пропускаем.
    Для предупреждений ставим False, чтобы не потерять проекты с исчерпанным тарифом.
    """
    grouped: Dict[int, List[dict]] = {}
    for project in projects:
        if require_today_data and not has_today_data(project.get("today_data")):
            continue
        chat_id = project.get("telegram_chat_id")
        if chat_id is None or chat_id == "":
            chat_id = default_chat_id
        grouped.setdefault(int(chat_id), []).append(project)
    return grouped


def format_rich_report_message(report_date: date, rows: List[ReportRow]) -> str:
    """Формирует одно Rich Markdown-сообщение вечернего отчёта."""
    if len(rows) == 1:
        project_name, today_value, tariff_used, tariff_limit, remain = rows[0]
        tariff = (
            f"{tariff_used if tariff_used is not None else '—'}/"
            f"{tariff_limit if tariff_limit is not None else '—'}"
        )
        lines = [
            f"## Отчёт · {report_date.strftime('%d.%m')}",
            "",
            f"| Проект | {escape_rich_table_cell(project_name)} |",
            "|:--|:--|",
            f"| Сегодня | {today_value} |",
            f"| Тариф | {escape_rich_table_cell(tariff)} |",
            f"| Остаток | {remain if remain is not None else '—'} |",
        ]
        return "\n".join(lines)

    lines = [
        f"## Отчёт · {report_date.strftime('%d.%m')}",
        "",
        "| Проект | Сегодня | Тариф | Остаток |",
        "|:--|--:|--:|--:|",
    ]
    for project_name, today_value, tariff_used, tariff_limit, remain in rows:
        tariff = (
            f"{tariff_used if tariff_used is not None else '—'} / "
            f"{tariff_limit if tariff_limit is not None else '—'}"
        )
        lines.append(
            "| "
            f"{escape_rich_table_cell(project_name)} | "
            f"{today_value} | "
            f"{escape_rich_table_cell(tariff)} | "
            f"{remain if remain is not None else '—'} |"
        )
    return "\n".join(lines)


def _split_rich_messages(rows: list, format_func) -> List[str]:
    """Режет любую Rich-таблицу на несколько сообщений, если не влезает в лимит API."""
    if not rows:
        return []

    messages: List[str] = []
    current_rows: list = []

    for row in rows:
        candidate_rows = [*current_rows, row]
        candidate = format_func(candidate_rows)
        too_many_rows = len(candidate_rows) > RICH_TABLE_MAX_DATA_ROWS
        too_large = len(candidate.encode("utf-8")) > RICH_MESSAGE_MAX_BYTES

        if current_rows and (too_many_rows or too_large):
            messages.append(format_func(current_rows))
            current_rows = [row]
            single_row_message = format_func(current_rows)
            if len(single_row_message.encode("utf-8")) > RICH_MESSAGE_MAX_BYTES:
                raise ValueError("Название проекта не помещается в Rich Message API")
            continue

        if not current_rows and too_large:
            raise ValueError("Название проекта не помещается в Rich Message API")

        current_rows = candidate_rows

    if current_rows:
        messages.append(format_func(current_rows))
    return messages


def build_rich_report_messages(
    report_date: date,
    rows: List[ReportRow],
) -> List[str]:
    """Режет основной отчёт на несколько сообщений, если не влезает в лимит API."""
    return _split_rich_messages(
        rows,
        lambda chunk: format_rich_report_message(report_date, chunk),
    )


def format_disable_warning_message(rows: List[Tuple[str, int]]) -> str:
    """Таблица «тарифы исчерпаны»: проект и остаток."""
    if len(rows) == 1:
        project_name, remain = rows[0]
        lines = [
            "## Внимание · тарифы исчерпаны",
            "",
            f"| Проект | {escape_rich_table_cell(project_name)} |",
            "|:--|:--|",
            f"| Остаток | {remain} |",
        ]
        return "\n".join(lines)

    lines = [
        "## Внимание · тарифы исчерпаны",
        "",
        "| Проект | Остаток |",
        "|:--|--:|",
    ]
    for project_name, remain in rows:
        lines.append(f"| {escape_rich_table_cell(project_name)} | {remain} |")
    return "\n".join(lines)


def format_reduce_warning_message(rows: List[Tuple[str, int]]) -> str:
    """Таблица «остаток меньше чем на день»: только проект и остаток."""
    if len(rows) == 1:
        project_name, remain = rows[0]
        lines = [
            "## Внимание · остаток меньше чем на день",
            "",
            f"| Проект | {escape_rich_table_cell(project_name)} |",
            "|:--|:--|",
            f"| Остаток | {remain} |",
        ]
        return "\n".join(lines)

    lines = [
        "## Внимание · остаток меньше чем на день",
        "",
        "| Проект | Остаток |",
        "|:--|--:|",
    ]
    for project_name, remain in rows:
        lines.append(f"| {escape_rich_table_cell(project_name)} | {remain} |")
    return "\n".join(lines)


def build_disable_warning_messages(rows: List[Tuple[str, int]]) -> List[str]:
    return _split_rich_messages(rows, format_disable_warning_message)


def build_reduce_warning_messages(rows: List[Tuple[str, int]]) -> List[str]:
    return _split_rich_messages(rows, format_reduce_warning_message)


def disable_projects_to_rows(projects: Iterable[dict]) -> List[Tuple[str, int]]:
    return [(project["name"], int(project["remaining"])) for project in projects]


def reduce_projects_to_rows(projects: Iterable[dict]) -> List[Tuple[str, int]]:
    return disable_projects_to_rows(projects)


def ensure_telegram_response_ok(response) -> None:
    """Проверяет HTTP-статус и поле ok в ответе Bot API."""
    response.raise_for_status()
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(payload.get("description") or "Telegram вернул ok=false")


def send_rich_telegram_message(bot_token: str, chat_id: int, text: str) -> None:
    """Отправляет Rich Markdown через официальный sendRichMessage."""
    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    payload = {"chat_id": chat_id, "rich_message": {"markdown": text}}
    response = requests.post(url, json=payload, timeout=15)
    ensure_telegram_response_ok(response)
