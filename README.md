# Customer Records: Customer Records Web App

A secure internal web app for a Thai small business to collect, search and share customer records, including bank account details that staff use to make transfers. Customers register themselves through a QR-code form; admins and staff work with the data behind a login, with role-based access, a full activity log and a mobile-first Thai interface.

Built as real client work with Django, PostgreSQL, HTMX and Alpine.js.

## Features

**Customers (public)**
- QR-code registration form: mobile-first, server-side validation, honeypot and per-IP rate limiting against spam

**Staff and admins**
- Customer list with search-as-you-type, Thai dictionary sorting, filters, pagination and auto-refresh every 10 seconds
- Tick-to-pin selection: ticked customers stay at the top across searches, pages and refreshes
- Copy, share (native phone share sheet, e.g. to LINE) and PDF export with an embedded Thai font
- Phone layout with expandable cards and icon actions; desktop table with even column spacing
- Light, dark and system themes, saved per account

**Admins only**
- Add, edit, hide and delete customers (single or bulk, with typed confirmation)
- Staff account management: create, edit, reset password, deactivate
- Append-only activity log with filters, a detail page and CSV export
- Excel import command with dry run and all-or-nothing transactions

## Security and privacy

The app stores bank account numbers, so access rules are enforced on the server and covered by tests:

- **Default deny:** every page requires login except the login page and the QR form
- **Role-based visibility:** staff never receive customers' phone numbers or hidden customers, in any page, search, export or URL
- **Server re-checks every ID:** bulk actions only act on customers the user is allowed to see
- **Masked account numbers** in lists; the full number appears only in deliberate copy or PDF exports, each logged
- **Append-only audit log** that never stores phone or account numbers
- **Login lockout** after 5 failed attempts (django-axes), CSRF on every change, POST-only logout
- **Production hardening:** HTTPS redirect, HSTS, secure cookies, a strict Content-Security-Policy, real client IP behind the proxy, and no customer text ever placed in client-side code (tested with attack strings)
- **Self-hosted assets:** no CDNs, trackers or analytics

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.15, Django 6.1 |
| Database | PostgreSQL 18 (Thai sorting with ICU collation) |
| Frontend | Server-rendered Django templates, HTMX 2, Alpine.js 3, Tailwind CSS 4 |
| PDF and Excel | fpdf2 with HarfBuzz text shaping, openpyxl |
| Security | django-axes, Django's built-in CSP and security middleware |
| Production | gunicorn, WhiteNoise, Render (web) and Neon (Postgres) |
| Tooling | uv, pytest + pytest-django, ruff |

## Architecture

A single Django project with three apps and one PostgreSQL database. It's deliberately simple: no separate API, no queues, no caches.

```
Browser ── HTMX (partial page swaps) + Alpine.js (selection, menus, theme)
   │
Django ─┬─ accounts/   users, login, roles, staff management
        ├─ customers/  customer model, list, filters, exports, QR form, Excel import
        └─ audit/      append-only activity log, CSV export, yearly archive
   │
PostgreSQL
```

**Design decisions**
- **Server-rendered HTML with HTMX** instead of a JavaScript framework: less code, and permissions are applied once, on the server.
- **One place for each rule:** `visible_customers(user)` is the only way views read customers, and one helper decides which fields a role may see.
- **Thin views, small service functions:** each action and its audit-log row run in one database transaction.
- **Settings from environment variables:** one `settings.py` for development and production; secrets never enter git.

## Getting started

Requirements: Python 3.15 via [uv](https://docs.astral.sh/uv/) and a local PostgreSQL.

```bash
git clone https://github.com/LynnAnya/customer-records-webapp.git
cd customer-records-webapp
createdb customer_records
cp .env.example .env          # then set SECRET_KEY (instructions inside the file)
uv run python manage.py migrate
uv run python manage.py create_admin yourname
uv run python manage.py seed_demo     # 60 fake customers for development
uv run python manage.py runserver
```

Then open http://127.0.0.1:8000.

## Tests

```bash
uv run pytest        # 396 tests: permissions, privacy rules, exports, security headers, import, UI fragments
uv run ruff check .
```

## Deployment

The app is set up for Render (web service) and Neon (PostgreSQL). `build.sh` installs the locked packages, collects static files, runs Django's production checks and applies migrations. Every setting is documented in [`.env.example`](.env.example).

## License

[MIT](LICENSE)
