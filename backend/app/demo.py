"""Fills the development database with demo data: three clubs with their admins and owners,
sixty players, and tournaments of every kind — finished ones (this season and the one before),
ones going on right now in every club (two at once in «Обь», one of them paused), one waiting to
be started, coming ones with players signed up and come, and cancelled ones.

    docker compose exec backend python -m app.demo

It first deletes every tournament (with its registrations and cashier), every player who is
not linked to a Telegram account, the clubs' own logs and the staff it takes on itself, so it can
be run again for a fresh set. Clubs, the seed's admins and owners and Telegram-linked players
stay; a linked player plays in the demo tournaments of «Енисей», so the bot sends them a result
and a reminder.

The league's part is done as the developer does it (app/league.py): «Томь» is founded and its
owner appointed by the league's functions. The other staff are taken on by their clubs' owners
in «Команда», and one admin of «Обь», who worked in its tournaments for months, was removed ten
days ago: his name stays in the cashier and the logs.

Everything goes through the API, as admins would do it, with the clock set back in time: seating,
places, points, the cashier, the action log and the blind clocks are what the system itself
worked out. A few players sign up and drop out by the bot's own rules, so the action log shows
what players did themselves too. Games going on now were started earlier and played up to this
minute, so their clocks run on."""

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from functools import partial
from typing import Any, NamedTuple

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import league
from app.auth import get_clock, new_session_token
from app.bot import conversation
from app.db import SessionLocal
from app.main import app
from app.models import (
    ActionLogEntry,
    Admin,
    AdminSession,
    Club,
    ClubPlayer,
    Player,
    Registration,
    TelegramUser,
    Tournament,
    Transaction,
)
from app.seasons import LEAGUE_TIME, season_at
from app.seed import seed

OB, ENISEY, TOM = "Покер-клуб «Обь»", "Покер-клуб «Енисей»", "Покер-клуб «Томь»"
TOM_COLORS = ("#1F5C4A", "#D9B44A")
# Until the owner can upload it in the club's settings, the demo puts it in place itself.
TOM_LOGO = "/logos/tom.svg"


class StaffMember(NamedTuple):
    club: str
    name: str
    phone: str


# The owner the league appoints to «Томь».
TOM_OWNER = StaffMember(TOM, "Наталья Широкова", "+79990000013")
# The admins the owners take on in «Команда»; the seed's admin and owner of «Обь» and «Енисей»
# are there already.
STAFF = [
    StaffMember(OB, "Сергей Лебедев", "+79990000021"),
    StaffMember(ENISEY, "Ольга Кравец", "+79990000022"),
    StaffMember(TOM, "Павел Громов", "+79990000003"),
]
# An admin of «Обь» who worked in its tournaments and was removed from the team ten days ago.
LEFT = StaffMember(OB, "Виталий Осипов", "+79990000031")
LEFT_DAYS_AGO = 10

NAMES = [
    "Алексей Смирнов", "Мария Кузнецова", "Иван Попов", "Екатерина Васильева", "Дмитрий Новиков",
    "Анна Морозова", "Сергей Волков", "Ольга Соловьёва", "Андрей Зайцев", "Татьяна Павлова",
    "Николай Семёнов", "Елена Голубева", "Михаил Виноградов", "Наталья Богданова",
    "Артём Воробьёв", "Юлия Фёдорова", "Павел Михайлов", "Ирина Белякова", "Роман Тарасов",
    "Светлана Беляева", "Евгений Комаров", "Ксения Орлова", "Владимир Киселёв", "Дарья Макарова",
    "Максим Андреев", "Алина Ковалёва", "Илья Ильин", "Виктория Гусева", "Кирилл Титов",
    "Полина Кузьмина", "Антон Кудрявцев", "Анастасия Баранова", "Григорий Куликов",
    "Вера Алексеева", "Олег Степанов", "Людмила Яковлева", "Станислав Сорокин", "Марина Сергеева",
    "Константин Романов", "Ангелина Захарова", "Тимур Борисов", "Алёна Королёва",
    "Вадим Герасимов", "Жанна Пономарёва", "Фёдор Григорьев", "Лариса Лазарева", "Глеб Медведев",
    "Софья Ершова", "Руслан Никитин", "Эльвира Соболева", "Денис Лукин", "Валерия Панова",
    "Ярослав Соколов", "Кристина Мельникова", "Арсений Давыдов", "Милена Зуева", "Борис Лебедев",
    "Оксана Фомина", "Егор Карпов", "Диана Абрамова",
]


