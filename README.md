# Attic

**Keep it. Find it.**

A private, single-user knowledge base for notes, links and snippets. Fast
search, a calm interface, and everything stored in one small SQLite file that
you own. No accounts, no cloud, no noise.

---

## What it does

- **Notes, links and snippets** in one place. Markdown for notes, a real link
  preview (safely fetched title + description), and syntax-highlighted code
  for snippets with one-click copy.
- **Instant search** backed by SQLite FTS5, with match highlighting, filters
  by type and tag, and sort options.
- **Organise lightly**: tags, pin, archive, trash with a configurable
  hold period, and "related items" that surface things sharing tags.
- **Keyboard-first**: `/` to search, `N` for a new item, arrows/Home/End to
  move, `Enter` to open, `?` for the full guide, `Esc` to dismiss.
- **Backup**: export everything to a single JSON file and import it back
  (duplicates are skipped, timestamps and flags are preserved).
- **Installable PWA** with offline support, app-icon shortcuts, and a
  `web+attic://new` quick-capture protocol.
- **Themes**: dark, light, or follow the system.
- **Private by default**: one owner account, bcrypt passwords, CSRF-protected
  writes, session cookies, login throttling, and a link fetcher that refuses
  to touch internal addresses.

## Tech

- **Backend:** FastAPI + Uvicorn, SQLite (with FTS5), Jinja2 templates.
- **Frontend:** vanilla JavaScript, hand-written CSS, an SVG sprite for
  icons. No build step.
- **Markdown:** `markdown` rendered and sanitized with `bleach`;
  `pygments` for code highlighting.

## Quick start

Requires **Python 3.10+**.

```bash
# 1. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate          # Windows (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# 2. Generate the PNG app icons (needed for the install prompt)
python make_icons.py

# 3. Run it
python run.py
```

Open <http://127.0.0.1:8000>. The first visit asks you to create your owner
account (username + password), then you're in.

## Day-to-day running

```bash
python run.py
```

That starts Uvicorn with auto-reload at `http://127.0.0.1:8000`. For anything
other than local development, run a single worker:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Run exactly one worker: SQLite and the login throttle are in-process.

## Project layout

```
Attic/
  app/
    main.py            # FastAPI app, middleware, PWA file routes
    config.py          # paths, secret key, environment settings
    db.py              # schema, migrations, connection, settings
    store.py           # all database queries (items, tags, trash, import/export)
    auth.py            # session/owner helpers
    security.py        # password hashing, CSRF, login throttling
    linkmeta.py        # safe link title/description fetching (SSRF-guarded)
    markdown_render.py # markdown -> HTML (sanitized) and code highlighting
    routers/           # account, items (JSON API), pages
    templates/         # Jinja2 pages and partials
    static/            # css, js, icons, manifest.json, service worker, offline page
  data/                # SQLite database + generated secret key (gitignored)
  make_icons.py        # writes the PWA PNG icons (stdlib only)
  run.py               # local development launcher
  DEPLOY.md            # free deployment guide
```

## Configuration

All settings are optional and read from environment variables. Defaults run a
real app with no configuration. See `.env.example` for a template.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ATTIC_DATA_DIR` | `./data` | folder for the database and secret key |
| `ATTIC_DB` | `<DATA_DIR>/attic.db` | path to the database file |
| `ATTIC_SECRET_KEY` | auto-generated in `data/secret_key` | signs session cookies |
| `ATTIC_SESSION_HOURS` | `720` (30 days) | how long a login lasts |
| `ATTIC_COOKIE_SECURE` | `false` | set `true` when served over HTTPS |
| `ATTIC_LOGIN_MAX_ATTEMPTS` | `10` | failed logins allowed per window |
| `ATTIC_LOGIN_WINDOW_SECONDS` | `900` | length of that window |

## Keyboard shortcuts

| Keys | Action |
| --- | --- |
| `?` | Show the shortcuts guide |
| `/` | Focus search |
| `N` | New item |
| `↑` / `↓` | Move through the list |
| `Home` / `End` | Jump to first / last item |
| `Enter` | Open the selected item |
| `Esc` | Close dialogs / clear selection |
| `Ctrl` + `Enter` | Save the capture box |

There is also a full page at `/shortcuts`.

## Install as an app & quick capture

Install Attic from your browser ("Install app" / add to home screen). It then
opens in its own window, works offline, and adds shortcuts from the app icon:
**New note**, **New link**, **New snippet**, **Search**.

Attic also registers a `web+attic://` protocol. Opening `web+attic://new`
while Attic is running in the background brings it forward with the capture
popup ready. On Windows you can assign a global hotkey to it — see the
"Quick capture from anywhere" section in [DEPLOY.md](DEPLOY.md).

## Backups

**Settings → Backup** exports every live item (with tags, timestamps and
flags) to a single JSON file, and imports one back. For hands-off backups,
copy `data/attic.db` and `data/secret_key` somewhere safe while the server is
stopped.

## Deployment

Attic runs comfortably on free hardware: a home machine behind a Cloudflare
Tunnel or Tailscale, or a free-tier PaaS. Full instructions, environment
variables, HTTPS notes and a security checklist live in [DEPLOY.md](DEPLOY.md).

## License

Personal project. Use it however you like.
