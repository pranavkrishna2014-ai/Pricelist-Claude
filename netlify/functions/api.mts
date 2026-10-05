// ═══════════════════════════════════════════════════════════════════════════
//  Mattress Price App — API
//  A faithful port of the original Flask app.py to a Netlify Function
//  backed by Supabase Postgres.
//
//  Every route keeps its original path, request shape, response shape and
//  error message, so the existing front-end works without modification.
// ═══════════════════════════════════════════════════════════════════════════

import type { Config, Context } from '@netlify/functions';
import postgres from 'postgres';
import bcrypt from 'bcryptjs';
import { SignJWT, jwtVerify } from 'jose';
import { createHash } from 'node:crypto';
import ExcelJS from 'exceljs';

export const config: Config = {
  path: ['/api/*', '/print/bills'],
};

// ───────────────────────────── Database ─────────────────────────────
// One connection is reused across warm invocations. `prepare: false` is
// required because Supabase's pooler runs in transaction mode.

let _sql: ReturnType<typeof postgres> | null = null;

function db() {
  if (!_sql) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error('DATABASE_URL is not set');
    // Supabase requires TLS; a local test database usually does not.
    const useSsl = !/sslmode=disable/.test(url);
    _sql = postgres(url, {
      ssl: useSsl ? 'require' : false,
      prepare: false,
      max: 1,
      idle_timeout: 20,
      connect_timeout: 15,
    });
  }
  return _sql;
}

// SQLite's datetime('now','localtime') — the app has always stored wall-clock
// India time as text, and the front-end prints it verbatim. Keep it that way.
function appNow(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).formatToParts(new Date());
  const g = (t: string) => parts.find(p => p.type === t)!.value;
  return `${g('year')}-${g('month')}-${g('day')} ${g('hour')}:${g('minute')}:${g('second')}`;
}

// ───────────────────────────── Responses ─────────────────────────────

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

const ERR_NOT_LOGGED_IN = { error: 'Not logged in' };
const ERR_NOT_ADMIN     = { error: 'Admin access required' };

// ───────────────────────────── Sessions ─────────────────────────────
// Flask kept a signed cookie; so do we, as a JWT. Same idea, same
// browser-session lifetime, no server-side state — which matters because
// serverless functions have nowhere to keep it.

const SESSION_COOKIE = 'session';

function secretKey(): Uint8Array {
  const s = process.env.SESSION_SECRET;
  if (!s || s.length < 16) {
    throw new Error('SESSION_SECRET is not set (needs at least 16 characters)');
  }
  return new TextEncoder().encode(s);
}

type User = { username: string; role: string };

// Netlify always serves over HTTPS, so `Secure` is right in production. Deriving
// it from the actual request keeps a plain-HTTP local run working too.
function isSecure(req: Request): boolean {
  const proto = req.headers.get('x-forwarded-proto');
  if (proto) return proto.split(',')[0].trim() === 'https';
  try { return new URL(req.url).protocol === 'https:'; } catch { return true; }
}

async function issueCookie(user: User, secure: boolean): Promise<string> {
  const token = await new SignJWT({ username: user.username, role: user.role })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('30d')
    .sign(secretKey());
  // No Max-Age: the cookie dies with the browser session, matching Flask.
  return `${SESSION_COOKIE}=${token}; HttpOnly;${secure ? ' Secure;' : ''} SameSite=Lax; Path=/`;
}

function clearCookie(secure: boolean): string {
  return `${SESSION_COOKIE}=; HttpOnly;${secure ? ' Secure;' : ''} SameSite=Lax; Path=/; Max-Age=0`;
}

function readCookie(req: Request, name: string): string | null {
  const header = req.headers.get('cookie');
  if (!header) return null;
  for (const part of header.split(';')) {
    const idx = part.indexOf('=');
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) return part.slice(idx + 1).trim();
  }
  return null;
}

async function currentUser(req: Request): Promise<User | null> {
  const token = readCookie(req, SESSION_COOKIE);
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secretKey());
    if (!payload.role || !payload.username) return null;
    return { username: String(payload.username), role: String(payload.role) };
  } catch {
    return null;
  }
}

// ───────────────────────────── Passwords ─────────────────────────────
// The old app stored unsalted SHA-256. We verify either form, and quietly
// re-hash to bcrypt the first time each person signs in, so nobody has to
// change their password and nothing breaks mid-migration.

function sha256(p: string): string {
  return createHash('sha256').update(p.trim(), 'utf8').digest('hex');
}

function hashPw(p: string): string {
  return bcrypt.hashSync(p.trim(), 10);
}

function verifyPw(plain: string, stored: string): { ok: boolean; needsUpgrade: boolean } {
  if (!stored) return { ok: false, needsUpgrade: false };
  if (stored.startsWith('$2a$') || stored.startsWith('$2b$') || stored.startsWith('$2y$')) {
    return { ok: bcrypt.compareSync(plain.trim(), stored), needsUpgrade: false };
  }
  // Legacy SHA-256 hex
  const ok = sha256(plain) === stored;
  return { ok, needsUpgrade: ok };
}

// ───────────────────────────── Helpers ─────────────────────────────

