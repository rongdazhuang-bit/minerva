"""Apply super-admin patch and seed for rongda@yeah.net (one-off ops script)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2

EMAIL = "rongda@yeah.net"


def main() -> int:
    url = os.getenv(
        "SYNC_DATABASE_URL",
        "postgresql://postgres:KnWhMG4C4aDGTrE6@127.0.0.1:55432/minerva",
    )
    root = Path(__file__).resolve().parents[1]
    files = [
        root / "sql" / "patches" / "2026-06-11-rename-sys-identity-tables.sql",
        root / "sql" / "patches" / "2026-06-10-users-super-admin.sql",
        root / "sql" / "seeds" / "super_admin_rongda.sql",
    ]
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for path in files:
                cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(
                "SELECT email, is_super_admin FROM sys_users WHERE lower(email)=lower(%s)",
                (EMAIL,),
            )
            user = cur.fetchone()
            if user is None:
                print(f"WARN: user {EMAIL} not found — register first, then re-run this script.")
                return 1
            print(f"OK: {user[0]} is_super_admin={user[1]}")
            cur.execute(
                """
                SELECT tm.role::text
                FROM sys_tenant_memberships tm
                JOIN sys_users u ON u.id = tm.user_id
                WHERE lower(u.email)=lower(%s)
                """,
                (EMAIL,),
            )
            print("tenant roles:", [r[0] for r in cur.fetchall()])
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
