from datetime import UTC, date, datetime
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
    # How many chips an add-on gives; needed only when the add-on is offered.
    addon_stack: int | None = None
    # What an add-on costs, in roubles; needed only when the add-on is offered.
    addon_price: int | None = None
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
    # The secret part of the hall board's link, /board/<board_token>.
    board_token: str


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


class Refund(BaseModel):
    # Roubles given back to the player by a storno of the buy-in they paid; 0 when none.
    refunded: int


class CheckInUndone(RegistrationOut, Refund):
    pass


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
    # To the millisecond: the admin panel and the hall board count down from the same moment,
    # so their timers turn over together (ADR-0007).
    seconds_left: float


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
    # Rating points, once the tournament is finished.
    points: int | None


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


class BoardState(BaseModel):
    """A tournament as the hall board shows it to everyone in the club: no player names."""

    club: ClubOut
    name: str
    starts_at: Annotated[AwareDatetime, AfterValidator(_in_utc)]
    status: TournamentStatus
    starting_stack: int
    structure: list[StructureItem]
    # None until the tournament starts.
    clock: ClockOut | None
    # Still at the tables.
    players_left: int
    # Everyone who has sat down at a table, counted once however many times they re-entered.
    players: int
    reentries: int
    # All the chips in play shared among the players left; None while nobody is at a table.
    average_stack: int | None


class ResultOut(BaseModel):
    """A player's result in a finished tournament."""

    model_config = ConfigDict(from_attributes=True)

    place: int
    player: PlayerOut
    points: int
    reentries: int
    addons: int


class TournamentResults(BaseModel):
    status: TournamentStatus
    # By place, the winner first; empty until the tournament is finished.
    results: list[ResultOut]


class PlaceIn(BaseModel):
    place: int


class SeasonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # The year and its half, such as "2026-2".
    id: str
    name: str
    first_day: date
    last_day: date


class RatingRow(BaseModel):
    # Equal points share a position; the next position counts everyone above.
    position: int
    player: PlayerOut
    points: int
    # Finished tournaments of the club the player has played this season.
    tournaments: int


class ClubRating(BaseModel):
    season: SeasonOut
    # Ids of the seasons either side, to look back at; no next one from the current season.
    previous_season: str
    next_season: str | None
    # By points, the most first; equal points by name.
    players: list[RatingRow]


TransactionKind = Literal["buy_in", "reentry", "addon"]
PaymentMethod = Literal["cash", "card"]


class PaymentIn(BaseModel):
    """How the player pays; needed only when there is something to pay."""

    payment_method: PaymentMethod | None = None


class PaymentMethodIn(BaseModel):
    payment_method: PaymentMethod


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Annotated[AwareDatetime, AfterValidator(_in_utc)]
    kind: TransactionKind
    # In roubles; negative for a storno.
    amount: int
    payment_method: PaymentMethod
    player: PlayerOut
    # Who took the money, or reversed it.
    admin: AdminOut
    # The transaction this storno reverses.
    reverses_id: int | None
    # The payment taken the wrong way that this one replaces.
    replaces_id: int | None
    # The storno that has reversed this transaction, if one has.
    reversed_by_id: int | None


class KindTotal(BaseModel):
    kind: TransactionKind
    # Operations that stand: not a storno and not reversed.
    count: int
    amount: int


class MethodTotal(BaseModel):
    payment_method: PaymentMethod
    amount: int


class Cashier(BaseModel):
    """A tournament's cashier: what has been paid, by kind of operation and by payment method."""

    # Buy-in, re-entry and add-on, always all three.
    by_kind: list[KindTotal]
    # Cash and card, always both.
    by_method: list[MethodTotal]
    total: int
    # In the order they were made, storno included.
    transactions: list[TransactionOut]