async function body(req: Request): Promise<any> {
  try {
    const text = await req.text();
    if (!text) return {};
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function num(v: unknown, fallback = 0): number {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''));
  return Number.isFinite(n) ? n : fallback;
}

function str(v: unknown, fallback = ''): string {
  return v === undefined || v === null ? fallback : String(v);
}

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&#34;').replace(/'/g, '&#39;');   // &#34; matches Jinja's escaping
}

function money(n: unknown): string {
  return num(n).toFixed(2);
}

// What a line charges per piece on top of the net price.
function savedAddon(it: { addon_amount?: unknown }): number {
  return num(it.addon_amount);
}

// The per-piece price a saved line's stored total came from, so the printed
// Net + Add-on, times Qty, always equals the printed Total.
function savedNet(it: { quantity?: unknown; total_value?: unknown; addon_amount?: unknown }): number {
  const qty = num(it.quantity);
  if (qty <= 0) return 0;
  return Math.max(0, num(it.total_value) / qty - savedAddon(it));
}

// 18 prints as "18", 2.5 as "2.5" — no trailing zeros on a tax rate.
function rateStr(n: unknown): string {
  return String(Math.round(num(n) * 100) / 100);
}

// ═══════════════════════════════════════════════════════════════════════════
//  Router
// ═══════════════════════════════════════════════════════════════════════════

