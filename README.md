# Mattress Price App — Netlify + Supabase

The same app your office uses every day, moved off the DigitalOcean droplet.
The screens, buttons and workflow are unchanged; only what runs underneath
is different.

| | Before | Now |
|---|---|---|
| Front end | Flask serving `templates/index.html` | The same HTML, served as a static file by Netlify |
| API | 37 Flask routes in `app.py` | The same 37 routes, in one Netlify Function |
| Database | `mattress.db` (SQLite) on the droplet | Supabase Postgres |
| Login | Flask session cookie, SHA-256 passwords | Signed cookie, bcrypt (old passwords still work) |
| Backup | Google Drive upload of the `.db` file | Supabase's own backups + "Download Everything (.xlsx)" |
| Cost | DigitalOcean droplet | £0 — both free tiers |

## Layout

```
db/schema.sql              Postgres schema — run once in Supabase
netlify/functions/api.mts  The whole backend
public/index.html          The app your office sees (unchanged apart from the backup panel)
migrate/migrate.py         Copies mattress.db into Supabase
tests/local-server.mts     Runs the backend locally for testing
DEPLOY.md                  Step-by-step setup and cutover
```

## Environment variables

Both are set in Netlify (**Site configuration → Environment variables**):

| Name | What it is |
|---|---|
| `DATABASE_URL` | Supabase **transaction pooler** connection string (port 6543) |
| `SESSION_SECRET` | Any long random string. Changing it logs everyone out. |

## Running it locally

```bash
npm install
DATABASE_URL="postgresql://...?sslmode=disable" \
SESSION_SECRET="something-at-least-16-characters" \
npx tsx tests/local-server.mts 5055
```

Then open `public/index.html` through any static server pointed at the same
origin, or use `npx netlify dev`, which serves both together.

## Notes for whoever maintains this next

- Timestamps are stored as `YYYY-MM-DD HH:MM:SS` text in India time, exactly as
  SQLite did, so migrated rows and new rows look the same in the UI.
- Text columns are pinned to `COLLATE "C"`. Postgres would otherwise sort
  case-insensitively and reorder the price list compared with what staff see today.
- Client and bill searches use `ILIKE`, because SQLite's `LIKE` was already
  case-insensitive and the office relies on that.
- Bill numbers are allocated with `SELECT ... FOR UPDATE`, so two people billing
  at the same moment can no longer be handed the same number.
