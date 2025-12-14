import gettext
import os
from pathlib import Path


def get_translator():
    """Return a gettext translator based on MONITOR_LANG, defaulting to English.

    If translation files are not available, falls back to no-op gettext.
    """
    lang = os.getenv("MONITOR_LANG", "en")
    locales_dir = Path(__file__).parent / "locales"
    try:
        t = gettext.translation("monitor", localedir=str(locales_dir), languages=[lang])
        t.install()
        return t.gettext
    except Exception:
        return gettext.gettext


_ = get_translator()

