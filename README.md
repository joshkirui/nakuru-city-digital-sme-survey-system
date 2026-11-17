# Nakuru SME E-Commerce Survey System

A self-contained web system that operationalises Chapter Three of the research project
**"E-Commerce and the Performance of Selected Small and Medium Enterprises in Nakuru County, Kenya"**.

It collects the six-section questionnaire anonymously, plus a final branching question on whether
the business needs software developed, stores responses under a code, monitors
progress towards the 384-response Cochran sample, computes construct scores and a preliminary
regression, and exports data that opens directly in SPSS.

- **Stack:** Python 3.11+, Flask, SQLite locally and Supabase PostgreSQL in production. No
  internet connection is needed at runtime for the interface; all styling and scripts are local.
- **Respondents:** `/survey` (mobile-first, about 12 minutes).
- **Researcher:** `/admin` (password-protected dashboard, response register, exports).

---

## 1. Quick start

```powershell
git clone https://github.com/joshkirui/nakuru-city-digital-sme-survey-system.git
cd nakuru-city-digital-sme-survey-system
pip install -r requirements.txt
python app.py
```

Then open:

| Page | URL |
| --- | --- |
| Questionnaire | http://127.0.0.1:8000/survey |
| Researcher sign in | http://127.0.0.1:8000/admin |
| Health check | http://127.0.0.1:8000/health |

The default admin password is `nakuru2026`. **Change it before any fieldwork.**

```powershell
$env:MSME_ADMIN_PASSWORD = "a-long-password-of-your-choice"
python app.py
```

The Flask session secret is generated once and stored in `data/.secret_key`. Set
`MSME_SECRET` to supply your own. For a persistent production database, set `DATABASE_URL` to a
PostgreSQL connection string; otherwise the app uses SQLite. See section 8.

`.env.example` documents the supported variables. The app reads them from the process
environment; it does not load `.env` automatically, so set them in the shell or in the hosting
dashboard.

---

## 2. Preview with demo data

The demo script creates 140 realistic synthetic responses in a separate database, so it never
touches live fieldwork data.

```powershell
python seed_demo.py
.\run_demo.ps1
```

Sign in at http://127.0.0.1:8000/admin. The dashboard should show roughly 140 responses, means
between 2 and 4, Cronbach's alpha above 0.90 and a significant regression model.

To return to the live database, close the server and start `python app.py` again without the
`MSME_DB` variable. Useful options:

```powershell
python seed_demo.py --count 200 --db data/demo.db --force
python seed_demo.py --help
```

---

## 3. Run the tests

```powershell
python smoke_test.py
python storage_test.py
```

`smoke_test.py` starts the app on a free port with a temporary database and checks 46 behaviours:
the questionnaire, validation (including the software-development branch), anonymous code
generation, sign-in, dashboard, response register, detail view, CSV exports, codebook, SPSS syntax,
health check, logout and 404 handling. It leaves no files behind.

`storage_test.py` checks the database adapter: SQLite insert/read/count and schema migration, plus a
simulated PostgreSQL driver for placeholder translation, `RETURNING id`, schema dialect and
connection normalisation. It needs no server and no PostgreSQL package.

---

## 4. What the system implements from Chapter Three

| Chapter Three requirement | Implementation |
| --- | --- |
| Target: SMEs in Nakuru CBD and around Wakulima Market using at least one e-commerce channel | Section A asks for location and channels; a submission without a channel is rejected |
| Stratified random sampling of 384 respondents, 430 distributed | Dashboard tracks collected vs 384 target and response rate vs 430 |
| Six-section questionnaire (A background, B online stores, C social commerce, D digital payments, E performance, F challenges) | `questions.py` drives the form: 5 select questions, 1 channel question, 36 Likert items, 1 open question and a final Yes/No software-development branch |
| Final branching question: does the business need software developed? | Section G requires Yes or No. Yes reveals a required details box; No finishes the questionnaire and ignores the details |
| Five-point Likert scales | Agree scale for B, C, D, F; change scale for E |
| Cronbach's alpha ≥ 0.70 | Computed per construct on the dashboard |
| `Y = β0 + β1X1 + β2X2 + β3X3 + ε` | Preliminary OLS on the dashboard with B, SE, t, p, R², adjusted R², F and n |
| Challenges grouped by TOE, top challenges ranked | Challenge ranking table and technological / organisational / environmental means |
| Anonymity and Data Protection Act, 2019 | No name, business name, phone or email fields; code-only records; consent required; aggregate reporting |

### Instrument layout