def phone_of(number: int) -> str:
    """Demo players' phones: +7 913 500-00-01 and on."""
    return f"+7913500{number + 1:04d}"


# Which demo players (by their number in NAMES) are on each club's list; some are on two. Those
# playing in the games going on now are never in two of them.
CLUB_PLAYERS = {
    OB: list(range(0, 34)),
    ENISEY: list(range(30, 50)),
    TOM: list(range(50, 60)) + [0, 1, 2],
}

# The number standing for the linked Telegram player in the lists of players below.
MISHA = -1


class DemoClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Spec:
    """One demo tournament and how it goes."""

    club: str
    name: str
    starts: datetime
    # finished, running, paused, waiting (players came, not started yet), scheduled, cancelled
    outcome: str
    template: str = "standard"
    buy_in: int = 2000
    stack: int = 20000
    seats: int = 9
    reentry: int | None = 2
    addon: int | None = 2
    addon_stack: int | None = 30000
    addon_price: int | None = 1000
    late: int | None = 3
    # Players by number: those who come before the start, those registered who never come, and
    # those who sit down during late registration (the first half of them signed up beforehand).
    players: list[int] = field(default_factory=list)
    no_shows: list[int] = field(default_factory=list)
    late_players: list[int] = field(default_factory=list)
    reentries: int = 0
    addon_share: float = 0.5
    # How long a finished game lasted; players left at the tables of one going on.
    play_minutes: int = 180
    left: int = 1
    # Of `players`, how many have already come to a coming or cancelled tournament.
    come: int = 0
    undo_check_in: bool = False
    # Of `players`, how many signed up in the bot themselves; and whether one more player signed
    # up there and then dropped out.
    bot_sign_ups: int = 0
    bot_drop_out: bool = False
    # The buy-in the owner changes the coming tournament to after the sign-ups.
    new_buy_in: int | None = None
    undo_knock_out: bool = False
    cashier_fixes: bool = False
    # A finished tournament's place corrected: (the place it was, the place it becomes).
    correct_place: tuple[int, int] | None = None
    # The admin closes registration to players of a coming tournament: the hall is full.
    close_registration: bool = False
    # The admin puts the clock of a game going on right: the level restarted and a minute added
    # while it runs, a minute taken off on the pause.
    clock_fixes: bool = False
    # The admin closes the late registration of a game going on early, if it is still open.
    close_late_registration: bool = False


