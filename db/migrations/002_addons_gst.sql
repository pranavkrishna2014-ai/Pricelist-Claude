-- Add-ons and GST.
-- Safe to run more than once. Every column defaults to nothing charged, so
-- bills saved before this ran keep the exact totals they already had.

ALTER TABLE bills
  ADD COLUMN IF NOT EXISTS subtotal     double precision DEFAULT 0,
  ADD COLUMN IF NOT EXISTS addon_label  text COLLATE "C" DEFAULT '',
  ADD COLUMN IF NOT EXISTS addon_type   text COLLATE "C" DEFAULT 'amount',
  ADD COLUMN IF NOT EXISTS addon_value  double precision DEFAULT 0,
  ADD COLUMN IF NOT EXISTS addon_amount double precision DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gst_rate     double precision DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gst_amount   double precision DEFAULT 0;

ALTER TABLE bill_items
  ADD COLUMN IF NOT EXISTS addon_label  text COLLATE "C" DEFAULT '',
  ADD COLUMN IF NOT EXISTS addon_type   text COLLATE "C" DEFAULT 'amount',
  ADD COLUMN IF NOT EXISTS addon_value  double precision DEFAULT 0,
  ADD COLUMN IF NOT EXISTS addon_amount double precision DEFAULT 0;

-- Existing rows get the defaults rather than NULL, so nothing reads as blank.
UPDATE bills SET
  subtotal     = coalesce(subtotal, 0),
  addon_label  = coalesce(addon_label, ''),
  addon_type   = coalesce(addon_type, 'amount'),
  addon_value  = coalesce(addon_value, 0),
  addon_amount = coalesce(addon_amount, 0),
  gst_rate     = coalesce(gst_rate, 0),
  gst_amount   = coalesce(gst_amount, 0);

UPDATE bill_items SET
  addon_label  = coalesce(addon_label, ''),
  addon_type   = coalesce(addon_type, 'amount'),
  addon_value  = coalesce(addon_value, 0),
  addon_amount = coalesce(addon_amount, 0);