| Section | Items | Scale |
| --- | --- | --- |
| A. Background | sector, years, employees, role, location, channels | nominal / multiple choice |
| B. Online stores | B1–B6 | 1 = strongly disagree … 5 = strongly agree |
| C. Social commerce | C1–C6 | 1 = strongly disagree … 5 = strongly agree |
| D. Digital payments | D1–D6 | 1 = strongly disagree … 5 = strongly agree |
| E. Performance | E1–E8 | 1 = strongly decreased … 5 = strongly increased |
| F. Challenges | F1–F10 + open question | 1 = strongly disagree … 5 = strongly agree |
| G. Software development | Yes/No, plus conditional details | nominal / free text |

Items are defined once in `questions.py`. The form, validation, exports, codebook and SPSS
syntax all read from that file, so editing an item there keeps every output consistent.

---

## 5. Researcher dashboard

`/admin` shows:

- **KPIs:** collected vs 384, sample progress, response rate vs 430, complete cases, mean
  completion time, number of open-ended comments and number of software-development requests.
- **Sample composition:** sector, location, years trading, employees and respondent role.
- **Channel use:** online stores, social commerce and digital payments.
- **Software development requests:** each respondent who chose Yes, with the details they supplied.
- **Constructs:** n, mean, standard deviation and Cronbach's alpha for X1, X2, X3 and Y.
- **Correlations:** Pearson matrix for X1–X3 and Y.
- **Regression:** the Chapter Three model with coefficients, standard errors, t, p, R²,
  adjusted R², F and n.
- **Challenges:** the five highest-ranked items, all ten items, and TOE group means.
- **Trend and recent submissions:** responses per day for 14 days, latest records, and
  item-level means inside collapsible sections.
- **Data-quality checks:** fast completions, comments available for coding, median duration.

All statistics are descriptive or preliminary. The dashboard is a monitoring aid, not a
substitute for the SPSS analysis plan.

`/admin/responses` lists every record with filters by code and sector. Each code opens a
read-only detail page that renders the chosen Likert label for every item.

---

## 6. Exports

| Export | File | Use |
| --- | --- | --- |
| Numeric CSV | `nakuru_survey_YYYY-MM-DD.csv` | SPSS / Stata / R. Categorical answers are numeric codes; items are 1–5; composites are 4-decimal means |
| Labelled CSV | `nakuru_survey_labelled_YYYY-MM-DD.csv` | Reading in Excel; UTF-8 with BOM |
| Codebook | `nakuru_codebook.csv` | Variable names, labels, types, value codes and notes |
| SPSS syntax | `nakuru_analysis.sps` | Variable labels, value labels, descriptives, frequencies, reliability, correlations and regression |

Both CSV files end with `needs_software` (1 = yes, 0 = no in the numeric file; Yes/No in the
labelled file) and `software_details`. The codebook and SPSS syntax document both variables.

### SPSS workflow

1. In SPSS: **File → Open → Data**, select `nakuru_survey_YYYY-MM-DD.csv`.
2. Confirm that the first row is treated as variable names and that the decimal separator is a
   full stop.
3. Open and run `nakuru_analysis.sps` (**File → Open → Syntax**, then **Run → All**).
4. Check the reliability table against the 0.70 threshold.
5. Inspect the regression output and run the assumption tests listed in Chapter Three
   (Shapiro–Wilk, residual plots, Breusch–Pagan, VIF, Durbin–Watson). The dashboard does not
   replace these checks.

The `.sps` file assumes the CSV is already open as the active dataset. It is generated from the
same item definitions as the questionnaire, so it stays aligned if items are edited.

---

## 7. Data model and privacy

By default, a SQLite database at `system/data/survey.db` (override with `MSME_DB`). When
`DATABASE_URL` is set, the same schema is created in PostgreSQL instead.

```
responses
  id                internal row id
  code              NK-0001, NK-0002, ... (the only identifier)
  created_at        ISO 8601 UTC timestamp
  consent           1 = informed consent given
  sector, years, employees, role, location
  channels          JSON list of channels used
  answers           JSON object: item code -> 1..5
  duration_seconds  time taken in the browser
  open_challenge    optional free text, limited to 2,000 characters
  needs_software    yes/no; the final branching question
  software_details  free text, required when needs_software = yes, limited to 2,000 characters
```

New columns are added automatically at startup, so an existing database keeps its responses when
the questionnaire changes.

Privacy design:

- No name, business name, phone number, email address or IP address is written to the database.
- The response code is derived from the row number, not from the respondent.
- Consent is required and recorded.
- The open-ended answer and the software details are free text. Respondents are asked not to
  include personal details; review both before publishing quotations or sharing requests.
- The dashboard reports aggregates only; the register shows codes only.
- The server access log records IP addresses for each request. For fieldwork, configure the
  reverse proxy or server to discard or rotate logs, or explain their retention in the data
  management plan.

Back up the database by copying `survey.db` (and `survey.db-wal` if present) while the server is
stopped, or use SQLite's `.backup` command. On PostgreSQL, use the provider's automated backups or
`pg_dump`. Do not publish the `data/` folder or a database connection string.

