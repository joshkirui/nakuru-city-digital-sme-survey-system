# Nakuru SME E-Commerce Survey System

A self-contained web system that operationalises Chapter Three of the research project
**"E-Commerce and the Performance of Selected Small and Medium Enterprises in Nakuru County, Kenya"**.

It collects the six-section questionnaire anonymously, stores responses under a code, monitors
progress towards the 384-response Cochran sample, computes construct scores and a preliminary
regression, and exports data that opens directly in SPSS.

- **Stack:** Python 3.11+, Flask, SQLite. No internet connection is needed at runtime; all
  styling and scripts are local.
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
`MSME_SECRET` to supply your own.

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
```

The test starts the app on a free port with a temporary database and checks 33 behaviours:
the questionnaire, validation, anonymous code generation, sign-in, dashboard, response register,
detail view, CSV exports, codebook, SPSS syntax, health check, logout and 404 handling. It leaves
no files behind.

---

## 4. What the system implements from Chapter Three

| Chapter Three requirement | Implementation |
| --- | --- |
| Target: SMEs in Nakuru CBD and around Wakulima Market using at least one e-commerce channel | Section A asks for location and channels; a submission without a channel is rejected |
| Stratified random sampling of 384 respondents, 430 distributed | Dashboard tracks collected vs 384 target and response rate vs 430 |
| Six-section questionnaire (A background, B online stores, C social commerce, D digital payments, E performance, F challenges) | `questions.py` drives the form: 5 select questions, 1 channel question, 36 Likert items and 1 open question |
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

Items are defined once in `questions.py`. The form, validation, exports, codebook and SPSS
syntax all read from that file, so editing an item there keeps every output consistent.

---

## 5. Researcher dashboard

`/admin` shows:

- **KPIs:** collected vs 384, sample progress, response rate vs 430, complete cases, mean
  completion time, number of open-ended comments.
- **Sample composition:** sector, location, years trading, employees and respondent role.
- **Channel use:** online stores, social commerce and digital payments.
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

SQLite database at `system/data/survey.db` (override with `MSME_DB`).

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
```

Privacy design:

- No name, business name, phone number, email address or IP address is written to the database.
- The response code is derived from the row number, not from the respondent.
- Consent is required and recorded.
- The open-ended answer is free text. Respondents are asked not to include personal details;
  review comments before publishing quotations.
- The dashboard reports aggregates only; the register shows codes only.
- The server access log records IP addresses for each request. For fieldwork, configure the
  reverse proxy or server to discard or rotate logs, or explain their retention in the data
  management plan.

Back up the database by copying `survey.db` (and `survey.db-wal` if present) while the server is
stopped, or use SQLite's `.backup` command. Do not publish the `data/` folder.

---

## 8. Deployment notes

The development server is suitable for a pilot and for the demonstration. For real fieldwork:

1. Set a strong `MSME_ADMIN_PASSWORD` and, preferably, `MSME_SECRET`.
2. Install a production server and serve behind HTTPS:
   ```powershell
   pip install waitress
   waitress-serve --listen=0.0.0.0:8000 app:app
   ```
   Put nginx, Caddy or IIS in front with a TLS certificate, and forward only to the app port.
3. Restrict `/admin` at the proxy if the deployment is public (for example by IP allow-list or
   basic auth in addition to the app password).
4. Set `SESSION_COOKIE_SECURE=True` when HTTPS is in use (edit `create_app` or add a config
   override).
5. Schedule backups and test restoring them.
6. Keep the machine's clock correct; timestamps are stored in UTC and displayed in East Africa
   Time.

SQLite is adequate for a survey of a few hundred responses. It allows one writer at a time, which
is not a constraint at this volume.

---

## 9. Files

```
app.py               Flask app: routes, validation, dashboard, exports
questions.py         single source of truth for items, scales and constructs
stats.py             mean, SD, Cronbach alpha, Pearson, t/F p-values, OLS
seed_demo.py         synthetic demo data in a separate database
smoke_test.py        end-to-end test, 33 checks
requirements.txt
run_demo.ps1         launch the app against data/demo.db
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

---

## 12. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: flask` | `pip install -r requirements.txt` |
| Dashboard shows 0 responses | You are probably on the live database; run `seed_demo.py` and `run_demo.ps1`, or submit through `/survey` |
| `Port 8000 already in use` | Set `$env:PORT = "8001"` before `python app.py` |
| Forgot the admin password | Restart with `$env:MSME_ADMIN_PASSWORD = "new-password"` |
| Signed out unexpectedly | Admin sessions expire after 30 minutes of inactivity |
| Export opens with strange characters in Excel | Use the labelled CSV (UTF-8 BOM) or import the numeric CSV through **Data → From Text/CSV** |
| SPSS shows `submitted_at` as text | Expected: it is an ISO timestamp. Use it for auditing only; analysis uses `duration_seconds` and the item columns |