export default async function handler(req: Request, _context: Context) {
  let sql: ReturnType<typeof postgres>;
  try {
    sql = db();
  } catch (e: any) {
    return json({ error: `Server not configured: ${e.message}` }, 500);
  }

  const url    = new URL(req.url);
  const path   = url.pathname.replace(/\/+$/, '') || '/';
  const method = req.method.toUpperCase();
  const seg    = path.split('/').filter(Boolean);
  const qs     = url.searchParams;

  const user = await currentUser(req);
  const notLoggedIn = () => (user ? null : json(ERR_NOT_LOGGED_IN, 401));
  const notAdmin    = () => (user?.role === 'admin' ? null : json(ERR_NOT_ADMIN, 403));

  // Match a method + path pattern (":name" captures a segment)
  function m(wantMethod: string, pattern: string): Record<string, string> | null {
    if (method !== wantMethod) return null;
    const ps = pattern.split('/').filter(Boolean);
    if (ps.length !== seg.length) return null;
    const out: Record<string, string> = {};
    for (let i = 0; i < ps.length; i++) {
      if (ps[i].startsWith(':')) out[ps[i].slice(1)] = decodeURIComponent(seg[i]);
      else if (ps[i] !== seg[i]) return null;
    }
    return out;
  }
  // Routes declared <int:x> in Flask only matched integers; keep that.
  const asInt = (v: string): number | null => (/^\d+$/.test(v) ? parseInt(v, 10) : null);

  let p: Record<string, string> | null;

  try {
    // ───────────────────────── Auth ─────────────────────────

    if (m('POST', '/api/login')) {
      const data     = await body(req);
      const username = str(data.username).trim();
      const pw       = str(data.password);
      const rows = await sql`
        SELECT id, role, password_hash FROM users WHERE username = ${username}`;
      const row = rows[0];
      if (row) {
        const { ok, needsUpgrade } = verifyPw(pw, row.password_hash);
        if (ok) {
          if (needsUpgrade) {
            // Silent SHA-256 → bcrypt upgrade on first successful login
            try {
              await sql`UPDATE users SET password_hash = ${hashPw(pw)} WHERE id = ${row.id}`;
            } catch { /* a failed upgrade must never block a valid login */ }
          }
          const cookie = await issueCookie({ username, role: row.role }, isSecure(req));
          return json({ success: true, role: row.role, username }, 200, { 'Set-Cookie': cookie });
        }
      }
      return json({ error: 'Incorrect username or password' }, 401);
    }

    if (m('POST', '/api/logout')) {
      return json({ success: true }, 200, { 'Set-Cookie': clearCookie(isSecure(req)) });
    }

    if (m('GET', '/api/me')) {
      return json({ role: user?.role ?? null, username: user?.username ?? null });
    }

    // ───────────────────────── Users ─────────────────────────

    if (m('GET', '/api/users')) {
      const bad = notAdmin(); if (bad) return bad;
      const rows = await sql`
        SELECT id, username, role, created_at FROM users ORDER BY role DESC, username`;
      return json(rows);
    }

    if (m('POST', '/api/users')) {
      const bad = notAdmin(); if (bad) return bad;
      const data     = await body(req);
      const username = str(data.username).trim();
      const pw       = str(data.password);
      const role     = str(data.role, 'user');
      if (!username)          return json({ error: 'Username is required' }, 400);
      if (pw.length < 4)      return json({ error: 'Password must be at least 4 characters' }, 400);
      if (!['admin', 'user'].includes(role))
                              return json({ error: 'Role must be admin or user' }, 400);
      try {
        const rows = await sql`
          INSERT INTO users (username, password_hash, role)
          VALUES (${username}, ${hashPw(pw)}, ${role})
          RETURNING id, username, role, created_at`;
        return json(rows[0]);
      } catch {
        return json({ error: 'Username already exists' }, 400);
      }
    }

    if ((p = m('PUT', '/api/users/:id/password'))) {
      const bad = notAdmin(); if (bad) return bad;
      const uid = asInt(p.id); if (uid === null) return json({ error: 'Not found' }, 404);
      const data = await body(req);
      const pw   = str(data.password);
      if (pw.length < 4) return json({ error: 'Password must be at least 4 characters' }, 400);
      await sql`UPDATE users SET password_hash = ${hashPw(pw)} WHERE id = ${uid}`;
      return json({ success: true });
    }

    if ((p = m('DELETE', '/api/users/:id'))) {
      const bad = notAdmin(); if (bad) return bad;
      const uid = asInt(p.id); if (uid === null) return json({ error: 'Not found' }, 404);
      const rows = await sql`SELECT username, role FROM users WHERE id = ${uid}`;
      if (!rows[0]) return json({ error: 'User not found' }, 404);
      if (rows[0].username === user!.username)
        return json({ error: 'You cannot delete your own account' }, 400);
      const [{ count }] = await sql`SELECT COUNT(*)::int AS count FROM users WHERE role = 'admin'`;
      if (rows[0].role === 'admin' && count <= 1)
        return json({ error: 'Cannot delete the last admin account' }, 400);
      await sql`DELETE FROM users WHERE id = ${uid}`;
      return json({ success: true });
    }

    // ───────────────────────── Price list ─────────────────────────

    if (m('GET', '/api/products')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const rows = await sql`
        SELECT DISTINCT brand, product FROM price_list ORDER BY brand, product`;
      const result: Record<string, string[]> = {};
      for (const r of rows) {
        if (!result[r.brand]) result[r.brand] = [];
        if (!result[r.brand].includes(r.product)) result[r.brand].push(r.product);
      }
      return json(result);
    }

    if (m('GET', '/api/sizes')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const rows = await sql`
        SELECT DISTINCT size_code, size_metric FROM price_list
        WHERE brand = ${qs.get('brand') ?? ''} AND product = ${qs.get('product') ?? ''}
        ORDER BY size_code`;
      return json(rows.map(r => ({ code: r.size_code, metric: r.size_metric })));
    }

    if (m('GET', '/api/thicknesses')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const rows = await sql`
        SELECT thickness, price FROM price_list
        WHERE brand = ${qs.get('brand') ?? ''} AND product = ${qs.get('product') ?? ''}
          AND size_code = ${qs.get('size_code') ?? ''}
        ORDER BY thickness`;
      return json(rows.map(r => ({ thickness: r.thickness, price: r.price })));
    }

    if (m('GET', '/api/price')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const rows = await sql`
        SELECT price FROM price_list
        WHERE brand = ${qs.get('brand') ?? ''} AND product = ${qs.get('product') ?? ''}
          AND size_code = ${qs.get('size_code') ?? ''} AND thickness = ${qs.get('thickness') ?? ''}`;
      return json({ price: rows[0] ? rows[0].price : 0 });
    }

    if (m('GET', '/api/pricelist/export')) {
      const bad = notAdmin(); if (bad) return bad;
      return await exportPricelist(sql);
    }

    if (m('POST', '/api/pricelist/import')) {
      const bad = notAdmin(); if (bad) return bad;
      return await importPricelist(sql, req);
    }

    if (m('GET', '/api/pricelist')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const brand   = qs.get('brand')   ?? '';
      const product = qs.get('product') ?? '';
      const rows = await sql`
        SELECT * FROM price_list
        WHERE TRUE
          ${brand   ? sql`AND brand = ${brand}`     : sql``}
          ${product ? sql`AND product = ${product}` : sql``}
        ORDER BY brand, product, size_code, thickness`;
      return json(rows);
    }

    if (m('POST', '/api/pricelist')) {
      const bad = notAdmin(); if (bad) return bad;
      const d = await body(req);
      if (d.brand === undefined || d.product === undefined || d.size_code === undefined ||
          d.size_metric === undefined || d.thickness === undefined) {
        return json({ error: 'Missing required fields' }, 400);
      }
      try {
        const rows = await sql`
          INSERT INTO price_list (brand, product, size_code, size_metric, thickness, price)
          VALUES (${str(d.brand)}, ${str(d.product)}, ${str(d.size_code)},
                  ${str(d.size_metric)}, ${str(d.thickness)}, ${num(d.price)})
          RETURNING *`;
        return json(rows[0]);
      } catch (e: any) {
        return json({ error: str(e.message, 'Could not add entry') }, 400);
      }
    }

    if ((p = m('PUT', '/api/pricelist/:id/full'))) {
      const bad = notAdmin(); if (bad) return bad;
      const pid = asInt(p.id); if (pid === null) return json({ error: 'Not found' }, 404);
      const d = await body(req);
      if (d.brand === undefined || d.product === undefined || d.size_code === undefined ||
          d.size_metric === undefined || d.thickness === undefined) {
        return json({ error: 'Missing required fields' }, 400);
      }
      try {
        const rows = await sql`
          UPDATE price_list SET brand = ${str(d.brand)}, product = ${str(d.product)},
            size_code = ${str(d.size_code)}, size_metric = ${str(d.size_metric)},
            thickness = ${str(d.thickness)}, price = ${num(d.price)}, updated_at = ${appNow()}
          WHERE id = ${pid} RETURNING *`;
        return json(rows[0] ?? null);
      } catch (e: any) {
        return json({ error: str(e.message, 'Could not update entry') }, 400);
      }
    }

    if ((p = m('PUT', '/api/pricelist/:id'))) {
      const bad = notAdmin(); if (bad) return bad;
      const pid = asInt(p.id); if (pid === null) return json({ error: 'Not found' }, 404);
      const d = await body(req);
      await sql`
        UPDATE price_list SET price = ${num(d.price)}, updated_at = ${appNow()} WHERE id = ${pid}`;
      return json({ success: true });
    }

    if ((p = m('DELETE', '/api/pricelist/:id'))) {
      const bad = notAdmin(); if (bad) return bad;
      const pid = asInt(p.id); if (pid === null) return json({ error: 'Not found' }, 404);
      await sql`DELETE FROM price_list WHERE id = ${pid}`;
      return json({ success: true });
    }

    // ───────────────────────── Clients ─────────────────────────

    if (m('GET', '/api/clients')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const q = qs.get('q') ?? '';
      const rows = q
        ? await sql`SELECT * FROM clients WHERE name ILIKE ${'%' + q + '%'} ORDER BY name`
        : await sql`SELECT * FROM clients ORDER BY name`;
      return json(rows);
    }

    if (m('POST', '/api/clients')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const d = await body(req);
      if (d.name === undefined) return json({ error: 'Name is required' }, 400);
      const rows = await sql`
        INSERT INTO clients (name, phone, address, discount_value)
        VALUES (${str(d.name)}, ${str(d.phone)}, ${str(d.address)}, ${num(d.discount_value)})
        RETURNING *`;
      return json(rows[0]);
    }

    if ((p = m('PUT', '/api/clients/:id'))) {
      const bad = notLoggedIn(); if (bad) return bad;
      const cid = asInt(p.id); if (cid === null) return json({ error: 'Not found' }, 404);
      const d = await body(req);
      if (d.name === undefined) return json({ error: 'Name is required' }, 400);
      const rows = await sql`
        UPDATE clients SET name = ${str(d.name)}, phone = ${str(d.phone)},
          address = ${str(d.address)}, discount_value = ${num(d.discount_value)}
        WHERE id = ${cid} RETURNING *`;
      return json(rows[0] ?? null);
    }

    if ((p = m('DELETE', '/api/clients/:id'))) {
      const bad = notAdmin(); if (bad) return bad;
      const cid = asInt(p.id); if (cid === null) return json({ error: 'Not found' }, 404);
      await sql`DELETE FROM clients WHERE id = ${cid}`;
      return json({ success: true });
    }

    // ───────────────────────── Bills ─────────────────────────

    if (m('GET', '/api/bills/next_no')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const rows = await sql`SELECT value FROM settings WHERE key = 'bill_counter'`;
      const counter = parseInt(str(rows[0]?.value, '1'), 10) || 1;
      return json({ bill_no: `BILL-${String(counter).padStart(4, '0')}` });
    }

    if (m('GET', '/api/bills')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const from   = qs.get('from')   ?? '';
      const to     = qs.get('to')     ?? '';
      const client = qs.get('client') ?? '';
      const slip   = qs.get('slip')   ?? '';
      const rows = await sql`
        SELECT * FROM bills
        WHERE TRUE
          ${from   ? sql`AND LEFT(created_at, 10) >= ${from}`                : sql``}
          ${to     ? sql`AND LEFT(created_at, 10) <= ${to}`                  : sql``}
          ${client ? sql`AND client_name ILIKE ${'%' + client + '%'}`        : sql``}
          ${slip   ? sql`AND packing_slip_no ILIKE ${'%' + slip + '%'}`      : sql``}
        ORDER BY created_at DESC`;
      return json(rows);
    }

    if ((p = m('GET', '/api/bills/:id'))) {
      const bad = notLoggedIn(); if (bad) return bad;
      const bid = asInt(p.id); if (bid === null) return json({ error: 'Not found' }, 404);
      const bills = await sql`SELECT * FROM bills WHERE id = ${bid}`;
      if (!bills[0]) return json({ error: 'Not found' }, 404);
      const items = await sql`SELECT * FROM bill_items WHERE bill_id = ${bid} ORDER BY sno`;
      return json({ bill: bills[0], items });
    }

    if (m('POST', '/api/bills')) {
      const bad = notLoggedIn(); if (bad) return bad;
      const d = await body(req);
      if (d.client_name === undefined) return json({ error: 'Client name is required' }, 400);

      const result = await sql.begin(async (tx: any) => {
        // Lock the counter row so two people billing at once can't collide.
        // The original had a race here; the port closes it.
        const [c] = await tx`
          SELECT value FROM settings WHERE key = 'bill_counter' FOR UPDATE`;
        const counter = parseInt(str(c?.value, '1'), 10) || 1;
        const billNo  = `BILL-${String(counter).padStart(4, '0')}`;
        await tx`UPDATE settings SET value = ${String(counter + 1)} WHERE key = 'bill_counter'`;

        const [bill] = await tx`
          INSERT INTO bills (bill_no, packing_slip_no, client_id, client_name,
                             despatch_date, subtotal, addon_label, addon_type,
                             addon_value, addon_amount, gst_rate, gst_amount,
                             grand_total, created_by)
          VALUES (${billNo}, ${str(d.packing_slip_no)}, ${d.client_id ?? null},
                  ${str(d.client_name)}, ${str(d.despatch_date)},
                  ${num(d.subtotal)}, ${str(d.addon_label)},
                  ${str(d.addon_type, 'amount')}, ${num(d.addon_value)},
                  ${num(d.addon_amount)}, ${num(d.gst_rate)}, ${num(d.gst_amount)},
                  ${num(d.grand_total)}, ${user!.username})
          RETURNING id`;

        const items = Array.isArray(d.items) ? d.items : [];
        if (items.length) {
          const payload = items.map((it: any) => ({
            bill_id: bill.id,
            sno: it.sno ?? null,
            brand: str(it.brand), product: str(it.product),
            size_code: str(it.size_code), size_metric: str(it.size_metric),
            thickness: str(it.thickness),
            quantity: Math.trunc(num(it.quantity, 1)),
            unit_price: num(it.unit_price),
            discount_type: str(it.discount_type, 'amount'),
            discount_value: num(it.discount_value),
            total_value: num(it.total_value),
            addon_label: str(it.addon_label),
            addon_type: str(it.addon_type, 'amount'),
            addon_value: num(it.addon_value),
            addon_amount: num(it.addon_amount),
          }));
          await tx`INSERT INTO bill_items ${tx(payload,
            'bill_id', 'sno', 'brand', 'product', 'size_code', 'size_metric',
            'thickness', 'quantity', 'unit_price', 'discount_type',
            'discount_value', 'total_value', 'addon_label', 'addon_type',
            'addon_value', 'addon_amount')}`;
        }
        return { bill_no: billNo, id: bill.id };
      });

      return json({ success: true, ...result });
    }

    if ((p = m('DELETE', '/api/bills/:id'))) {
      const bad = notAdmin(); if (bad) return bad;
      const bid = asInt(p.id); if (bid === null) return json({ error: 'Not found' }, 404);
      await sql`DELETE FROM bills WHERE id = ${bid}`;
      return json({ success: true });
    }

    // ───────────────────────── Backup (now a full Excel export) ─────────────

    if (m('GET', '/api/backup')) {
      const bad = notAdmin(); if (bad) return bad;
      return await exportEverything(sql);
    }

    // ───────────────────────── Printing ─────────────────────────

    if (m('GET', '/print/bills')) {
      if (!user) return new Response('Not logged in', { status: 401 });
      return await printBills(sql, qs.get('ids') ?? '');
    }

    // ───────────────────────── Settings ─────────────────────────

    if (m('GET', '/api/settings')) {
      const bad = notAdmin(); if (bad) return bad;
      const rows = await sql`
        SELECT key, value FROM settings
        WHERE key NOT IN ('admin_pw', 'user_pw') AND key NOT LIKE 'gdrive%'`;
      const out: Record<string, string> = {};
      for (const r of rows) out[r.key] = r.value;
      return json(out);
    }

    if (m('PUT', '/api/settings/company')) {
      const bad = notAdmin(); if (bad) return bad;
      const d = await body(req);
      await sql`
        INSERT INTO settings (key, value) VALUES ('company_name', ${str(d.name)})
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`;
      return json({ success: true });
    }

    return json({ error: 'Not found' }, 404);

  } catch (e: any) {
    console.error('API error', method, path, e);
    return json({ error: 'Server error', detail: str(e?.message) }, 500);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Excel  —  replaces openpyxl, same layout and styling as before
// ═══════════════════════════════════════════════════════════════════════════

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

const HEADER_FILL = {
  type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF4F46E5' },
} as const;
const HEADER_FONT = { bold: true, color: { argb: 'FFFFFFFF' } } as const;

function styleHeader(ws: any, widths: number[]) {
  const row = ws.getRow(1);
  row.eachCell((cell: any) => {
    cell.fill      = HEADER_FILL as any;
    cell.font      = HEADER_FONT as any;
    cell.alignment = { horizontal: 'center' };
  });
  widths.forEach((w, i) => { ws.getColumn(i + 1).width = w; });
  ws.views = [{ state: 'frozen', ySplit: 1 }];
}

async function workbookResponse(wb: any, filename: string) {
  const buf = await wb.xlsx.writeBuffer();
  return new Response(new Uint8Array(buf), {
    status: 200,
    headers: {
      'Content-Type': XLSX_MIME,
      'Content-Disposition': `attachment; filename=${filename}`,
      'Cache-Control': 'no-store',
    },
  });
}

async function exportPricelist(sql: any) {
  const rows = await sql`
    SELECT brand, product, size_code, thickness, price FROM price_list
    ORDER BY brand, product, size_code, thickness`;

  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('Prices');
  ws.addRow(['Brand', 'Product', 'Size Code', 'Thickness', 'Price']);
  for (const r of rows) {
    ws.addRow([r.brand, r.product, r.size_code, r.thickness, r.price]);
  }
  styleHeader(ws, [16, 24, 14, 12, 12]);
  return workbookResponse(wb, 'mattress_prices.xlsx');
}

// A cell can hold rich text, a formula result, a date… flatten it to a string.
function cellText(v: any): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') {
    if (Array.isArray(v.richText)) return v.richText.map((t: any) => t.text).join('');
    if ('result' in v)   return cellText(v.result);
    if ('text' in v)     return String(v.text);
    if (v instanceof Date) return v.toISOString().slice(0, 10);
    return '';
  }
  return String(v);
}