`.gitignore` excludes `data/`, generated exports (`nakuru_*.csv`, `nakuru_analysis.sps`), Python
caches, virtual environments and local secrets (`.env`, `.secret_key`), so response data cannot
be committed to the repository by accident.

---

## 8. Deployment notes

### Local or a persistent-disk server

The default storage is SQLite at `data/survey.db`. For a pilot, a demonstration, or a single
machine that persists:

1. Set a strong `MSME_ADMIN_PASSWORD` and, preferably, `MSME_SECRET`.
2. Install a production server and serve behind HTTPS:
   ```powershell
   pip install waitress
   waitress-serve --listen=0.0.0.0:8000 app:app
   ```
   Put nginx, Caddy or IIS in front with a TLS certificate, and forward only to the app port.
3. Restrict `/admin` at the proxy if the deployment is public (for example by IP allow-list or
   basic auth in addition to the app password).
4. `SESSION_COOKIE_SECURE` is set automatically when `VERCEL` is present. On any other HTTPS host,
   set `MSME_HTTPS=1`.
5. Back up the database file (and its `-wal`/`-shm` siblings) on a schedule and test restoring.
6. Keep the machine's clock correct; timestamps are stored in UTC and displayed in East Africa
   Time.

SQLite is adequate for a survey of a few hundred responses. It allows one writer at a time, which
is not a constraint at this volume.

### Vercel + Supabase (recommended for fieldwork)

Vercel detects Flask directly: it looks for a top-level `app` in `app.py`, `index.py`, `server.py`,
`main.py`, `wsgi.py`, or `asgi.py`. No custom entrypoint and no rewrites are needed; `vercel.json`
only raises the function timeout.

Vercel's filesystem is read-only apart from a private, per-instance `/tmp`, so SQLite there is
disposable. The app therefore uses PostgreSQL whenever `DATABASE_URL` is set, and falls back to a
temporary SQLite file only for a preview. Deploying without `DATABASE_URL` is allowed, but the
startup log warns that responses will disappear.

#### 1. Create the Supabase database

