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
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM responses"
        ).fetchone()["total"]
        check("sqlite: count uses named column", count == 1, str(count))
        check("sqlite: schema uses AUTOINCREMENT", "AUTOINCREMENT" in storage.SQLITE_SCHEMA)
    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            (tmp / f"storage.db{suffix}").unlink(missing_ok=True)


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
    conn.close()


def main() -> None:
    test_sqlite()
    test_postgres()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        raise SystemExit(1)
    print(f"{checks} of {checks} checks passed")
    print("All checks passed.")


if __name__ == "__main__":
    main()
