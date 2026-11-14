"""Vercel serverless entrypoint.

Vercel's Python runtime turns every file in ``api/`` into a function and serves
the WSGI callable it finds there. The Flask application lives in the repository
root, so this module only puts the root on ``sys.path`` and re-exports it.

This is for previews and demonstrations only. The serverless filesystem is
read-only apart from a private, per-instance temporary directory, so responses
written to SQLite do not survive: every cold start begins with an empty
database. Use a host with a persistent disk for real fieldwork.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402  (imported after sys.path is adjusted)

# Vercel serves either name; keeping both makes the contract explicit.
application = app
