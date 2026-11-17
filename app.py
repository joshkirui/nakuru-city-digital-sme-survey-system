"""Flask survey system for the Nakuru SME e-commerce study.

The app implements the data-collection and preliminary-analysis parts of
Chapter Three: an anonymous six-section questionnaire, a response store, a
fieldwork dashboard, and SPSS-ready exports.

Run locally:
    python app.py

Environment variables:
    MSME_DB              path to the SQLite database (default: data/survey.db;
                         on Vercel: a temporary file, demo only)
    MSME_ADMIN_PASSWORD  password for /admin (default: nakuru2026)
    MSME_SECRET          Flask session secret (default: generated in data/)
    PORT                 port for the development server (default: 8000)
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import secrets
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import questions as q
import stats

BASE = Path(__file__).resolve().parent
# Kenya has no daylight saving, so a fixed offset avoids a dependency on the
# system time-zone database (which Windows Python builds often lack).
EAT = timezone(timedelta(hours=3), name="EAT")
ADMIN_TIMEOUT = 30 * 60  # seconds of inactivity before the admin session expires
DEFAULT_PASSWORD = "nakuru2026"


# --------------------------------------------------------------------------- app


def load_secret() -> str:
    """Return a persistent session secret, generating one on first use."""
    env = os.environ.get("MSME_SECRET")
    if env:
        return env
    path = BASE / "data" / ".secret_key"
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(32)
        path.write_text(value, encoding="utf-8")
        return value
    except OSError as error:
        # A read-only bundle (for example a serverless platform) cannot persist
        # the key, so each instance would sign cookies with a different secret.
        if os.environ.get("VERCEL") and not env:
            print(
                "warning: MSME_SECRET is not set and the secret file is not "
                f"writable ({error}). Sign-in will fail intermittently across "
                "serverless instances. Set MSME_SECRET in the project's "
                "environment variables.",
                file=sys.stderr,
            )
        return secrets.token_hex(32)


def runtime_db_path() -> Path:
    """Choose where the SQLite file lives.

    Serverless platforms mount the deployment bundle read-only and give each
    instance a private temporary directory, so a database written there is
    disposable. That is acceptable for a preview, never for fieldwork.
    """
    configured = os.environ.get("MSME_DB")
    if configured:
        return Path(configured)
    if os.environ.get("VERCEL"):
        return Path(tempfile.gettempdir()) / "survey.db"
    return BASE / "data" / "survey.db"


def ensure_parent(path: Path) -> None:
    """Create the database directory, tolerating a read-only filesystem."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(
            f"warning: cannot create {path.parent} ({error}); "
            "the database path must be writable.",
            file=sys.stderr,
        )


def report_runtime(app: Flask) -> None:
    """Write one startup line so hosting logs show what the app detected.

    ``FUNCTION_INVOCATION_FAILED`` replaces the real traceback in the browser,
    so the useful evidence has to reach the platform's runtime logs. Never
    print secret values, only where they came from.
    """
    secret_source = "environment"
    if not os.environ.get("MSME_SECRET"):
        secret_file = BASE / "data" / ".secret_key"
        secret_source = "file" if secret_file.exists() else "generated-per-instance"
    password_source = (
        "environment" if os.environ.get("MSME_ADMIN_PASSWORD") else "default"
    )
    print(
        "msme startup: "
        f"platform={'vercel' if os.environ.get('VERCEL') else 'local'} "
        f"db={app.config['DB_PATH']} "
        f"secret={secret_source} "
        f"admin_password={password_source}",
        file=sys.stderr,
    )
    if os.environ.get("VERCEL") and password_source == "default":
        print(
            "warning: MSME_ADMIN_PASSWORD is not set; /admin is protected by "
            "the public demo password. Set it in the project's environment "
            "variables.",
            file=sys.stderr,
        )


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    default_db = runtime_db_path()
    ensure_parent(default_db)

    app.config.update(
        SECRET_KEY=load_secret(),
        ADMIN_PASSWORD=os.environ.get("MSME_ADMIN_PASSWORD", DEFAULT_PASSWORD),
        DB_PATH=str(default_db),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Vercel serves every deployment over HTTPS.
        SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
        SEND_FILE_MAX_AGE_DEFAULT=3600,
        TARGET=384,
        DISTRIBUTED=430,
        ALPHA_LEVEL=0.70,
    )
    if config:
        app.config.update(config)

    app.teardown_appcontext(close_db)
    register_filters(app)
    register_routes(app)

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["CHANNEL_LABELS"] = q.CHANNEL_LABELS

    with app.app_context():
        init_db()

    report_runtime(app)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create the database tables."""
        init_db()
        print(f"initialised {current_app.config['DB_PATH']}")

    return app


# --------------------------------------------------------------------- database


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DB_PATH"], timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS responses (
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
        );
        CREATE INDEX IF NOT EXISTS idx_responses_created
            ON responses (created_at);
        """
    )
    conn.commit()


