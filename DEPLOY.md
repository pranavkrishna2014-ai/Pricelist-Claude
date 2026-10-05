# Moving the app to Supabase + Netlify

Follow these in order. Nothing here touches the droplet until the very last
step, so the app your office is using stays up the whole time.

Set aside about an hour. You need: the GitHub account that already holds the
repo, an email address, and about ten minutes on the DigitalOcean console.

---

## Step 1 — Create the Supabase project

1. Go to **supabase.com**, sign up (the GitHub button is quickest), and click
   **New project**.
2. Name it `pricelist`. Choose region **Mumbai** or **Singapore** — the closer it
   is to your office, the faster every screen feels.
3. It asks for a **database password**. Generate one, and paste it somewhere
   safe right now. You cannot see it again, and you need it in Step 3.
4. Wait for the project to finish building — a couple of minutes.

## Step 2 — Create the tables

1. In the left sidebar click **SQL Editor**, then **New query**.
2. Open `db/schema.sql` from this project, copy the whole file, paste it in.
3. Click **Run**. You should see "Success. No rows returned."

That has created the six tables. They are empty; the data comes in Step 6.

## Step 3 — Copy the connection strings

In Supabase, click **Connect** at the top of the screen. You need two strings
from there, and they differ only in the port number:

- **Transaction pooler**, port **6543** — this is the one the app uses.
- **Session pooler**, port **5432** — this is the one the migration uses.

Both look like:

```
postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

Replace `[YOUR-PASSWORD]` with the password from Step 1. If the password has
symbols in it, percent-encode them (`@` becomes `%40`, `#` becomes `%23`).

## Step 4 — Put this project on GitHub

From the folder containing this file:

```bash
git init
git add .
git commit -m "Move Mattress Price App to Netlify and Supabase"
git branch -M main
git remote add origin https://github.com/pranavkrishna2014-ai/pricelist-cloud.git
git push -u origin main
```

Create that empty repository on GitHub first (**New repository**, no README).
Use a **new** repo rather than the old one — the old one stays untouched as a
fallback.

## Step 5 — Create the Netlify site

1. Go to **netlify.com**, sign up with GitHub, then **Add new site → Import an
   existing project → GitHub**, and pick the repo you just pushed.
2. Leave the build settings alone — `netlify.toml` already fills them in.
   Click **Deploy**.
3. When it finishes, go to **Site configuration → Environment variables** and
   add two:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the **port 6543** string from Step 3 |
   | `SESSION_SECRET` | a long random string — run `openssl rand -base64 32` in Terminal, or mash the keyboard for 40 characters |

4. Go to **Deploys → Trigger deploy → Deploy site** so the new variables take
   effect.
5. Under **Site configuration → General**, change the site name to something
   memorable. Your address becomes `https://that-name.netlify.app`.

Open it. You should get the familiar login screen. You cannot log in yet —
there are no users until Step 6.

## Step 6 — Bring your data across

**6a. Get the database file off the droplet.**

You need admin access to the old app to download it. If you have it, log in,
go to **Settings → Manual Backup → Download Backup (.db)**. If you have
forgotten the password, open the DigitalOcean console and reset it first:

```bash
cd /root/Pricelist-Claude      # wherever mattress.db lives
python3 -c "import sqlite3;print(sqlite3.connect('mattress.db').execute('SELECT id,username,role FROM users').fetchall())"
```

That prints your usernames. Then, replacing the id and password:

```bash
python3 -c "import sqlite3,hashlib;d=sqlite3.connect('mattress.db');d.execute('UPDATE users SET password_hash=? WHERE id=1',(hashlib.sha256('TempPass123'.encode()).hexdigest(),));d.commit()"
```

Log in with that, download the backup, and note where it saved — probably
your Downloads folder.

**6b. Run the migration.** In Terminal on your Mac:

