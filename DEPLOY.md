# Deploying Attic for free

Attic is a single-user FastAPI + SQLite app, so it is very light. This page
covers running it on your own hardware and exposing it without paying for a
host, plus the free tiers of a few platforms.

## Before you go anywhere

From the project root:

```bash
pip install -r requirements.txt
python make_icons.py      # creates the PNG icons the install prompt needs
```

Start it locally to confirm everything works:

```bash
python run.py             # serves http://127.0.0.1:8000
```

For production you run uvicorn directly (no reload):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Run exactly **one** worker. SQLite and the login throttle are in-process, so
extra workers only cause lock contention and split state for no benefit.

## Everything stays local: home server + Cloudflare Tunnel (recommended)

The safest and 100% free option. A tunnel reaches your home machine from the
public internet without opening ports or exposing your IP.

1. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Run Attic as above on some machine on your network.
3. Set up a quick tunnel:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

   This prints a `https://xxx.trycloudflare.com` URL you can open anywhere.
   For a permanent address sign up at Cloudflare, add a tunnel with your
   domain, and point the DNS record at it.

Private-network alternative: [Tailscale](https://tailscale.com) (free tier)
lets you reach your machine from your own devices over an encrypted mesh, no
public exposure at all.

## Free-tier hosts

These "free" tiers pause when idle and may not sleep-resume instantly, which
is fine for a personal app:

- **Fly.io** - a free allowance of small machines; mount a volume for the
  `data/` folder and run `uvicorn app.main:app --port 8080`.
- **Render / Railway** - free web services, but spinning down when unused.
  SQLite written to their ephemeral disk **is lost on redeploy**, so set
  `ATTIC_DATA_DIR` to a persistent volume or rely on the export backup.

Whichever host you use, `data/` must survive restarts - that is where the
database and the session signing key live (`config.py`).

## Environment variables

All optional; defaults run a real app with no config:

| Variable | Default | Why you'd change it |
| --- | --- | --- |
| `ATTIC_SECRET_KEY` | generated & saved to `data/secret_key` | set your own for predictable deploys |
| `ATTIC_DATA_DIR` | `<project>/data` | point at a persistent volume |
| `ATTIC_DB` | `<DATA_DIR>/attic.db` | relocate just the database |
| `ATTIC_COOKIE_SECURE` | `0` | `1` when Attic is served over HTTPS |
| `ATTIC_SESSION_HOURS` | `720` | session length (default 30 days, so PWA launch opens straight in) |
| `ATTIC_LOGIN_MAX_ATTEMPTS` / `ATTIC_LOGIN_WINDOW_SECONDS` | `10` / `900` | login throttling |

## HTTPS on local machines

For a tunnel or PaaS, HTTPS is already terminated upstream. Set
`ATTIC_COOKIE_SECURE=1` so the session cookie is only sent over TLS. Leave it
`0` for plain `http://localhost`.

## Backups

Use the built-in **Settings → Backup** export to download one JSON file of
everything, and re-import it on any other machine. For hands-off backups,
copy the single `data/attic.db` file (and `data/secret_key`) somewhere off-box
periodically while the server is stopped.

## Quick capture from anywhere

Attic registers a `web+attic://` protocol. Opening that link while Attic is
running (even minimized in the background) brings it to the front with the
**New note** popup already open.

- **PWA:** right-click the installed app's taskbar/dock icon → "New note".
- **Any app:** link to `web+attic://new` — the OS opens the registered handler.
- **Global hotkey (Windows):** make a shortcut to `web+attic://new`:
  1. Right-click the desktop → New → Shortcut.
  2. Location: `cmd.exe /c start "" "web+attic://new"`
  3. Right-click it → Properties → Shortcut key → e.g. `Ctrl+Alt+A`.

  Pressing the hotkey anywhere opens (or focuses) Attic's capture popup.
  The web platform can't register a system-wide hotkey by itself, so this
  one-setup shortcut is the standard trick.

Web pages cannot read keypresses they never receive, so there is no in-page
way to act while the browser tab is in the background - the protocol handler
(or the PWA taskbar shortcut) is the intended mechanism.

## PWA and offline

Install App/Add-to-home-screen makes Attic open in its own window with
shortcuts (New note / link / snippet, Search) and keeps the app shell working
offline. The service worker caches the last view and serves a friendly
"offline" page when there is no connection.

## Security checklist (what's already handled)

- Sessions: signed cookie, `httpOnly`, `SameSite=Lax`, optional `Secure`.
- No interactive API docs exposed (`openapi_url=None`).
- Every state-changing request needs a CSRF token.
- Passwords: bcrypt, never stored or logged in plain text.
- Login throttled per IP (10 tries per 15 minutes by default).
- Markdown and rendered HTML are sanitized before they are shown.
- Link titles are fetched with timeouts, size caps, and a blocklist that
  refuses internal/private network addresses (SSRF guard).
- Security headers: `nosniff`, `DENY` framing, strict referrer, and a
  restrictive permissions policy.