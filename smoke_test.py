"""End-to-end smoke test for the survey system (no extra packages).

Starts the Flask app on a free port against a temporary database, submits a
valid questionnaire and an invalid one, signs in to the dashboard, and checks
the exports.

    python smoke_test.py
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from werkzeug.datastructures import MultiDict

BASE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="msme-smoke-"))
PASSWORD = "smoke-test-password"

os.environ["MSME_DB"] = str(TMP / "smoke.db")
os.environ["MSME_SECRET"] = "smoke-test-secret"
os.environ["MSME_ADMIN_PASSWORD"] = PASSWORD
# The smoke test always uses its own SQLite file, even if the developer's
# shell happens to have a production DATABASE_URL exported.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_URL", None)

import app as survey  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def fetch(path: str, data: dict | None = None):
    url = path if path.startswith("http") else BASE_URL + path
    body = None
    headers = {"User-Agent": "msme-smoke-test"}
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.headers


def token_from(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("no CSRF token in page")
    return match.group(1)


def survey_payload(token: str, complete: bool = True) -> dict:
    fields = {
        "csrf_token": token,
        "consent": "yes",
        "sector": "retail",
        "years": "4to6",
        "employees": "1to9",
        "role": "owner",
        "location": "wakulima",
        "duration_seconds": "640",
        "open_challenge": "Internet is unreliable during the rainy season.",
        "channels": ["online_store", "social", "payments"],
        "needs_software": "yes",
        "software_details": "An online ordering page with M-Pesa checkout.",
    }
    import questions as q

    for position, code in enumerate(q.ALL_ITEMS):
        if not complete and position > 2:
            continue
        fields[code] = str(4 if position % 3 else 5)
    return fields


def main() -> int:
    global BASE_URL

    application = survey.app
    application.config.update(TESTING=True)

    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, application)
    port = server.server_port
    BASE_URL = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Smoke test server: {BASE_URL}")

    print("\nBranching question")
    no_payload = survey_payload("branch-token")
    no_payload["channels"] = "social"
    no_payload["needs_software"] = "no"
    no_payload["software_details"] = "This text must be ignored."
    parsed, errors, missing = survey.parse_submission(MultiDict(no_payload))
    check(
        "No branch needs no details and discards them",
        not errors
        and parsed["needs_software"] == "no"
        and parsed["software_details"] == "",
        str(errors),
    )

    try:
        print("\nPublic questionnaire")
        status, html, headers = fetch("/survey")
        check("GET /survey returns 200", status == 200, str(status))
        check("survey has consent checkbox", 'name="consent"' in html)
        check("survey has all challenge items", 'name="F10"' in html)
        check("survey has software question", 'name="needs_software"' in html)
        check(
            "software details start hidden",
            re.search(r'id="software-details"[^>]*hidden', html) is not None,
        )
        check("CSP header present", "frame-ancestors" in headers.get("Content-Security-Policy", ""))
        token = token_from(html)

        status, html, _ = fetch("/survey", survey_payload(token, complete=False))
        check("incomplete submit rejected", status == 200 and "still need a response" in html, str(status))
        with application.app_context():
            count = survey.get_db().execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        check("invalid submission not stored", count == 0, f"count={count}")

        missing_details = survey_payload(token)
        missing_details["software_details"] = ""
        status, html, _ = fetch("/survey", missing_details)
        check(
            "yes without software details rejected",
            status == 200 and "describe the software" in html.lower(),
            str(status),
        )
        with application.app_context():
            count = survey.get_db().execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        check("incomplete software branch not stored", count == 0, f"count={count}")

        status, body, headers = fetch("/survey", survey_payload(token, complete=True))
        location = headers.get("Location", "")
        check("valid submit redirects", status == 302, str(status))
        check("redirect targets thanks page", location.endswith("/thanks/NK-0001"), location)

        status, html, _ = fetch(location)
        check("thanks page shows code", status == 200 and "NK-0001" in html)
        check("thanks page confirms anonymity", "anonymous" in html.lower())

        print("\nAdmin authentication")
        status, body, headers = fetch("/admin")
        check("dashboard requires sign in", status == 302 and "/admin/login" in headers.get("Location", ""), str(status))

        status, html, _ = fetch("/admin/login")
        check("login page loads", status == 200)
        login_token = token_from(html)
        status, html, _ = fetch(
            "/admin/login",
            {"csrf_token": login_token, "password": "wrong-password"},
        )
        check("wrong password rejected", status == 401 and "Incorrect password" in html, str(status))

        status, body, headers = fetch(
            "/admin/login",
            {"csrf_token": login_token, "password": PASSWORD},
        )
        check("correct password redirects", status == 302, str(status))

        status, html, _ = fetch("/admin")
        check("dashboard loads", status == 200 and "Response monitoring" in html)
        check(
            "dashboard counts the response",
            re.search(r"Collected</span>\s*<strong>1</strong>", html) is not None,
        )
        check(
            "dashboard shows the software request",
            "Software requests" in html and "M-Pesa checkout" in html,
        )
        admin_token = token_from(html)

        print("\nAdmin pages and exports")
        status, html, _ = fetch("/admin/responses")
        check("response register lists the record", status == 200 and "NK-0001" in html)
        check("response register shows software column", "Software" in html)

        status, html, _ = fetch("/admin/responses/NK-0001")
        check("response detail loads", status == 200 and "Response record" in html)
        check("detail renders Likert labels", "Strongly agree" in html and "Increased" in html)
        check(
            "detail shows the software request",
            "Software development request" in html and "M-Pesa checkout" in html,
        )

        status, body, headers = fetch("/admin/export.csv")
        lines = [line for line in body.splitlines() if line]
        check("CSV export returns 200", status == 200, str(status))
        check("CSV has a header row", lines and lines[0].startswith("code,submitted_at"))
        check("CSV includes item columns", "B1" in lines[0] and "F10" in lines[0])
        check(
            "CSV includes the software columns",
            "needs_software" in lines[0] and "software_details" in lines[0],
        )
        check("CSV includes the submitted row", any("NK-0001" in line for line in lines))
        check("CSV includes the software details", "M-Pesa checkout" in body)
        check("CSV has 36 item columns", all(f",{code}," in f",{lines[0]}," for code in
                                             [f"B{i}" for i in range(1, 7)] +
                                             [f"C{i}" for i in range(1, 7)] +
                                             [f"D{i}" for i in range(1, 7)] +
                                             [f"E{i}" for i in range(1, 9)] +
                                             [f"F{i}" for i in range(1, 11)]))

        status, body, headers = fetch("/admin/export-labels.csv")
        check("labelled CSV returns 200", status == 200 and "Retail and wholesale trade" in body)
        check("labelled CSV includes the software request", "M-Pesa checkout" in body)

        status, body, headers = fetch("/admin/codebook.csv")
        check("codebook returns 200", status == 200 and body.startswith("variable,label,type,values,notes"))
        check(
            "codebook documents the software columns",
            "needs_software" in body and "software_details" in body,
        )

        status, body, headers = fetch("/admin/analysis.sps")
        check("SPSS syntax returns 200", status == 200 and "RELIABILITY" in body)
        check("SPSS syntax has regression block", "/DEPENDENT Y_performance" in body)
        check("SPSS syntax labels the software question", "needs_software" in body)

        status, body, headers = fetch("/health")
        check("health endpoint reports one response", status == 200 and json.loads(body)["responses"] == 1)

        print("\nSession handling")
        status, body, headers = fetch(
            "/admin/logout",
            {"csrf_token": admin_token},
        )
        check("logout redirects", status == 302, str(status))
        status, body, headers = fetch("/admin")
        check("dashboard locked after logout", status == 302 and "/admin/login" in headers.get("Location", ""))

        status, body, _ = fetch("/admin/export.csv")
        check("exports require sign in", status == 302)

        status, body, _ = fetch("/thanks/NK-9999")
        check("unknown code returns 404", status == 404)

    finally:
        server.shutdown()
        thread.join(timeout=5)
        shutil.rmtree(TMP, ignore_errors=True)

    print(f"\n{checks - len(failures)} of {checks} checks passed")
    if failures:
        print("Failures:")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
