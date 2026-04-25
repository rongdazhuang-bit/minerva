"""sys_dict workspace scope + sys_dict_item FKs and uniques

Revision ID: f8a2c9b01e77
Revises: d91e4f2a8c00
Create Date: 2026-04-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a2c9b01e77"
down_revision: Union[str, Sequence[str], None] = "d91e4f2a8c00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM sys_dict_item si WHERE NOT EXISTS "
            "(SELECT 1 FROM sys_dict d WHERE d.id = si.dict_uuid)"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM sys_dict_item WHERE dict_uuid IN "
            "(SELECT id FROM sys_dict WHERE workspace_id IS NULL)"
        )
    )
    op.execute(sa.text("DELETE FROM sys_dict WHERE workspace_id IS NULL"))

    op.execute(
        sa.text(
            "UPDATE sys_dict_item si SET parent_uuid = NULL WHERE parent_uuid IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM sys_dict_item p WHERE p.id = si.parent_uuid "
            "AND p.dict_uuid = si.dict_uuid)"
        )
    )

    op.drop_constraint("sys_dict_unique", "sys_dict", type_="unique")

    op.create_foreign_key(
        "sys_dict_workspace_id_fkey",
        "sys_dict",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("sys_dict", "workspace_id", existing_type=sa.UUID(), nullable=False)

    op.create_unique_constraint(
        "uq_sys_dict_workspace_dict_code",
        "sys_dict",
        ["workspace_id", "dict_code"],
    )

    op.create_foreign_key(
        "sys_dict_item_dict_uuid_fkey",
        "sys_dict_item",
        "sys_dict",
        ["dict_uuid"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "sys_dict_item_parent_uuid_fkey",
        "sys_dict_item",
        "sys_dict_item",
        ["parent_uuid"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_sys_dict_item_dict_code",
        "sys_dict_item",
        ["dict_uuid", "code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sys_dict_item_dict_code", "sys_dict_item", type_="unique")
    op.drop_constraint("sys_dict_item_parent_uuid_fkey", "sys_dict_item", type_="foreignkey")
    op.drop_constraint("sys_dict_item_dict_uuid_fkey", "sys_dict_item", type_="foreignkey")

    op.drop_constraint("uq_sys_dict_workspace_dict_code", "sys_dict", type_="unique")
    op.drop_constraint("sys_dict_workspace_id_fkey", "sys_dict", type_="foreignkey")
    op.alter_column("sys_dict", "workspace_id", existing_type=sa.UUID(), nullable=True)
    op.create_unique_constraint("sys_dict_unique", "sys_dict", ["dict_code"])
