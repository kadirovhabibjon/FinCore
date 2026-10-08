"""add service payments

Revision ID: b7d2e9f4a1c6
Revises: a1f4c8e2b6d9
Create Date: 2026-10-08 13:00:00.000000

Paying service providers (mobile, internet, utilities, TV). Each is a
merchant that belongs to FinCore rather than a customer; a payment to
one records which provider and which account it was for.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e9f4a1c6'
down_revision: Union[str, None] = 'a1f4c8e2b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A snapshot of app/services/billers.py as it was when this was written
# (ids are uuid5 of each provider's code): a migration must keep doing
# the same thing even if the catalogue changes later.
_SYSTEM_OWNER_ID = '00000000-0000-4000-8000-00000000b111'
_PROVIDERS = [
    ('726d4bfd-db8c-5d8e-8d29-b3e03d363f85', 'Beeline'),
    ('b112013d-4127-5820-bda0-7a0a58eef046', 'Ucell'),
    ('873ac6b3-91a3-5b14-a575-6931ef8d3d54', 'Uzmobile'),
    ('825f206c-c090-5987-83c9-90db3b0aba23', 'Mobiuz'),
    ('78691d0f-e5e3-5cf0-9410-820ed86ca12c', 'Humans'),
    ('4fad26bf-da43-52ca-b2a2-64234265d7af', 'Uzonline'),
    ('82aac766-16ad-5c1d-b2d8-8c975083db77', 'Turon Telecom'),
    ('dcaa851a-e52e-58b8-9c2f-05bc2123f1fb', 'Sarkor Telecom'),
    ('7b709619-69dd-5918-a26d-da24dfa20560', 'Comnet'),
    ('fa8bd45c-a900-51af-bc52-f7c2e20ab6c3', 'Electricity'),
    ('38677b34-c20b-510c-b31f-71d680d1a820', 'Natural gas'),
    ('d3d1e4d8-323f-53cb-ab83-de1209f3ecf4', 'Cold water'),
    ('a3144de7-12b7-5b57-89d6-228d8923bb1b', 'Heating and hot water'),
    ('659a012b-e01b-55d4-a09f-678a9d5536d8', 'Waste collection'),
    ('2e07534a-df3b-585d-b383-6006c684356e', 'Uzdigital TV'),
]


def upgrade() -> None:
    op.add_column('payments', sa.Column('service_code', sa.String(length=32), nullable=True))
    op.add_column('payments', sa.Column('service_account', sa.String(length=64), nullable=True))
    op.create_check_constraint(
        'ck_payments_service_code_and_account_together',
        'payments',
        '(service_code IS NULL) = (service_account IS NULL)',
    )
    for merchant_id, name in _PROVIDERS:
        op.execute(
            sa.text(
                "INSERT INTO merchants (id, owner_user_id, name, status) "
                "VALUES (CAST(:id AS uuid), CAST(:owner AS uuid), :name, 'ACTIVE')"
            ).bindparams(id=merchant_id, owner=_SYSTEM_OWNER_ID, name=name)
        )


def downgrade() -> None:
    # A database without service payments: the payments made to the
    # providers go with them, as other downgrades drop their tables
    # whole. A development rollback, not for real money.
    op.execute(
        sa.text(
            "DELETE FROM refunds WHERE payment_id IN (SELECT p.id FROM payments p "
            "JOIN merchants m ON m.id = p.merchant_id WHERE m.owner_user_id = CAST(:owner AS uuid))"
        ).bindparams(owner=_SYSTEM_OWNER_ID)
    )
    op.execute(
        sa.text(
            "DELETE FROM payments WHERE merchant_id IN "
            "(SELECT id FROM merchants WHERE owner_user_id = CAST(:owner AS uuid))"
        ).bindparams(owner=_SYSTEM_OWNER_ID)
    )
    op.execute(
        sa.text(
            "DELETE FROM merchants WHERE owner_user_id = CAST(:owner AS uuid)"
        ).bindparams(
            owner=_SYSTEM_OWNER_ID
        )
    )
    op.drop_constraint('ck_payments_service_code_and_account_together', 'payments')
    op.drop_column('payments', 'service_account')
    op.drop_column('payments', 'service_code')
