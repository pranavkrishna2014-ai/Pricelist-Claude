-- ═══════════════════════════════════════════════════════════════════
--  Mattress Price App — Supabase (PostgreSQL) schema
--  Mirrors the original SQLite schema exactly, including the practice
--  of storing timestamps as 'YYYY-MM-DD HH:MM:SS' text in India time,
--  so existing data migrates verbatim and the UI displays identically.
-- ═══════════════════════════════════════════════════════════════════

-- Helper: the exact equivalent of SQLite's datetime('now','localtime')
CREATE OR REPLACE FUNCTION app_now() RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT to_char(now() AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD HH24:MI:SS')
$$;

CREATE TABLE IF NOT EXISTS settings (
  key   text COLLATE "C" PRIMARY KEY,
  value text COLLATE "C"
);

CREATE TABLE IF NOT EXISTS users (
  id            serial PRIMARY KEY,
  username      text COLLATE "C" NOT NULL UNIQUE,
  password_hash text COLLATE "C" NOT NULL,
  role          text COLLATE "C" NOT NULL DEFAULT 'user',
  created_at    text COLLATE "C" DEFAULT app_now()
);

CREATE TABLE IF NOT EXISTS clients (
  id             serial PRIMARY KEY,
  name           text COLLATE "C" NOT NULL,
  phone          text COLLATE "C" DEFAULT '',
  address        text COLLATE "C" DEFAULT '',
  discount_value double precision DEFAULT 0,
  created_at     text COLLATE "C" DEFAULT app_now()
);

CREATE TABLE IF NOT EXISTS price_list (
  id          serial PRIMARY KEY,
  brand       text COLLATE "C" NOT NULL,
  product     text COLLATE "C" NOT NULL,
  size_code   text COLLATE "C" NOT NULL,
  size_metric text COLLATE "C" NOT NULL,
  thickness   text COLLATE "C" NOT NULL,
  price       double precision NOT NULL DEFAULT 0,
  updated_at  text COLLATE "C" DEFAULT app_now(),
  CONSTRAINT price_list_unique UNIQUE (brand, product, size_code, thickness)
);

CREATE TABLE IF NOT EXISTS bills (
  id              serial PRIMARY KEY,
  bill_no         text COLLATE "C",
  packing_slip_no text COLLATE "C" DEFAULT '',
  client_id       integer,
  client_name     text COLLATE "C" NOT NULL,
  despatch_date   text COLLATE "C" DEFAULT '',
  subtotal        double precision DEFAULT 0,
  addon_label     text COLLATE "C" DEFAULT '',
  addon_type      text COLLATE "C" DEFAULT 'amount',
  addon_value     double precision DEFAULT 0,
  addon_amount    double precision DEFAULT 0,
  gst_rate        double precision DEFAULT 0,
  gst_amount      double precision DEFAULT 0,
  grand_total     double precision DEFAULT 0,
  created_at      text COLLATE "C" DEFAULT app_now(),
  created_by      text COLLATE "C" DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bill_items (
  id             serial PRIMARY KEY,
  bill_id        integer NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  sno            integer,
  brand          text COLLATE "C",
  product        text COLLATE "C",
  size_code      text COLLATE "C",
  size_metric    text COLLATE "C",
  thickness      text COLLATE "C",
  quantity       integer DEFAULT 1,
  unit_price     double precision DEFAULT 0,
  discount_type  text COLLATE "C" DEFAULT 'amount',
  discount_value double precision DEFAULT 0,
  addon_label    text COLLATE "C" DEFAULT '',
  addon_type     text COLLATE "C" DEFAULT 'amount',
  addon_value    double precision DEFAULT 0,
  addon_amount   double precision DEFAULT 0,
  total_value    double precision DEFAULT 0
);

-- Indexes matching the app's real query patterns
CREATE INDEX IF NOT EXISTS idx_bill_items_bill  ON bill_items (bill_id);
CREATE INDEX IF NOT EXISTS idx_bills_created    ON bills (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bills_client     ON bills (client_name);
CREATE INDEX IF NOT EXISTS idx_price_lookup     ON price_list (brand, product, size_code, thickness);
CREATE INDEX IF NOT EXISTS idx_clients_name     ON clients (name);

-- Baseline settings (never overwrite existing values)
INSERT INTO settings (key, value) VALUES ('bill_counter', '1')  ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('company_name', 'My Company') ON CONFLICT (key) DO NOTHING;

-- ── Security ────────────────────────────────────────────────────────
-- Supabase exposes the public schema over its auto-generated REST API.
-- This app never ships a Supabase key to the browser: all access goes
-- through the Netlify function using the direct Postgres connection,
-- which owns these tables and is therefore unaffected by RLS.
-- Enabling RLS with no policies closes the REST API to everyone else.
ALTER TABLE settings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients    ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_list ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills      ENABLE ROW LEVEL SECURITY;
ALTER TABLE bill_items ENABLE ROW LEVEL SECURITY;
