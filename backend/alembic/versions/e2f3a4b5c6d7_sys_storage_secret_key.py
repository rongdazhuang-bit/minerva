"""sys_storage: secret_key for API_KEY auth

Revision ID: e2f3a4b5c6d7
Revises: f1e2d3c4b5a6
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pair with api_key for S3-style access key + secret; nullable for legacy rows.
    op.add_column(
        "sys_storage",
        sa.Column("secret_key", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sys_storage", "secret_key")
