"""Settings read Render's own hostname, so the first deploy needs no typing."""

import os
import subprocess
import sys


def settings_value(env: dict[str, str], expression: str) -> str:
    """Load settings in a fresh Python with these environment variables."""
    code = (
        "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
        f"django.setup(); from django.conf import settings as s; print({expression})"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_render_hostname_is_allowed_and_trusted() -> None:
    env = {"RENDER_EXTERNAL_HOSTNAME": "example.onrender.com", "ALLOWED_HOSTS": ""}

    hosts = settings_value(env, "s.ALLOWED_HOSTS")
    origins = settings_value(env, "s.CSRF_TRUSTED_ORIGINS")

    assert "example.onrender.com" in hosts
    assert "https://example.onrender.com" in origins


def test_without_render_nothing_is_added() -> None:
    env = {"RENDER_EXTERNAL_HOSTNAME": "", "ALLOWED_HOSTS": "localhost"}

    assert settings_value(env, "s.ALLOWED_HOSTS") == "['localhost']"