class Demo:
    def __init__(self, client: TestClient, clock: DemoClock, rng: random.Random) -> None:
        self.client = client
        self.clock = clock
        self.rng = rng
        self.real_now = clock.now
        self.tokens: dict[str, str] = {}
        # Club → phones of its staff: the admins in the order they were added, the owner last.
        self.staff: dict[str, list[str]] = {}
        # Phone → when they were removed from the team: they do nothing after that.
        self.removed: dict[str, datetime] = {}
        self.club_ids: dict[str, int] = {}
        # Demo number → player id.
        self.player_ids: dict[int, int] = {}
        self.boards: list[tuple[str, str, str]] = []

    # --- plumbing ---------------------------------------------------------------------------

    def call(self, method: str, url: str, body: Any = None) -> Any:
        response = self.client.request(method, url, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {url} → {response.status_code}: {response.text}")
        return response.json() if response.content else None

    def act_as(self, phone: str) -> None:
        self.client.cookies.set("admin_session", self.tokens[phone])

    def someone_of(self, club: str) -> None:
        """Mostly the club's first admin, now and then another admin or the owner."""
        phones = [
            phone
            for phone in self.staff[club]
            if phone not in self.removed or self.clock.now < self.removed[phone]
        ]
        weights = [6] + [3] * (len(phones) - 2) + [1]
        self.act_as(self.rng.choices(phones, weights=weights)[0])

    def payment(self) -> dict[str, str]:
        return {"payment_method": self.rng.choices(["cash", "card"], weights=[3, 2])[0]}

    def at(self, moment: datetime) -> None:
        # Nothing may happen later than now: the clocks of games going on run on from here.
        self.clock.now = min(moment, self.real_now)

    # --- people -----------------------------------------------------------------------------

    def staff_and_clubs(self, session: Session) -> None:
        """«Томь» and its owner by the league's command, more than half a year ago; then the
        owners take their admins on in «Команда»."""
        self.at(self.real_now - timedelta(days=215))
        tom = session.scalar(select(Club).where(Club.name == TOM))
        if tom is None:
            tom = league.found_club(session, TOM, *TOM_COLORS)
        tom.logo_url = TOM_LOGO
        league.appoint_owner(session, tom, TOM_OWNER.name, TOM_OWNER.phone, self.clock.now)
        session.commit()
        self.log_everyone_in(session)

        self.at(self.real_now - timedelta(days=210))
        for member in [*STAFF, LEFT]:
            self.act_as(self.staff[member.club][-1])
            self.call(
                "POST",
                f"/api/clubs/{self.club_ids[member.club]}/team",
                {"name": member.name, "phone": member.phone},
            )
        self.log_everyone_in(session)
        self.removed[LEFT.phone] = self.real_now - timedelta(days=LEFT_DAYS_AGO)

    def log_everyone_in(self, session: Session) -> None:
        """A session for each of the clubs' staff, the admins in the order they were taken on and
        the owners last."""
        for club in session.scalars(select(Club)).all():
            self.club_ids[club.name] = club.id
            admins = session.scalars(
                select(Admin)
                .where(Admin.club_id == club.id, Admin.removed_at.is_(None))
                .order_by(Admin.role, Admin.id)
            ).all()
            self.staff[club.name] = [a.phone for a in admins]
            for admin in admins:
                if admin.phone in self.tokens:
                    continue
                token, token_hash = new_session_token()
                session.add(
                    AdminSession(
                        token_hash=token_hash,
                        admin_id=admin.id,
                        expires_at=datetime(2100, 1, 1, tzinfo=UTC),
                    )
                )
                self.tokens[admin.phone] = token
        session.commit()

    def let_go(self) -> None:
        """The owner of «Обь» removes the admin who left, on the day he left."""
        team_url = f"/api/clubs/{self.club_ids[LEFT.club]}/team"
        self.at(self.removed[LEFT.phone])
        self.act_as(self.staff[LEFT.club][-1])
        member = next(m for m in self.call("GET", team_url) if m["phone"] == LEFT.phone)
        self.call("DELETE", f"{team_url}/{member['id']}")

    def players(self) -> None:
        """Every demo player came to their first club months ago, before the season before, and
        to a second one a week later."""
        for number, name in enumerate(NAMES):
            clubs = [club for club, numbers in CLUB_PLAYERS.items() if number in numbers]
            for place, club in enumerate(clubs):
                self.at(self.real_now - timedelta(days=200 - number) + timedelta(days=7 * place))
                self.act_as(self.staff[club][0])
                added = self.call(
                    "POST",
                    f"/api/clubs/{self.club_ids[club]}/players",
                    {"name": name, "phone": phone_of(number), "consent": True},
                )
                self.player_ids[number] = added["player"]["id"]

    # --- tournaments ------------------------------------------------------------------------

    def tournament(self, spec: Spec) -> None:
        club_id = self.club_ids[spec.club]
        created = min(spec.starts - timedelta(days=4), self.real_now - timedelta(hours=3))
        self.at(created)
        self.someone_of(spec.club)
        templates = {t["id"]: t for t in self.call("GET", "/api/blind-templates")}
        addon = spec.addon is not None
        tournament = self.call(
            "POST",
            f"/api/clubs/{club_id}/tournaments",
            {
                "name": spec.name,
                "starts_at": spec.starts.isoformat(),
                "buy_in": spec.buy_in,
                "starting_stack": spec.stack,
                "structure": templates[spec.template]["structure"],
                "reentry_until_level": spec.reentry,
                "addon_at_level": spec.addon,
                "addon_stack": spec.addon_stack if addon else None,
                "addon_price": spec.addon_price if addon else None,
                "late_registration_until_level": spec.late,
                "seats_per_table": spec.seats,
            },
        )
        url = f"/api/clubs/{club_id}/tournaments/{tournament['id']}"
        self.boards.append((spec.club, spec.name, tournament["board_token"]))

        # Sign-ups: those who come, those who never do, and the first half of the late ones.
        signed_late = spec.late_players[: len(spec.late_players) // 2]
        for index, number in enumerate(spec.players + spec.no_shows + signed_late):
            self.at(created + timedelta(hours=1, seconds=20 * index))
            if index < spec.bot_sign_ups:
                self.in_the_bot(conversation.sign_up, spec, tournament["id"], number)
                continue
            self.someone_of(spec.club)
            self.call("POST", f"{url}/registrations", {"player_id": self.player_ids[number]})
        if spec.bot_drop_out:
            # Someone of the club not playing in it changes their mind an hour later.
            playing = spec.players + spec.no_shows + spec.late_players
            number = next(n for n in CLUB_PLAYERS[spec.club] if n not in playing)
            self.at(created + timedelta(hours=2))
            self.in_the_bot(conversation.sign_up, spec, tournament["id"], number)
            self.at(created + timedelta(hours=3))
            self.in_the_bot(conversation.drop_out, spec, tournament["id"], number)
        if spec.new_buy_in is not None:
            self.at(created + timedelta(hours=4))
            self.act_as(self.staff[spec.club][-1])
            self.call("PUT", url, {**tournament, "buy_in": spec.new_buy_in})
        if spec.close_registration:
            self.at(created + timedelta(hours=5))
            self.someone_of(spec.club)
            self.call("POST", f"{url}/registrations/close")

        if spec.outcome == "scheduled":
            moment = max(spec.starts - timedelta(hours=11), self.real_now - timedelta(minutes=40))
            self.check_in(spec, url, spec.players[: spec.come], moment)
            return
        if spec.outcome == "cancelled":
            self.check_in(spec, url, spec.players[: spec.come], spec.starts - timedelta(hours=2))
            self.at(spec.starts - timedelta(minutes=20))
            self.act_as(self.staff[spec.club][-1])
            self.call("POST", f"{url}/cancel")
            return

        self.check_in(spec, url, spec.players, spec.starts - timedelta(minutes=45))
        if spec.outcome == "waiting":
            return
        self.play(spec, url, tournament["structure"])

    def in_the_bot(
        self,
        step: Callable[[Session, TelegramUser, int, datetime], object],
        spec: Spec,
        tournament_id: int,
        number: int,
    ) -> None:
        """The player signs up or drops out in the bot, by the bot's own rules. Their Telegram
        user is made up and never saved, so the bot has no one to send anything to."""
        with SessionLocal() as session:
            user = TelegramUser(telegram_id=0, consent_given_at=self.clock.now)
            user.player = session.get(Player, self.player_ids[number])
            user.club = session.get(Club, self.club_ids[spec.club])
            step(session, user, tournament_id, self.clock.now)
            session.commit()

    def check_in(self, spec: Spec, url: str, numbers: list[int], moment: datetime) -> None:
        # Check-in opens 12 hours before the start, and nobody comes later than now.
        if not numbers or moment > self.real_now or moment < spec.starts - timedelta(hours=12):
            return
        for index, number in enumerate(numbers):
            self.at(moment + timedelta(seconds=40 * index))
            self.someone_of(spec.club)
            player_url = f"{url}/registrations/{self.player_ids[number]}/check-in"
            self.call("POST", player_url, self.payment())
            if spec.undo_check_in and index == 1:
                # Checked in by mistake and at once put right: the buy-in given back, then taken.
                self.call("DELETE", player_url)
                self.call("POST", player_url, self.payment())

    def play(self, spec: Spec, url: str, structure: list[dict[str, Any]]) -> None:
        rng = self.rng
        starts = level_starts(structure)
        t0 = spec.starts + timedelta(minutes=rng.randint(3, 12))
        if spec.outcome == "finished":
            end = t0 + timedelta(minutes=spec.play_minutes)
        else:
            # A paused game was paused a few minutes after its last knock-out.
            end = self.real_now - timedelta(minutes=10 if spec.outcome == "paused" else 1)
        self.at(t0)
        self.someone_of(spec.club)
        self.call("POST", f"{url}/start")

        def minutes(m: float) -> datetime:
            return t0 + timedelta(minutes=m)

        # Re-entries and late seats happen while every window is open, before the add-on level.
        windows = [starts[level + 1] for level in (spec.reentry, spec.late) if level is not None]
        if spec.addon is not None:
            windows.append(starts[spec.addon])
        early_end = min([*windows, (end - t0).total_seconds() / 60])
        events: list[tuple[datetime, Callable[[], None]]] = []
        for _ in range(spec.reentries if spec.reentry else 0):
            moment = minutes(rng.uniform(2, max(2.5, early_end - 3)))
            events.append((moment, partial(self.knock_out_and_reenter, spec, url, moment)))
        signed_late = set(spec.late_players[: len(spec.late_players) // 2])
        for number in spec.late_players:
            moment = minutes(rng.uniform(2, max(2.5, early_end - 2)))
            events.append(
                (moment, partial(self.seat_late, spec, url, number, number in signed_late, moment))
            )
        for moment, event in sorted(events, key=lambda e: e[0]):
            if moment <= end:
                event()

        last_early = minutes(early_end)
        if spec.addon is not None and minutes(starts[spec.addon] + 1) < end:
            addon_time = minutes(starts[spec.addon] + 1)
            self.at(addon_time)
            for seated in self.game(url)["in_game"]:
                if rng.random() < spec.addon_share:
                    self.someone_of(spec.club)
                    self.call(
                        "POST", f"{url}/players/{seated['player']['id']}/addon", self.payment()
                    )
            last_early = max(last_early, addon_time)

        in_game = len(self.game(url)["in_game"])
        knock_outs = max(0, in_game - spec.left)
        first = last_early + timedelta(minutes=5)
        step = (end - first) / (knock_outs + 1) if end > first else timedelta(seconds=30)
        for index in range(knock_outs):
            moment = first + step * (index + 1)
            self.at(moment)
            victim = rng.choice(self.game(url)["in_game"])["player"]["id"]
            self.someone_of(spec.club)
            game = self.call("POST", f"{url}/players/{victim}/knock-out")
            last = index == knock_outs - 1
            if spec.undo_knock_out and last:
                # Marked by mistake, and taken back at once.
                self.at(moment + timedelta(minutes=1))
                game = self.call("POST", f"{url}/players/{victim}/undo-knock-out")
            # The admin makes the suggested moves, but the latest one of a game going on is left
            # for the admin panel to show.
            if game["suggested_move"] and not (last and spec.outcome != "finished"):
                self.at(moment + timedelta(minutes=1))
                move = game["suggested_move"]
                self.call(
                    "POST",
                    f"{url}/players/{move['player']['id']}/move",
                    {"table": move["to_table"], "seat": move["to_seat"]},
                )

        # Put right a minute or so after the last knock-out, so no window the demo used moves.
        if spec.close_late_registration and self.game(url)["can_close_late_registration"]:
            self.at(end + timedelta(seconds=10))
            self.someone_of(spec.club)
            self.call("POST", f"{url}/close-late-registration")
        if spec.clock_fixes and spec.outcome == "running":
            self.at(end + timedelta(seconds=20))
            self.someone_of(spec.club)
            self.call("POST", f"{url}/restart-level")
            self.at(end + timedelta(seconds=30))
            self.call("POST", f"{url}/add-minute")
        if spec.outcome == "paused":
            paused = self.real_now - timedelta(minutes=rng.randint(3, 8))
            self.at(paused)
            self.call("POST", f"{url}/pause")
            if spec.clock_fixes:
                self.at(paused + timedelta(minutes=1))
                self.call("POST", f"{url}/take-minute")
        if spec.outcome == "finished":
            self.after_the_end(spec, url, end)

    def game(self, url: str) -> Any:
        return self.call("GET", f"{url}/game")

    def knock_out_and_reenter(self, spec: Spec, url: str, moment: datetime) -> None:
        self.at(moment)
        victim = self.rng.choice(self.game(url)["in_game"])["player"]["id"]
        self.someone_of(spec.club)
        self.call("POST", f"{url}/players/{victim}/knock-out")
        self.at(moment + timedelta(minutes=1))
        self.call("POST", f"{url}/players/{victim}/reentry", self.payment())

    def seat_late(
        self, spec: Spec, url: str, number: int, signed_up: bool, moment: datetime
    ) -> None:
        self.at(moment)
        self.someone_of(spec.club)
        player_id = self.player_ids[number]
        if not signed_up:
            self.call("POST", f"{url}/registrations", {"player_id": player_id})
        self.call("POST", f"{url}/players/{player_id}/seat", self.payment())

    def after_the_end(self, spec: Spec, url: str, end: datetime) -> None:
        self.at(end + timedelta(minutes=15))
        if spec.correct_place:
            was, becomes = spec.correct_place
            results = self.call("GET", f"{url}/results")["results"]
            player = next(r for r in results if r["place"] == was)["player"]
            self.act_as(self.staff[spec.club][0])
            self.call("PUT", f"{url}/results/{player['id']}", {"place": becomes})
        if spec.cashier_fixes:
            self.act_as(self.staff[spec.club][0])
            transactions = self.call("GET", f"{url}/cashier")["transactions"]
            standing = [
                t for t in transactions if t["reverses_id"] is None and t["reversed_by_id"] is None
            ]
            addon = next((t for t in standing if t["kind"] == "addon"), None)
            if addon:
                # Taken by mistake: the player did not want the add-on after all.
                self.call("POST", f"{url}/cashier/transactions/{addon['id']}/reverse")
            cash = next(
                (t for t in standing if t["kind"] == "buy_in" and t["payment_method"] == "cash"),
                None,
            )
            if cash:
                # Paid by card, marked as cash.
                self.call(
                    "POST",
                    f"{url}/cashier/transactions/{cash['id']}/payment-method",
                    {"payment_method": "card"},
                )


def level_starts(structure: list[dict[str, Any]]) -> dict[int, float]:
    """Minutes from the start of play to the start of each level; one more for the end of the
    last level. A break belongs to the level before it, so it ends before the next level starts."""
    elapsed, number, starts = 0.0, 0, {}
    for item in structure:
        if item["kind"] == "level":
            number += 1
            starts[number] = elapsed
        elapsed += item["duration_minutes"]
    starts[number + 1] = elapsed
    return starts


def reset(session: Session) -> None:
    """Deletes every tournament, every player not linked to a Telegram account, the clubs' own
    logs and the staff the demo takes on (the seed's stay)."""
    linked = select(TelegramUser.player_id).where(TelegramUser.player_id.is_not(None))
    unlinked = select(Player.id).where(Player.id.not_in(linked))
    # The tournaments' logs and the clubs' own.
    session.execute(delete(ActionLogEntry))
    session.execute(delete(Transaction))
    session.execute(delete(Registration))
    session.execute(delete(Tournament))
    session.execute(delete(ClubPlayer).where(ClubPlayer.player_id.in_(unlinked)))
    session.execute(delete(Player).where(Player.id.in_(unlinked)))
    demo_staff = [member.phone for member in [*STAFF, LEFT, TOM_OWNER]]
    session.execute(delete(Admin).where(Admin.phone.in_(demo_staff)))
    session.commit()


def specs(now: datetime, misha: list[int]) -> list[Spec]:
    """The demo tournaments, around now. `misha` holds the linked Telegram player, if any."""
    today = now.astimezone(LEAGUE_TIME).date()

    def day(offset: int, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(today + timedelta(days=offset), time(hour, minute), LEAGUE_TIME)

    def rounded(moment: datetime) -> datetime:
        return moment.replace(minute=moment.minute - moment.minute % 5, second=0, microsecond=0)

    def ago(minutes: int) -> datetime:
        return rounded(now - timedelta(minutes=minutes))

    def ahead(minutes: int) -> datetime:
        return rounded(now + timedelta(minutes=minutes))

    # Some days before this season began: the season before.
    before = season_at(now).starts_at - timedelta(days=9)
    last_season_day = (before.astimezone(LEAGUE_TIME).date() - today).days
    ob, en, tom = OB, ENISEY, TOM
    return [
        # «Обь»: the season before, finished this season, two games at once now, coming ones.
        Spec(ob, "Летний финал", day(last_season_day, 18), "finished", buy_in=2500,
             reentry=3, addon=4, addon_stack=40000, addon_price=1500, late=4,
             players=list(range(0, 16)), no_shows=[16], late_players=[17, 18], reentries=3,
             play_minutes=300),
        Spec(ob, "Турнир выходного дня", day(-23, 17), "finished",
             players=list(range(0, 18)), no_shows=[18, 19], late_players=[20], reentries=3,
             play_minutes=260, correct_place=(7, 4)),
        Spec(ob, "Турбо-среда", day(-13, 19, 30), "finished", template="turbo", buy_in=1000,
             seats=6, reentry=None, addon=None, late=None,
             players=[1, 3, 5, 7, 9, 11, 13, 15], play_minutes=110),
        Spec(ob, "Фриролл для новичков", day(-10, 15), "finished", template="turbo", buy_in=0,
             stack=10000, seats=8, reentry=1, addon=None, late=2,
             players=[20, 21, 22, 23, 24, 25, 26], late_players=[27], reentries=2,
             play_minutes=100),
        Spec(ob, "Осенний кубок", day(-7, 18), "finished", buy_in=3000, seats=8,
             reentry=3, addon=3, addon_stack=50000, addon_price=2000, late=4,
             players=list(range(0, 24)), no_shows=[24], late_players=[25, 26], reentries=4,
             addon_share=0.7, play_minutes=330, undo_check_in=True),
        Spec(ob, "Вечерний кэш-стек", day(-3, 19), "finished", template="turbo", buy_in=1500,
             seats=6, reentry=2, addon=2, addon_stack=20000, addon_price=1000, late=3,
             players=list(range(6, 18)), late_players=[18], reentries=2, play_minutes=150,
             cashier_fixes=True),
        Spec(ob, "Покерный марафон", day(-2, 16), "cancelled",
             players=list(range(0, 10)), come=6),
        Spec(ob, "Турбо-серия", ago(55), "running", template="turbo", buy_in=1500, seats=5,
             reentry=4, addon=3, addon_stack=20000, addon_price=1000, late=6,
             players=list(range(0, 13)), no_shows=[15], late_players=[13, 14], reentries=2,
             left=9, undo_knock_out=True, bot_sign_ups=4, bot_drop_out=True,
             clock_fixes=True),
        Spec(ob, "Хайроллер", ago(130), "paused", buy_in=5000, stack=30000,
             reentry=2, addon=2, addon_stack=30000, addon_price=3000, late=3,
             players=list(range(16, 26)), reentries=1, addon_share=0.8, left=6,
             clock_fixes=True),
        Spec(ob, "Экспресс-турнир", ago(25), "waiting", template="turbo", buy_in=1000,
             seats=6, reentry=2, addon=None, late=3, players=list(range(26, 33))),
        Spec(ob, "Кубок новичков", ahead(200), "scheduled", players=list(range(14, 26)),
             bot_sign_ups=5, bot_drop_out=True),
        Spec(ob, "Турнир четверга", day(2, 19), "scheduled", players=list(range(0, 11)),
             new_buy_in=2500, close_registration=True),
        Spec(ob, "Большой субботний турнир", day(5, 16), "scheduled", buy_in=3500,
             stack=30000, seats=10, reentry=4, addon=4, addon_stack=50000, addon_price=2000,
             late=5, players=[0, 2, 4, 6, 8]),
        Spec(ob, "Мастер-класс по турнирной стратегии", day(3, 12), "cancelled",
             buy_in=0, reentry=None, addon=None, late=None, players=[1, 2, 3, 4]),
        Spec(ob, "Турнир без ребаев", day(9, 19), "scheduled", reentry=None, addon=None,
             late=None),
        # «Енисей»: its linked Telegram player's results, one of them today; a game going on;
        # a coming tournament soon enough for the bot to remind them.
        Spec(en, "Енисейская классика", day(last_season_day + 3, 18), "finished",
             players=list(range(30, 42)) + misha, late_players=[42], reentries=2,
             play_minutes=240),
        Spec(en, "Кубок Енисея. Этап 1", day(-12, 18), "finished", buy_in=2500,
             reentry=3, addon=3, addon_stack=40000, addon_price=1500, late=4,
             players=list(range(30, 44)) + misha, no_shows=[44], reentries=3,
             play_minutes=280),
        Spec(en, "Турбо-вторник", day(-6, 19), "finished", template="turbo", buy_in=1000,
             seats=6, reentry=None, addon=None, late=2,
             players=list(range(36, 46)) + misha, late_players=[46], play_minutes=120),
        Spec(en, "Кубок Енисея. Этап 2", ago(360), "finished", buy_in=2500,
             reentry=3, addon=3, addon_stack=40000, addon_price=1500, late=4,
             players=list(range(32, 46)) + misha, reentries=2, play_minutes=240),
        Spec(en, "Енисей-турбо", ago(40), "running", template="turbo", buy_in=1500,
             seats=7, reentry=3, addon=3, addon_stack=20000, addon_price=1000, late=5,
             players=list(range(34, 47)), late_players=[47], reentries=1, left=10,
             close_late_registration=True),
        Spec(en, "Кубок Енисея. Этап 3", ahead(110), "scheduled", buy_in=2500,
             reentry=3, addon=3, addon_stack=40000, addon_price=1500, late=4,
             players=[48, 49] + list(range(30, 40)) + misha, come=2),
        Spec(en, "Выходной турнир на Енисее", day(4, 17), "scheduled",
             players=list(range(30, 38)) + misha),
        # «Томь»: the club's first tournament, and a game going on at the same time as the others.
        Spec(tom, "Открытие клуба", day(-9, 18), "finished", buy_in=0, reentry=None,
             addon=None, late=2, players=list(range(50, 60)) + [0, 1], late_players=[2],
             play_minutes=200),
        Spec(tom, "Томский турбо", ago(30), "running", template="turbo", buy_in=1000,
             seats=6, reentry=2, addon=2, addon_stack=20000, addon_price=800, late=4,
             players=list(range(50, 60)), reentries=1, left=8),
        Spec(tom, "Турнир выходного дня в Томи", day(4, 16), "scheduled",
             players=[50, 51, 52, 0, 1]),
    ]


def main() -> None:
    seed()
    with SessionLocal() as session:
        reset(session)
        linked_ids = [
            player_id
            for player_id in session.scalars(select(TelegramUser.player_id)).all()
            if player_id is not None
        ]
    clock = DemoClock()
    app.dependency_overrides[get_clock] = lambda: clock
    try:
        with TestClient(app) as client, SessionLocal() as session:
            demo = Demo(client, clock, random.Random(2026))
            demo.staff_and_clubs(session)
            demo.players()
            misha: list[int] = []
            enisey = demo.club_ids[ENISEY]
            for player_id in linked_ids[:1]:
                demo.player_ids[MISHA] = player_id
                # On the list of «Енисей», whose demo tournaments they play.
                if session.get(ClubPlayer, (enisey, player_id)) is None:
                    session.add(ClubPlayer(club_id=enisey, player_id=player_id, added_at=clock.now))
                    session.commit()
                misha.append(MISHA)
            for spec in specs(demo.real_now, misha):
                demo.tournament(spec)
                print(f"{spec.club}: {spec.name} — {spec.outcome}")
            demo.let_go()
            report(demo)
    finally:
        del app.dependency_overrides[get_clock]


def report(demo: Demo) -> None:
    print()
    print("Входы в админ-панель, http://localhost:5173/admin:")
    with SessionLocal() as session:
        for admin in session.scalars(select(Admin).order_by(Admin.club_id, Admin.role, Admin.id)):
            role = "владелец" if admin.role == "owner" else "администратор"
            removed = ", убран из команды: не входит" if admin.removed_at else ""
            print(f"  {admin.club.name}: {role} {admin.name}, {admin.phone}{removed}")
        live = set(
            session.scalars(
                select(Tournament.board_token).where(Tournament.status.in_(("running", "paused")))
            )
        )
    print()
    print(
        f"Игроки для кабинета, http://localhost:5173: телефоны {phone_of(0)} … "
        f"{phone_of(len(NAMES) - 1)}"
    )
    print()
    print("Табло идущих турниров:")
    for club, name, token in demo.boards:
        if token in live:
            print(f"  {club}, {name}: http://localhost:5173/board/{token}")


if __name__ == "__main__":
    main()
