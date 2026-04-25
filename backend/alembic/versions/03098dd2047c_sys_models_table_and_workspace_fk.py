"""sys_models table and workspace fk

Revision ID: 03098dd2047c
Revises: f8a2c9b01e77
Create Date: 2026-04-25 23:49:29.367695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03098dd2047c'
down_revision: Union[str, Sequence[str], None] = 'f8a2c9b01e77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATED_SYS_MODELS_IN_THIS_MIGRATION = False


def upgrade() -> None:
    """Upgrade schema."""
    global _CREATED_SYS_MODELS_IN_THIS_MIGRATION
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("sys_models"):
        op.create_table(
            "sys_models",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("workspace_id", sa.UUID(), nullable=False),
            sa.Column("provider_name", sa.String(length=128), nullable=False),
            sa.Column("model_name", sa.String(length=128), nullable=False),
            sa.Column("model_type", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column(
                "load_balancing_enabled",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("auth_type", sa.String(length=64), nullable=False),
            sa.Column("endpoint_url", sa.String(length=128), nullable=True),
            sa.Column("api_key", sa.String(length=128), nullable=True),
            sa.Column("auth_name", sa.String(length=64), nullable=True),
            sa.Column("auth_passwd", sa.String(length=128), nullable=True),
            sa.Column("context_size", sa.SmallInteger(), nullable=True),
            sa.Column("max_tokens_to_sample", sa.SmallInteger(), nullable=True),
            sa.Column("model_config", sa.Text(), nullable=True),
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
                name="sys_models_workspace_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id", name="sys_models_pk"),
        )
        op.create_index(
            op.f("ix_sys_models_workspace_id"),
            "sys_models",
            ["workspace_id"],
            unique=False,
        )
        _CREATED_SYS_MODELS_IN_THIS_MIGRATION = True
        return

    # Table already exists (created outside Alembic / manual SQL); ensure FK + index.
    op.execute(
        sa.text(
            "DO $$ "
            "BEGIN "
            "IF NOT EXISTS ("
            "  SELECT 1 FROM pg_constraint"
            "  WHERE conname = 'sys_models_workspace_id_fkey'"
            ") THEN"
            "  ALTER TABLE sys_models"
            "    ADD CONSTRAINT sys_models_workspace_id_fkey"
            "    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;"
            "END IF;"
            "END $$;"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_sys_models_workspace_id ON sys_models (workspace_id);"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _CREATED_SYS_MODELS_IN_THIS_MIGRATION and insp.has_table("sys_models"):
        op.drop_index(op.f("ix_sys_models_workspace_id"), table_name="sys_models")
        op.drop_table("sys_models")
        return

    if insp.has_table("sys_models"):
        op.execute(
            sa.text("DROP INDEX IF EXISTS ix_sys_models_workspace_id")
        )
        op.execute(
            sa.text("ALTER TABLE sys_models DROP CONSTRAINT IF EXISTS sys_models_workspace_id_fkey")
        )
