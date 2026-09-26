"""Rules a tournament must follow before it is saved, each broken rule with a message for the admin.

The database does not check the JSONB blind structure, so these rules are what keeps it sound
(docs/adr/ADR-0004-blind-structure-storage.md)."""

from datetime import datetime

from app.schemas import BlindLevel, TournamentIn

MAX_NAME_LENGTH = 200  # models.Tournament.name
MAX_AMOUNT = 2_147_483_647  # PostgreSQL integer, the type of buy_in and starting_stack


def _field_errors(tournament: TournamentIn, now: datetime) -> list[str]:
    errors: list[str] = []
    if not tournament.name:
        errors.append("Укажите название турнира")
    if len(tournament.name) > MAX_NAME_LENGTH:
        errors.append(f"Название длиннее {MAX_NAME_LENGTH} символов")
    if tournament.starts_at <= now:
        errors.append("Время начала уже прошло")
    if tournament.buy_in < 0:
        errors.append("Бай-ин не может быть отрицательным")
    if tournament.buy_in > MAX_AMOUNT:
        errors.append("Бай-ин слишком большой")
    if tournament.starting_stack <= 0:
        errors.append("Стартовый стек должен быть больше нуля")
    if tournament.starting_stack > MAX_AMOUNT:
        errors.append("Стартовый стек слишком большой")
    return errors


def _structure_errors(tournament: TournamentIn) -> list[str]:
    errors: list[str] = []
    level_number = 0
    for item in tournament.structure:
        if isinstance(item, BlindLevel):
            level_number += 1
            where = f"Уровень {level_number}"
            if item.small_blind <= 0:
                errors.append(f"{where}: малый блайнд должен быть больше нуля")
            if item.big_blind < item.small_blind:
                errors.append(f"{where}: большой блайнд не может быть меньше малого")
            if item.ante < 0:
                errors.append(f"{where}: анте не может быть отрицательным")
        else:
            where = f"Перерыв после уровня {level_number}" if level_number else "Перерыв в начале"
        if item.duration_minutes <= 0:
            errors.append(f"{where}: длительность должна быть больше нуля")
    return errors


def tournament_errors(tournament: TournamentIn, now: datetime) -> list[str]:
    errors = _field_errors(tournament, now) + _structure_errors(tournament)
    level_count = sum(isinstance(item, BlindLevel) for item in tournament.structure)
    if level_count == 0:
        # Without levels there is nothing for re-entry, add-on and late registration to point at.
        return errors + ["В структуре блайндов нет ни одного уровня"]
    for option, level in [
        ("Re-entry", tournament.reentry_until_level),
        ("Add-on", tournament.addon_at_level),
        ("Поздняя регистрация", tournament.late_registration_until_level),
    ]:
        if level is not None and not 1 <= level <= level_count:
            errors.append(f"{option}: уровня {level} нет в структуре, в ней уровни с 1 по {level_count}")
    return errors
