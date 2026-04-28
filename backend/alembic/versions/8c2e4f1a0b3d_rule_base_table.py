"""rule_base table

Revision ID: 8c2e4f1a0b3d
Revises: f8a2c9b01e77
Create Date: 2026-04-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8c2e4f1a0b3d"
down_revision: Union[str, Sequence[str], None] = "f8a2c9b01e77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rule_base",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("sequence_number", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("subject_code", sa.String(length=64), nullable=True),
        sa.Column("serial_number", sa.String(length=32), nullable=True),
        sa.Column("document_type", sa.String(length=64), nullable=True),
        sa.Column("review_section", sa.String(length=128), nullable=False),
        sa.Column("review_object", sa.String(length=128), nullable=False),
        sa.Column("review_rules", sa.Text(), nullable=False),
        sa.Column("review_result", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="rule_base_pk"),
    )
    op.create_index(
        op.f("ix_rule_base_workspace_id"),
        "rule_base",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_base_workspace_id"), table_name="rule_base")
    op.drop_table("rule_base")
