"""Create a realistic demo database so the dashboard can be previewed.

The script writes to its own database (data/demo.db by default) and never
touches the live survey database.

    python seed_demo.py
    python seed_demo.py --count 200 --db data/demo.db --force
    $env:MSME_DB = "data/demo.db"; python app.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

SECTORS = [
    ("retail", 0.46),
    ("food", 0.20),
    ("services", 0.24),
    ("manufacturing", 0.07),
    ("other", 0.03),
]

YEARS = [("under1", 0.06), ("1to3", 0.24), ("4to6", 0.28), ("7to10", 0.24), ("over10", 0.18)]

EMPLOYEES = {
    "retail": [("1to9", 0.72), ("10to49", 0.28)],
    "food": [("1to9", 0.82), ("10to49", 0.18)],
    "services": [("1to9", 0.66), ("10to49", 0.34)],
    "manufacturing": [("1to9", 0.30), ("10to49", 0.62), ("50to99", 0.08)],
    "other": [("1to9", 0.60), ("10to49", 0.40)],
}

LOCATIONS = [("cbd", 0.56), ("wakulima", 0.29), ("other_nakuru", 0.15)]
ROLES = [("owner", 0.58), ("manager", 0.28), ("employee", 0.14)]

B_OFFSETS = {"B1": 0.30, "B2": 0.05, "B3": -0.10, "B4": -0.20, "B5": -0.85, "B6": -0.35}
C_OFFSETS = {"C1": 0.25, "C2": -0.10, "C3": 0.00, "C4": -0.20, "C5": -0.55, "C6": -0.35}
D_OFFSETS = {"D1": 0.25, "D2": -0.55, "D3": -0.20, "D4": 0.10, "D5": -0.45, "D6": -0.10}
E_OFFSETS = {"E1": -0.10, "E2": 0.00, "E3": -0.18, "E4": -0.28, "E5": -0.05, "E6": -0.12, "E7": 0.05, "E8": 0.00}

CHALLENGE_MEANS = {
    "F1": 4.05,  # connectivity
    "F2": 4.18,  # devices and data
    "F3": 3.35,  # digital skills
    "F4": 3.92,  # transaction charges
    "F5": 3.18,  # customer trust
    "F6": 3.30,  # cybersecurity
    "F7": 2.95,  # delivery
    "F8": 3.58,  # finance
    "F9": 3.00,  # regulation
    "F10": 3.12,  # time
}

OPEN_COMMENTS = [
    "Internet is unreliable during the rainy season, so orders are delayed.",
    "M-Pesa transaction charges take a big share of small sales.",
    "Older customers still prefer cash and do not trust paying online.",
    "Data bundles are expensive when we post products every day.",
    "Delivering goods outside Nakuru is costly for a small shop.",
    "We need training on how to run the online shop properly.",
    "Customers sometimes place orders on WhatsApp and never collect them.",
    "Fraud attempts on social media make us careful about new buyers.",
    "The fees charged by the online marketplace reduce our profit.",
    "Electricity cuts interrupt posting and order processing.",
    "We do not have enough capital to hold stock for online orders.",
    "Keeping the shop and the online page running needs more staff.",
]


def weighted(choices):
    roll = random.random()
    cumulative = 0.0
    for value, weight in choices:
        cumulative += weight
        if roll <= cumulative:
            return value
    return choices[-1][0]


def clamp(value: float) -> int:
    return int(max(1, min(5, round(value))))


def build_answers(has_online: bool, has_social: bool, has_payments: bool, sector: str):
    online_base = random.gauss(3.35, 0.62) if has_online else random.gauss(1.65, 0.55)
    social_base = random.gauss(3.95, 0.55) if has_social else random.gauss(1.75, 0.55)
    payment_base = random.gauss(4.05, 0.52) if has_payments else random.gauss(1.85, 0.5)

    answers = {}
    for code, offset in B_OFFSETS.items():
        answers[code] = clamp(online_base + offset + random.gauss(0, 0.42))
    for code, offset in C_OFFSETS.items():
        answers[code] = clamp(social_base + offset + random.gauss(0, 0.42))
    for code, offset in D_OFFSETS.items():
        answers[code] = clamp(payment_base + offset + random.gauss(0, 0.42))

    x1 = sum(answers[f"B{i}"] for i in range(1, 7)) / 6
    x2 = sum(answers[f"C{i}"] for i in range(1, 7)) / 6
    x3 = sum(answers[f"D{i}"] for i in range(1, 7)) / 6

    performance = 1.02 + 0.24 * x1 + 0.30 * x2 + 0.21 * x3 + random.gauss(0, 0.38)
    if sector == "food":
        performance -= 0.06
    for code, offset in E_OFFSETS.items():
        answers[code] = clamp(performance + offset + random.gauss(0, 0.35))

    adoption = (x1 + x2 + x3) / 3
    for code, base_mean in CHALLENGE_MEANS.items():
        value = base_mean - 0.10 * (adoption - 2.8) + random.gauss(0, 0.55)
        if sector == "food" and code == "F7":
            value += 0.35
        if sector in ("retail", "food") and code == "F4":
            value += 0.12
        if sector == "manufacturing" and code == "F9":
            value += 0.18
        answers[code] = clamp(value)

    return answers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=140, help="number of synthetic responses")
    parser.add_argument("--db", default=str(BASE / "data" / "demo.db"), help="database file to write")
    parser.add_argument("--force", action="store_true", help="replace existing responses in the target database")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    args = parser.parse_args()

    random.seed(args.seed)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = (BASE / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # The application reads its database path from the environment at import.
    os.environ["MSME_DB"] = str(db_path)
    # Demo data is SQLite-only and must never be written to a production database.
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("POSTGRES_URL", None)
    os.environ.setdefault("MSME_ADMIN_PASSWORD", "nakuru2026")

    import app as survey  # noqa: E402  (import after environment is set)

    application = survey.app
    with application.app_context():
        survey.init_db()
        conn = survey.get_db()
        existing = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        if existing and not args.force:
            print(f"{db_path} already contains {existing} responses.")
            print("Use --force to replace them, or choose another --db path.")
            return
        if existing:
            conn.execute("DELETE FROM responses")
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'responses'")
            conn.commit()

        now = datetime.now(timezone.utc)
        inserted = 0
        for index in range(args.count):
            sector = weighted(SECTORS)
            location = weighted(LOCATIONS)
            role = weighted(ROLES)
            years = weighted(YEARS)
            employees = weighted(EMPLOYEES[sector])

            has_online = random.random() < (0.30 if sector == "food" else 0.46)
            has_social = random.random() < 0.90
            has_payments = random.random() < 0.94
            if not (has_online or has_social or has_payments):
                has_social = True

            channels = []
            if has_online:
                channels.append("online_store")
            if has_social:
                channels.append("social")
            if has_payments:
                channels.append("payments")

            answers = build_answers(has_online, has_social, has_payments, sector)

            days_ago = random.randint(0, 20)
            stamp = now - timedelta(
                days=days_ago,
                hours=random.randint(0, 8),
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )
            duration = int(max(210, min(1500, random.gauss(640, 190))))
            comment = random.choice(OPEN_COMMENTS) if random.random() < 0.58 else ""

            cursor = conn.execute(
                """
                INSERT INTO responses
                    (code, created_at, consent, sector, years, employees, role,
                     location, channels, answers, duration_seconds, open_challenge)
                VALUES ('', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp.isoformat(timespec="seconds"),
                    sector,
                    years,
                    employees,
                    role,
                    location,
                    json.dumps(channels),
                    json.dumps(answers, sort_keys=True),
                    duration,
                    comment,
                ),
            )
            conn.execute(
                "UPDATE responses SET code = ? WHERE id = ?",
                (f"NK-{cursor.lastrowid:04d}", cursor.lastrowid),
            )
            inserted += 1

        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        performance = [
            json.loads(row["answers"])["E1"]
            for row in conn.execute("SELECT answers FROM responses")
        ]
        y_mean = sum(performance) / len(performance) if performance else 0.0

    print(f"Wrote {inserted} demo responses to {db_path}")
    print(f"Responses now in the database: {total}. Average E1 (sales change): {y_mean:.2f}")
    print("")
    print("Preview the dashboard with:")
    print(f'  $env:MSME_DB = "{db_path}"; python app.py')
    print("Then open http://127.0.0.1:8000/admin and sign in with the admin password.")


if __name__ == "__main__":
    main()
