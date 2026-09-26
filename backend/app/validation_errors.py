"""Turns FastAPI's request validation errors into short Russian messages, one per problem,
in the same {"detail": [message, ...]} form as the tournament rules (app/tournament_rules.py)."""

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_FIELDS = {
    "name": "Название",
    "starts_at": "Начало",
    "buy_in": "Бай-ин",
    "starting_stack": "Стартовый стек",
    "structure": "Структура блайндов",
    "reentry_until_level": "Re-entry",
    "addon_at_level": "Add-on",
    "late_registration_until_level": "Поздняя регистрация",
    "small_blind": "малый блайнд",
    "big_blind": "большой блайнд",
    "ante": "анте",
    "duration_minutes": "длительность",
    "phone": "Телефон",
    "code": "Код",
    "club_id": "Номер клуба",
    "tournament_id": "Номер турнира",
}

_PROBLEMS = {
    "missing": "не заполнено",
    "int_type": "нужно целое число",
    "int_parsing": "нужно целое число",
    "int_from_float": "нужно целое число",
    "string_type": "нужен текст",
    "datetime_type": "нужны дата и время",
    "datetime_parsing": "нужны дата и время",
    "datetime_from_date_parsing": "нужны дата и время",
    "timezone_aware": "нужны дата и время с часовым поясом",
    "list_type": "нужен список",
    "union_tag_invalid": "нужен уровень или перерыв",
    "union_tag_not_found": "нужен уровень или перерыв",
    "json_invalid": "некорректный JSON",
}

# Discriminated union tags that pydantic puts into the error location.
_TAGS = {"level", "break"}


def _where(location: tuple[Any, ...]) -> str:
    parts = []
    for part in location[1:]:  # location[0] is "body", "query" etc.
        if isinstance(part, int):
            parts.append(f"строка {part + 1}")
        elif part not in _TAGS:
            parts.append(_FIELDS.get(part, f"поле «{part}»"))
    return ", ".join(parts)


def _message(error: dict[str, Any]) -> str:
    problem = _PROBLEMS.get(error["type"], "некорректное значение")
    where = _where(tuple(error["loc"]))
    return f"{where}: {problem}" if where else problem.capitalize()


async def russian_validation_errors(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": [_message(error) for error in exc.errors()]},
    )
