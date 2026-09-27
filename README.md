# Lookout

**Continuous portfolio monitoring that runs on your own machine.**

Four bots watch your stocks around the clock — price moves, earnings, news
and the economy. When something happens, Lookout works out whether it
actually matters *for your holdings*, using each stock's measured history
of reacting to that kind of event, and a small language model running
locally explains it in plain English.

Your holdings never leave your computer. Neither does the model.

Built at HackGT 13 · Oracle of the Deep (ML/AI) track.

---

## What makes it different

Most portfolio apps tell you a stock moved. Lookout answers the harder
question: **does this matter to me, and how do I know?**

- **A fingerprint per stock.** Six years of events, each measured against
  what an ordinary week looks like for that same stock. NVDA moving 8% on
  earnings is normal; KO moving 8% is not, and the app knows the
  difference.
- **An evidence ledger.** Every number is clickable down to the real past
  events behind it — the stock's move, the market's move, and what's left
  over once the market is removed.
- **Alerts ranked by expected impact**, not drama: probability of a sharp
  drop × how much of your portfolio it is × how much this stock typically
  moves on this kind of event.
- **A local model that can't invent numbers.** Every figure in generated
  prose is checked against the model output it was given. If a number
  wasn't in the facts, the text is rejected and rewritten.
- **A time machine.** Any page, any past date, computed from only what was
  public on that day.

---

## Quick start

Requires Python 3.11+ and Node 18+.

```bash
# 1. backend dependencies
pip install -r requirements.txt

# 2. keys (both free; macro and news are optional but recommended)
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FRED_KEY=your_key            # fredaccount.stlouisfed.org/apikeys
export ALPHAVANTAGE_KEY=your_key    # alphavantage.co/support/#api-key

# 3. pull real market data (a few minutes; Yahoo rate-limits earnings)
export FLASK_APP=run:app
flask ingest

# 4. find events, measure them, train, write alerts
flask detect --days 400 --news-fetch
flask build
flask train
flask alerts

# 5. the local model (optional — the app tells you if it's missing)
flask llm --setup

# 6. run it: two terminals
flask run                       # http://127.0.0.1:5000
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Open <http://localhost:5173>. You can explore the demo portfolio without
signing up, or create an account and add your own holdings.

> **One rule:** DuckDB allows a single writer. Stop `flask run` before
> running `ingest`, `detect`, `build`, `train` or `alerts`, and vice versa.

---

## The commands

| Command | What it does | When to rerun |
| --- | --- | --- |
| `flask ingest` | Prices and earnings from Yahoo, macro releases from FRED | Daily, or when adding tickers |
| `flask detect` | Runs the technical and news bots over recent sessions | After ingest |
| `flask build` | Evidence ledger and fingerprint (the event study) | After detect |
| `flask train` | Trains the drawdown risk model, prints the scorecard | Weekly |
| `flask alerts` | Generates and narrates alerts | Daily, or `--replay START:END` |
| `flask llm` | Local model status; `--setup` installs and starts it | Once |

Useful flags: `--as-of 2025-09-10` for a past date, `--skip-prices` to
avoid refetching, `--no-llm` for templates-free instant generation,
`--placebo` on `build` for the sanity check.

**Order matters.** `build` rebuilds the evidence ledger wholesale, so run
it *after* `detect`, or the new events won't be measured.

---

## How it works

Six layers, each reading only from the one above it. Layers 1–5 run
offline; the web app only serves what they wrote.

```
sources     Yahoo (prices, earnings) · FRED (macro) · Alpha Vantage (news)
   ↓
bots        technical · earnings · news · macro        → events
   ↓
store       DuckDB, every row stamped with known_at
   ↓
models      fingerprint · risk classifier · relevance · portfolio maths
   ↓
narrator    severity, then local Qwen writes it — every number checked
   ↓
