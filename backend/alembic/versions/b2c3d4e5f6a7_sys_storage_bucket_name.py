"""sys_storage: bucket_name (S3 bucket), name is display label

Revision ID: b2c3d4e5f6a7
Revises: e2f3a4b5c6d7
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # S3 object bucket; legacy rows used ``name`` for this — copy into bucket_name.
    op.add_column(
        "sys_storage",
        sa.Column("bucket_name", sa.String(length=63), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE sys_storage
            SET bucket_name = TRIM(BOTH FROM name)
            WHERE bucket_name IS NULL
              AND name IS NOT NULL
              AND TRIM(BOTH FROM name) <> ''
            """
        )
    )


def downgrade() -> None:
    op.drop_column("sys_storage", "bucket_name")
