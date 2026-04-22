"""rules v1

Revision ID: 947e36be8860
Revises: 3552a1daa5cc
Create Date: 2026-04-22 17:18:42.834808

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "947e36be8860"
down_revision: Union[str, Sequence[str], None] = "3552a1daa5cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("current_published_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rules_workspace_id"), "rules", ["workspace_id"], unique=False
    )
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("flow_schema_version", sa.Integer(), nullable=False),
        sa.Column("flow_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["rules.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "version", name="uq_rule_version_num"),
    )
    op.create_index(
        op.f("ix_rule_versions_rule_id"), "rule_versions", ["rule_id"], unique=False
    )
    op.create_foreign_key(
        "fk_rules_current_published_version_id",
        "rules",
        "rule_versions",
        ["current_published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_rules_current_published_version_id", "rules", type_="foreignkey")
    op.drop_index(op.f("ix_rule_versions_rule_id"), table_name="rule_versions")
    op.drop_table("rule_versions")
    op.drop_index(op.f("ix_rules_workspace_id"), table_name="rules")
    op.drop_table("rules")