app         Flask API → Next-style React frontend
```

### The one rule of the data layer

Every fact carries `known_at`: the moment it became public, not the date
it describes. July's CPI is stamped mid-August. An earnings report
released after the close belongs to the *next* trading day. Every query
goes through `visible(table, as_of)`, so replaying a past date cannot see
the future.

### Two event-study methods, on purpose

Company events (earnings, company news) are measured **against the
market**: if a stock fell 6% on a day the market fell 5%, almost nothing
happened to it specifically.

Macro events (Fed, CPI, jobs) are **not** market-adjusted, because on a
Fed day the market itself is the thing reacting — subtracting it would
erase the effect being measured.

Three habits keep the numbers honest: a baseline from random non-event
windows, shrinkage toward the cross-stock average (a mean of six events is
noisy), and bootstrap intervals, with a `reliable` flag only when the
interval clears the baseline.

### The risk model

Labels are scaled per stock: risky means "worse than 1.5× *its own*
five-day volatility", using volatility known before the drop. A fixed
threshold would flag every volatile stock and never a calm one.

Splits are by time with an eight-day purge, because each label looks five
days ahead and neighbouring rows overlap. Probabilities are calibrated,
and `flask train` prints the result beside a volatility-only baseline with
a confidence interval on the lift. **Report whatever it says** — an honest
tie with a stated interval is worth more than an unverifiable claim.

### The narrator

The local model never supplies a number. It receives a JSON fact sheet
built entirely from model output, writes prose, and every numeral is
checked back against the sheet. If a number wasn't there, the offending
figures are named back to the model and it tries again, up to three times.
Failing that, the alert stores no text and the UI says so.

There are no templates imitating the model. Prompts live in
`app/services/prompts/*.md` and are read at call time, so edits apply to
the next alert with no restart.

---

## Layout

```
lookout/
├── run.py                  entry point
├── config.py               all settings, keys, method constants
├── app/
│   ├── models/             data access; base.py holds the as-of gate
│   ├── services/           the thinking: event_study, risk_model, plan,
│   │   ├── bots/           weather, severity, narrator, stock_detail
│   │   ├── sources/        market (Yahoo), macro (FRED), news (AV)
│   │   └── prompts/        editable prompt files
│   ├── controllers/        thin Flask blueprints, one per screen
│   └── utils/              error shape
├── cli/                    flask ingest | detect | build | train | alerts | llm
├── data/                   lookout.duckdb + caches (gitignored)
└── frontend/               React + Vite
    └── src/
        ├── pages/          one per screen
        ├── components/     Shell, Sidebar, charts, scene
        └── lib/            api client, auth, time machine
```

Services never import Flask, which is why the CLI can reuse them.
Controllers stay thin: read args, call one service, return JSON.

---

## The screens

| Screen | What it answers |
| --- | --- |
| **Overview** | How is my portfolio doing, and what needs a look today? |
| **Signal log** | Everything the bots noticed, ranked by how much it moves my money |
| **Chart a course** | What's worth thinking about, and what would it change? |
| **Holdings** | One stock at a time: chart, technicals, fingerprint, evidence, news |
| **Weather report** | Which big forces push my portfolio, and how hard? |
| **What moves my stocks** | The fingerprint heatmap across every holding |

Every page takes `?as_of=YYYY-MM-DD`. The time machine writes it into the
URL, so a replayed day survives a refresh and can be shared as a link.

---

## Troubleshooting

**"Can't open a connection to same database file"** — two processes want
DuckDB. Stop the server before running a CLI job.

**Everything says "Calm"** — sea state is judged against your own
portfolio's normal swing *and* an absolute floor. If it still looks quiet,
you are probably on a quiet day; try a date with a real event.

**Alerts show no write-up** — the local model isn't running. Click **Turn
it on** in the banner, or `flask llm --setup`. Every number still works
without it.

**"No comparable past events"** — the fingerprint has no snapshot at or
before that date. It builds one on demand, but if you just reran `detect`,
run `build` too and reload with `&refresh=1`.

**FRED returns 400** — the key must be 32 lowercase letters and digits.
The error message now says what FRED objected to.

**Yahoo drops tickers** — some symbols fail (renamed, delisted, class
shares). Ingest reports which and moves on.

---

## Honest limits

- Alpha Vantage gives article summaries, not full text; most publishers'
  terms don't allow storing the body. Summaries are usually enough to tell
  whether a story is really about your company.
- Macro "surprises" are measured against the previous reading, not an
  analyst consensus, which needs a paid calendar. The code says so where
  it matters.
- The relevance score is currently a transparent weighted blend, not yet
  the trained model described in the PRD.
- Yahoo provides roughly 4–8 quarters of earnings per ticker, so earnings
  fingerprints rest on few events. That's why intervals and shrinkage are
  shown rather than hidden.
- Nothing here is financial advice, and Lookout never places a trade.

---

## Licence and data

Personal project, built for a hackathon. Market data belongs to its
providers (Yahoo Finance, FRED, Alpha Vantage) and is subject to their
terms.