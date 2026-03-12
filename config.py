import os
import re
from urllib.parse import unquote

CANVAS_BASE_URL = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
CANVAS_COOKIE = os.environ.get("CANVAS_COOKIE", "")
API_BASE = f"{CANVAS_BASE_URL}/api/v1"

def _extract_csrf_token(cookie_str: str) -> str:
    match = re.search(r"_csrf_token=([^;]+)", cookie_str)
    if match:
        return unquote(match.group(1))
    return ""

CSRF_TOKEN: str = _extract_csrf_token(CANVAS_COOKIE)
