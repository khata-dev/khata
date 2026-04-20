-- khata canonical schema. SQLite with WAL.
-- Multi-user schema with single-user default (users.id = 1).
-- All timestamps stored as ISO-8601 UTC strings. All monetary values as paise (int).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE,
    display     TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Single-user default row. Multi-user deployments just insert more.
INSERT OR IGNORE INTO users (id, username, display) VALUES (1, 'default', 'You');

-- Encrypted broker credentials. Value is AES-GCM(KHATA_SECRET, json_payload).
CREATE TABLE IF NOT EXISTS broker_credentials (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    broker          TEXT NOT NULL,
    label           TEXT,                  -- optional nickname e.g. "main account"
    encrypted_blob  BLOB NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, broker, label)
);

-- Every raw broker API response lands here first. Lets us reprocess without re-fetching.
CREATE TABLE IF NOT EXISTS broker_events (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    broker          TEXT NOT NULL,
    event_type      TEXT NOT NULL,         -- trade | order | position | holding | postback
    external_id     TEXT,                  -- broker's id for dedup
    payload_json    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    processed_at    TEXT,
    UNIQUE (broker, event_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_broker_events_unprocessed
    ON broker_events (processed_at) WHERE processed_at IS NULL;

-- Normalised executions. One row per fill.
CREATE TABLE IF NOT EXISTS executions (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    broker              TEXT NOT NULL,
    broker_order_id     TEXT,
    broker_trade_id     TEXT NOT NULL,
    symbol              TEXT NOT NULL,                -- display, e.g. NIFTY 24-APR-25 24350 CE
    underlying          TEXT,                         -- NIFTY
    exchange            TEXT NOT NULL,                -- NSE | BSE | NFO | BFO | MCX | CDS
    segment             TEXT NOT NULL,                -- NSE_EQ | NSE_FNO | BSE_EQ | ...
    instrument_type     TEXT NOT NULL,                -- EQ | FUT | OPT
    option_type         TEXT,                         -- CE | PE | NULL
    strike_paise        INTEGER,
    expiry              TEXT,                         -- YYYY-MM-DD
    side                TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    qty                 INTEGER NOT NULL,
    price_paise         INTEGER NOT NULL,
    ts                  TEXT NOT NULL,                -- UTC ISO
    product_type        TEXT,                         -- INTRADAY | CNC | MARGIN | MIS | NRML
    brokerage_paise     INTEGER NOT NULL DEFAULT 0,
    stt_paise           INTEGER NOT NULL DEFAULT 0,
    exch_txn_paise      INTEGER NOT NULL DEFAULT 0,
    sebi_paise          INTEGER NOT NULL DEFAULT 0,
    stamp_paise         INTEGER NOT NULL DEFAULT 0,
    gst_paise           INTEGER NOT NULL DEFAULT 0,
    ipft_paise          INTEGER NOT NULL DEFAULT 0,
    other_paise         INTEGER NOT NULL DEFAULT 0,
    raw_event_id        INTEGER REFERENCES broker_events(id),
    UNIQUE (broker, broker_trade_id)
);

CREATE INDEX IF NOT EXISTS idx_executions_user_ts ON executions (user_id, ts);
CREATE INDEX IF NOT EXISTS idx_executions_symbol ON executions (underlying, expiry, strike_paise);

-- Reconstructed round-trip trades.
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    symbol          TEXT NOT NULL,
    underlying      TEXT,
    instrument_type TEXT NOT NULL,
    option_type     TEXT,
    strike_paise    INTEGER,
    expiry          TEXT,
    direction       TEXT NOT NULL CHECK (direction IN ('LONG','SHORT')),
    qty             INTEGER NOT NULL,
    avg_entry_paise INTEGER NOT NULL,
    avg_exit_paise  INTEGER,
    entry_ts        TEXT NOT NULL,
    exit_ts         TEXT,
    gross_pnl_paise INTEGER,
    fees_paise      INTEGER NOT NULL DEFAULT 0,
    net_pnl_paise   INTEGER,
    r_multiple      REAL,
    duration_s      INTEGER,
    status          TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')) DEFAULT 'OPEN',
    exit_kind       TEXT,                             -- MANUAL | EXPIRY | STOP | TARGET | NULL
    strategy_id     INTEGER REFERENCES strategies(id),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_user_entry ON trades (user_id, entry_ts);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (user_id, status);

-- M-to-M between trades and the executions that formed them.
CREATE TABLE IF NOT EXISTS trade_legs (
    trade_id        INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    execution_id    INTEGER NOT NULL REFERENCES executions(id),
    leg_role        TEXT NOT NULL CHECK (leg_role IN ('ENTRY','EXIT','SCALE_IN','SCALE_OUT')),
    qty_contributed INTEGER NOT NULL,
    PRIMARY KEY (trade_id, execution_id, leg_role)
);

CREATE INDEX IF NOT EXISTS idx_trade_legs_execution ON trade_legs (execution_id);

-- Strategy groups (user-defined: "scalp", "iron condor", "BTST", ...).
CREATE TABLE IF NOT EXISTS strategies (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    kind        TEXT,                                 -- freeform
    rules_md    TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, name)
);

-- Free-form notes. Attached to either a trade OR a date (daily reflection).
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    trade_id    INTEGER REFERENCES trades(id) ON DELETE CASCADE,
    for_date    TEXT,                                 -- YYYY-MM-DD (daily note)
    body_md     TEXT NOT NULL DEFAULT '',
    mood        TEXT,                                 -- calm | tilted | focused | anxious
    conviction  INTEGER,                              -- 1..5
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((trade_id IS NOT NULL) <> (for_date IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_notes_trade ON notes (trade_id);
CREATE INDEX IF NOT EXISTS idx_notes_date ON notes (user_id, for_date);

-- Tags (psych, setup, mistake, ...). Many-to-many with trades.
CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name    TEXT NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('psych','setup','mistake','custom')),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS trade_tags (
    trade_id    INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (trade_id, tag_id)
);

-- Attachments. Belong to a trade OR a note, never both.
CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    trade_id    INTEGER REFERENCES trades(id) ON DELETE CASCADE,
    note_id     INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('image','video','audio','pdf','other')),
    path        TEXT NOT NULL,                        -- relative to KHATA_MEDIA_DIR
    mime        TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    width       INTEGER,                              -- images/video
    height      INTEGER,
    duration_s  REAL,                                 -- audio/video
    caption     TEXT,
    transcript  TEXT,                                 -- populated if whisper enabled
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((trade_id IS NOT NULL) <> (note_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_attachments_trade ON attachments (trade_id);
CREATE INDEX IF NOT EXISTS idx_attachments_note ON attachments (note_id);

-- Pre-trade rules (playbook checklists).
CREATE TABLE IF NOT EXISTS playbooks (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    checklist_json  TEXT NOT NULL,                    -- [{id, label, required}]
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS trade_playbook_runs (
    trade_id    INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    playbook_id INTEGER NOT NULL REFERENCES playbooks(id),
    checks_json TEXT NOT NULL,                        -- [{id, passed, note}]
    score       REAL,
    PRIMARY KEY (trade_id, playbook_id)
);

-- Sync run log for observability.
CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    broker      TEXT NOT NULL,
    kind        TEXT NOT NULL,                        -- backfill | intraday | eod | postback
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    ok          INTEGER,                              -- 0/1, null = running
    stats_json  TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_broker ON sync_runs (broker, started_at DESC);
