"""The tournament cashier: what has been paid for the tournament, by kind of operation and by
payment method, with every transaction in the history. Transactions are recorded as players pay
(app/transactions.py). This is sport poker, so money only comes in, for the table and the
dealer: there are no prizes to pay out.

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003)."""

import csv
from collections.abc import Sequence
from datetime import datetime
from io import StringIO
from typing import cast, get_args

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAdmin, DbSession, Now
from app.clubs import AdminClub
from app.models import Tournament, Transaction
from app.schemas import (
    AdminOut,
    Cashier,
    KindTotal,
    MethodTotal,
    PaymentMethod,
    PaymentMethodIn,
    PlayerOut,
    TransactionKind,
    TransactionOut,
)
from app.seasons import LEAGUE_TIME
from app.tournaments import club_tournament
from app.transactions import pay_again, reverse

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}")

PAID_BY = {"cash": "наличными", "card": "картой"}
KIND_NAMES = {"buy_in": "Бай-ин", "reentry": "Re-entry", "addon": "Add-on"}
METHOD_NAMES = {"cash": "Наличные", "card": "Карта"}
# The byte order mark tells Excel the file is in UTF-8.
BOM = "﻿"


def _transactions(session: Session, tournament: Tournament) -> list[Transaction]:
    return list(
        session.scalars(
            select(Transaction)
            .where(Transaction.tournament_id == tournament.id)
            .order_by(Transaction.id)
        ).all()
    )


def _reversed_by(transactions: Sequence[Transaction]) -> dict[int, int]:
    """The storno of each reversed transaction, by the id of the one it reverses."""
    return {t.reverses_id: t.id for t in transactions if t.reverses_id is not None}


def _transaction_out(transaction: Transaction, reversed_by: dict[int, int]) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        created_at=transaction.created_at,
        kind=cast(TransactionKind, transaction.kind),
        amount=transaction.amount,
        payment_method=cast(PaymentMethod, transaction.payment_method),
        player=PlayerOut.model_validate(transaction.player),
        admin=AdminOut.model_validate(transaction.admin),
        reverses_id=transaction.reverses_id,
        replaces_id=transaction.replaces_id,
        reversed_by_id=reversed_by.get(transaction.id),
    )


def kind_totals(transactions: Sequence[Transaction]) -> list[KindTotal]:
    """What came in for each kind of operation, and how many operations stand: neither a storno
    nor reversed by one. The owner's reports (app/reports.py) add up a period's the same way."""
    reversed_by = _reversed_by(transactions)
    standing = [t for t in transactions if t.reverses_id is None and t.id not in reversed_by]
    return [
        KindTotal(
            kind=kind,
            count=sum(t.kind == kind for t in standing),
            amount=sum(t.amount for t in transactions if t.kind == kind),
        )
        for kind in get_args(TransactionKind)
    ]


def method_totals(transactions: Sequence[Transaction]) -> list[MethodTotal]:
    return [
        MethodTotal(
            payment_method=method,
            amount=sum(t.amount for t in transactions if t.payment_method == method),
        )
        for method in get_args(PaymentMethod)
    ]


def _cashier(transactions: Sequence[Transaction]) -> Cashier:
    reversed_by = _reversed_by(transactions)
    return Cashier(
        by_kind=kind_totals(transactions),
        by_method=method_totals(transactions),
        total=sum(t.amount for t in transactions),
        transactions=[_transaction_out(t, reversed_by) for t in transactions],
    )


@router.get("/cashier")
def get_cashier(tournament_id: int, club: AdminClub, session: DbSession) -> Cashier:
    return _cashier(_transactions(session, club_tournament(session, club, tournament_id)))


@router.get("/cashier.csv")
def export_cashier(tournament_id: int, club: AdminClub, session: DbSession) -> Response:
    tournament = club_tournament(session, club, tournament_id)
    return Response(
        content=BOM + _csv(tournament, _cashier(_transactions(session, tournament))),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="kassa-{tournament.id}.csv"'},
    )


def _local(moment: datetime) -> str:
    """In the league's time, as the clubs' clocks show it (app/seasons.py)."""
    return moment.astimezone(LEAGUE_TIME).strftime("%d.%m.%Y %H:%M")


def _note(transaction: TransactionOut) -> str:
    notes = []
    if transaction.reverses_id is not None:
        notes.append(f"Сторно операции № {transaction.reverses_id}")
    if transaction.replaces_id is not None:
        notes.append(f"Взамен операции № {transaction.replaces_id}")
    if transaction.reversed_by_id is not None:
        notes.append(f"Сторнирована операцией № {transaction.reversed_by_id}")
    return "; ".join(notes)


def excel_text(value: str) -> str:
    """Text as Excel shows it, never as a formula: a name such as "=HYPERLINK(...)", which
    a player could give, would otherwise be run when the file is opened."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def _csv(tournament: Tournament, cashier: Cashier) -> str:
    """The history and the summary as one table, for Excel: semicolons, as a Russian Excel
    expects, and no phone numbers, which the accounts do not need."""
    out = StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow([f"Касса турнира «{tournament.name}», начало {_local(tournament.starts_at)}"])
    writer.writerow([])
    writer.writerow(
        ["№", "Время", "Операция", "Игрок", "Способ оплаты", "Сумма", "Администратор", "Примечание"]
    )
    for t in cashier.transactions:
        writer.writerow([
            t.id,
            _local(t.created_at),
            KIND_NAMES[t.kind],
            excel_text(t.player.name),
            METHOD_NAMES[t.payment_method],
            t.amount,
            excel_text(t.admin.name),
            _note(t),
        ])
    writer.writerow([])
    writer.writerow(["Итог", "Операций", "Сумма"])
    for kind in cashier.by_kind:
        writer.writerow([KIND_NAMES[kind.kind], kind.count, kind.amount])
    for method in cashier.by_method:
        writer.writerow([METHOD_NAMES[method.payment_method], "", method.amount])
    writer.writerow(["Всего", "", cashier.total])
    return out.getvalue()


def _reversible(transactions: Sequence[Transaction], transaction_id: int) -> Transaction:
    transaction = next((t for t in transactions if t.id == transaction_id), None)
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Операция не найдена")
    if transaction.reverses_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сторно не сторнируют")
    if transaction.id in _reversed_by(transactions):
        raise HTTPException(status.HTTP_409_CONFLICT, "Операция уже сторнирована")
    return transaction


@router.post("/cashier/transactions/{transaction_id}/reverse")
def reverse_transaction(
    tournament_id: int,
    transaction_id: int,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> Cashier:
    """Reverses a mistaken transaction by a storno: the money was given back, or never taken.
    The game is not changed: a mistaken knock-out, for one, is undone in the game."""
    # Locked, so that two admins cannot reverse the same transaction at once.
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    transaction = _reversible(_transactions(session, tournament), transaction_id)
    reverse(session, tournament, transaction, admin, now)
    session.commit()
    return _cashier(_transactions(session, tournament))


@router.post("/cashier/transactions/{transaction_id}/payment-method")
def change_payment_method(
    tournament_id: int,
    transaction_id: int,
    body: PaymentMethodIn,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> Cashier:
    """Puts right a payment taken the wrong way, cash for card or card for cash: a storno of it,
    and the same payment taken again the other way."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    transaction = _reversible(_transactions(session, tournament), transaction_id)
    if transaction.payment_method == body.payment_method:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Операция и так оплачена {PAID_BY[body.payment_method]}"
        )
    pay_again(session, tournament, transaction, body.payment_method, admin, now)
    session.commit()
    return _cashier(_transactions(session, tournament))
