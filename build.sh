#!/usr/bin/env bash
# Render runs this on every deploy (Build Command: ./build.sh). Stop at the
# first failing command: a failed build never replaces the live site.
# Start Command on Render: uv run --no-sync gunicorn config.wsgi:application
set -o errexit

# Use the Python that Render installs from .python-version. Never let uv
# download its own copy: it would live outside the project folder and might
# be missing when the app starts. If that Python is missing, stop here.
export UV_PYTHON_DOWNLOADS=never

# Install exactly what uv.lock lists, the same packages as the laptop.
# --locked stops the build if uv.lock no longer matches pyproject.toml
# (someone forgot `uv lock`); --no-dev skips pytest, ruff and pypdf.
uv sync --locked --no-dev

# The steps below run inside the environment just built. --no-sync: use it
# as it is, never install or remove anything.

# Gather CSS, JS and fonts into staticfiles/ for WhiteNoise. input.css is the
# Tailwind source (built into app.css on the laptop), not a file for browsers.
uv run --no-sync python manage.py collectstatic --noinput --clear --ignore input.css

# Refuse to deploy with unsafe production settings.
uv run --no-sync python manage.py check --deploy --fail-level WARNING

# Create or update the database tables (Render Free has no Pre-Deploy Command).
uv run --no-sync python manage.py migrate --noinput
