import os
import re
import subprocess
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

# Maps browser identifiers (macOS bundle IDs, Linux .desktop stems, Windows ProgIDs,
# and plain names) to their browser_cookie3 extraction functions.
_BROWSER_MAP: dict[str, object] = {
    # macOS bundle IDs
    "com.google.chrome": browser_cookie3.chrome,
    "com.apple.safari": browser_cookie3.safari,
    "com.microsoft.edgemac": browser_cookie3.edge,
    "org.mozilla.firefox": browser_cookie3.firefox,
    "com.brave.browser": browser_cookie3.brave,
    "org.chromium.chromium": browser_cookie3.chromium,
    "company.thebrowser.browser": browser_cookie3.arc,
    "com.operasoftware.opera": browser_cookie3.opera,
    "com.vivaldi.vivaldi": browser_cookie3.vivaldi,
    # Linux .desktop file stems (without .desktop suffix)
    "google-chrome": browser_cookie3.chrome,
    "chromium": browser_cookie3.chromium,
    "chromium-browser": browser_cookie3.chromium,
    "microsoft-edge": browser_cookie3.edge,
    "firefox": browser_cookie3.firefox,
    "brave-browser": browser_cookie3.brave,
    "opera": browser_cookie3.opera,
    "vivaldi-stable": browser_cookie3.vivaldi,
    "arc": browser_cookie3.arc,
    # Windows ProgIDs (lowercase)
    "chromehtml": browser_cookie3.chrome,
    "msedgehtm": browser_cookie3.edge,
    "firefoxurl": browser_cookie3.firefox,
    "bravehtml": browser_cookie3.brave,
    "operastable": browser_cookie3.opera,
    # Plain names for BROWSER env var
    "chrome": browser_cookie3.chrome,
    "safari": browser_cookie3.safari,
    "edge": browser_cookie3.edge,
    "brave": browser_cookie3.brave,
    "vivaldi": browser_cookie3.vivaldi,
    "librewolf": browser_cookie3.librewolf,
    "opera_gx": browser_cookie3.opera_gx,
    "operagx": browser_cookie3.opera_gx,
}

# Tried in order if OS detection fails or yields no cookies.
_BROWSER_FALLBACK_ORDER = [
    ("Chrome", browser_cookie3.chrome),
    ("Safari", browser_cookie3.safari),
    ("Edge", browser_cookie3.edge),
    ("Firefox", browser_cookie3.firefox),
    ("Brave", browser_cookie3.brave),
    ("Chromium", browser_cookie3.chromium),
    ("Arc", browser_cookie3.arc),
    ("Opera", browser_cookie3.opera),
    ("Vivaldi", browser_cookie3.vivaldi),
    ("LibreWolf", browser_cookie3.librewolf),
]


def _extract_csrf_token(cookie_str: str) -> str:
    match = re.search(r"_csrf_token=([^;]+)", cookie_str)
    if match:
        return unquote(match.group(1))
    return ""


def _try_browser(fn, name: str, domain: str) -> str:
    """Try extracting cookies with the given browser_cookie3 function. Returns cookie string or ''."""
    try:
        cj = fn(domain_name=domain)
        parts = [f"{c.name}={c.value}" for c in cj]
        cookie_str = "; ".join(parts)
        if cookie_str:
            print(f"INFO: Successfully extracted Canvas cookies from {name}.", file=sys.stderr)
            return cookie_str
    except Exception:
        pass
    return ""


def _detect_default_browser():
    """
    Detect the OS default browser.
    Returns (browser_fn, browser_name) or (None, None) if detection fails.
    """
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "com.apple.LaunchServices/com.apple.launchservices.secure"],
                capture_output=True, text=True, timeout=5,
            )
            # Find the LSHandlerRoleAll entry associated with the http scheme
            # Output format: blocks of { LSHandlerContentType/URLScheme, LSHandlerRoleAll, ... }
            # We look for the block where LSHandlerURLScheme = http or https
            lines = result.stdout.splitlines()
            in_http_block = False
            handler_id = None
            for i, line in enumerate(lines):
                stripped = line.strip().strip('"').lower()
                if "lshandlerurlscheme" in stripped and ('"http"' in line.lower() or "= http" in line.lower()):
                    in_http_block = True
                if in_http_block and "lshandlerroleall" in stripped:
                    # Value is on same line: LSHandlerRoleAll = "com.google.chrome";
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        handler_id = parts[1].strip().strip('";').lower()
                    break
            if handler_id and handler_id in _BROWSER_MAP:
                name = handler_id.split(".")[-1].capitalize()
                return _BROWSER_MAP[handler_id], name

        elif sys.platform.startswith("linux"):
            result = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            )
            desktop_file = result.stdout.strip().lower().removesuffix(".desktop")
            if desktop_file in _BROWSER_MAP:
                name = desktop_file.replace("-", " ").title()
                return _BROWSER_MAP[desktop_file], name

        elif sys.platform == "win32":
            import winreg
            key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                prog_id_lower = prog_id.lower()
                for known_id, fn in _BROWSER_MAP.items():
                    if known_id in prog_id_lower:
                        return fn, prog_id
    except Exception:
        pass
    return None, None


def _get_canvas_cookie() -> str:
    """
    Get the Canvas cookie string.
    Priority:
      1. CANVAS_COOKIE env var (manual override)
      2. BROWSER env var (explicit browser name, e.g. 'firefox')
      3. OS default browser detection
      4. Ordered fallback across all supported browsers
    """
    if CANVAS_COOKIE:
        return CANVAS_COOKIE

    if not CANVAS_BASE_URL:
        return ""

    domain = urlparse(CANVAS_BASE_URL).netloc
    if not domain:
        return ""

    print("INFO: CANVAS_COOKIE not set, attempting automatic browser cookie extraction...", file=sys.stderr)

    # 1. BROWSER env var override
    browser_env = os.environ.get("BROWSER", "").strip().lower()
    if browser_env:
        fn = _BROWSER_MAP.get(browser_env)
        if fn:
            result = _try_browser(fn, browser_env.capitalize(), domain)
            if result:
                return result
            print(f"WARNING: BROWSER={browser_env!r} set but no Canvas cookies found in that browser.", file=sys.stderr)
        else:
            print(f"WARNING: BROWSER={browser_env!r} is not a recognized browser name.", file=sys.stderr)

    # 2. OS default browser
    detected_fn, detected_name = _detect_default_browser()
    if detected_fn:
        result = _try_browser(detected_fn, detected_name, domain)
        if result:
            return result

    # 3. Fallback: try all supported browsers in popularity order
    for name, fn in _BROWSER_FALLBACK_ORDER:
        result = _try_browser(fn, name, domain)
        if result:
            return result

    print(
        "WARNING: No Canvas cookies found in any browser. "
        "Please log into Canvas in your browser, or set CANVAS_COOKIE manually.",
        file=sys.stderr,
    )
    return ""


# This creates a shared active cookie used throughout the application
ACTIVE_CANVAS_COOKIE = _get_canvas_cookie()

CSRF_TOKEN: str = _extract_csrf_token(ACTIVE_CANVAS_COOKIE)

if ACTIVE_CANVAS_COOKIE and not CSRF_TOKEN:
    print(
        "WARNING: _csrf_token not found in Canvas cookies. Write operations (POST/PUT) "
        "will likely fail with 422. Make sure you are logged into Canvas in your browser.",
        file=sys.stderr,
    )
