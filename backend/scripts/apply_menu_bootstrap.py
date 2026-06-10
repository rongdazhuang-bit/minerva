"""Apply sys_menu patch/seed and super-admin for rongda@yeah.net (one-off ops)."""

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
        root / "sql" / "patches" / "2026-06-10-sys-menu.sql",
        root / "sql" / "patches" / "2026-06-10-users-super-admin.sql",
        root / "sql" / "seeds" / "sys_menu_seed.sql",
        root / "sql" / "seeds" / "super_admin_rongda.sql",
    ]
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for path in files:
                print(f"Applying {path.name}...")
                cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("SELECT count(*) FROM sys_menu")
            menu_count = cur.fetchone()[0]
            print(f"OK: sys_menu rows={menu_count}")
            cur.execute(
                "SELECT email, is_super_admin FROM users WHERE lower(email)=lower(%s)",
                (EMAIL,),
            )
            user = cur.fetchone()
            if user is None:
                print(f"WARN: user {EMAIL} not found — register first, then re-run.")
                return 1
            print(f"OK: {user[0]} is_super_admin={user[1]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