1. Create a project at [supabase.com](https://supabase.com) and wait for provisioning to finish.
2. Open **Project Settings → Database → Connection string**.
3. Choose **Transaction pooler** (port `6543`) and copy the URI. It looks like:
   ```
   postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
4. Replace `[YOUR-PASSWORD]` with the database password. If the password contains `@`, `#`, `/`,
   `:` or `%`, URL-encode it (`@` becomes `%40`, for example).
5. Keep `sslmode=require`. The app also adds it automatically for `*.supabase.com` and
   `*.supabase.co` hosts if it is missing. If the copied URI contains `?pgbouncer=true`, leave it
   in: the app strips parameters that libpq does not understand.

Use the **transaction pooler** (port `6543`), not the direct connection. Supabase's direct
database host is IPv6-only, and Vercel functions may not have IPv6. Session mode (port `5432`)
also works but holds a connection for each request and consumes more of the pool.

#### 2. Configure Vercel

1. In Vercel, open **Project → Settings → Environment Variables** and set these for Production and
   Preview:
   - `DATABASE_URL` — the Supabase transaction-pooler URI.
   - `MSME_SECRET` — 64 random hex characters. Without it each instance signs cookies with a
     different key, and researcher sign-in fails intermittently.
   - `MSME_ADMIN_PASSWORD` — a strong password; otherwise `/admin` uses the public demo password.
2. Redeploy. Environment changes only apply to a new deployment.
3. Open **Logs → Runtime Logs** and look for a line like
   `msme startup: platform=vercel backend=postgres host=aws-0-...pooler.supabase.com/postgres secret=environment admin_password=environment`.
4. Open `/health`; it should return `{"status":"ok","responses":0}`.
5. Submit one test response, refresh `/health`, and confirm the count increments. Then sign in to
   `/admin` and export the response to prove the round trip.

The first request creates the `responses` table in the `public` schema
(`CREATE TABLE IF NOT EXISTS`), so no migration tool is required.

#### Notes and limits

- The adapter disables prepared statements (`prepare_threshold=None`) because Supabase's
  transaction pooler cannot keep them between transactions. This is harmless on session or direct
  connections.
- Supabase free projects pause after a period of inactivity. Wake the project before fieldwork and
  check the current limits in the Supabase dashboard.
- `DATABASE_URL` contains the database password. Keep it in Vercel's environment variables, never in
  the repository or browser code.
- If authentication fails, reset the database password in Supabase, URL-encode any special
  characters, and update `DATABASE_URL`.
- `DATABASE_URL` is honoured locally too, so the Supabase path can be tested before deploying.
  Leave it unset to keep using SQLite.
- If you later host on a VPS with a persistent disk, SQLite remains supported and needs no
  Supabase account.

---

## 9. Files

```
app.py               Flask app: routes, validation, dashboard, exports
questions.py         single source of truth for items, scales and constructs
stats.py             mean, SD, Cronbach alpha, Pearson, t/F p-values, OLS
storage.py           SQLite/PostgreSQL adapter and schema
storage_test.py      adapter tests (SQLite and simulated PostgreSQL)
seed_demo.py         synthetic demo data in a separate database
smoke_test.py        end-to-end test, 46 checks
requirements.txt
.env.example         documented environment variables (copy to .env locally)
run_demo.ps1         launch the app against data/demo.db
vercel.json          Vercel function timeout (Flask is auto-detected from app.py)
templates/           base, survey, thanks, login, dashboard, responses, detail, error
static/              offline CSS, progress script, favicon
screenshots/         dashboard.png and survey.png captured from the demo data
data/                created at runtime: survey.db, demo.db, .secret_key
```

`data/` is created automatically and is excluded from version control, so a fresh clone starts
with an empty live database. There is no build step and no CDN dependency.

---

## 10. Customising

- **Change wording or add an item:** edit `SECTIONS` in `questions.py`. Also add the item code to
  the relevant group in `CONSTRUCTS` or `TOE_GROUPS`, and update `total_fields` if the number of
  demographic questions changes. The form, CSV, codebook and SPSS syntax follow automatically.
- **Change the sample target:** edit `TARGET` and `DISTRIBUTED` in `create_app`.
- **Change the alpha threshold:** edit `ALPHA_LEVEL`.
- **Colours and typography:** `static/style.css` (design tokens at the top).
- **Add a Kikuyu or Kiswahili version:** duplicate `SECTIONS` with translated text and add a
  language switch; the export codes remain unchanged.

---

## 11. Known limitations

- The regression is a monitoring estimate: it uses listwise deletion and does not run the full
  assumption-testing suite. Report the SPSS output in Chapter Four.
- Factor analysis (KMO, Bartlett, EFA) is not implemented; do it in SPSS on the pilot data.
- The questionnaire requires an internet connection to the server. It is not an offline
  progressive web app.
- There is no email or SMS reminder system and no respondent login, by design (anonymity).
- The open-ended text is not coded automatically; export it and code themes manually.
- The system assumes a purely quantitative design, as specified in Chapter Three.
- On Vercel, Supabase (or another PostgreSQL host) is required: without `DATABASE_URL` the app uses
  a temporary SQLite file and responses are lost when the instance is recycled. See section 8.
- PostgreSQL adds a network dependency. If the database provider is unreachable, submissions fail
  until it recovers; SQLite on a persistent disk has no such dependency.

---

## 12. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: flask` | `pip install -r requirements.txt` |
| `ModuleNotFoundError: psycopg` | `pip install -r requirements.txt` (needed when `DATABASE_URL` is set) |
| Dashboard shows 0 responses | You are probably on the live database; run `seed_demo.py` and `run_demo.ps1`, or submit through `/survey` |
| Vercel returns `FUNCTION_INVOCATION_FAILED` | Open **Logs → Runtime Logs** and read the traceback. The `msme startup:` line shows the detected backend, database host and credential sources |
| Responses vanish on Vercel | `DATABASE_URL` is not set, or the deployment predates it. Set it and redeploy; see section 8 |
| `psycopg.OperationalError` on Vercel | Check the Supabase transaction-pooler URI, the database password, `sslmode=require`, the pooler region, and whether the project is paused |
| `invalid URI query parameter: "pgbouncer"` | Use the latest code (it strips ORM-only parameters), or remove `&pgbouncer=true` from `DATABASE_URL` |
| `password authentication failed for user "postgres..."` | Reset the database password in Supabase, URL-encode special characters, and update `DATABASE_URL` |
| `Tenant or user not found` | Wrong pooler username or region; copy the Transaction pooler URI again from Supabase |
| `too many connections` | Use the transaction pooler (port 6543), not the direct or session connection |
| `prepared statement ... does not exist` | The transaction pooler cannot keep prepared statements; use the latest code, which disables them |
| `Port 8000 already in use` | Set `$env:PORT = "8001"` before `python app.py` |
| Forgot the admin password | Restart with `$env:MSME_ADMIN_PASSWORD = "new-password"` |
| Signed out unexpectedly | Admin sessions expire after 30 minutes of inactivity |
| Export opens with strange characters in Excel | Use the labelled CSV (UTF-8 BOM) or import the numeric CSV through **Data → From Text/CSV** |
| SPSS shows `submitted_at` as text | Expected: it is an ISO timestamp. Use it for auditing only; analysis uses `duration_seconds` and the item columns |