async function importPricelist(sql: any, req: Request) {
  let file: File | null = null;
  try {
    const form = await req.formData();
    const f = form.get('file');
    if (f && typeof f !== 'string') file = f as File;
  } catch { /* fall through to the same error the old app gave */ }

  if (!file) return json({ error: 'No file uploaded' }, 400);

  const wb = new ExcelJS.Workbook();
  try {
    await wb.xlsx.load(await file.arrayBuffer());
  } catch {
    return json(
      { error: 'Could not read the file. Please upload a valid .xlsx Excel file.' }, 400);
  }

  // openpyxl's `wb.active` reads the sheet the file was saved on, which is not
  // always the first one. Mirror that, or a workbook saved with a different tab
  // selected would import from a different sheet than the old app used.
  const activeTab = wb.views?.[0]?.activeTab;
  const ws = (typeof activeTab === 'number' ? wb.worksheets[activeTab] : undefined)
             ?? wb.worksheets[0];
  if (!ws) {
    return json(
      { error: 'Could not read the file. Please upload a valid .xlsx Excel file.' }, 400);
  }

  // Support both the current 5-column sheet and the older 6-column one
  const header: string[] = [];
  for (let c = 1; c <= ws.columnCount; c++) {
    header.push(cellText(ws.getCell(1, c).value).trim().toLowerCase());
  }
  const hasSizeMetric = header.includes('size metric');

  const newRows: any[] = [];
  let skipped = 0;

  for (let r = 2; r <= ws.rowCount; r++) {
    const row = ws.getRow(r);
    const cells: string[] = [];
    const width = hasSizeMetric ? 6 : 5;
    for (let c = 1; c <= width; c++) cells.push(cellText(row.getCell(c).value));
    if (cells.every(c => c.trim() === '')) continue;

    let brand, product, sizeCode, sizeMetric, thickness, priceRaw;
    if (hasSizeMetric) {
      [brand, product, sizeCode, sizeMetric, thickness, priceRaw] = cells;
    } else {
      [brand, product, sizeCode, thickness, priceRaw] = cells;
      sizeMetric = '';
    }

    if (!brand?.trim() || !product?.trim() || !sizeCode?.trim() || !thickness?.trim()) {
      skipped++;
      continue;
    }

    const price = parseFloat(priceRaw);
    newRows.push({
      brand: brand.trim(),
      product: product.trim(),
      size_code: sizeCode.trim(),
      size_metric: (sizeMetric ?? '').trim(),
      thickness: thickness.trim(),
      price: Number.isFinite(price) ? price : 0,
    });
  }

  if (!newRows.length) {
    return json({ error: 'No valid rows found in the file. Nothing was changed.' }, 400);
  }

  // The original wiped the table then inserted. Same behaviour, but wrapped in a
  // transaction so a mid-import failure can no longer leave the office with an
  // empty price list.
  try {
    await sql.begin(async (tx: any) => {
      await tx`DELETE FROM price_list`;
      for (let i = 0; i < newRows.length; i += 500) {
        const chunk = newRows.slice(i, i + 500);
        await tx`INSERT INTO price_list ${tx(chunk,
          'brand', 'product', 'size_code', 'size_metric', 'thickness', 'price')}`;
      }
    });
  } catch (e: any) {
    return json({
      error: 'Import failed, nothing was changed. ' +
             'Check for duplicate Brand/Product/Size/Thickness rows in the file.',
      detail: str(e?.message),
    }, 400);
  }

  return json({ success: true, total: newRows.length, skipped });
}

