"""Recording a tournament's transactions as players pay, and reversing them. The cashier's API,
with its summary, lives in app/cashier.py.

Every buy-in, re-entry and add-on is a transaction, paid in cash or by card and taken by an
admin. Transactions are only ever added: a mistaken one is reversed by a storno, a transaction
of the opposite amount that points at it, so the original stays in the history."""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Admin, Tournament, Transaction
from app.schemas import PaymentIn, PaymentMethod, TransactionKind


def price(tournament: Tournament, kind: TransactionKind) -> int:
    """What the operation costs by the tournament's rules: a re-entry buys the player in again."""
    if kind == "addon":
        return tournament.addon_price or 0
    return tournament.buy_in


def _add(
    session: Session,
    tournament: Tournament,
    player_id: int,
    kind: str,
    amount: int,
    payment_method: str,
    admin: Admin,
    now: datetime,
    *,
    reverses: Transaction | None = None,
    replaces: Transaction | None = None,
) -> None:
    session.add(
        Transaction(
            club_id=tournament.club_id,
            tournament_id=tournament.id,
            player_id=player_id,
            admin_id=admin.id,
            kind=kind,
            amount=amount,
            payment_method=payment_method,
            created_at=now,
            reverses_id=None if reverses is None else reverses.id,
            replaces_id=None if replaces is None else replaces.id,
        )
    )


def take_payment(
    session: Session,
    tournament: Tournament,
    player_id: int,
    kind: TransactionKind,
    payment: PaymentIn | None,
    admin: Admin,
    now: datetime,
) -> None:
    """Records the payment for the operation at the tournament's price; nothing when it is free.
    Call it before changing anything, so that a missing payment method refuses the operation."""
    amount = price(tournament, kind)
    if amount == 0:
        return
    if payment is None or payment.payment_method is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ["Укажите способ оплаты: наличные или карта"]
        )
    _add(session, tournament, player_id, kind, amount, payment.payment_method, admin, now)


def reverse(
    session: Session,
    tournament: Tournament,
    transaction: Transaction,
    admin: Admin,
    now: datetime,
) -> None:
    """A storno of the transaction: the same payment with the opposite amount."""
    _add(
        session,
        tournament,
        transaction.player_id,
        transaction.kind,
        -transaction.amount,
        transaction.payment_method,
        admin,
        now,
        reverses=transaction,
    )


def pay_again(
    session: Session,
    tournament: Tournament,
    transaction: Transaction,
    payment_method: PaymentMethod,
    admin: Admin,
    now: datetime,
) -> None:
    """Takes the transaction's payment again, this time the given way; the mistaken one is
    reversed first."""
    reverse(session, tournament, transaction, admin, now)
    _add(
        session,
        tournament,
        transaction.player_id,
        transaction.kind,
        transaction.amount,
        payment_method,
        admin,
        now,
        replaces=transaction,
    )


def give_buy_ins_back(
    session: Session,
    tournament: Tournament,
    admin: Admin,
    now: datetime,
    player_id: int | None = None,
) -> int:
    """Reverses the buy-ins paid for the tournament, or only the player's: they did not come
    after all, they dropped out before the start, or the tournament was cancelled. Returns how
    much is given back: what was paid, whatever the buy-in is now."""
    reversed_ids = select(Transaction.reverses_id).where(Transaction.reverses_id.is_not(None))
    buy_ins = select(Transaction).where(
        Transaction.tournament_id == tournament.id,
        Transaction.kind == "buy_in",
        Transaction.reverses_id.is_(None),
        Transaction.id.not_in(reversed_ids),
    )
    if player_id is not None:
        buy_ins = buy_ins.where(Transaction.player_id == player_id)
    paid = session.scalars(buy_ins).all()
    for buy_in in paid:
        reverse(session, tournament, buy_in, admin, now)
    return sum(buy_in.amount for buy_in in paid)
