"""Unit tests for the SQLite/PostgreSQL adapter.

PostgreSQL is simulated, so this runs without a database server and without
the psycopg package. It checks the differences that matter: placeholder
translation, schema dialect, and the INSERT ... RETURNING id path.

    python storage_test.py
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import types
from pathlib import Path

failures: list[str] = []
checks = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  PASS  {name}")
    else:
        failures.append(name)
        print(f"  FAIL  {name}{(' - ' + detail) if detail else ''}")


VALUES = {
    "created_at": "2026-11-17T09:00:00+00:00",
    "consent": 1,
    "sector": "retail",
    "years": "4to6",
    "employees": "1to9",
    "role": "owner",
    "location": "cbd",
    "channels": '["social"]',
    "answers": '{"A1": 4}',
    "duration_seconds": 600,
    "open_challenge": "Connectivity",
    "needs_software": "yes",
    "software_details": "An online ordering page with M-Pesa checkout.",
}


def test_sqlite() -> None:
    import storage

    tmp = Path(tempfile.mkdtemp(prefix="msme-storage-"))
    path = tmp / "storage.db"
    conn = storage.SQLiteConnection(str(path))
    try:
        storage.init_schema(conn)
        conn.commit()
        response_id = storage.insert_response(conn, VALUES)
        storage.set_code(conn, response_id, f"NK-{response_id:04d}")
        conn.commit()

        check("sqlite: insert returns id 1", response_id == 1, str(response_id))
        row = conn.execute(
            "SELECT * FROM responses WHERE code = ?", ("NK-0001",)
        ).fetchone()
        check("sqlite: row is retrievable by code", row is not None)
        check("sqlite: answers round-trip", row["answers"] == VALUES["answers"])
        check(
            "sqlite: software branch round-trips",
            row["needs_software"] == "yes"
            and row["software_details"] == VALUES["software_details"],
        )
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM responses"
        ).fetchone()["total"]
        check("sqlite: count uses named column", count == 1, str(count))
        check("sqlite: schema uses AUTOINCREMENT", "AUTOINCREMENT" in storage.SQLITE_SCHEMA)
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            (tmp / f"storage.db{suffix}").unlink(missing_ok=True)


def test_sqlite_migration() -> None:
    """A database created before the software question must gain the columns."""
    import storage

    tmp = Path(tempfile.mkdtemp(prefix="msme-migration-"))
    path = tmp / "legacy.db"
    conn = storage.SQLiteConnection(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE responses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                code             TEXT UNIQUE NOT NULL,
                created_at       TEXT NOT NULL,
                consent          INTEGER NOT NULL DEFAULT 0,
                sector           TEXT NOT NULL,
                years            TEXT NOT NULL,
                employees        TEXT NOT NULL,
                role             TEXT NOT NULL,
                location         TEXT NOT NULL,
                channels         TEXT NOT NULL,
                answers          TEXT NOT NULL,
                duration_seconds INTEGER,
                open_challenge   TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO responses "
            "(code, created_at, consent, sector, years, employees, role, "
            " location, channels, answers) "
            "VALUES ('NK-0001', '2026-11-17T09:00:00+00:00', 1, 'retail', "
            "'4to6', '1to9', 'owner', 'cbd', '[\"social\"]', '{\"A1\": 4}')"
        )
        conn.commit()

        storage.init_schema(conn)
        conn.commit()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(responses)").fetchall()
        }
        check(
            "sqlite: migration adds both software columns",
            {"needs_software", "software_details"} <= columns,
            str(sorted(columns)),
        )
        old_row = conn.execute(
            "SELECT * FROM responses WHERE code = ?", ("NK-0001",)
        ).fetchone()
        check(
            "sqlite: existing rows default to no",
            old_row["needs_software"] == "no" and old_row["software_details"] is None,
        )

        # Running startup again must not raise a duplicate-column error.
        storage.init_schema(conn)
        conn.commit()
        new_id = storage.insert_response(conn, VALUES)
        check("sqlite: insert works after migration", new_id == 2, str(new_id))
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            (tmp / f"legacy.db{suffix}").unlink(missing_ok=True)


def test_postgres() -> None:
    # Install a fake driver before importing storage so no package or server
    # is needed. The fake records SQL and returns dict rows like psycopg3.
    fake = types.ModuleType("psycopg")

    class FakeError(Exception):
        pass

    fake.Error = FakeError  # type: ignore[attr-defined]
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()  # type: ignore[attr-defined]
    fake.rows = rows  # type: ignore[attr-defined]

    state: dict = {"url": None, "kwargs": None, "calls": [], "next_id": 7}

    class FakeCursor:
        def __init__(self, return_id=None):
            self._return_id = return_id

        def fetchone(self):
            if self._return_id is not None:
                return {"id": self._return_id}
            return None

    class FakeConnection:
        def execute(self, sql, params=()):
            state["calls"].append((sql, params))
            if "RETURNING id" in sql:
                return FakeCursor(state["next_id"])
            return FakeCursor()

        def commit(self):
            state["calls"].append(("COMMIT", ()))

        def rollback(self):
            state["calls"].append(("ROLLBACK", ()))

        def close(self):
            state["calls"].append(("CLOSE", ()))

    def connect(url, **kwargs):
        state["url"] = url
        state["kwargs"] = kwargs
        return FakeConnection()

    fake.connect = connect  # type: ignore[attr-defined]

    sys.modules["psycopg"] = fake
    sys.modules["psycopg.rows"] = rows

    import storage

    importlib.reload(storage)

    check("postgres: driver detected", storage._PSYCOPG_AVAILABLE)
    check(
        "postgres: driver error is caught",
        FakeError in storage.StorageError,
    )
    check(
        "postgres: postgres:// is normalised",
        storage.normalise_url("postgres://u:p@host/db")
        == "postgresql://u:p@host/db",
    )
    label = storage.database_label("postgresql://user:secret@host.example/db")
    check("postgres: label hides password", "secret" not in label, label)
    check("postgres: label names host", "host.example" in label, label)

    supabase_pooler = (
        "postgresql://postgres.project:secret@"
        "aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        "?pgbouncer=true&sslmode=require"
    )
    cleaned = storage.normalise_url(supabase_pooler)
    check(
        "supabase: pgbouncer parameter removed",
        "pgbouncer" not in cleaned,
        cleaned,
    )
    check(
        "supabase: sslmode preserved",
        "sslmode=require" in cleaned,
        cleaned,
    )
    no_ssl = storage.normalise_url(
        "postgresql://postgres.project:secret@"
        "aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
    )
    check(
        "supabase: sslmode added when missing",
        "sslmode=require" in no_ssl,
        no_ssl,
    )

    conn = storage.PostgresConnection("postgres://u:p@host/db")
    check(
        "postgres: URL normalised before connect",
        state["url"] == "postgresql://u:p@host/db",
        str(state["url"]),
    )
    check(
        "postgres: connect timeout is set",
        state["kwargs"].get("connect_timeout") == 10,
        str(state["kwargs"]),
    )
    check(
        "postgres: prepared statements disabled",
        state["kwargs"].get("prepare_threshold") is None,
        str(state["kwargs"]),
    )

    conn.execute("SELECT * FROM responses WHERE code = ?", ("NK-0001",))
    check(
        "postgres: ? becomes %s",
        state["calls"][-1][0]
        == "SELECT * FROM responses WHERE code = %s",
        state["calls"][-1][0],
    )

    response_id = storage.insert_response(conn, VALUES)
    insert_sql = state["calls"][-1][0]
    check("postgres: insert returns id", response_id == 7, str(response_id))
    check("postgres: insert uses RETURNING id", "RETURNING id" in insert_sql)
    check(
        "postgres: insert uses %s placeholders",
        "%s" in insert_sql and "?" not in insert_sql,
    )
    check(
        "postgres: temporary code is unique",
        "TMP-" in insert_sql or "TMP-" in str(state["calls"][-1][1]),
    )

    storage.set_code(conn, 7, "NK-0007")
    update_sql = state["calls"][-1][0]
    check(
        "postgres: update translates placeholders",
        update_sql == "UPDATE responses SET code = %s WHERE id = %s",
        update_sql,
    )

    state["calls"].clear()
    conn.executescript("CREATE TABLE x (id int); CREATE INDEX i ON x (id);")
    check(
        "postgres: script is split into statements",
        len(state["calls"]) == 2,
        str(state["calls"]),
    )
    check(
        "postgres: schema uses IDENTITY",
        "IDENTITY" in storage.POSTGRES_SCHEMA
        and "AUTOINCREMENT" not in storage.POSTGRES_SCHEMA,
    )

    state["calls"].clear()
    storage.init_schema(conn)
    alters = [sql for sql, _ in state["calls"] if "ADD COLUMN" in sql]
    check(
        "postgres: migration uses IF NOT EXISTS",
        len(alters) == 2 and all("IF NOT EXISTS" in sql for sql in alters),
        str(alters),
    )
    check(
        "postgres: migration covers both software columns",
        any("needs_software" in sql for sql in alters)
        and any("software_details" in sql for sql in alters),
        str(alters),
    )
    conn.close()


def main() -> None:
    test_sqlite()
    test_sqlite_migration()
    test_postgres()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        raise SystemExit(1)
    print(f"{checks} of {checks} checks passed")
    print("All checks passed.")


if __name__ == "__main__":
    main()
