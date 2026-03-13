import os
import re
import sys
from urllib.parse import unquote, urlparse
import browser_cookie3

CANVAS_BASE_URL = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
if CANVAS_BASE_URL and not CANVAS_BASE_URL.startswith("https://"):
    raise ValueError(
        f"CANVAS_BASE_URL must use HTTPS (got {CANVAS_BASE_URL!r}). "
        "Set CANVAS_BASE_URL to an https:// URL."
    )
CANVAS_COOKIE = os.environ.get("CANVAS_COOKIE", "")
API_BASE = f"{CANVAS_BASE_URL}/api/v1"

def _extract_csrf_token(cookie_str: str) -> str:
    match = re.search(r"_csrf_token=([^;]+)", cookie_str)
    if match:
        return unquote(match.group(1))
    return ""

def _get_canvas_cookie() -> str:
    """
    Get the Canvas cookie string.
    If CANVAS_COOKIE is set, use it. Otherwise, try to extract it from Brave browser.
    """
    if CANVAS_COOKIE:
        return CANVAS_COOKIE
    
    if not CANVAS_BASE_URL:
        return ""
        
    try:
        domain = urlparse(CANVAS_BASE_URL).netloc
        if not domain:
            return ""
            
        print("INFO: CANVAS_COOKIE not set, attempting to extract cookies from Brave browser...", file=sys.stderr)
        cj = browser_cookie3.brave(domain_name=domain)
        cookie_parts = []
        for cookie in cj:
            cookie_parts.append(f"{cookie.name}={cookie.value}")
        
        extracted_cookie = "; ".join(cookie_parts)
        if extracted_cookie:
            print("INFO: Successfully extracted Canvas cookies from Brave browser.", file=sys.stderr)
            return extracted_cookie
        else:
            print("WARNING: No Canvas cookies found. Please login to Canvas in Brave.", file=sys.stderr)
            return ""
    except Exception as e:
        print(f"WARNING: Failed to extract cookies from Brave browser ({type(e).__name__}).", file=sys.stderr)
        return ""

# This creates a shared active cookie used throughout the application
ACTIVE_CANVAS_COOKIE = _get_canvas_cookie()

CSRF_TOKEN: str = _extract_csrf_token(ACTIVE_CANVAS_COOKIE)

if ACTIVE_CANVAS_COOKIE and not CSRF_TOKEN:
    print(
        "WARNING: _csrf_token not found in Canvas cookies. Write operations (POST/PUT) "
        "will likely fail with 422. Make sure you are logged into Canvas in Brave.",
        file=sys.stderr,
    )