```bash
pip3 install psycopg2-binary
cd <this project>/migrate
python3 migrate.py --db ~/Downloads/mattress_backup_2026-08-25.db \
  --url "postgresql://postgres.abcdefgh:PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres" \
  --replace
```

Use the **port 5432** string here. It prints a row count for every table and a
verification table at the end. Every line should say `OK`. If any says `!!`,
stop and sort that out before going further — do not switch the office over.

The script never writes to the `.db` file, and `--replace` means you can run it
again as many times as you like; each run leaves Supabase matching the file.

## Step 7 — Get yourself logged in

Your old passwords came across and still work. If you still don't know them,
reset the admin account from Supabase's **SQL Editor**:

```sql
-- shows what accounts exist
SELECT id, username, role FROM users ORDER BY id;
```

```sql
-- sets both a new username and a new password on one account
UPDATE users
SET username = 'yourname',
    password_hash = crypt('YourNewPassword', gen_salt('bf'))
WHERE id = 1;
```

If `crypt` reports an error, run `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
once, then try again.

Log in at your Netlify address. The first time each person signs in, their old
password is quietly re-hashed to bcrypt — they will not notice anything.

## Step 8 — Check it before anyone relies on it

Go through this list on the new site:

- [ ] Log in as admin, and as one ordinary user
- [ ] The price list shows every brand and product, in the order you expect
- [ ] Look up a price the way you would when making a bill
- [ ] Client search finds a client by typing part of the name in lower case
- [ ] Records tab shows all your old bills, with the right dates and totals
- [ ] Open an old bill and print it — the layout matches the old printout
- [ ] Create a test bill, check the bill number continues from where you were
- [ ] Delete that test bill
- [ ] Settings → company name is right
- [ ] Settings → Download Everything (.xlsx) opens in Excel with six sheets
- [ ] Admin → export the price list, change one price in Excel, re-import it,
      confirm the change landed (then put it back)
- [ ] Add a user, change their password, log in as them, delete them

## Step 9 — Switch over

1. Send the office the new address.
2. **Leave the droplet running for a week or two.** It costs a few pounds and it
   is your rollback: if anything is wrong, everyone goes back to the old address
   and nothing is lost.
3. Any bills created on the old app during that window will *not* appear on the
   new one. Either tell staff to switch completely on day one, or re-run the
   migration (Step 6) afterwards to pull everything across again.
4. Once you are happy, destroy the droplet in the DigitalOcean dashboard.
   **Download a backup first.**

---

## What this costs

Nothing, as long as usage stays inside the free tiers — and an office app of
this size is nowhere near them.

- **Supabase free:** 500 MB database (your data is a few megabytes), 5 GB
  transfer a month, 2 projects.
- **Netlify free:** 300 credits a month, covering both the site and the API.

One catch worth knowing: **Supabase pauses a free project after a full week
with no activity.** Daily office use keeps it awake permanently. If you close
for a long holiday, the first person back may find it asleep — open the
Supabase dashboard and click resume, and the data is all still there.

## If something goes wrong

**"Server not configured" or every request fails** — `DATABASE_URL` or
`SESSION_SECRET` is missing or misspelt in Netlify, or you added them without
redeploying. Check both, then trigger a fresh deploy.

**Login says the password is wrong, but you're sure it isn't** — check the
password in `DATABASE_URL` is percent-encoded if it contains symbols. A broken
connection string can look like a rejected login.

**Everyone gets logged out at once** — `SESSION_SECRET` changed. Set it back,
or just have people log in again.

**Timeouts, or "too many connections"** — you used the port 5432 string for
`DATABASE_URL`. The app needs the transaction pooler on **6543**.

**The site loads but every button spins** — open the browser's developer
console (F12) and look at the Network tab. If `/api/...` calls return 404, the
function did not deploy; check the deploy log in Netlify for a build error.

**You want to undo everything** — the droplet is still there and still has the
data as it was when you took the backup. Point people back at the old address.
