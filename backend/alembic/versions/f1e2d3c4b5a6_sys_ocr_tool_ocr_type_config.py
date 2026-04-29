"""sys_ocr_tool: ocr_type and ocr_config

Revision ID: f1e2d3c4b5a6
Revises: d4e5f6a7b8c9
Create Date: 2026-04-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sys_ocr_tool",
        sa.Column("ocr_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "sys_ocr_tool",
        sa.Column("ocr_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sys_ocr_tool", "ocr_config")
    op.drop_column("sys_ocr_tool", "ocr_type")