// The old "Download Backup (.db)" button copied the SQLite file. There is no
// file any more — Supabase keeps the database backed up — so this hands back
// the entire dataset as a readable workbook instead.
async function exportEverything(sql: any) {
  const wb = new ExcelJS.Workbook();
  wb.created = new Date();

  const prices = await sql`
    SELECT id, brand, product, size_code, size_metric, thickness, price, updated_at
    FROM price_list ORDER BY brand, product, size_code, thickness`;
  const ws1 = wb.addWorksheet('Price List');
  ws1.addRow(['ID', 'Brand', 'Product', 'Size Code', 'Size Metric', 'Thickness', 'Price', 'Updated']);
  for (const r of prices) {
    ws1.addRow([r.id, r.brand, r.product, r.size_code, r.size_metric, r.thickness, r.price, r.updated_at]);
  }
  styleHeader(ws1, [8, 16, 24, 14, 18, 12, 12, 20]);

  const clients = await sql`
    SELECT id, name, phone, address, discount_value, created_at FROM clients ORDER BY name`;
  const ws2 = wb.addWorksheet('Clients');
  ws2.addRow(['ID', 'Name', 'Phone', 'Address', 'Discount', 'Created']);
  for (const r of clients) {
    ws2.addRow([r.id, r.name, r.phone, r.address, r.discount_value, r.created_at]);
  }
  styleHeader(ws2, [8, 28, 16, 40, 12, 20]);

  const bills = await sql`
    SELECT id, bill_no, packing_slip_no, client_id, client_name, despatch_date,
           subtotal, addon_label, addon_type, addon_value, addon_amount,
           gst_rate, gst_amount, grand_total, created_at, created_by
    FROM bills ORDER BY id`;
  const ws3 = wb.addWorksheet('Bills');
  ws3.addRow(['ID', 'Bill No', 'Packing Slip', 'Client ID', 'Client', 'Despatch Date',
              'Subtotal', 'Add-on For', 'Add-on Type', 'Add-on Value', 'Add-on Amount',
              'GST %', 'GST Amount', 'Grand Total', 'Created', 'Created By']);
  for (const r of bills) {
    ws3.addRow([r.id, r.bill_no, r.packing_slip_no, r.client_id, r.client_name,
                r.despatch_date, r.subtotal, r.addon_label, r.addon_type,
                r.addon_value, r.addon_amount, r.gst_rate, r.gst_amount,
                r.grand_total, r.created_at, r.created_by]);
  }
  styleHeader(ws3, [8, 14, 16, 10, 28, 16, 14, 22, 12, 13, 14, 9, 13, 14, 20, 14]);

  const items = await sql`
    SELECT id, bill_id, sno, brand, product, size_code, size_metric, thickness,
           quantity, unit_price, discount_type, discount_value,
           addon_label, addon_type, addon_value, addon_amount, total_value
    FROM bill_items ORDER BY bill_id, sno`;
  const ws4 = wb.addWorksheet('Bill Items');
  ws4.addRow(['ID', 'Bill ID', 'S.No', 'Brand', 'Product', 'Size Code', 'Size Metric',
              'Thickness', 'Qty', 'Unit Price', 'Discount Type', 'Discount',
              'Add-on For', 'Add-on Type', 'Add-on Value', 'Add-on Per Piece', 'Total']);
  for (const r of items) {
    ws4.addRow([r.id, r.bill_id, r.sno, r.brand, r.product, r.size_code, r.size_metric,
                r.thickness, r.quantity, r.unit_price, r.discount_type,
                r.discount_value, r.addon_label, r.addon_type, r.addon_value,
                r.addon_amount, r.total_value]);
  }
  styleHeader(ws4, [8, 10, 8, 14, 24, 14, 18, 12, 8, 12, 14, 12, 22, 12, 13, 16, 14]);

  // Deliberately no password hashes here — this file gets emailed around.
  const users = await sql`SELECT id, username, role, created_at FROM users ORDER BY id`;
  const ws5 = wb.addWorksheet('Users');
  ws5.addRow(['ID', 'Username', 'Role', 'Created']);
  for (const r of users) ws5.addRow([r.id, r.username, r.role, r.created_at]);
  styleHeader(ws5, [8, 24, 12, 20]);

  const settings = await sql`
    SELECT key, value FROM settings WHERE key NOT LIKE 'gdrive%' ORDER BY key`;
  const ws6 = wb.addWorksheet('Settings');
  ws6.addRow(['Key', 'Value']);
  for (const r of settings) ws6.addRow([r.key, r.value]);
  styleHeader(ws6, [24, 40]);

  const date = appNow().slice(0, 10);
  return workbookResponse(wb, `mattress_backup_${date}.xlsx`);
}

