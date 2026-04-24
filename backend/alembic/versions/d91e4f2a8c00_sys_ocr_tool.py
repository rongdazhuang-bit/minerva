"""sys_ocr_tool with workspace_id

Revision ID: d91e4f2a8c00
Revises: c4f8a91b2d10
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d91e4f2a8c00"
down_revision: Union[str, Sequence[str], None] = "c4f8a91b2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_ocr_tool",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=128), nullable=False),
        sa.Column("auth_type", sa.String(length=64), nullable=True),
        sa.Column("user_name", sa.String(length=64), nullable=True),
        sa.Column("user_passwd", sa.String(length=128), nullable=True),
        sa.Column("api_key", sa.String(length=128), nullable=True),
        sa.Column("remark", sa.String(length=128), nullable=True),
        sa.Column(
            "create_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("update_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="sys_ocr_tool_pk"),
    )
    op.create_index(
        op.f("ix_sys_ocr_tool_workspace_id"),
        "sys_ocr_tool",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_ocr_tool_workspace_id"), table_name="sys_ocr_tool")
    op.drop_table("sys_ocr_tool")