def fetch_responses() -> list[dict]:
    rows = get_db().execute("SELECT * FROM responses ORDER BY id").fetchall()
    out = []
    for row in rows:
        try:
            channels = json.loads(row["channels"] or "[]")
        except ValueError:
            channels = []
        try:
            answers = {
                str(k): int(v)
                for k, v in json.loads(row["answers"] or "{}").items()
            }
        except (ValueError, TypeError):
            answers = {}
        out.append(
            {
                "id": row["id"],
                "code": row["code"],
                "created_at": row["created_at"],
                "consent": row["consent"],
                "sector": row["sector"],
                "years": row["years"],
                "employees": row["employees"],
                "role": row["role"],
                "location": row["location"],
                "channels": channels,
                "answers": answers,
                "duration_seconds": row["duration_seconds"],
                "open_challenge": row["open_challenge"] or "",
            }
        )
    return out


# ------------------------------------------------------------------------ forms


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def check_csrf() -> None:
    sent = request.form.get("csrf_token", "")
    saved = session.get("csrf_token", "")
    if not saved or not sent or not secrets.compare_digest(saved, sent):
        abort(400, "The form token is missing or has expired. Reload the page and try again.")


def channel_field() -> dict:
    return next(d for d in q.DEMOGRAPHICS if d["name"] == "channels")


def parse_submission(form) -> tuple[dict, list[str], set[str]]:
    """Validate a submission.

    Returns (payload, errors, missing_fields). missing_fields is used only to
    highlight the inputs that the respondent still has to complete.
    """
    errors: list[str] = []
    missing: set[str] = set()
    if form.get("consent") != "yes":
        errors.append("Please confirm that you have read the information and agree to take part.")
        missing.add("consent")

    demographics: dict[str, str] = {}
    for field in q.DEMOGRAPHICS:
        if field["type"] == "checkbox":
            continue
        value = (form.get(field["name"]) or "").strip()
        allowed = {option[0] for option in field["options"]}
        if value not in allowed:
            errors.append(f"Please answer: {field['label']}.")
            missing.add(field["name"])
        demographics[field["name"]] = value

    chosen = [c for c in form.getlist("channels") if c in q.CHANNEL_LABELS]
    chosen = list(dict.fromkeys(chosen))
    if not chosen:
        errors.append("Please select at least one e-commerce channel used by the business.")
        missing.add("channels")

    answers: dict[str, int] = {}
    unanswered: list[str] = []
    for code in q.ALL_ITEMS:
        raw = (form.get(code) or "").strip()
        if raw not in {"1", "2", "3", "4", "5"}:
            unanswered.append(code)
        else:
            answers[code] = int(raw)
    if unanswered:
        errors.append(
            f"Please answer every statement. {len(unanswered)} statement"
            f"{'' if len(unanswered) == 1 else 's'} still need a response."
        )
        missing.update(unanswered)

    duration = None
    raw_duration = (form.get("duration_seconds") or "").strip()
    if raw_duration.isdigit():
        duration = max(0, min(int(raw_duration), 86400))

    open_text = (form.get("open_challenge") or "").strip()
    if len(open_text) > 2000:
        open_text = open_text[:2000]

    payload = {
        "consent": 1 if form.get("consent") == "yes" else 0,
        **{key: demographics.get(key, "") for key in
           ("sector", "years", "employees", "role", "location")},
        "channels": chosen,
        "answers": answers,
        "duration_seconds": duration,
        "open_challenge": open_text,
    }
    return payload, errors, missing


# --------------------------------------------------------------------- helpers


def fmt_dt(value: str | None, fmt: str = "%d %b %Y, %H:%M") -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(EAT).strftime(fmt)


