from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field


class ClubOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    logo_url: str
    primary_color: str
    accent_color: str


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str


class Me(BaseModel):
    admin: AdminOut
    club: ClubOut


class BlindLevel(BaseModel):
    kind: Literal["level"]
    small_blind: int
    big_blind: int
    ante: int
    duration_minutes: int


class Break(BaseModel):
    kind: Literal["break"]
    duration_minutes: int


StructureItem = Annotated[BlindLevel | Break, Field(discriminator="kind")]


class BlindTemplate(BaseModel):
    id: str
    name: str
    structure: list[StructureItem]


class TournamentIn(BaseModel):
    """What the admin fills in. Only the shape is checked here; the rules live in
    app/tournament_rules.py so that every broken rule gets its own clear message."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    starts_at: AwareDatetime
    buy_in: int
    starting_stack: int
    structure: list[StructureItem]
    # Play level numbers (breaks are not counted); None means the option is not offered.
    reentry_until_level: int | None = None
    addon_at_level: int | None = None
    late_registration_until_level: int | None = None


def _in_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


class TournamentOut(TournamentIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: Annotated[AwareDatetime, AfterValidator(_in_utc)]
    status: Literal["scheduled", "cancelled"]


class TournamentList(BaseModel):
    upcoming: list[TournamentOut]
    past: list[TournamentOut]
