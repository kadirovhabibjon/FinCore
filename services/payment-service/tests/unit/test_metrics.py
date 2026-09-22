import uuid

from fincore_common import EventType

from app.core.metrics import PAYMENTS_TOTAL, TRANSFERS_TOTAL
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.services.payments import payment_outbox_event
from app.services.transfers import _transfer_outbox_event


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def test_building_a_transfer_outbox_event_increments_the_counter_for_its_status() -> None:
    before = _counter_value(TRANSFERS_TOTAL, status=TransferStatus.COMPLETED.value)
    transfer = Transfer(
        initiator_user_id=uuid.uuid4(),
        source_wallet_id=uuid.uuid4(),
        destination_wallet_id=uuid.uuid4(),
        amount_minor=100_00,
        currency="UZS",
    )

    _transfer_outbox_event(transfer, EventType.TRANSFER_COMPLETED, status=TransferStatus.COMPLETED)

    assert _counter_value(TRANSFERS_TOTAL, status=TransferStatus.COMPLETED.value) == before + 1


def test_building_a_payment_outbox_event_increments_the_counter_for_its_status() -> None:
    before = _counter_value(PAYMENTS_TOTAL, status=PaymentStatus.FAILED.value)
    payment = Payment(
        initiator_user_id=uuid.uuid4(),
        source_wallet_id=uuid.uuid4(),
        merchant_id=uuid.uuid4(),
        amount_minor=250_00,
        currency="UZS",
    )

    payment_outbox_event(
        payment, EventType.PAYMENT_FAILED, status=PaymentStatus.FAILED, failure_reason="blocked"
    )

    assert _counter_value(PAYMENTS_TOTAL, status=PaymentStatus.FAILED.value) == before + 1
