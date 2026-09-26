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
    seats_per_table: int = 9


# scheduled → running ⇄ paused → finished; or scheduled → cancelled.
TournamentStatus = Literal["scheduled", "running", "paused", "finished", "cancelled"]


def _in_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


class TournamentOut(TournamentIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: Annotated[AwareDatetime, AfterValidator(_in_utc)]
    status: TournamentStatus


class TournamentList(BaseModel):
    # Running or paused, by start time.
    live: list[TournamentOut]
    upcoming: list[TournamentOut]
    past: list[TournamentOut]


class PlayerIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    phone: str
    # The player agreed to the processing of personal data (152-ФЗ).
    consent: bool


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str


# created: a new league player; added_to_club: already in the league, now also in this club;
# already_in_club: nothing changed.
AddPlayerOutcome = Literal["created", "added_to_club", "already_in_club"]


class PlayerAdded(BaseModel):
    player: PlayerOut
    outcome: AddPlayerOutcome


class RegistrationIn(BaseModel):
    player_id: int


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player: PlayerOut
    # registered: signed up; checked_in: has come to the club on the day; in_game: seated in the
    # running tournament; out: finished with a place.
    status: Literal["registered", "checked_in", "in_game", "out"]


class TournamentRegistrations(BaseModel):
    # Whether players can sign up: until the tournament is started, then while late registration
    # is open.
    registration_open: bool
    # Whether players can drop out: until the tournament is started.
    drop_out_open: bool
    # Whether arrivals can be checked in: from 12 hours before the start to 12 hours after it.
    check_in_open: bool
    registrations: list[RegistrationOut]


class ClockOut(BaseModel):
    running: bool
    # The structure item (level or break) being played: an index into the tournament's structure.
    item: int
    seconds_left: int


class EntryWindowsOut(BaseModel):
    reentry: bool
    addon: bool
    late_registration: bool


class SeatedPlayer(BaseModel):
    player: PlayerOut
    table: int
    seat: int
    reentries: int
    addons: int
    # One add-on per entry: whether the current entry has had it.
    addon_this_entry: bool


class FinishedPlayer(BaseModel):
    player: PlayerOut
    place: int
    reentries: int
    addons: int


class MoveOut(BaseModel):
    player: PlayerOut
    from_table: int
    from_seat: int
    to_table: int
    to_seat: int


class GameState(BaseModel):
    """A tournament's game as the admin runs it."""

    status: TournamentStatus
    seats_per_table: int
    # None until the tournament starts.
    clock: ClockOut | None
    windows: EntryWindowsOut
    # By table and seat.
    in_game: list[SeatedPlayer]
    # Knocked out, and at the end the winner; by place.
    out: list[FinishedPlayer]
    # Registered but not seated: not come yet, or come but not yet sat down.
    waiting: list[RegistrationOut]
    # A move that keeps tables even, when they are not.
    suggested_move: MoveOut | None


class MoveIn(BaseModel):
    table: int
    seat: int
