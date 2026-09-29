"""The club owner's reports: the money, the attendance and the best players of the club's
tournaments over a period the owner picks. A tournament is in the period its scheduled start
falls in, in the league's time, as in the rating's seasons, so the whole of its cashier is in one
period however late it finishes. Worked out afresh from the tournaments' transactions and
registrations on every request, like the cashier (ADR-0009).

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003), and the owner's alone:
the club's admins do not see them (OwnerClub)."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from io import StringIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import DbSession
from app.cashier import BOM, KIND_NAMES, METHOD_NAMES, excel_text, kind_totals, method_totals
from app.clubs import OwnerClub
from app.models import Club, Registration, Tournament, Transaction
from app.rating import club_standings
from app.schemas import Attendance, ClubReport, Finances, RatingRow, WeekAttendance
from app.seasons import LEAGUE_TIME

router = APIRouter(prefix="/api/clubs/{club_id}")

HELD = ("running", "paused", "finished")
# The longest period a report covers: a year, a leap one too. Its weeks are listed one by one.
LONGEST_PERIOD = timedelta(days=366)
# How many players the lists of the best players show. Not positions: early in a period nearly
# everyone shares a position by tournaments played, and the list would be the whole club.
TOP = 10


@dataclass(frozen=True)
class Period:
    first_day: date
    last_day: date


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=LEAGUE_TIME)


def _weeks(first_day: date, last_day: date) -> list[tuple[date, date]]:
    """The period's weeks, Monday to Sunday, the first and the last cut to the period."""
    weeks = []
    start = first_day
    while start <= last_day:
        sunday = start + timedelta(days=6 - start.weekday())
        weeks.append((start, min(sunday, last_day)))
        start = sunday + timedelta(days=1)
    return weeks


def _attendance(shown: Period, held: list[tuple[datetime, int]]) -> Attendance:
    """`held`: when each tournament held starts, and how many players came to it."""
    days = [(starts_at.astimezone(LEAGUE_TIME).date(), came) for starts_at, came in held]
    weeks = [
        WeekAttendance(
            first_day=monday,
            last_day=sunday,
            tournaments=sum(monday <= day <= sunday for day, _ in days),
            participants=sum(came for day, came in days if monday <= day <= sunday),
        )
        for monday, sunday in _weeks(shown.first_day, shown.last_day)
    ]
    participants = sum(came for _, came in days)
    return Attendance(
        weeks=weeks,
        participants=participants,
        average_players=round(participants / len(days), 1) if days else None,
    )


def _by_tournaments(standings: list[RatingRow]) -> list[RatingRow]:
    """The rating's players by the tournaments they played, the most first, then by points;
    equal numbers share a position, and the next position counts everyone above."""
    rows: list[RatingRow] = []
    for number, row in enumerate(sorted(standings, key=lambda r: -r.tournaments), start=1):
        tied = rows and rows[-1].tournaments == row.tournaments
        rows.append(row.model_copy(update={"position": rows[-1].position if tied else number}))
    return rows


def period(
    first_day: Annotated[date, Query(alias="from")],
    last_day: Annotated[date, Query(alias="to")],
) -> Period:
    """The days the owner picked, both included."""
    if first_day > last_day:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, ["Период: начало позже конца"])
    if last_day - first_day >= LONGEST_PERIOD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, ["Период: не больше 366 дней"])
    return Period(first_day, last_day)


ReportPeriod = Annotated[Period, Depends(period)]


def _report(session: Session, club: Club, shown: Period) -> ClubReport:
    starts_at = _midnight(shown.first_day)
    ends_at = _midnight(shown.last_day + timedelta(days=1))
    in_period = (
        Tournament.club_id == club.id,
        Tournament.starts_at >= starts_at,
        Tournament.starts_at < ends_at,
    )
    transactions = session.scalars(
        select(Transaction)
        .join(Tournament, Tournament.id == Transaction.tournament_id)
        .where(*in_period)
        .order_by(Transaction.id)
    ).all()
    # Each tournament held, and the players who came to it: checked in, as a late seat does too.
    held = session.execute(
        select(Tournament.starts_at, func.count(Registration.checked_in_at))
        .outerjoin(Registration, Registration.tournament_id == Tournament.id)
        .where(*in_period, Tournament.status.in_(HELD))
        .group_by(Tournament.id)
    ).all()
    standings = club_standings(session, club.id, starts_at, ends_at)
    return ClubReport(
        finances=Finances(
            tournaments=len(held),
            by_kind=kind_totals(transactions),
            by_method=method_totals(transactions),
            total=sum(t.amount for t in transactions),
        ),
        attendance=_attendance(shown, [(start, came) for start, came in held]),
        top_by_points=standings[:TOP],
        top_by_tournaments=_by_tournaments(standings)[:TOP],
    )


@router.get("/reports")
def club_report(club: OwnerClub, session: DbSession, shown: ReportPeriod) -> ClubReport:
    return _report(session, club, shown)


@router.get("/reports.csv")
def export_club_report(club: OwnerClub, session: DbSession, shown: ReportPeriod) -> Response:
    filename = f"otchet-{shown.first_day.isoformat()}-{shown.last_day.isoformat()}.csv"
    return Response(
        content=BOM + _csv(club, shown, _report(session, club, shown)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _day(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _date_range(first_day: date, last_day: date) -> str:
    return f"{_day(first_day)} – {_day(last_day)}"


def _csv(club: Club, shown: Period, report: ClubReport) -> str:
    """The report as one table for Excel, section by section, as the cashier's export is
    (app/cashier.py): semicolons, and a decimal comma, as a Russian Excel expects."""
    out = StringIO()
    writer = csv.writer(out, delimiter=";")
    finances, attendance = report.finances, report.attendance
    writer.writerow([
        f"Отчёт клуба «{club.name}» за {_date_range(shown.first_day, shown.last_day)}"
    ])
    writer.writerow([])
    writer.writerow(["Финансы"])
    writer.writerow(["Турниров проведено", finances.tournaments])
    writer.writerow(["Операция", "Операций", "Сумма"])
    for kind in finances.by_kind:
        writer.writerow([KIND_NAMES[kind.kind], kind.count, kind.amount])
    for method in finances.by_method:
        writer.writerow([METHOD_NAMES[method.payment_method], "", method.amount])
    writer.writerow(["Всего", "", finances.total])
    writer.writerow([])
    writer.writerow(["Посещаемость"])
    writer.writerow(["Неделя", "Турниров", "Участников"])
    for week in attendance.weeks:
        writer.writerow([_date_range(week.first_day, week.last_day), week.tournaments, week.participants])
    writer.writerow(["Всего", finances.tournaments, attendance.participants])
    average = attendance.average_players
    writer.writerow([
        "Среднее число игроков на турнир",
        "" if average is None else f"{average:.1f}".replace(".", ","),
    ])
    _best_players(writer, "Лучшие игроки по очкам", report.top_by_points, by_points=True)
    _best_players(writer, "Лучшие игроки по числу турниров", report.top_by_tournaments, by_points=False)
    return out.getvalue()


def _best_players(writer: Any, title: str, rows: list[RatingRow], by_points: bool) -> None:
    """A list of the best players, the column they are ranked by first after the name."""
    writer.writerow([])
    writer.writerow([title])
    columns = ["Очки", "Турниров"] if by_points else ["Турниров", "Очки"]
    writer.writerow(["Место", "Игрок", *columns])
    for row in rows:
        values = [row.points, row.tournaments] if by_points else [row.tournaments, row.points]
        writer.writerow([row.position, excel_text(row.player.name), *values])
