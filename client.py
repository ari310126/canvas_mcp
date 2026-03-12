import httpx
from typing import Dict, Optional, Any, List
from config import CANVAS_COOKIE, CSRF_TOKEN, API_BASE

http_client = httpx.AsyncClient(
    timeout=30.0,
    follow_redirects=True,
)

def _read_headers() -> Dict[str, str]:
    return {
        "Cookie": CANVAS_COOKIE,
        "Accept": "application/json",
    }

def _write_headers() -> Dict[str, str]:
    return {
        "Cookie": CANVAS_COOKIE,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": CSRF_TOKEN,
    }

async def get(endpoint: str, params: Optional[Dict] = None) -> Any:
    r = await http_client.get(f"{API_BASE}{endpoint}", params=params or {}, headers=_read_headers())
    r.raise_for_status()
    return r.json()

async def post(endpoint: str, payload: Dict) -> Any:
    r = await http_client.post(f"{API_BASE}{endpoint}", json=payload, headers=_write_headers())
    r.raise_for_status()
    return r.json()

async def put(endpoint: str, payload: Dict) -> Any:
    r = await http_client.put(f"{API_BASE}{endpoint}", json=payload, headers=_write_headers())
    r.raise_for_status()
    return r.json()

async def patch(endpoint: str, payload: Dict) -> Any:
    r = await http_client.patch(f"{API_BASE}{endpoint}", json=payload, headers=_write_headers())
    r.raise_for_status()
    return r.json()

async def delete(endpoint: str) -> Any:
    r = await http_client.delete(f"{API_BASE}{endpoint}", headers=_write_headers())
    r.raise_for_status()
    return r.json()

async def paginate(endpoint: str, params: Optional[Dict] = None, limit: int = 50) -> List[Any]:
    collected: List[Any] = []
    url = f"{API_BASE}{endpoint}"
    query = dict(params or {})
    query.setdefault("per_page", min(limit, 100))

    while url and len(collected) < limit:
        r = await http_client.get(url, params=query, headers=_read_headers())
        r.raise_for_status()
        page = r.json()
        if isinstance(page, list):
            collected.extend(page)
        else:
            collected.append(page)
        url = _next_link(r.headers.get("Link", ""))
        query = {} 

    return collected[:limit]

def _next_link(link_header: str) -> Optional[str]:
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None

def handle_error(e: Exception) -> str:
    from config import CANVAS_BASE_URL, CSRF_TOKEN
    if isinstance(e, httpx.HTTPStatusError):
        s = e.response.status_code
        if s == 401:
            return (
                "Error: Unauthenticated (401). Your CANVAS_COOKIE may have expired. "
                "Log into Canvas, open DevTools → Network, click any request and copy "
                "the 'Cookie' header value, then restart the MCP server with the new value."
            )
        if s == 403:
            return "Error: Forbidden (403). You don't have permission to access this resource."
        if s == 404:
            return "Error: Not Found (404). Check that the course/resource ID is correct."
        if s == 422:
            detail = e.response.text[:500]
            csrf_hint = (
                " — CSRF token may be missing or stale. Re-copy the full Cookie header "
                "from your browser DevTools (including _csrf_token=...) and update CANVAS_COOKIE."
                if not CSRF_TOKEN else ""
            )
            return f"Error: Unprocessable Entity (422){csrf_hint}. Canvas response: {detail}"
        if s == 429:
            return "Error: Rate Limited (429). Too many requests — wait a moment and try again."
        return f"Error: Canvas API returned HTTP {s}: {e.response.text[:300]}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Canvas may be slow — try again shortly."
    if isinstance(e, httpx.ConnectError):
        return (
            f"Error: Cannot connect to Canvas at {CANVAS_BASE_URL}. "
            "Check that CANVAS_BASE_URL is correct and your network is available."
        )
    return f"Error: Unexpected error — {type(e).__name__}: {e}"
