"""When a running tournament takes re-entries, add-ons and late registrations.

The rules name play levels ("re-entry until level N", "add-on at level N"), breaks not counted.
A break belongs to the level before it: on the break after level N the windows of level N are
still open, which is when clubs usually give the add-on (a decision taken with the customer
for ticket #6)."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas import BlindLevel, StructureItem


def level_reached(structure: Sequence[StructureItem], item: int) -> int:
    """The number of the level being played at `item`, or of the level before a break;
    0 for a break before the first level."""
    return sum(isinstance(played, BlindLevel) for played in structure[: item + 1])


@dataclass(frozen=True)
class EntryWindows:
    reentry: bool
    addon: bool
    late_registration: bool


def entry_windows(
    structure: Sequence[StructureItem],
    item: int,
    *,
    reentry_until_level: int | None,
    addon_at_level: int | None,
    late_registration_until_level: int | None,
) -> EntryWindows:
    level = level_reached(structure, item)
    return EntryWindows(
        reentry=reentry_until_level is not None and level <= reentry_until_level,
        addon=addon_at_level is not None and level == addon_at_level,
        late_registration=(
            late_registration_until_level is not None and level <= late_registration_until_level
        ),
    )
