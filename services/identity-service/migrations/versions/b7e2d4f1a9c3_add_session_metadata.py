"""add session metadata (user agent, ip address, last used)

Revision ID: b7e2d4f1a9c3
Revises: 60d7bf424217
Create Date: 2026-09-28 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f1a9c3'
down_revision: Union[str, None] = '60d7bf424217'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('user_agent', sa.String(length=255), nullable=True))
    op.add_column('sessions', sa.Column('ip_address', sa.String(length=64), nullable=True))
    op.add_column('sessions', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'last_used_at')
    op.drop_column('sessions', 'ip_address')
    op.drop_column('sessions', 'user_agent')
