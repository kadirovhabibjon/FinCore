"""normalize stored phone numbers to their canonical form

Revision ID: e8a1c4f7b2d9
Revises: d3f9a2c8e1b4
Create Date: 2026-10-02 18:00:00.000000

Phones used to be stored as typed ("917807722", "+998 90 ..."); sign-in by
phone compares canonical forms ("+998901234567", app/core/phone.py), so
existing rows are rewritten once. A row is left as it was when its number
can't be normalized or when the canonical form already belongs to another
account (the UNIQUE constraint decides, never a silent merge).

The rules are copied here rather than imported: a migration must keep
meaning what it meant when it ran, whatever app code later becomes.
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8a1c4f7b2d9"
down_revision: str | None = "d3f9a2c8e1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _canonical(raw: str) -> str | None:
    text = raw.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9:
        digits = "998" + digits
    if digits.startswith("998") and len(digits) != 12:
        return None
    if not 8 <= len(digits) <= 15:
        return None
    return f"+{digits}"


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, phone FROM users")).fetchall()
    taken = {phone for _, phone in rows}
    for user_id, phone in rows:
        canonical = _canonical(phone)
        if canonical is None or canonical == phone or canonical in taken:
            continue
        connection.execute(
            sa.text("UPDATE users SET phone = :phone WHERE id = :id"),
            {"phone": canonical, "id": user_id},
        )
        taken.discard(phone)
        taken.add(canonical)


def downgrade() -> None:
    # Only the formatting changed; the original spelling isn't kept and
    # isn't needed by older code (it compared phones exactly as stored).
    pass