def duration_text(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    minutes, secs = divmod(int(seconds), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes} min"
    return f"{minutes} min {secs:02d} s"


def demo_code(field_name: str, value: str):
    for field in q.DEMOGRAPHICS:
        if field["name"] == field_name:
            for index, (key, _label) in enumerate(field["options"], start=1):
                if key == value:
                    return index
    return ""


def construct_scores(row: dict) -> dict[str, float]:
    scores = {}
    for key, _label, items in q.CONSTRUCTS:
        if all(code in row["answers"] for code in items):
            scores[key] = stats.mean([row["answers"][code] for code in items])
    if all(f"F{i}" in row["answers"] for i in range(1, 11)):
        scores["CH"] = stats.mean([row["answers"][f"F{i}"] for i in range(1, 11)])
    return scores


def item_stats(responses: list[dict], code: str) -> dict:
    values = [r["answers"][code] for r in responses if code in r["answers"]]
    return {
        "n": len(values),
        "mean": stats.mean(values) if values else None,
        "sd": stats.sd(values) if len(values) > 1 else None,
    }


def construct_table(responses: list[dict]) -> list[dict]:
    rows = []
    for key, label, items in q.CONSTRUCTS:
        vectors = [
            [r["answers"][code] for code in items]
            for r in responses
            if all(code in r["answers"] for code in items)
        ]
        composites = [stats.mean(v) for v in vectors]
        rows.append(
            {
                "key": key,
                "label": label,
                "items": len(items),
                "n": len(vectors),
                "mean": stats.mean(composites) if composites else None,
                "sd": stats.sd(composites) if len(composites) > 1 else None,
                "alpha": stats.cronbach_alpha(vectors),
            }
        )
    return rows


def distribution(responses: list[dict], field: str, labels: dict) -> list[dict]:
    counts = Counter(r[field] for r in responses)
    total = len(responses)
    return [
        {
            "code": code,
            "label": label,
            "n": counts.get(code, 0),
            "pct": (100 * counts.get(code, 0) / total) if total else 0.0,
        }
        for code, label in labels.items()
    ]


def correlation_table(complete: list[dict]) -> dict:
    series = {}
    for key, _label, items in q.CONSTRUCTS:
        series[key] = [stats.mean([r["answers"][code] for code in items]) for r in complete]
    keys = [key for key, _l, _i in q.CONSTRUCTS]
    labels = {key: label for key, label, _items in q.CONSTRUCTS}
    rows = []
    for a in keys:
        cells = []
        for b in keys:
            value = 1.0 if a == b else stats.pearson(series[a], series[b])
            cells.append(value)
        rows.append({"key": a, "cells": cells})
    return {"variables": keys, "labels": labels, "rows": rows, "n": len(complete)}


def build_dashboard() -> dict:
    responses = fetch_responses()
    total = len(responses)
    target = current_app.config["TARGET"]
    distributed = current_app.config["DISTRIBUTED"]

    complete = [
        r for r in responses
        if all(code in r["answers"] for code in q.ALL_ITEMS)
    ]
    durations = [
        r["duration_seconds"]
        for r in responses
        if r["duration_seconds"] is not None
    ]
    ordered = sorted(durations)
    median = ordered[len(ordered) // 2] if ordered else None

    regression = None
    if len(complete) >= 6:
        labels = [f"{label} ({key})" for key, label, _items in q.CONSTRUCTS[:3]]
        y_values = []
        x_rows = []
        for row in complete:
            scores = construct_scores(row)
            y_values.append(scores["Y"])
            x_rows.append([scores["X1"], scores["X2"], scores["X3"]])
        regression = stats.ols(y_values, x_rows, labels)
        if regression:
            for term in regression["terms"]:
                term["stars"] = stats.stars(term["p"])

    items = []
    for section in q.SECTIONS:
        items.append(
            {
                "id": section["id"],
                "title": section["title"],
                "items": [
                    {"code": code, "text": text, **item_stats(responses, code)}
                    for code, text in section["items"]
                ],
            }
        )

    challenge_rows = []
    for index in range(1, 11):
        code = f"F{index}"
        challenge_rows.append(
            {
                "code": code,
                "text": q.ITEM_TEXT[code],
                **item_stats(responses, code),
            }
        )
    ranked = sorted(
        challenge_rows,
        key=lambda row: (row["mean"] is None, -(row["mean"] or 0)),
    )

    toe = []
    for name, codes in q.TOE_GROUPS:
        composites = [
            stats.mean([r["answers"][code] for code in codes])
            for r in responses
            if all(code in r["answers"] for code in codes)
        ]
        toe.append(
            {
                "name": name,
                "mean": stats.mean(composites) if composites else None,
                "sd": stats.sd(composites) if len(composites) > 1 else None,
                "n": len(composites),
            }
        )

    today = datetime.now(EAT).date()
    day_counts = Counter(fmt_dt(r["created_at"], "%Y-%m-%d") for r in responses)
    daily = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        daily.append(
            {
                "key": key,
                "label": day.strftime("%d %b"),
                "n": day_counts.get(key, 0),
            }
        )
    daily_max = max((d["n"] for d in daily), default=0) or 1
    for day in daily:
        day["pct"] = 100 * day["n"] / daily_max

    recent = []
    for row in reversed(responses[-8:]):
        scores = construct_scores(row)
        recent.append(
            {
                "code": row["code"],
                "created_at": row["created_at"],
                "sector": q.SECTOR_LABELS.get(row["sector"], row["sector"]),
                "location": q.LOCATION_LABELS.get(row["location"], row["location"]),
                "channels": [q.CHANNEL_LABELS[c] for c in row["channels"] if c in q.CHANNEL_LABELS],
                "duration": row["duration_seconds"],
                "y": scores.get("Y"),
            }
        )

    channels = [
        {
            "key": key,
            "label": label,
            "n": sum(1 for r in responses if key in r["channels"]),
            "pct": (100 * sum(1 for r in responses if key in r["channels"]) / total)
            if total else 0.0,
        }
        for key, label in q.CHANNEL_LABELS.items()
    ]

    return {
        "total": total,
        "target": target,
        "distributed": distributed,
        "remaining": max(0, target - total),
        "pct": min(100.0, 100 * total / target) if target else 0.0,
        "response_rate": (100 * total / distributed) if distributed else 0.0,
        "valid": len(complete),
        "complete_pct": (100 * len(complete) / total) if total else 0.0,
        "mean_minutes": (stats.mean(durations) / 60) if durations else None,
        "median_seconds": median,
        "fast": sum(1 for value in durations if value < 180),
        "comments": sum(1 for r in responses if r["open_challenge"]),
        "first": fmt_dt(responses[0]["created_at"]) if responses else None,
        "last": fmt_dt(responses[-1]["created_at"]) if responses else None,
        "composition": {
            "sector": distribution(responses, "sector", q.SECTOR_LABELS),
            "location": distribution(responses, "location", q.LOCATION_LABELS),
            "years": distribution(responses, "years", q.YEARS_LABELS),
            "employees": distribution(responses, "employees", q.EMPLOYEE_LABELS),
            "role": distribution(responses, "role", q.ROLE_LABELS),
        },
        "channels": channels,
        "constructs": construct_table(responses),
        "correlations": correlation_table(complete) if len(complete) >= 3 else None,
        "regression": regression,
        "challenges": ranked,
        "challenge_groups": toe,
        "sections": items,
        "daily": daily,
        "recent": recent,
        "alpha_level": current_app.config["ALPHA_LEVEL"],
    }


# ---------------------------------------------------------------------- exports


def export_fieldnames() -> list[str]:
    names = [
        "code",
        "submitted_at",
        "duration_seconds",
        "consent",
        "sector",
        "years",
        "employees",
        "role",
        "location",
        "ch_online_store",
        "ch_social",
        "ch_payments",
        "n_channels",
    ]
    names += q.ALL_ITEMS
    names += ["X1_online", "X2_social", "X3_payments", "Y_performance", "CH_mean", "open_challenge"]
    return names


def numeric_csv(responses: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(export_fieldnames())
    for row in responses:
        scores = construct_scores(row)
        values = [
            row["code"],
            row["created_at"],
            row["duration_seconds"] if row["duration_seconds"] is not None else "",
            1 if row["consent"] else 0,
            demo_code("sector", row["sector"]),
            demo_code("years", row["years"]),
            demo_code("employees", row["employees"]),
            demo_code("role", row["role"]),
            demo_code("location", row["location"]),
            1 if "online_store" in row["channels"] else 0,
            1 if "social" in row["channels"] else 0,
            1 if "payments" in row["channels"] else 0,
            len(row["channels"]),
        ]
        values += [row["answers"].get(code, "") for code in q.ALL_ITEMS]
        values += [
            round(scores[key], 4) if key in scores else ""
            for key in ("X1", "X2", "X3", "Y", "CH")
        ]
        values.append(row["open_challenge"])
        writer.writerow(values)
    return buffer.getvalue()


def labelled_csv(responses: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            "code",
            "submitted_at_eat",
            "duration_seconds",
            "consent",
            "sector",
            "years_in_operation",
            "employees",
            "role",
            "location",
            "channels",
            "n_channels",
        ]
        + q.ALL_ITEMS
        + ["X1_online", "X2_social", "X3_payments", "Y_performance", "CH_mean", "open_challenge"]
    )
    for row in responses:
        scores = construct_scores(row)
        writer.writerow(
            [
                row["code"],
                fmt_dt(row["created_at"]),
                row["duration_seconds"] if row["duration_seconds"] is not None else "",
                "Yes" if row["consent"] else "No",
                q.SECTOR_LABELS.get(row["sector"], row["sector"]),
                q.YEARS_LABELS.get(row["years"], row["years"]),
                q.EMPLOYEE_LABELS.get(row["employees"], row["employees"]),
                q.ROLE_LABELS.get(row["role"], row["role"]),
                q.LOCATION_LABELS.get(row["location"], row["location"]),
                "; ".join(q.CHANNEL_LABELS[c] for c in row["channels"] if c in q.CHANNEL_LABELS),
                len(row["channels"]),
            ]
            + [row["answers"].get(code, "") for code in q.ALL_ITEMS]
            + [round(scores[key], 2) if key in scores else "" for key in ("X1", "X2", "X3", "Y", "CH")]
            + [row["open_challenge"]]
        )
    return buffer.getvalue()


def codebook_csv() -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["variable", "label", "type", "values", "notes"])

    writer.writerow(["code", "Response code", "String", "NK-0001, NK-0002, ...",
                     "Code only; no personal identifiers are collected"])
    writer.writerow(["submitted_at", "Submission timestamp", "Datetime (ISO 8601, UTC)",
                     "e.g. 2026-11-13T14:22:07+00:00", "Displayed in East Africa Time on the dashboard"])
    writer.writerow(["duration_seconds", "Time taken to complete the questionnaire", "Numeric",
                     "0-86400", "Recorded by the browser"])
    writer.writerow(["consent", "Informed consent given", "Dichotomous", "1 = yes; 0 = no", ""])

    for field in q.DEMOGRAPHICS:
        if field["type"] == "checkbox":
            continue
        values = "; ".join(f"{index} = {label}" for index, (_key, label) in enumerate(field["options"], 1))
        writer.writerow([field["name"], field["label"], "Nominal", values, ""])

    writer.writerow(["ch_online_store", "Uses an online store or website", "Dichotomous",
                     "0 = no; 1 = yes", "Channel selected by the respondent"])
    writer.writerow(["ch_social", "Uses social commerce", "Dichotomous", "0 = no; 1 = yes", ""])
    writer.writerow(["ch_payments", "Uses digital payments", "Dichotomous", "0 = no; 1 = yes", ""])
    writer.writerow(["n_channels", "Number of e-commerce channels used", "Numeric", "0-3", ""])

    for section in q.SECTIONS:
        scale = "; ".join(f"{key} = {label}" for key, label in section["scale"])
        for code, text in section["items"]:
            writer.writerow([code, text, "Ordinal (Likert)", scale, f"Section {section['id']}"])

    composite_names = {
        "X1": "X1_online",
        "X2": "X2_social",
        "X3": "X3_payments",
        "Y": "Y_performance",
    }
    for key, label, items in q.CONSTRUCTS:
        writer.writerow([composite_names[key], label, "Scale", "1.00-5.00",
                         f"Mean of {', '.join(items)}; computed only when all items are answered"])
    writer.writerow(["CH_mean", "Challenges composite", "Scale", "1.00-5.00",
                     f"Mean of {', '.join(f'F{i}' for i in range(1, 11))}"])
    writer.writerow(["open_challenge", "Most serious challenge (open-ended)",
                     "String", "Free text", "Optional; respondent advised not to give personal details"])

    return buffer.getvalue()


def sps_syntax() -> str:
    quote = chr(34)
    apostrophe = chr(39)

    def clean(text: str) -> str:
        return text.replace(quote, apostrophe)

    lines = [
        "* Encoding: UTF-8.",
        f"* Generated {datetime.now(EAT).strftime('%d %B %Y')} by the Nakuru SME e-commerce survey system.",
        "* Apply these labels after importing the numeric CSV (nakuru_survey_*.csv).",
        "* In SPSS: File > Open > Data, select the CSV, then run this syntax.",
        "",
        "DATASET ACTIVATE DataSet1.",
        "",
        "VARIABLE LABELS",
    ]
    entries = [
        ("code", "Response code"),
        ("submitted_at", "Date and time of submission (ISO 8601)"),
        ("duration_seconds", "Time taken to complete the questionnaire, seconds"),
        ("consent", "Informed consent given"),
    ]
    for field in q.DEMOGRAPHICS:
        if field["type"] != "checkbox":
            entries.append((field["name"], field["label"]))
    entries += [
        ("ch_online_store", "Uses an online store or website"),
        ("ch_social", "Uses social commerce"),
        ("ch_payments", "Uses digital payments"),
        ("n_channels", "Number of e-commerce channels used"),
    ]
    entries += [(code, q.ITEM_TEXT[code]) for code in q.ALL_ITEMS]
    entries += [
        ("X1_online", "Online stores composite (mean of B1 to B6)"),
        ("X2_social", "Social commerce composite (mean of C1 to C6)"),
        ("X3_payments", "Digital payment systems composite (mean of D1 to D6)"),
        ("Y_performance", "SME performance composite (mean of E1 to E8)"),
        ("CH_mean", "Challenges composite (mean of F1 to F10)"),
    ]
    for name, label in entries:
        lines.append(f"    {name} {quote}{clean(label)}{quote}")
    lines += [".", "EXECUTE.", "", "VALUE LABELS"]

    lines.append(f"    consent 1 {quote}Yes{quote} 0 {quote}No{quote}")
    for field in q.DEMOGRAPHICS:
        if field["type"] == "checkbox":
            continue
        values = " ".join(
            f"{index} {quote}{clean(label)}{quote}"
            for index, (_key, label) in enumerate(field["options"], 1)
        )
        lines.append(f"    {field['name']} {values}")
    for name in ("ch_online_store", "ch_social", "ch_payments"):
        lines.append(f"    {name} 1 {quote}Yes{quote} 0 {quote}No{quote}")
    lines += [".", "EXECUTE.", ""]

    lines += [
        "DESCRIPTIVES VARIABLES=X1_online X2_social X3_payments Y_performance CH_mean",
        "  /STATISTICS=MEAN STDDEV MIN MAX.",
        "",
        "FREQUENCIES VARIABLES=sector years employees role location",
        "  ch_online_store ch_social ch_payments",
        "  /ORDER=ANALYSIS.",
        "",
        "CORRELATIONS",
        "  /VARIABLES=X1_online X2_social X3_payments Y_performance",
        "  /PRINT=TWOTAIL NOSIG",
        "  /MISSING=PAIRWISE.",
        "",
    ]
    for key, label, items in q.CONSTRUCTS:
        lines += [
            f"RELIABILITY",
            f"  /VARIABLES={' '.join(items)}",
            f"  /SCALE({quote}{clean(label)}{quote}) ALL",
            f"  /MODEL=ALPHA",
            f"  /SUMMARY=TOTAL.",
            "",
        ]

    lines += [
        "REGRESSION",
        "  /DESCRIPTIVES MEAN STDDEV CORR SIG N",
        "  /MISSING LISTWISE",
        "  /STATISTICS COEFF OUTS CI(95) R ANOVA",
        "  /CRITERIA=PIN(.05) POUT(.10)",
        "  /NOORIGIN",
        "  /DEPENDENT Y_performance",
        "  /METHOD=ENTER X1_online X2_social X3_payments.",
        "",
        "FREQUENCIES VARIABLES=F1 F2 F3 F4 F5 F6 F7 F8 F9 F10",
        "  /STATISTICS=MEAN STDDEV MIN MAX",
        "  /ORDER=ANALYSIS.",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------- routes


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        last_seen = session.get("admin_seen", 0)
        now = time.time()
        if now - last_seen > ADMIN_TIMEOUT:
            session.clear()
            flash("Your session expired. Please sign in again.", "warn")
            return redirect(url_for("admin_login"))
        session["admin_seen"] = now
        return view(*args, **kwargs)

    return wrapped


def safe_next(target: str | None) -> str:
    if (
        target
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    ):
        return target
    return url_for("admin_dashboard")


def register_routes(app: Flask) -> None:
    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
        )
        return response

    @app.get("/")
    def index():
        return redirect(url_for("survey"))

    @app.get("/health")
    def health():
        return {"status": "ok", "responses": get_db().execute("SELECT COUNT(*) FROM responses").fetchone()[0]}

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /admin\nAllow: /survey\n", mimetype="text/plain")

    # ------------------------------------------------------------- public

    @app.get("/survey")
    def survey():
        return render_template(
            "survey.html",
            demographics=[d for d in q.DEMOGRAPHICS if d["type"] != "checkbox"],
            channels_field=channel_field(),
            sections=q.SECTIONS,
            open_question=q.OPEN_QUESTION,
            form={},
            chosen_channels=[],
            missing_items=set(),
            missing_fields=set(),
            errors=[],
            total_fields=len(q.ALL_ITEMS) + 5 + 1 + 1,
        )

    @app.post("/survey")
    def survey_submit():
        payload, errors, missing = parse_submission(request.form)
        if errors:
            return (
                render_template(
                    "survey.html",
                    demographics=[d for d in q.DEMOGRAPHICS if d["type"] != "checkbox"],
                    channels_field=channel_field(),
                    sections=q.SECTIONS,
                    open_question=q.OPEN_QUESTION,
                    form=request.form,
                    chosen_channels=request.form.getlist("channels"),
                    missing_items=missing,
                    missing_fields=missing,
                    errors=errors,
                    total_fields=len(q.ALL_ITEMS) + 5 + 1 + 1,
                ),
                200,
            )

        conn = get_db()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            cursor = conn.execute(
                """
                INSERT INTO responses
                    (code, created_at, consent, sector, years, employees, role,
                     location, channels, answers, duration_seconds, open_challenge)
                VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    payload["consent"],
                    payload["sector"],
                    payload["years"],
                    payload["employees"],
                    payload["role"],
                    payload["location"],
                    json.dumps(payload["channels"]),
                    json.dumps(payload["answers"], sort_keys=True),
                    payload["duration_seconds"],
                    payload["open_challenge"],
                ),
            )
            response_id = cursor.lastrowid
            code = f"NK-{response_id:04d}"
            conn.execute("UPDATE responses SET code = ? WHERE id = ?", (code, response_id))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            current_app.logger.exception("could not store a survey response")
            return render_template("error.html", message="The response could not be saved. Please try again."), 500

        return redirect(url_for("thanks", code=code))

    @app.get("/thanks/<code>")
    def thanks(code: str):
        row = get_db().execute("SELECT * FROM responses WHERE code = ?", (code,)).fetchone()
        if row is None:
            abort(404)
        return render_template(
            "thanks.html",
            code=row["code"],
            submitted=fmt_dt(row["created_at"], "%d %B %Y at %H:%M"),
        )

    # -------------------------------------------------------------- admin

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            check_csrf()
            now = time.time()
            locked_until = session.get("locked_until", 0)
            if locked_until and now < locked_until:
                flash("Too many failed attempts. Please wait a moment and try again.", "warn")
                return render_template("login.html"), 429

            password = request.form.get("password", "")
            expected = current_app.config["ADMIN_PASSWORD"]
            if secrets.compare_digest(password, expected):
                target = safe_next(request.form.get("next") or request.args.get("next"))
                session.clear()
                session["admin"] = True
                session["admin_seen"] = now
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(target)

            fails = session.get("login_fails", 0) + 1
            session["login_fails"] = fails
            if fails >= 5:
                session["locked_until"] = now + 60
                session["login_fails"] = 0
                flash("Too many failed attempts. Please wait one minute.", "warn")
            else:
                flash("Incorrect password.", "error")
            return render_template("login.html"), 401

        if session.get("admin"):
            return redirect(url_for("admin_dashboard"))
        return render_template("login.html")

    @app.post("/admin/logout")
    def admin_logout():
        if session.get("admin"):
            check_csrf()
        session.clear()
        flash("You have signed out.", "info")
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        return render_template("dashboard.html", d=build_dashboard())

    @app.get("/admin/responses")
    @admin_required
    def admin_responses():
        responses = fetch_responses()
        sector = (request.args.get("sector") or "").strip()
        needle = (request.args.get("q") or "").strip().lower()
        filtered = [
            row
            for row in responses
            if (not sector or row["sector"] == sector)
            and (not needle or needle in row["code"].lower())
        ]
        per_page = 25
        page = max(1, request.args.get("page", type=int) or 1)
        pages = max(1, math.ceil(len(filtered) / per_page))
        page = min(page, pages)
        chunk = filtered[(page - 1) * per_page: page * per_page]

        listed = []
        for row in chunk:
            scores = construct_scores(row)
            listed.append(
                {
                    "code": row["code"],
                    "created_at": row["created_at"],
                    "sector": q.SECTOR_LABELS.get(row["sector"], row["sector"]),
                    "location": q.LOCATION_LABELS.get(row["location"], row["location"]),
                    "channels": [q.CHANNEL_LABELS[c] for c in row["channels"] if c in q.CHANNEL_LABELS],
                    "duration": row["duration_seconds"],
                    "y": scores.get("Y"),
                }
            )

        return render_template(
            "responses.html",
            rows=listed,
            total=len(filtered),
            page=page,
            pages=pages,
            sector=sector,
            needle=needle,
            sectors=q.SECTOR_LABELS,
        )

    @app.get("/admin/responses/<code>")
    @admin_required
    def admin_response(code: str):
        row = get_db().execute("SELECT * FROM responses WHERE code = ?", (code,)).fetchone()
        if row is None:
            abort(404)
        try:
            answers = {str(k): int(v) for k, v in json.loads(row["answers"] or "{}").items()}
        except (ValueError, TypeError):
            answers = {}
        channels = []
        try:
            channels = json.loads(row["channels"] or "[]")
        except ValueError:
            pass
        record = {
            "code": row["code"],
            "created_at": row["created_at"],
            "duration_seconds": row["duration_seconds"],
            "sector": q.SECTOR_LABELS.get(row["sector"], row["sector"]),
            "location": q.LOCATION_LABELS.get(row["location"], row["location"]),
            "years": q.YEARS_LABELS.get(row["years"], row["years"]),
            "employees": q.EMPLOYEE_LABELS.get(row["employees"], row["employees"]),
            "role": q.ROLE_LABELS.get(row["role"], row["role"]),
            "channels": [q.CHANNEL_LABELS[c] for c in channels if c in q.CHANNEL_LABELS],
            "answers": answers,
            "open_challenge": row["open_challenge"] or "",
        }
        scale_maps = {section["id"]: dict(section["scale"]) for section in q.SECTIONS}
        return render_template(
            "detail.html",
            r=record,
            sections=q.SECTIONS,
            scale_maps=scale_maps,
        )

    @app.get("/admin/export.csv")
    @admin_required
    def export_csv():
        body = numeric_csv(fetch_responses())
        filename = f"nakuru_survey_{datetime.now(EAT):%Y-%m-%d}.csv"
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/admin/export-labels.csv")
    @admin_required
    def export_labels():
        body = "\ufeff" + labelled_csv(fetch_responses())
        filename = f"nakuru_survey_labelled_{datetime.now(EAT):%Y-%m-%d}.csv"
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/admin/codebook.csv")
    @admin_required
    def export_codebook():
        return Response(
            codebook_csv(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="nakuru_codebook.csv"'},
        )

    @app.get("/admin/analysis.sps")
    @admin_required
    def export_sps():
        return Response(
            sps_syntax(),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="nakuru_analysis.sps"'},
        )

    # -------------------------------------------------------------- errors

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", message="That page does not exist."), 404

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", message=getattr(error, "description", "Bad request.")), 400

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("error.html", message="The submitted form was too large."), 413

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", message="Something went wrong. Please try again."), 500


def register_filters(app: Flask) -> None:
    @app.template_filter("num")
    def num_filter(value, digits: int = 2):
        if value is None:
            return "-"
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "-"

    @app.template_filter("pct")
    def pct_filter(value, digits: int = 1):
        if value is None:
            return "-"
        return f"{float(value):.{digits}f}%"

    @app.template_filter("dt")
    def dt_filter(value, fmt: str = "%d %b %Y, %H:%M"):
        return fmt_dt(value, fmt)

    @app.template_filter("pval")
    def pval_filter(value):
        if value is None:
            return "-"
        if value < 0.001:
            return "< .001"
        text = f"{value:.3f}"
        return text[1:] if text.startswith("0") else text

    @app.template_filter("pstat")
    def pstat_filter(value):
        if value is None:
            return "p = -"
        if value < 0.001:
            return "p < .001"
        text = f"{value:.3f}"
        text = text[1:] if text.startswith("0") else text
        return f"p = {text}"

    @app.template_filter("duration")
    def duration_filter(value):
        return duration_text(value)


app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        debug=bool(os.environ.get("FLASK_DEBUG")),
    )
