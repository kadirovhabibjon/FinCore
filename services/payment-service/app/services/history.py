"""Narrowing a customer's history: by kind of operation, by direction,
by date, and by words (a reference, a note, the other side's name).

Each operation type lives in its own table, so a filter becomes extra
conditions for each table's own query - or the knowledge that a table
has nothing to contribute (payments are never "received").
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_

from app.api.v1.schemas import TransactionDirection, TransactionType
from app.domain.exchange import Exchange
from app.domain.payment import Payment
from app.domain.transfer import Transfer

Conditions = Sequence[Any]


@dataclass(frozen=True)
class HistoryFilter:
    type: TransactionType | None = None
    direction: TransactionDirection | None = None
    # Words to find, as typed.
    q: str | None = None
    # Calendar days in UTC, both included.
    date_from: date | None = None
    date_to: date | None = None

    @property
    def words(self) -> str | None:
        text = (self.q or "").strip()
        return text or None


def _contains(column: Any, words: str) -> Any:
    """`column` contains `words`, whatever the case; the customer's
    text is matched as text, never as a pattern."""
    escaped = words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _dated(model: Any, wanted: HistoryFilter) -> list[Any]:
    conditions = []
    if wanted.date_from is not None:
        conditions.append(model.created_at >= datetime.combine(wanted.date_from, time.min, UTC))
    if wanted.date_to is not None:
        conditions.append(
            model.created_at < datetime.combine(wanted.date_to + timedelta(days=1), time.min, UTC)
        )
    return conditions


def for_transfers(wanted: HistoryFilter, user_id: UUID) -> Conditions | None:
    """Extra conditions for the caller's transfers, or None when no
    transfer can match."""
    if wanted.type not in (None, TransactionType.TRANSFER):
        return None
    if wanted.direction is TransactionDirection.SELF:
        return None
    conditions = _dated(Transfer, wanted)
    sent = Transfer.initiator_user_id == user_id
    received = Transfer.initiator_user_id != user_id
    if wanted.direction is TransactionDirection.OUT:
        conditions.append(sent)
    elif wanted.direction is TransactionDirection.IN:
        conditions.append(received)
    if wanted.words:
        conditions.append(
            or_(
                _contains(Transfer.reference, wanted.words),
                _contains(Transfer.description, wanted.words),
                # The other side's name: who it went to, or who it came from.
                and_(sent, _contains(Transfer.recipient_name, wanted.words)),
                and_(received, _contains(Transfer.sender_name, wanted.words)),
            )
        )
    return conditions


def for_payments(wanted: HistoryFilter) -> Conditions | None:
    if wanted.type not in (None, TransactionType.PAYMENT):
        return None
    # A payment is always money the caller paid out.
    if wanted.direction not in (None, TransactionDirection.OUT):
        return None
    conditions = _dated(Payment, wanted)
    if wanted.words:
        conditions.append(
            or_(
                _contains(Payment.reference, wanted.words),
                _contains(Payment.description, wanted.words),
                _contains(Payment.merchant_name, wanted.words),
                _contains(Payment.service_account, wanted.words),
            )
        )
    return conditions


def for_exchanges(wanted: HistoryFilter) -> Conditions | None:
    if wanted.type not in (None, TransactionType.EXCHANGE):
        return None
    if wanted.direction not in (None, TransactionDirection.SELF):
        return None
    conditions = _dated(Exchange, wanted)
    if wanted.words:
        conditions.append(_contains(Exchange.reference, wanted.words))
    return conditions