// ═══════════════════════════════════════════════════════════════════════════
//  Print view  —  the former Jinja template, rendered here instead
// ═══════════════════════════════════════════════════════════════════════════

const PRINT_CSS = `
  body { font-family: Arial, sans-serif; font-size: 11pt; background: #fff; margin: 0; padding: 12px; }
  .no-print { margin-bottom: 16px; }
  @media print { .no-print { display: none !important; } }
  .bill-page { max-width: 780px; margin: 0 auto 40px auto; padding: 18px 20px; border: 1px solid #ccc; page-break-after: always; }
  .bill-page:last-child { page-break-after: auto; }
  .print-header { border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: flex-start; }
  .print-meta { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; margin-bottom: 10px; }
  .print-meta-item span:first-child { color: #666; display: block; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; }
  table { width: 100%; border-collapse: collapse; font-size: 9pt; }
  th, td { border: 1px solid #ccc; padding: 3px 5px; vertical-align: middle; }
  th { background: #eee; text-align: left; }
  .text-end { text-align: right; }
  .text-center { text-align: center; }
  .print-footer { margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
  .sign-box { border-top: 1px solid #333; padding-top: 6px; font-size: 0.78rem; color: #555; text-align: center; }
  .grand-total-row { font-weight: 700; background: #f8f9fa; }
`;

