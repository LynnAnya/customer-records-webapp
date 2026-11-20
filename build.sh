#!/usr/bin/env bash
# Render runs this on every deploy (Build Command: ./build.sh).
# Stop at the first command that fails: a failed build never replaces the live site.
set -o errexit

# Install exactly the locked packages, without the test tools.
uv sync --frozen --no-dev

# Gather CSS, JS and fonts into staticfiles/ for WhiteNoise. input.css is the
# Tailwind source (built into app.css on the laptop), not a file for browsers.
uv run --no-dev python manage.py collectstatic --noinput --clear --ignore input.css

# Refuse to deploy with unsafe production settings.
uv run --no-dev python manage.py check --deploy --fail-level WARNING
