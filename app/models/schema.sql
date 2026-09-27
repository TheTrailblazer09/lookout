-- Lookout schema. Every fact table carries known_at: the moment the fact
-- became public. That column is what makes the time machine honest.

CREATE TABLE IF NOT EXISTS prices (
  ticker      TEXT,
  date        DATE,
  open        DOUBLE,
  high        DOUBLE,
  low         DOUBLE,
  close       DOUBLE,
  adj_close   DOUBLE,
  volume      BIGINT,
  known_at    TIMESTAMP
);

-- One row per detected event. ticker IS NULL for macro events (they hit
-- every stock), which is why the ticker column is nullable.
CREATE TABLE IF NOT EXISTS events (
  id          TEXT,
  ticker      TEXT,
  type        TEXT,      -- earnings | news | fed | cpi | jobs | oil | technical
  subtype     TEXT,      -- beat/miss/inline, hot/cold, hike/hold/cut, pos/neg
  known_at    TIMESTAMP, -- when it became public
  day0        DATE,      -- first trading day that could react to it
  value       DOUBLE,    -- raw surprise (EPS surprise %, actual - consensus)
  surprise_z  DOUBLE,    -- standardized, comparable across companies
  source      TEXT,
  description TEXT
);

-- Full articles, stored so alerts can cite real headlines.
CREATE TABLE IF NOT EXISTS news_articles (
  id           TEXT,
  url          TEXT,
  source       TEXT,
  source_tier  INTEGER,  -- 1 wire/filing, 2 press release, 3 blog
  published_at TIMESTAMP,
  known_at     TIMESTAMP,
  title        TEXT,
  summary      TEXT,
  body         TEXT,     -- only where the publisher's terms allow it
  cluster_id   TEXT      -- syndicated copies share a cluster
);

-- One row per article per ticker it mentions.
CREATE TABLE IF NOT EXISTS news_scores (
  article_id    TEXT,
  ticker        TEXT,
  entity_score  DOUBLE,  -- how central the company is to the story
  topic         TEXT,
  topic_conf    DOUBLE,
  novelty       DOUBLE,  -- 1 - similarity to the prior 72h
  sentiment     DOUBLE,  -- FinBERT, -1..+1
  relevance     DOUBLE,  -- trained: will this article move the price?
  model_version TEXT
);

CREATE TABLE IF NOT EXISTS sentiment_daily (
  ticker          TEXT,
  date            DATE,
  mood            DOUBLE,  -- relevance-weighted mean sentiment
  headline_count  INTEGER,
  top_article_ids TEXT
);

-- The evidence ledger: one row per stock per past event, with what
-- actually happened afterwards. The fingerprint is only a summary of this.
CREATE TABLE IF NOT EXISTS evidence (
  ticker           TEXT,
  event_id         TEXT,
  event_type       TEXT,
  subtype          TEXT,
  day0             DATE,
  window_days      INTEGER,
  outcome_known_at TIMESTAMP,  -- when the window closed; before this the row is unusable
  surprise_z       DOUBLE,
  ret20_before     DOUBLE,     -- state before the event, for finding analogs
  vol_before       DOUBLE,
  stock_ret        DOUBLE,
  market_ret       DOUBLE,
  abnormal_ret     DOUBLE,     -- market-adjusted (company events only)
  normal_spread    DOUBLE,     -- this stock's usual move over the same span
  move_z           DOUBLE,     -- reaction / normal_spread
  included         BOOLEAN,
  exclusion_reason TEXT,
  description      TEXT,
  alpha            DOUBLE,
  beta             DOUBLE,
  method_version   TEXT
);

-- The fingerprint: evidence summarized per stock x event type x direction.
CREATE TABLE IF NOT EXISTS fingerprint (
  ticker        TEXT,
  event_type    TEXT,
  direction     TEXT,     -- all | pos | neg  (beats vs misses)
  as_of         DATE,     -- snapshots: same key at many as_of dates
  n             INTEGER,
  typical_move  DOUBLE,
  baseline_move DOUBLE,   -- same statistic on non-event windows
  shrunk_move   DOUBLE,   -- pulled toward the cross-stock mean
  ci_low        DOUBLE,
  ci_high       DOUBLE,
  share_up      DOUBLE,
  reliable      BOOLEAN,
  method_version TEXT
);

CREATE TABLE IF NOT EXISTS features (
  ticker  TEXT,
  date    DATE,
  payload TEXT           -- JSON: one key per feature
);

CREATE TABLE IF NOT EXISTS predictions (
  ticker        TEXT,
  date          DATE,
  p_drawdown    DOUBLE,
  drivers       TEXT,     -- JSON: top contributing features
  model_version TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
  id               TEXT,
  as_of            DATE,
  ticker           TEXT,
  severity         TEXT,  -- Storm | Choppy | Heads-up | Calm
  category         TEXT,
  facts            TEXT,  -- JSON fact sheet handed to the narrator
  text             TEXT,  -- JSON: title, why, history
  analog_event_ids TEXT,  -- JSON list of the 5 closest past events
  grounded         BOOLEAN
);

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT UNIQUE,
  password_hash TEXT,
  display_name  TEXT,
  created_at    TIMESTAMP
);

-- portfolio_id is the owning user's id, so holdings are per-user with no
-- extra join. The demo portfolio uses the literal id 'demo'.
CREATE TABLE IF NOT EXISTS holdings (
  portfolio_id TEXT,
  ticker       TEXT,
  shares       DOUBLE
);

CREATE TABLE IF NOT EXISTS feedback (
  alert_id   TEXT,
  vote       TEXT,
  created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
  portfolio_id TEXT,
  payload      TEXT,
  updated_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
  portfolio_id TEXT,
  as_of        DATE,
  payload      TEXT,
  created_at   TIMESTAMP
);