async function printBills(sql: any, idsStr: string) {
  if (!idsStr) return new Response('No bill IDs provided', { status: 400 });

  const ids = idsStr.split(',').map(s => s.trim()).filter(Boolean);
  if (!ids.every(i => /^\d+$/.test(i))) {
    return new Response('Invalid bill IDs', { status: 400 });
  }
  const numericIds = ids.map(i => parseInt(i, 10));

  const cRow = await sql`SELECT value FROM settings WHERE key = 'company_name'`;
  const companyName = cRow[0]?.value ?? 'My Company';

  const bills = await sql`SELECT * FROM bills WHERE id = ANY(${numericIds})`;
  const items = await sql`
    SELECT * FROM bill_items WHERE bill_id = ANY(${numericIds}) ORDER BY bill_id, sno`;

  const byBill = new Map<number, any[]>();
  for (const it of items) {
    if (!byBill.has(it.bill_id)) byBill.set(it.bill_id, []);
    byBill.get(it.bill_id)!.push(it);
  }
  const billById = new Map<number, any>(bills.map((b: any) => [b.id, b]));

  // Preserve the order the ids arrived in, exactly as the Flask loop did
  const pages: string[] = [];
  for (const id of numericIds) {
    const bill = billById.get(id);
    if (!bill) continue;
    const rows = (byBill.get(id) ?? []).map(it => `
      <tr>
        <td>${esc(it.sno)}</td>
        <td>${esc(it.brand)}</td>
        <td>${esc(it.product)}</td>
        <td>${esc(it.size_code)}<br><small style="color:#666;">${esc(it.size_metric)}</small></td>
        <td>${esc(it.thickness)}</td>
        <td class="text-center">${esc(it.quantity)}</td>
        <td class="text-end">₹${money(it.unit_price)}</td>
        <td class="text-center">${num(it.discount_value) > 0 ? money(it.discount_value) + '%' : '—'}</td>
        <td class="text-end">₹${money(savedNet(it))}</td>
        <td class="text-end">${savedAddon(it) > 0 ? '₹' + money(savedAddon(it)) : '—'}</td>
        <td class="text-end"><strong>₹${money(it.total_value)}</strong></td>
      </tr>`).join('');

    // Bills saved before add-ons and GST existed carry none of these figures,
    // so they print exactly the single Grand Total line they always did.
    const billAddon = num(bill.addon_amount);
    const billGst   = num(bill.gst_amount);
    const storedSub = num(bill.subtotal);
    const subtotal  = storedSub > 0 ? storedSub : num(bill.grand_total) - billAddon - billGst;
    const extraRow  = (label: string, value: number) => `
      <tr>
        <td colspan="8"></td>
        <td colspan="2" class="text-end">${label}</td>
        <td class="text-end">₹${money(value)}</td>
      </tr>`;
    const summary = (billAddon > 0 || billGst > 0)
      ? extraRow('Items Subtotal:', subtotal)
        + (billAddon > 0
            ? extraRow(bill.addon_label ? `Add-on — ${esc(bill.addon_label)}:` : 'Add-on:', billAddon)
            : '')
        + extraRow(`GST @ ${rateStr(bill.gst_rate)}%:`, billGst)
      : '';

    pages.push(`
<div class="bill-page">
  <div class="print-header">
    <div>
      <h4 style="margin:0;font-weight:700;">${esc(companyName)}</h4>
      <div style="font-size:0.85rem;color:#555;">Dispatch Reference Sheet</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:1.1rem;font-weight:700;">${esc(bill.bill_no)}</div>
      <div style="font-size:0.8rem;color:#555;">${esc(bill.created_at)}</div>
    </div>
  </div>
  <div class="print-meta">
    <div class="print-meta-item"><span>Client</span><strong>${esc(bill.client_name)}</strong></div>
    <div class="print-meta-item"><span>Packing Slip No.</span><strong>${bill.packing_slip_no ? esc(bill.packing_slip_no) : '—'}</strong></div>
    <div class="print-meta-item"><span>Despatch Date</span><strong>${bill.despatch_date ? esc(bill.despatch_date) : '—'}</strong></div>
    <div class="print-meta-item"><span>Created By</span><strong>${bill.created_by ? esc(bill.created_by) : '—'}</strong></div>
  </div>
  <table>
    <thead>
      <tr>
        <th style="width:24px;">#</th>
        <th style="width:60px;">Brand</th>
        <th>Product</th>
        <th style="width:70px;">Size</th>
        <th style="width:32px;">H.</th>
        <th style="width:28px;">Qty</th>
        <th style="width:80px;">Price (₹)</th>
        <th style="width:40px;">Disc.</th>
        <th style="width:80px;">Net (₹)</th>
        <th style="width:76px;">Add-on (₹)</th>
        <th style="width:84px;">Total (₹)</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
    <tfoot>${summary}
      <tr class="grand-total-row">
        <td colspan="8"></td>
        <td colspan="2" class="text-end">Grand Total:</td>
        <td class="text-end">₹${money(bill.grand_total)}</td>
      </tr>
    </tfoot>
  </table>
  <div class="print-footer">
    <div class="sign-box">Prepared by</div>
    <div class="sign-box">Checked by</div>
    <div class="sign-box">Authorised by</div>
  </div>
  <div style="margin-top:12px;font-size:0.75rem;color:#999;text-align:center;">
    This document is for internal reference only. Not a tax invoice.
  </div>
</div>`);
  }

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Print Bills</title>
<style>${PRINT_CSS}</style>
</head>
<body>
<div class="no-print">
  <button onclick="window.print()" style="padding:8px 16px;font-size:1rem;cursor:pointer;">Print / Save as PDF</button>
  <button onclick="window.close()" style="padding:8px 16px;font-size:1rem;cursor:pointer;margin-left:8px;">Close</button>
</div>
${pages.join('\n')}
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
