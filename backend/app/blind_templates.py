"""League-wide blind structure templates. In the MVP they live in code, not in the database:
the league sets the defaults, and each tournament keeps its own adjusted copy.
See docs/adr/ADR-0004-blind-structure-storage.md."""

from fastapi import APIRouter

from app.auth import CurrentAdmin
from app.schemas import BlindLevel, BlindTemplate, Break, StructureItem

router = APIRouter(prefix="/api/blind-templates")

# (small blind, big blind, ante) per level; None marks a break.
_BLINDS: list[tuple[int, int, int] | None] = [
    (100, 200, 0),
    (150, 300, 0),
    (200, 400, 0),
    (300, 600, 75),
    None,
    (400, 800, 100),
    (500, 1000, 100),
    (600, 1200, 200),
    (800, 1600, 200),
    None,
    (1000, 2000, 300),
    (1500, 3000, 400),
    (2000, 4000, 500),
    (3000, 6000, 1000),
]


def _structure(level_minutes: int, break_minutes: int) -> list[StructureItem]:
    return [
        Break(kind="break", duration_minutes=break_minutes)
        if blinds is None
        else BlindLevel(
            kind="level",
            small_blind=blinds[0],
            big_blind=blinds[1],
            ante=blinds[2],
            duration_minutes=level_minutes,
        )
        for blinds in _BLINDS
    ]


TEMPLATES = [
    BlindTemplate(id="standard", name="Стандартная лиги (уровни по 20 минут)", structure=_structure(20, 10)),
    BlindTemplate(id="turbo", name="Турбо (уровни по 10 минут)", structure=_structure(10, 5)),
]


@router.get("")
def list_templates(admin: CurrentAdmin) -> list[BlindTemplate]:
    return TEMPLATES
