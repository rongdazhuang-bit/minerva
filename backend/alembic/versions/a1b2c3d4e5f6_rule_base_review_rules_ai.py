"""rule_base: review_rules_ai column

Revision ID: a1b2c3d4e5f6
Revises: 8c2e4f1a0b3d
Create Date: 2026-04-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "8c2e4f1a0b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rule_base",
        sa.Column("review_rules_ai", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rule_base", "review_rules_ai")
