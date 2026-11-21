#!/usr/bin/env bash
# Render runs this on every deploy (Build Command: ./build.sh), the pattern
# from Render's Django guide. Stop at the first failing command: a failed
# build never replaces the live site.
set -o errexit

# Install the exact locked packages (requirements.txt is generated from
# uv.lock; see the command at its top). Hashes make pip refuse altered files.
pip install -r requirements.txt

# Gather CSS, JS and fonts into staticfiles/ for WhiteNoise. input.css is the
# Tailwind source (built into app.css on the laptop), not a file for browsers.
python manage.py collectstatic --noinput --clear --ignore input.css

# Refuse to deploy with unsafe production settings.
python manage.py check --deploy --fail-level WARNING

# Create or update the database tables (Render Free has no Pre-Deploy Command).
python manage.py migrate --noinput
