"""rule_config_prompt table and scope unique index

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rule_config_prompt",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("engineering_code", sa.String(length=64), nullable=True),
        sa.Column("subject_code", sa.String(length=64), nullable=True),
        sa.Column("document_type", sa.String(length=64), nullable=True),
        sa.Column("sys_prompt", sa.String(length=1024), nullable=True),
        sa.Column("user_prompt", sa.Text(), nullable=True),
        sa.Column("chat_memory", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["sys_models.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="rule_config_prompt_pkey"),
    )
    op.create_index(
        op.f("ix_rule_config_prompt_workspace_id"),
        "rule_config_prompt",
        ["workspace_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_rule_config_prompt_workspace_scope
        ON rule_config_prompt (
            workspace_id,
            coalesce(engineering_code, ''),
            coalesce(subject_code, ''),
            coalesce(document_type, '')
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rule_config_prompt_workspace_scope")
    op.drop_index(
        op.f("ix_rule_config_prompt_workspace_id"), table_name="rule_config_prompt"
    )
    op.drop_table("rule_config_prompt")
