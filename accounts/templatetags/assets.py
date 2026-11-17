from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


def _version(path: str) -> str:
    """The file's last-modified time, used as a version number."""
    found = finders.find(path)
    try:
        return str(int(Path(found).stat().st_mtime)) if found else ""
    except OSError:
        return ""


_cached_version = lru_cache(maxsize=None)(_version)


@register.simple_tag
def asset(path: str) -> str:
    """Like `{% static %}`, plus `?v=<version>`.

    Browsers keep CSS and JavaScript files for a long time. The version changes
    whenever the file changes, so everyone gets the new file at once and nobody
    has to clear their cache. In development the file is checked on every
    request; in production once per process.
    """
    version = _version(path) if settings.DEBUG else _cached_version(path)
    url = static(path)
    return f"{url}?v={version}" if version else url
