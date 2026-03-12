#!/usr/bin/env python3
"""
Canvas LMS MCP Server

Provides tools to read and write Canvas LMS course content using the same
browser-session-cookie approach as the AI Tutor browser extension — no Canvas
developer key or OAuth2 registration required.

Authentication:
    Set the following environment variables before starting the server:
        CANVAS_BASE_URL   Canvas instance root URL, e.g. https://uvu.instructure.com
        CANVAS_COOKIE     Raw Cookie header value copied from any authenticated
                          Canvas network request in your browser DevTools.
                          Example: "canvas_session=abc123; log_session_id=xyz789"

Usage:
    python server.py                   # stdio (default, for local Claude Desktop)
    python server.py --http            # streamable-HTTP on port 8080
"""

import json
import os
import re
import sys
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CANVAS_BASE_URL = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
CANVAS_COOKIE = os.environ.get("CANVAS_COOKIE", "")
API_BASE = f"{CANVAS_BASE_URL}/api/v1"

if not CANVAS_BASE_URL:
    print(
        "WARNING: CANVAS_BASE_URL is not set. Set it to your Canvas instance URL "
        "(e.g. https://uvu.instructure.com).",
        file=sys.stderr,
    )
if not CANVAS_COOKIE:
    print(
        "WARNING: CANVAS_COOKIE is not set. Copy the Cookie header from any "
        "authenticated Canvas request in your browser DevTools and set it here.",
        file=sys.stderr,
    )


def _extract_csrf_token(cookie_str: str) -> str:
    """
    Extract and URL-decode the _csrf_token from the raw Cookie header string.

    Canvas uses cookie-based CSRF protection. When authenticating via session
    cookies (the same approach as the browser extension), every POST/PUT/DELETE
    request must include the X-CSRF-Token header whose value is the URL-decoded
    contents of the _csrf_token cookie. Without this, Canvas returns 422.
    """
    match = re.search(r"_csrf_token=([^;]+)", cookie_str)
    if match:
        return unquote(match.group(1))
    return ""


# Parsed once at startup; refreshed whenever CANVAS_COOKIE is re-set.
CSRF_TOKEN: str = _extract_csrf_token(CANVAS_COOKIE)

if not CSRF_TOKEN:
    print(
        "WARNING: _csrf_token not found in CANVAS_COOKIE. Write operations (POST/PUT) "
        "will likely fail with 422. Make sure your CANVAS_COOKIE includes the "
        "_csrf_token= cookie from your browser session.",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("canvas_mcp")

# ---------------------------------------------------------------------------
# Shared HTTP client helpers
# ---------------------------------------------------------------------------

def _read_headers() -> Dict[str, str]:
    """Headers for read (GET) requests — cookie auth only."""
    return {
        "Cookie": CANVAS_COOKIE,
        "Accept": "application/json",
    }


def _write_headers() -> Dict[str, str]:
    """
    Headers for write (POST/PUT/DELETE) requests.

    Canvas requires X-CSRF-Token for all state-changing requests when
    authenticating via session cookie, matching browser behaviour.
    """
    return {
        "Cookie": CANVAS_COOKIE,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": CSRF_TOKEN,
    }


def _make_client(write: bool = False) -> httpx.AsyncClient:
    """Return a configured async HTTP client."""
    return httpx.AsyncClient(
        headers=_write_headers() if write else _read_headers(),
        timeout=30.0,
        follow_redirects=True,
    )


async def _get(endpoint: str, params: Optional[Dict] = None) -> Any:
    """Perform a GET request against the Canvas API."""
    async with _make_client(write=False) as client:
        r = await client.get(f"{API_BASE}{endpoint}", params=params or {})
        r.raise_for_status()
        return r.json()


async def _post(endpoint: str, payload: Dict) -> Any:
    """Perform a POST request against the Canvas API (includes X-CSRF-Token)."""
    async with _make_client(write=True) as client:
        r = await client.post(f"{API_BASE}{endpoint}", json=payload)
        r.raise_for_status()
        return r.json()


async def _put(endpoint: str, payload: Dict) -> Any:
    """Perform a PUT request against the Canvas API (includes X-CSRF-Token)."""
    async with _make_client(write=True) as client:
        r = await client.put(f"{API_BASE}{endpoint}", json=payload)
        r.raise_for_status()
        return r.json()


async def _patch(endpoint: str, payload: Dict) -> Any:
    """Perform a PATCH request against the Canvas API (includes X-CSRF-Token)."""
    async with _make_client(write=True) as client:
        r = await client.patch(f"{API_BASE}{endpoint}", json=payload)
        r.raise_for_status()
        return r.json()


async def _delete(endpoint: str) -> Any:
    """Perform a DELETE request against the Canvas API (includes X-CSRF-Token)."""
    async with _make_client(write=True) as client:
        r = await client.delete(f"{API_BASE}{endpoint}")
        r.raise_for_status()
        return r.json()


async def _paginate(endpoint: str, params: Optional[Dict] = None, limit: int = 50) -> List[Any]:
    """
    Follow Canvas Link-header pagination and collect up to `limit` items.
    Canvas returns paginated responses with a Link header pointing to the next page.
    """
    collected: List[Any] = []
    url = f"{API_BASE}{endpoint}"
    query = dict(params or {})
    query.setdefault("per_page", min(limit, 100))

    async with _make_client() as client:
        while url and len(collected) < limit:
            r = await client.get(url, params=query)
            r.raise_for_status()
            page = r.json()
            if isinstance(page, list):
                collected.extend(page)
            else:
                collected.append(page)
            # Parse Link header for next page
            url = _next_link(r.headers.get("Link", ""))
            query = {}  # params are embedded in the next URL already

    return collected[:limit]


def _next_link(link_header: str) -> Optional[str]:
    """Extract the 'next' URL from a Canvas Link response header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None


def _handle_error(e: Exception) -> str:
    """Format API errors into actionable messages."""
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


# ---------------------------------------------------------------------------
# Enums / shared models
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable.",
    )


class CourseListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enrollment_state: Optional[str] = Field(
        default="active",
        description="Filter by enrollment state: 'active', 'completed', 'invited', or 'current_and_invited'.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of courses to return.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CourseIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., description="The Canvas numeric course ID.", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AssignmentListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., description="Canvas course ID.", gt=0)
    bucket: Optional[str] = Field(
        default=None,
        description="Filter by bucket: 'past', 'overdue', 'undated', 'ungraded', 'upcoming', 'future'.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AssignmentGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class PageListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class PageGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    page_url: str = Field(
        ...,
        description="The URL slug of the page (e.g. 'week-1-overview'), not a full URL.",
        min_length=1,
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class PageCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Page title.")
    body: str = Field(..., description="Page body as HTML.")
    published: bool = Field(default=False, description="Whether to publish immediately.")


class PageUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    page_url: str = Field(..., min_length=1, description="Existing page URL slug to update.")
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, description="New HTML body. Replaces existing content.")
    published: Optional[bool] = Field(default=None)


class ModuleListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ModuleItemsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AnnouncementListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AnnouncementCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., description="Announcement body as HTML.")
    delayed_post_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 datetime to schedule the announcement (e.g. '2025-09-01T08:00:00Z').",
    )


class DiscussionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class DiscussionReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    topic_id: int = Field(..., gt=0, description="The discussion topic ID.")
    message: str = Field(..., min_length=1, description="Reply body as HTML or plain text.")


class AssignmentCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, description="Assignment instructions as HTML.")
    points_possible: Optional[float] = Field(default=None, ge=0)
    due_at: Optional[str] = Field(
        default=None,
        description="Due date as ISO 8601 (e.g. '2025-10-15T23:59:00Z').",
    )
    submission_types: List[str] = Field(
        default_factory=lambda: ["online_text_entry"],
        description="List of submission types: 'online_text_entry', 'online_upload', 'online_url', 'none', etc.",
    )
    published: bool = Field(default=False)


class AssignmentUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    points_possible: Optional[float] = Field(default=None, ge=0)
    due_at: Optional[str] = Field(default=None)
    published: Optional[bool] = Field(default=None)


class PlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (e.g. '2025-09-01'). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (e.g. '2025-12-31'). Defaults to 4 weeks out.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SubmissionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class FileListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# Helper formatters
# ---------------------------------------------------------------------------

def _fmt_course(c: Dict) -> str:
    score = c.get("enrollments", [{}])[0].get("computed_current_score")
    score_str = f" | Score: {score}%" if score is not None else ""
    return (
        f"### {c.get('name', 'Untitled')} (ID: {c.get('id')})\n"
        f"- Code: {c.get('course_code', 'N/A')}{score_str}\n"
    )


def _fmt_assignment(a: Dict) -> str:
    parts = [f"### {a.get('name', 'Untitled')} (ID: {a.get('id')})"]
    if a.get("due_at"):
        parts.append(f"- **Due**: {a['due_at']}")
    if a.get("points_possible") is not None:
        parts.append(f"- **Points**: {a['points_possible']}")
    if a.get("submission_types"):
        parts.append(f"- **Submission**: {', '.join(a['submission_types'])}")
    if a.get("html_url"):
        parts.append(f"- **Link**: {a['html_url']}")
    if a.get("description"):
        # Trim long HTML descriptions
        desc = a["description"][:300].replace("\n", " ")
        parts.append(f"- **Description** (excerpt): {desc}…")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# TOOLS — Read: Profile & Courses
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_get_profile",
    annotations={
        "title": "Get Canvas User Profile",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_profile(params: EmptyInput) -> str:
    """
    Get the current user's Canvas profile (name, ID, avatar, bio).

    Uses the authenticated browser session to call /api/v1/users/self.
    No Canvas developer key is required.

    Returns:
        str: Profile information in the requested format.

    Examples:
        - "Who am I on Canvas?" → canvas_get_profile()
        - "What is my Canvas user ID?" → canvas_get_profile()
    """
    try:
        data = await _get("/users/self")
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        return (
            f"# Canvas Profile\n\n"
            f"**Name**: {data.get('name', 'N/A')}\n"
            f"**ID**: {data.get('id', 'N/A')}\n"
            f"**Login**: {data.get('login_id', 'N/A')}\n"
            f"**Email**: {data.get('email', 'N/A')}\n"
            f"**Bio**: {data.get('bio') or '(none)'}\n"
            f"**Avatar**: {data.get('avatar_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_courses",
    annotations={
        "title": "List Canvas Courses",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_courses(params: CourseListInput) -> str:
    """
    List Canvas courses for the current user.

    Mirrors the course-listing logic in the AI Tutor browser extension, using the
    browser session cookie instead of an API key.

    Args:
        params (CourseListInput):
            - enrollment_state (str): Filter by 'active', 'completed', 'invited', etc.
            - limit (int): Maximum courses to return (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of courses with IDs, names, course codes, and current scores.

    Examples:
        - "What courses am I enrolled in?" → canvas_list_courses()
        - "Show me all completed courses" → canvas_list_courses(enrollment_state='completed')
    """
    try:
        courses = await _paginate(
            "/courses",
            params={
                "enrollment_state": params.enrollment_state,
                "include[]": ["total_scores", "computed_current_score", "course_image"],
                "per_page": 50,
            },
            limit=params.limit,
        )
        if not courses:
            return "No courses found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(courses, indent=2)
        lines = [f"# Canvas Courses ({len(courses)} found)\n"]
        for c in courses:
            lines.append(_fmt_course(c))
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_course",
    annotations={
        "title": "Get Canvas Course Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_course(params: CourseIdInput) -> str:
    """
    Get detailed information about a specific Canvas course, including its syllabus.

    Args:
        params (CourseIdInput):
            - course_id (int): The Canvas numeric course ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Course details including name, code, description, and syllabus body.

    Examples:
        - "Tell me about course 12345" → canvas_get_course(course_id=12345)
        - "Get the syllabus for my CS 101 course (ID 9988)" → canvas_get_course(course_id=9988)
    """
    try:
        data = await _get(
            f"/courses/{params.course_id}",
            params={"include[]": ["syllabus_body", "public_description", "total_scores"]},
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        syllabus = data.get("syllabus_body") or "(no syllabus)"
        return (
            f"# {data.get('name', 'Untitled')} (ID: {data.get('id')})\n\n"
            f"**Course Code**: {data.get('course_code', 'N/A')}\n"
            f"**Description**: {data.get('public_description') or '(none)'}\n\n"
            f"## Syllabus\n{syllabus}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Assignments
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_list_assignments",
    annotations={
        "title": "List Course Assignments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_assignments(params: AssignmentListInput) -> str:
    """
    List assignments for a Canvas course.

    Mirrors the assignment-fetching logic in the AI Tutor browser extension.
    Returns due dates, point values, submission types, and rubrics.

    Args:
        params (AssignmentListInput):
            - course_id (int): Canvas course ID.
            - bucket (str, optional): 'past', 'overdue', 'undated', 'ungraded', 'upcoming', 'future'.
            - limit (int): Max assignments to return (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of assignments with IDs, due dates, and point values.

    Examples:
        - "What assignments are upcoming in course 12345?" →
          canvas_list_assignments(course_id=12345, bucket='upcoming')
        - "List all assignments for course 9988" →
          canvas_list_assignments(course_id=9988)
    """
    try:
        query: Dict[str, Any] = {
            "include[]": ["rubric", "score_statistics"],
            "order_by": "due_at",
        }
        if params.bucket:
            query["bucket"] = params.bucket

        assignments = await _paginate(
            f"/courses/{params.course_id}/assignments",
            params=query,
            limit=params.limit,
        )
        if not assignments:
            return f"No assignments found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(assignments, indent=2)
        lines = [f"# Assignments — Course {params.course_id} ({len(assignments)} found)\n"]
        for a in assignments:
            lines.append(_fmt_assignment(a))
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_assignment",
    annotations={
        "title": "Get Assignment Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_assignment(params: AssignmentGetInput) -> str:
    """
    Get full details for a specific Canvas assignment, including its description and rubric.

    Args:
        params (AssignmentGetInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Full assignment details including description, rubric, submission types, and dates.
    """
    try:
        data = await _get(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}",
            params={"include[]": ["rubric", "submission"]},
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        rubric_lines = []
        for item in data.get("rubric") or []:
            rubric_lines.append(f"  - {item.get('description', '?')} ({item.get('points', '?')} pts)")
        rubric_str = "\n".join(rubric_lines) if rubric_lines else "  (no rubric)"
        return (
            f"# {data.get('name', 'Untitled')} (ID: {data.get('id')})\n\n"
            f"**Course**: {params.course_id}\n"
            f"**Due**: {data.get('due_at') or 'No due date'}\n"
            f"**Points**: {data.get('points_possible', 'N/A')}\n"
            f"**Submission Types**: {', '.join(data.get('submission_types', []))}\n"
            f"**Published**: {data.get('published', False)}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n\n"
            f"## Description\n{data.get('description') or '(no description)'}\n\n"
            f"## Rubric\n{rubric_str}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Pages (Wiki)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_list_pages",
    annotations={
        "title": "List Course Pages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_pages(params: PageListInput) -> str:
    """
    List wiki pages in a Canvas course.

    Args:
        params (PageListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max pages to return (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of pages with URL slugs, titles, and published status.

    Examples:
        - "What pages are in course 12345?" → canvas_list_pages(course_id=12345)
    """
    try:
        pages = await _paginate(f"/courses/{params.course_id}/pages", limit=params.limit)
        if not pages:
            return f"No pages found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(pages, indent=2)
        lines = [f"# Pages — Course {params.course_id} ({len(pages)} found)\n"]
        for p in pages:
            pub = "✓" if p.get("published") else "✗"
            lines.append(f"- [{p.get('title', 'Untitled')}] slug: `{p.get('url')}` | Published: {pub}")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_page",
    annotations={
        "title": "Get Page Content",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_page(params: PageGetInput) -> str:
    """
    Get the full content of a specific Canvas wiki page by its URL slug.

    Args:
        params (PageGetInput):
            - course_id (int): Canvas course ID.
            - page_url (str): Page URL slug (e.g. 'week-1-overview').
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Page title, body (HTML), and metadata.

    Examples:
        - "Show me the content of the 'syllabus-overview' page in course 12345"
          → canvas_get_page(course_id=12345, page_url='syllabus-overview')
    """
    try:
        data = await _get(f"/courses/{params.course_id}/pages/{params.page_url}")
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        return (
            f"# {data.get('title', 'Untitled')} (slug: {data.get('url')})\n\n"
            f"**Published**: {data.get('published', False)}\n"
            f"**Updated**: {data.get('updated_at', 'N/A')}\n"
            f"**Editor**: {data.get('last_edited_by', {}).get('display_name', 'N/A')}\n\n"
            f"## Body\n{data.get('body') or '(empty page)'}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Modules
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_list_modules",
    annotations={
        "title": "List Course Modules",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_modules(params: ModuleListInput) -> str:
    """
    List modules (content units) in a Canvas course.

    Args:
        params (ModuleListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max modules to return (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of modules with IDs, names, and item counts.
    """
    try:
        modules = await _paginate(f"/courses/{params.course_id}/modules", limit=params.limit)
        if not modules:
            return f"No modules found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(modules, indent=2)
        lines = [f"# Modules — Course {params.course_id} ({len(modules)} found)\n"]
        for m in modules:
            pub = "✓" if m.get("published") else "✗"
            lines.append(
                f"- **{m.get('name', 'Untitled')}** (ID: {m.get('id')}) "
                f"| Items: {m.get('items_count', '?')} | Published: {pub}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_module_items",
    annotations={
        "title": "List Module Items",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_module_items(params: ModuleItemsInput) -> str:
    """
    List all items inside a specific Canvas module.

    Args:
        params (ModuleItemsInput):
            - course_id (int): Canvas course ID.
            - module_id (int): Canvas module ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of module items with type, title, and URL.
    """
    try:
        items = await _paginate(
            f"/courses/{params.course_id}/modules/{params.module_id}/items",
            limit=100,
        )
        if not items:
            return f"No items found in module {params.module_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(items, indent=2)
        lines = [f"# Module {params.module_id} Items ({len(items)} found)\n"]
        for item in items:
            pub = "✓" if item.get("published") else "✗"
            lines.append(
                f"- [{item.get('type', '?')}] **{item.get('title', 'Untitled')}** "
                f"(ID: {item.get('id')}) | Published: {pub}"
            )
            if item.get("html_url"):
                lines.append(f"  Link: {item['html_url']}")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Announcements & Discussions
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_list_announcements",
    annotations={
        "title": "List Course Announcements",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_announcements(params: AnnouncementListInput) -> str:
    """
    List recent announcements for a Canvas course.

    Args:
        params (AnnouncementListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max announcements to return (default 20).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of announcements with titles, dates, and preview of message body.
    """
    try:
        announcements = await _paginate(
            "/announcements",
            params={"context_codes[]": f"course_{params.course_id}", "per_page": 20},
            limit=params.limit,
        )
        if not announcements:
            return f"No announcements found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(announcements, indent=2)
        lines = [f"# Announcements — Course {params.course_id} ({len(announcements)} found)\n"]
        for a in announcements:
            preview = (a.get("message") or "")[:200].replace("\n", " ")
            lines.append(
                f"### {a.get('title', 'Untitled')} (ID: {a.get('id')})\n"
                f"- **Posted**: {a.get('posted_at') or a.get('created_at', 'N/A')}\n"
                f"- **Author**: {a.get('author', {}).get('display_name', 'N/A')}\n"
                f"- **Preview**: {preview}…\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_discussions",
    annotations={
        "title": "List Course Discussions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_discussions(params: DiscussionListInput) -> str:
    """
    List discussion topics in a Canvas course.

    Args:
        params (DiscussionListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max discussions to return (default 20).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Discussion topics with IDs, titles, reply counts, and last activity.
    """
    try:
        topics = await _paginate(
            f"/courses/{params.course_id}/discussion_topics",
            limit=params.limit,
        )
        if not topics:
            return f"No discussions found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(topics, indent=2)
        lines = [f"# Discussions — Course {params.course_id} ({len(topics)} found)\n"]
        for t in topics:
            lines.append(
                f"### {t.get('title', 'Untitled')} (ID: {t.get('id')})\n"
                f"- **Replies**: {t.get('discussion_subentry_count', 0)}\n"
                f"- **Last Activity**: {t.get('last_reply_at') or t.get('created_at', 'N/A')}\n"
                f"- **Link**: {t.get('html_url', 'N/A')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Planner & Activity Stream
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_get_planner",
    annotations={
        "title": "Get Canvas Planner Items",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_planner(params: PlannerInput) -> str:
    """
    Get planner items (upcoming assignments, events, quizzes) for the current user.

    Mirrors the planner-fetching logic in the AI Tutor browser extension.

    Args:
        params (PlannerInput):
            - start_date (str, optional): ISO 8601 date (e.g. '2025-09-01').
            - end_date (str, optional): ISO 8601 date (e.g. '2025-12-31').
            - limit (int): Max items to return (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Upcoming tasks with due dates, types, and completion status.

    Examples:
        - "What's due this week?" → canvas_get_planner(start_date='2025-09-01', end_date='2025-09-07')
    """
    try:
        query: Dict[str, Any] = {"per_page": 50}
        if params.start_date:
            query["start_date"] = params.start_date
        if params.end_date:
            query["end_date"] = params.end_date

        items = await _paginate("/planner/items", params=query, limit=params.limit)
        if not items:
            return "No planner items found for the specified date range."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(items, indent=2)

        lines = [f"# Planner Items ({len(items)} found)\n"]
        for item in items:
            plannable = item.get("plannable", {})
            subs = item.get("submissions", {})
            status_parts = []
            if subs and isinstance(subs, dict):
                if subs.get("submitted"):
                    status_parts.append("✅ Submitted")
                if subs.get("missing"):
                    status_parts.append("❌ Missing")
                if subs.get("late"):
                    status_parts.append("⏰ Late")
                if subs.get("graded"):
                    status_parts.append("📝 Graded")
            status = " | ".join(status_parts) if status_parts else "—"
            lines.append(
                f"- **{plannable.get('title', 'Untitled')}** [{item.get('plannable_type', '?')}]\n"
                f"  Due: {item.get('plannable_date', 'N/A')} | Status: {status}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_activity_stream",
    annotations={
        "title": "Get Canvas Activity Stream",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_activity_stream(params: EmptyInput) -> str:
    """
    Get the current user's Canvas activity stream (recent notifications, submissions, messages).

    Mirrors the activity-stream logic in the AI Tutor browser extension.

    Returns:
        str: Recent activity items with type, title, and timestamp.
    """
    try:
        items = await _paginate(
            "/users/self/activity_stream",
            params={"only_active_courses": "true"},
            limit=50,
        )
        if not items:
            return "No activity found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(items, indent=2)
        lines = ["# Activity Stream\n"]
        for item in items:
            lines.append(
                f"- [{item.get('type', '?')}] **{item.get('title', 'Untitled')}** "
                f"| {item.get('created_at', 'N/A')}\n"
                f"  {(item.get('message') or '')[:120].replace(chr(10), ' ')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Read: Files & Submissions
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_list_files",
    annotations={
        "title": "List Course Files",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_files(params: FileListInput) -> str:
    """
    List files uploaded to a Canvas course.

    Args:
        params (FileListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max files to return (default 30).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: File list with names, sizes, types, and download URLs.
    """
    try:
        files = await _paginate(f"/courses/{params.course_id}/files", limit=params.limit)
        if not files:
            return f"No files found in course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(files, indent=2)
        lines = [f"# Files — Course {params.course_id} ({len(files)} found)\n"]
        for f in files:
            size_kb = round((f.get("size") or 0) / 1024, 1)
            lines.append(
                f"- **{f.get('display_name', 'Untitled')}** "
                f"({f.get('content-type', '?')}, {size_kb} KB)\n"
                f"  URL: {f.get('url', 'N/A')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_submissions",
    annotations={
        "title": "List Assignment Submissions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_submissions(params: SubmissionListInput) -> str:
    """
    List student submissions for an assignment (requires instructor/TA access).

    Args:
        params (SubmissionListInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - limit (int): Max submissions to return (default 30).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Submissions with user IDs, scores, submission dates, and grading status.
    """
    try:
        subs = await _paginate(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}/submissions",
            params={"include[]": ["user", "submission_comments"]},
            limit=params.limit,
        )
        if not subs:
            return "No submissions found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(subs, indent=2)
        lines = [f"# Submissions — Assignment {params.assignment_id} ({len(subs)} found)\n"]
        for s in subs:
            user = s.get("user", {})
            lines.append(
                f"- **{user.get('name', 'Unknown')}** (user {s.get('user_id')})\n"
                f"  Score: {s.get('score', 'ungraded')} | "
                f"Status: {s.get('workflow_state', '?')} | "
                f"Submitted: {s.get('submitted_at') or 'not submitted'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Write: Pages
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_create_page",
    annotations={
        "title": "Create Canvas Page",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_create_page(params: PageCreateInput) -> str:
    """
    Create a new wiki page in a Canvas course (requires Teacher/TA access).

    Args:
        params (PageCreateInput):
            - course_id (int): Canvas course ID.
            - title (str): Page title.
            - body (str): Page body as HTML.
            - published (bool): Publish immediately (default False).

    Returns:
        str: Confirmation with the new page's URL slug and link.

    Examples:
        - "Create a 'Week 5 Overview' page in course 12345 with content <p>Hello</p>"
          → canvas_create_page(course_id=12345, title='Week 5 Overview', body='<p>Hello</p>')
    """
    try:
        data = await _post(
            f"/courses/{params.course_id}/pages",
            {"wiki_page": {"title": params.title, "body": params.body, "published": params.published}},
        )
        return (
            f"✅ Page created successfully.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**Slug**: {data.get('url')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_page",
    annotations={
        "title": "Update Canvas Page",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_update_page(params: PageUpdateInput) -> str:
    """
    Update an existing wiki page in a Canvas course (requires Teacher/TA access).

    Only the fields you provide will be updated; omitted fields remain unchanged.

    Args:
        params (PageUpdateInput):
            - course_id (int): Canvas course ID.
            - page_url (str): Existing page URL slug to update.
            - title (str, optional): New title.
            - body (str, optional): New HTML body — replaces existing content.
            - published (bool, optional): Change publish status.

    Returns:
        str: Confirmation with updated page metadata.

    Examples:
        - "Update the body of page 'week-1-overview' in course 12345"
          → canvas_update_page(course_id=12345, page_url='week-1-overview', body='<p>New content</p>')
    """
    try:
        payload: Dict[str, Any] = {}
        if params.title is not None:
            payload["title"] = params.title
        if params.body is not None:
            payload["body"] = params.body
        if params.published is not None:
            payload["published"] = params.published
        data = await _put(
            f"/courses/{params.course_id}/pages/{params.page_url}",
            {"wiki_page": payload},
        )
        return (
            f"✅ Page updated.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**Slug**: {data.get('url')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Updated At**: {data.get('updated_at')}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Write: Assignments
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_create_assignment",
    annotations={
        "title": "Create Canvas Assignment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_create_assignment(params: AssignmentCreateInput) -> str:
    """
    Create a new assignment in a Canvas course (requires Teacher/TA access).

    Args:
        params (AssignmentCreateInput):
            - course_id (int): Canvas course ID.
            - name (str): Assignment name.
            - description (str, optional): Instructions as HTML.
            - points_possible (float, optional): Max points.
            - due_at (str, optional): ISO 8601 due date (e.g. '2025-10-15T23:59:00Z').
            - submission_types (List[str]): e.g. ['online_upload', 'online_text_entry'].
            - published (bool): Whether to publish (default False).

    Returns:
        str: Confirmation with new assignment ID and link.
    """
    try:
        payload: Dict[str, Any] = {
            "name": params.name,
            "submission_types": params.submission_types,
            "published": params.published,
        }
        if params.description is not None:
            payload["description"] = params.description
        if params.points_possible is not None:
            payload["points_possible"] = params.points_possible
        if params.due_at is not None:
            payload["due_at"] = params.due_at

        data = await _post(f"/courses/{params.course_id}/assignments", {"assignment": payload})
        return (
            f"✅ Assignment created.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Due**: {data.get('due_at') or 'No due date'}\n"
            f"**Points**: {data.get('points_possible', 'N/A')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_assignment",
    annotations={
        "title": "Update Canvas Assignment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_update_assignment(params: AssignmentUpdateInput) -> str:
    """
    Update an existing Canvas assignment (requires Teacher/TA access).

    Only provided fields are changed; others remain as-is.

    Args:
        params (AssignmentUpdateInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - name (str, optional): New name.
            - description (str, optional): New HTML description.
            - points_possible (float, optional): New point value.
            - due_at (str, optional): New ISO 8601 due date.
            - published (bool, optional): Change publish status.

    Returns:
        str: Confirmation with updated assignment metadata.
    """
    try:
        payload: Dict[str, Any] = {}
        if params.name is not None:
            payload["name"] = params.name
        if params.description is not None:
            payload["description"] = params.description
        if params.points_possible is not None:
            payload["points_possible"] = params.points_possible
        if params.due_at is not None:
            payload["due_at"] = params.due_at
        if params.published is not None:
            payload["published"] = params.published

        data = await _put(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}",
            {"assignment": payload},
        )
        return (
            f"✅ Assignment updated.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Due**: {data.get('due_at') or 'No due date'}\n"
            f"**Points**: {data.get('points_possible', 'N/A')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Write: Announcements & Discussions
# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_create_announcement",
    annotations={
        "title": "Create Course Announcement",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_create_announcement(params: AnnouncementCreateInput) -> str:
    """
    Post a new announcement to a Canvas course (requires Teacher/TA access).

    Args:
        params (AnnouncementCreateInput):
            - course_id (int): Canvas course ID.
            - title (str): Announcement title.
            - message (str): Announcement body as HTML.
            - delayed_post_at (str, optional): ISO 8601 datetime to schedule posting.

    Returns:
        str: Confirmation with announcement ID and link.

    Examples:
        - "Post an announcement 'Midterm reminder' to course 12345"
          → canvas_create_announcement(course_id=12345, title='Midterm reminder', message='<p>Don't forget!</p>')
    """
    try:
        payload: Dict[str, Any] = {
            "title": params.title,
            "message": params.message,
            "is_announcement": True,
        }
        if params.delayed_post_at:
            payload["delayed_post_at"] = params.delayed_post_at

        data = await _post(f"/courses/{params.course_id}/discussion_topics", payload)
        return (
            f"✅ Announcement posted.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Posted At**: {data.get('posted_at') or data.get('delayed_post_at') or 'N/A'}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_post_discussion_reply",
    annotations={
        "title": "Post Discussion Reply",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_post_discussion_reply(params: DiscussionReplyInput) -> str:
    """
    Post a reply to a Canvas discussion topic.

    Args:
        params (DiscussionReplyInput):
            - course_id (int): Canvas course ID.
            - topic_id (int): Discussion topic ID (from canvas_list_discussions).
            - message (str): Reply body as HTML or plain text.

    Returns:
        str: Confirmation with reply ID and timestamp.

    Examples:
        - "Reply to discussion 456 in course 12345 with 'Great point!'"
          → canvas_post_discussion_reply(course_id=12345, topic_id=456, message='Great point!')
    """
    try:
        data = await _post(
            f"/courses/{params.course_id}/discussion_topics/{params.topic_id}/entries",
            {"message": params.message},
        )
        return (
            f"✅ Reply posted.\n\n"
            f"**Reply ID**: {data.get('id')}\n"
            f"**Author**: {data.get('user_name', 'N/A')}\n"
            f"**Created At**: {data.get('created_at', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Grading
# ---------------------------------------------------------------------------

class RubricCriterionGrade(BaseModel):
    """Grade for a single rubric criterion."""
    model_config = ConfigDict(extra="forbid")
    criterion_id: str = Field(
        ...,
        description=(
            "The Canvas criterion ID from the assignment rubric "
            "(e.g. '_4521', 'crit_abc123'). "
            "Retrieve it via canvas_get_assignment."
        ),
    )
    points: Optional[float] = Field(
        default=None,
        ge=0,
        description="Points awarded for this criterion.",
    )
    rating_id: Optional[str] = Field(
        default=None,
        description="ID of the selected rating (optional; use with rubric rating scales).",
    )
    comments: Optional[str] = Field(
        default=None,
        description="Free-text feedback for this specific criterion.",
    )


class SubmissionGradeInput(BaseModel):
    """Input for grading a student submission."""
    model_config = ConfigDict(extra="forbid")

    course_id: int = Field(..., gt=0, description="Canvas course ID.")
    assignment_id: int = Field(..., gt=0, description="Canvas assignment ID.")
    user_id: int = Field(
        ..., gt=0,
        description="Canvas user ID of the student whose submission is being graded.",
    )
    posted_grade: Optional[str] = Field(
        default=None,
        description=(
            "The grade to assign. Accepts multiple formats depending on the assignment's "
            "grading type:\n"
            "  • Points: '87' or '87.5'\n"
            "  • Percentage: '92%'\n"
            "  • Letter: 'A-', 'B+'\n"
            "  • Pass/Fail: 'pass' or 'fail'\n"
            "  • Complete/Incomplete: 'complete' or 'incomplete'\n"
            "Leave null to only add a comment or rubric assessment without changing the grade."
        ),
    )
    excuse: Optional[bool] = Field(
        default=None,
        description="Set to true to mark the submission as excused (exempt from grading).",
    )
    late_policy_status: Optional[str] = Field(
        default=None,
        description=(
            "Override the late policy status: 'late', 'missing', 'extended', 'none', or null "
            "to clear an override."
        ),
    )
    seconds_late_override: Optional[int] = Field(
        default=None,
        ge=0,
        description="If late_policy_status='late', specify how many seconds late the submission is.",
    )
    text_comment: Optional[str] = Field(
        default=None,
        description="Text comment to add to the submission (visible to the student).",
    )
    group_comment: Optional[bool] = Field(
        default=None,
        description="If true and this is a group assignment, the comment applies to all group members.",
    )
    rubric_criteria: Optional[List[RubricCriterionGrade]] = Field(
        default=None,
        description=(
            "List of per-criterion rubric grades. Each item must include criterion_id "
            "(from the assignment rubric) and at least one of: points, rating_id, comments. "
            "Use canvas_get_assignment to retrieve criterion IDs first."
        ),
    )


class SubmissionGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0, description="Canvas user ID of the student.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GradeableStudentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SubmissionCountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)


# ---------------------------------------------------------------------------

@mcp.tool(
    name="canvas_get_submission",
    annotations={
        "title": "Get Single Student Submission",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_submission(params: SubmissionGetInput) -> str:
    """
    Get a specific student's submission for an assignment, including score, grade,
    submission content, comments, rubric assessment, and workflow state.

    Args:
        params (SubmissionGetInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - user_id (int): Canvas user ID of the student.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Submission details — grade, score, status, submitted content, and comments.

    Examples:
        - "Show me student 4521's submission for assignment 789 in course 12345"
          → canvas_get_submission(course_id=12345, assignment_id=789, user_id=4521)
    """
    try:
        data = await _get(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/submissions/{params.user_id}",
            params={
                "include[]": [
                    "submission_comments",
                    "rubric_assessment",
                    "user",
                    "assignment",
                ]
            },
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)

        user = data.get("user", {})
        comments = data.get("submission_comments", [])
        rubric = data.get("rubric_assessment", {})

        comment_lines = []
        for c in comments:
            comment_lines.append(
                f"  - [{c.get('created_at', '?')}] **{c.get('author_name', '?')}**: "
                f"{c.get('comment', '')}"
            )

        rubric_lines = []
        for crit_id, assessment in rubric.items():
            rubric_lines.append(
                f"  - Criterion `{crit_id}`: "
                f"{assessment.get('points', '?')} pts — {assessment.get('comments', '(no comment)')}"
            )

        return (
            f"# Submission — {user.get('name', f'User {params.user_id}')}\n\n"
            f"**Assignment ID**: {params.assignment_id}\n"
            f"**Status**: {data.get('workflow_state', 'N/A')}\n"
            f"**Grade**: {data.get('grade') or '(ungraded)'}\n"
            f"**Score**: {data.get('score') or '(ungraded)'}\n"
            f"**Excused**: {data.get('excused', False)}\n"
            f"**Late**: {data.get('late', False)}\n"
            f"**Missing**: {data.get('missing', False)}\n"
            f"**Submitted At**: {data.get('submitted_at') or 'not submitted'}\n"
            f"**Submission Type**: {data.get('submission_type') or 'N/A'}\n\n"
            + (f"## Submitted Content\n{data.get('body') or data.get('url') or '(no content)'}\n\n"
               if data.get("body") or data.get("url") else "")
            + (f"## Rubric Assessment\n" + "\n".join(rubric_lines) + "\n\n" if rubric_lines else "")
            + (f"## Comments ({len(comments)})\n" + "\n".join(comment_lines) if comments else "")
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_gradeable_students",
    annotations={
        "title": "List Gradeable Students",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_gradeable_students(params: GradeableStudentsInput) -> str:
    """
    List students eligible to be graded for a specific assignment (instructor/TA only).

    Returns Canvas user IDs needed for canvas_grade_submission.

    Args:
        params (GradeableStudentsInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: List of students with IDs and names.

    Examples:
        - "Who can I grade on assignment 789 in course 12345?"
          → canvas_list_gradeable_students(course_id=12345, assignment_id=789)
    """
    try:
        students = await _paginate(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}/gradeable_students",
            limit=200,
        )
        if not students:
            return "No gradeable students found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(students, indent=2)
        lines = [f"# Gradeable Students — Assignment {params.assignment_id} ({len(students)} found)\n"]
        for s in students:
            lines.append(f"- **{s.get('display_name', 'Unknown')}** (user_id: {s.get('id')})")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_submission_counts",
    annotations={
        "title": "Get Submission Grading Counts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_submission_counts(params: SubmissionCountInput) -> str:
    """
    Get grading progress counts for an assignment: how many submissions are
    graded, ungraded, or not yet submitted.

    Args:
        params (SubmissionCountInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.

    Returns:
        str: Counts of graded, ungraded, and not_submitted submissions.

    Examples:
        - "How many submissions are still ungraded for assignment 789?"
          → canvas_get_submission_counts(course_id=12345, assignment_id=789)
    """
    try:
        data = await _get(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            "/submission_summary"
        )
        graded = data.get("graded", 0)
        ungraded = data.get("ungraded", 0)
        not_submitted = data.get("not_submitted", 0)
        total = graded + ungraded + not_submitted
        return (
            f"# Submission Summary — Assignment {params.assignment_id}\n\n"
            f"- ✅ **Graded**: {graded}\n"
            f"- 🕐 **Ungraded** (submitted but not graded): {ungraded}\n"
            f"- ❌ **Not Submitted**: {not_submitted}\n"
            f"- 📊 **Total enrolled**: {total}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_grade_submission",
    annotations={
        "title": "Grade Student Submission",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_grade_submission(params: SubmissionGradeInput) -> str:
    """
    Grade a student's submission — assign a score, fill in a rubric assessment,
    leave a text comment, or mark as excused. Requires Teacher/TA access.

    Supports all Canvas grading types: points, percentage, letter grade, pass/fail,
    complete/incomplete. Also supports per-criterion rubric grading and inline comments.

    WORKFLOW: First call canvas_get_assignment to get rubric criterion IDs, then
    canvas_list_gradeable_students to get student user IDs, then this tool to grade.

    Args:
        params (SubmissionGradeInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - user_id (int): Canvas user ID of the student to grade.
            - posted_grade (str, optional): Grade to assign. Examples:
                '87' (points), '92%' (percentage), 'A-' (letter), 'pass', 'complete'.
            - excuse (bool, optional): True to mark the submission as excused.
            - late_policy_status (str, optional): 'late', 'missing', 'extended', 'none'.
            - seconds_late_override (int, optional): Seconds late (when late_policy_status='late').
            - text_comment (str, optional): Text feedback visible to the student.
            - group_comment (bool, optional): Apply comment to all group members.
            - rubric_criteria (list, optional): Per-criterion rubric grades. Each item:
                { criterion_id: str, points: float, rating_id: str, comments: str }
                Get criterion IDs from canvas_get_assignment first.

    Returns:
        str: Updated submission details showing new grade, score, and workflow state.

    Examples:
        - Grade with points and a comment:
          canvas_grade_submission(course_id=12345, assignment_id=789, user_id=4521,
                                  posted_grade='87', text_comment='Great analysis!')
        - Grade with rubric only (no overall score — Canvas computes total):
          canvas_grade_submission(course_id=12345, assignment_id=789, user_id=4521,
                                  rubric_criteria=[
                                      {'criterion_id': '_123', 'points': 5, 'comments': 'Excellent'},
                                      {'criterion_id': '_456', 'points': 3}
                                  ])
        - Excuse an assignment:
          canvas_grade_submission(course_id=12345, assignment_id=789, user_id=4521, excuse=True)
        - Mark as missing:
          canvas_grade_submission(course_id=12345, assignment_id=789, user_id=4521,
                                  late_policy_status='missing')

    Error Handling:
        - 401: Session cookie expired — re-copy CANVAS_COOKIE from browser
        - 403: You don't have grading permission for this course
        - 404: Student not enrolled or assignment not found
        - 422: Check that criterion_id values match the actual assignment rubric
    """
    try:
        payload: Dict[str, Any] = {}

        # ---- submission sub-params ----
        submission: Dict[str, Any] = {}
        if params.posted_grade is not None:
            submission["posted_grade"] = params.posted_grade
        if params.excuse is not None:
            submission["excuse"] = params.excuse
        if params.late_policy_status is not None:
            submission["late_policy_status"] = params.late_policy_status
        if params.seconds_late_override is not None:
            submission["seconds_late_override"] = params.seconds_late_override
        if submission:
            payload["submission"] = submission

        # ---- comment sub-params ----
        comment: Dict[str, Any] = {}
        if params.text_comment is not None:
            comment["text_comment"] = params.text_comment
        if params.group_comment is not None:
            comment["group_comment"] = params.group_comment
        if comment:
            payload["comment"] = comment

        # ---- rubric assessment ----
        # Canvas expects a nested dict: { criterion_id: { points, rating_id, comments } }
        if params.rubric_criteria:
            rubric_payload: Dict[str, Any] = {}
            for crit in params.rubric_criteria:
                entry: Dict[str, Any] = {}
                if crit.points is not None:
                    entry["points"] = crit.points
                if crit.rating_id is not None:
                    entry["rating_id"] = crit.rating_id
                if crit.comments is not None:
                    entry["comments"] = crit.comments
                if entry:
                    rubric_payload[crit.criterion_id] = entry
            if rubric_payload:
                payload["rubric_assessment"] = rubric_payload

        if not payload:
            return (
                "Error: No grading parameters provided. Specify at least one of: "
                "posted_grade, excuse, late_policy_status, text_comment, or rubric_criteria."
            )

        data = await _put(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/submissions/{params.user_id}",
            payload,
        )

        rubric = data.get("rubric_assessment", {})
        rubric_lines = []
        for crit_id, assessment in rubric.items():
            rubric_lines.append(
                f"  - `{crit_id}`: {assessment.get('points', '?')} pts"
                + (f" — {assessment.get('comments')}" if assessment.get("comments") else "")
            )

        return (
            f"✅ Submission graded.\n\n"
            f"**Student user_id**: {data.get('user_id')}\n"
            f"**Assignment**: {params.assignment_id}\n"
            f"**Grade**: {data.get('grade') or '(pending)'}\n"
            f"**Score**: {data.get('score') or '(pending)'}\n"
            f"**Excused**: {data.get('excused', False)}\n"
            f"**Workflow State**: {data.get('workflow_state', 'N/A')}\n"
            f"**Grade Matches Current Submission**: {data.get('grade_matches_current_submission', 'N/A')}\n"
            + (f"\n**Rubric Assessment**:\n" + "\n".join(rubric_lines) if rubric_lines else "")
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Assignment Overrides (per-student / per-section / per-group dates)
# ---------------------------------------------------------------------------

class OverrideTarget(str, Enum):
    """What the override targets."""
    STUDENTS = "students"
    SECTION = "section"
    GROUP = "group"


class OverrideListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class OverrideGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0, description="Canvas assignment override ID.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class OverrideCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)

    # Target — exactly one must be provided
    student_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "List of Canvas user IDs to include in this override. "
            "Use when setting different dates for specific students. "
            "Get user IDs from canvas_list_gradeable_students."
        ),
    )
    course_section_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Canvas section ID. Use to override dates for an entire section.",
    )
    group_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Canvas group ID. Use to override dates for a group assignment group.",
    )

    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description=(
            "Human-readable label for this override (required when targeting student_ids). "
            "Example: 'Extended deadline — Smith, Jones'."
        ),
    )
    due_at: Optional[str] = Field(
        default=None,
        description=(
            "New due date as ISO 8601 (e.g. '2025-10-20T23:59:00Z'). "
            "Pass null to remove a due date override."
        ),
    )
    unlock_at: Optional[str] = Field(
        default=None,
        description="Date the assignment becomes available to the target (ISO 8601). Null to remove.",
    )
    lock_at: Optional[str] = Field(
        default=None,
        description=(
            "Date the assignment locks for the target (ISO 8601). "
            "This is the 'Until' date students see. Null to remove."
        ),
    )


class OverrideUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0, description="ID of the override to update.")

    # ⚠️ Canvas replaces ALL date fields on PUT — omitting a date removes its override.
    # The tool fetches the existing override first and merges, so only fields you
    # explicitly provide will change.
    student_ids: Optional[List[int]] = Field(
        default=None,
        description="Replace the list of targeted student IDs.",
    )
    title: Optional[str] = Field(default=None, max_length=255)
    due_at: Optional[str] = Field(
        default=None,
        description=(
            "New due date (ISO 8601). Pass the string 'null' to explicitly remove the due date override."
        ),
    )
    unlock_at: Optional[str] = Field(
        default=None,
        description="New unlock date (ISO 8601). Pass 'null' to remove.",
    )
    lock_at: Optional[str] = Field(
        default=None,
        description="New lock/Until date (ISO 8601). Pass 'null' to remove.",
    )


class OverrideDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0)


# ---------------------------------------------------------------------------

def _fmt_override(o: Dict) -> str:
    """Format a single assignment override as a markdown block."""
    target_parts = []
    if o.get("student_ids"):
        target_parts.append(f"Students: {o['student_ids']}")
    if o.get("course_section_id"):
        target_parts.append(f"Section ID: {o['course_section_id']}")
    if o.get("group_id"):
        target_parts.append(f"Group ID: {o['group_id']}")
    target = " | ".join(target_parts) if target_parts else "Unknown"

    return (
        f"### {o.get('title', 'Untitled')} (Override ID: {o.get('id')})\n"
        f"- **Target**: {target}\n"
        f"- **Due At**: {o.get('due_at') or '(not overridden)'}\n"
        f"- **Unlock At**: {o.get('unlock_at') or '(not overridden)'}\n"
        f"- **Lock At (Until)**: {o.get('lock_at') or '(not overridden)'}\n"
        f"- **All Day**: {o.get('all_day', False)}\n"
    )


@mcp.tool(
    name="canvas_list_assignment_overrides",
    annotations={
        "title": "List Assignment Overrides",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_assignment_overrides(params: OverrideListInput) -> str:
    """
    List all date overrides for a Canvas assignment (per-student, per-section, per-group).

    Each override can independently set a due date, unlock date, and lock/Until date
    for a specific set of students, a section, or a group.

    Args:
        params (OverrideListInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: All overrides with IDs, targets, and date fields.

    Examples:
        - "What due date overrides exist for assignment 789?"
          → canvas_list_assignment_overrides(course_id=12345, assignment_id=789)
    """
    try:
        overrides = await _paginate(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}/overrides",
            limit=200,
        )
        if not overrides:
            return f"No overrides found for assignment {params.assignment_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(overrides, indent=2)
        lines = [
            f"# Assignment Overrides — Assignment {params.assignment_id} "
            f"({len(overrides)} found)\n"
        ]
        for o in overrides:
            lines.append(_fmt_override(o))
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_assignment_override",
    annotations={
        "title": "Get Assignment Override",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_get_assignment_override(params: OverrideGetInput) -> str:
    """
    Get a single assignment date override by its ID.

    Args:
        params (OverrideGetInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - override_id (int): The override ID (from canvas_list_assignment_overrides).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Override details including target, due_at, unlock_at, lock_at.
    """
    try:
        data = await _get(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/overrides/{params.override_id}"
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        return f"# Override Details\n\n{_fmt_override(data)}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_assignment_override",
    annotations={
        "title": "Create Assignment Override",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_create_assignment_override(params: OverrideCreateInput) -> str:
    """
    Create a new assignment date override for specific students, a section, or a group.

    Use this to give individual students extended deadlines or different availability
    windows without changing the assignment's default dates for the rest of the class.

    Target rules — provide exactly ONE of:
        - student_ids: list of Canvas user IDs (get from canvas_list_gradeable_students)
        - course_section_id: override the whole section
        - group_id: override a group (for group assignments)

    Args:
        params (OverrideCreateInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - student_ids (List[int], optional): Specific student user IDs.
            - course_section_id (int, optional): Section ID.
            - group_id (int, optional): Group ID.
            - title (str, optional): Label for this override (required for student overrides).
            - due_at (str, optional): New due date, ISO 8601 (e.g. '2025-10-20T23:59:00Z').
            - unlock_at (str, optional): New unlock/available-from date, ISO 8601.
            - lock_at (str, optional): New lock/Until date, ISO 8601.

    Returns:
        str: Confirmation with the new override ID and its dates.

    Examples:
        - "Give student 4521 a one-week extension on assignment 789":
          canvas_create_assignment_override(
              course_id=12345, assignment_id=789,
              student_ids=[4521], title='Extension — Student Name',
              due_at='2025-11-01T23:59:00Z', lock_at='2025-11-02T23:59:00Z'
          )
        - "Make assignment 789 available two days later for section 55":
          canvas_create_assignment_override(
              course_id=12345, assignment_id=789,
              course_section_id=55, unlock_at='2025-10-17T00:00:00Z',
              due_at='2025-10-24T23:59:00Z'
          )
    """
    try:
        target_count = sum([
            bool(params.student_ids),
            bool(params.course_section_id),
            bool(params.group_id),
        ])
        if target_count == 0:
            return (
                "Error: You must specify exactly one target — "
                "student_ids, course_section_id, or group_id."
            )
        if target_count > 1:
            return (
                "Error: Specify only one target type — "
                "student_ids, course_section_id, or group_id (not multiple)."
            )
        if params.student_ids and not params.title:
            return (
                "Error: title is required when targeting specific students. "
                "Example: 'Extended deadline — Smith'."
            )

        override: Dict[str, Any] = {}
        if params.student_ids:
            override["student_ids"] = params.student_ids
        if params.course_section_id:
            override["course_section_id"] = params.course_section_id
        if params.group_id:
            override["group_id"] = params.group_id
        if params.title:
            override["title"] = params.title
        if params.due_at is not None:
            override["due_at"] = params.due_at
        if params.unlock_at is not None:
            override["unlock_at"] = params.unlock_at
        if params.lock_at is not None:
            override["lock_at"] = params.lock_at

        data = await _post(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}/overrides",
            {"assignment_override": override},
        )
        return (
            f"✅ Assignment override created.\n\n"
            f"{_fmt_override(data)}"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_assignment_override",
    annotations={
        "title": "Update Assignment Override",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_update_assignment_override(params: OverrideUpdateInput) -> str:
    """
    Update an existing assignment date override (change due date, lock date, etc.).

    Canvas replaces ALL date fields on a PUT, so this tool first fetches the existing
    override and merges your changes — only the fields you explicitly provide will change.
    Pass the string 'null' for a date field to explicitly remove that override.

    Args:
        params (OverrideUpdateInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - override_id (int): ID of the override to update.
            - student_ids (List[int], optional): Replace targeted student IDs.
            - title (str, optional): New label.
            - due_at (str, optional): New due date (ISO 8601) or 'null' to remove.
            - unlock_at (str, optional): New unlock date (ISO 8601) or 'null' to remove.
            - lock_at (str, optional): New lock/Until date (ISO 8601) or 'null' to remove.

    Returns:
        str: Updated override details.

    Examples:
        - "Change the due date on override 99 to Nov 5":
          canvas_update_assignment_override(
              course_id=12345, assignment_id=789, override_id=99,
              due_at='2025-11-05T23:59:00Z'
          )
        - "Remove the lock date from override 99":
          canvas_update_assignment_override(
              course_id=12345, assignment_id=789, override_id=99,
              lock_at='null'
          )
    """
    try:
        # Fetch current state so we can merge — Canvas removes any omitted date field
        existing = await _get(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/overrides/{params.override_id}"
        )

        # Start from existing values
        override: Dict[str, Any] = {}

        # Preserve existing target (read-only after creation, but must be sent)
        if existing.get("student_ids"):
            override["student_ids"] = existing["student_ids"]
        if existing.get("course_section_id"):
            override["course_section_id"] = existing["course_section_id"]
        if existing.get("group_id"):
            override["group_id"] = existing["group_id"]

        # Title
        override["title"] = params.title if params.title is not None else existing.get("title", "")

        # Student IDs override (replace)
        if params.student_ids is not None:
            override["student_ids"] = params.student_ids

        # Date fields: apply provided changes; 'null' string → Python None → removes override
        def _resolve_date(new_val: Optional[str], existing_val: Optional[str]) -> Optional[str]:
            if new_val is None:
                return existing_val  # unchanged
            if new_val.lower() == "null":
                return None  # explicitly remove
            return new_val  # update

        override["due_at"] = _resolve_date(params.due_at, existing.get("due_at"))
        override["unlock_at"] = _resolve_date(params.unlock_at, existing.get("unlock_at"))
        override["lock_at"] = _resolve_date(params.lock_at, existing.get("lock_at"))

        data = await _put(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/overrides/{params.override_id}",
            {"assignment_override": override},
        )
        return (
            f"✅ Assignment override updated.\n\n"
            f"{_fmt_override(data)}"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_delete_assignment_override",
    annotations={
        "title": "Delete Assignment Override",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_delete_assignment_override(params: OverrideDeleteInput) -> str:
    """
    Delete an assignment date override.

    After deletion, the affected students/section/group will revert to the
    assignment's default due/unlock/lock dates.

    Args:
        params (OverrideDeleteInput):
            - course_id (int): Canvas course ID.
            - assignment_id (int): Canvas assignment ID.
            - override_id (int): ID of the override to delete.

    Returns:
        str: Confirmation that the override was deleted.

    Examples:
        - "Remove the extension override 99 for assignment 789":
          canvas_delete_assignment_override(course_id=12345, assignment_id=789, override_id=99)
    """
    try:
        data = await _delete(
            f"/courses/{params.course_id}/assignments/{params.assignment_id}"
            f"/overrides/{params.override_id}"
        )
        return (
            f"✅ Override deleted. The affected students/section now use the assignment's "
            f"default dates.\n\n"
            f"Deleted override: **{data.get('title', 'Untitled')}** (ID: {data.get('id')})"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Enrollments / Roster
# ---------------------------------------------------------------------------

class EnrollmentListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    role: Optional[str] = Field(
        default=None,
        description=(
            "Filter by enrollment role. Common values: 'StudentEnrollment', "
            "'TeacherEnrollment', 'TaEnrollment', 'ObserverEnrollment', 'DesignerEnrollment'. "
            "Leave empty to return all roles."
        ),
    )
    section_id: Optional[int] = Field(
        default=None, gt=0,
        description="Filter to a specific section ID.",
    )
    state: Optional[str] = Field(
        default="active",
        description="Enrollment state: 'active', 'invited', 'creation_pending', 'deleted', 'rejected', 'completed', 'inactive'.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="canvas_list_enrollments",
    annotations={
        "title": "List Course Enrollments / Roster",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_enrollments(params: EnrollmentListInput) -> str:
    """
    List enrollments for a Canvas course — the full class roster, filterable by role and section.

    Use this to get student user IDs (needed for grading/messaging/overrides),
    see TAs, or check who is enrolled in a specific section.

    Args:
        params (EnrollmentListInput):
            - course_id (int): Canvas course ID.
            - role (str, optional): 'StudentEnrollment', 'TaEnrollment', 'TeacherEnrollment', etc.
            - section_id (int, optional): Restrict to a specific section.
            - state (str): Enrollment state (default 'active').
            - limit (int): Max results (default 50).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Roster with names, user IDs, roles, sections, and current grades.

    Examples:
        - "Who are all the students in course 12345?"
          → canvas_list_enrollments(course_id=12345, role='StudentEnrollment')
        - "Show TAs for course 12345"
          → canvas_list_enrollments(course_id=12345, role='TaEnrollment')
    """
    try:
        query: Dict[str, Any] = {
            "state[]": params.state,
            "include[]": ["user", "avatar_url", "current_points"],
        }
        if params.role:
            query["type[]"] = params.role
        if params.section_id:
            query["section_id"] = params.section_id

        enrollments = await _paginate(f"/courses/{params.course_id}/enrollments", params=query, limit=params.limit)
        if not enrollments:
            return f"No enrollments found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(enrollments, indent=2)

        lines = [f"# Roster — Course {params.course_id} ({len(enrollments)} enrollments)\n"]
        for e in enrollments:
            user = e.get("user", {})
            grade = e.get("grades", {}).get("current_score")
            grade_str = f" | Grade: {grade}%" if grade is not None else ""
            lines.append(
                f"- **{user.get('name', 'Unknown')}** (user_id: {user.get('id')}) "
                f"| Role: {e.get('type', '?')} "
                f"| Section: {e.get('course_section_id', '?')}"
                f"{grade_str}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Sections
# ---------------------------------------------------------------------------

class SectionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="canvas_list_sections",
    annotations={
        "title": "List Course Sections",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_sections(params: SectionListInput) -> str:
    """
    List all sections in a Canvas course with enrollment counts.

    Useful for understanding course structure before creating section-targeted
    assignment overrides or filtering enrollments by section.

    Args:
        params (SectionListInput):
            - course_id (int): Canvas course ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Sections with IDs, names, and student counts.

    Examples:
        - "What sections does course 12345 have?"
          → canvas_list_sections(course_id=12345)
    """
    try:
        sections = await _paginate(
            f"/courses/{params.course_id}/sections",
            params={"include[]": "total_students"},
            limit=100,
        )
        if not sections:
            return f"No sections found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(sections, indent=2)
        lines = [f"# Sections — Course {params.course_id} ({len(sections)} found)\n"]
        for s in sections:
            lines.append(
                f"- **{s.get('name', 'Untitled')}** (section_id: {s.get('id')}) "
                f"| Students: {s.get('total_students', '?')} "
                f"| SIS ID: {s.get('sis_section_id') or '—'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Conversations / Inbox
# ---------------------------------------------------------------------------

class SendMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipients: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "List of recipient identifiers. Can be:\n"
            "  • Canvas user IDs as strings: ['4521', '4522']\n"
            "  • A whole course: ['course_12345']\n"
            "  • A section: ['section_678']\n"
            "  • A group: ['group_90']\n"
            "Get user IDs from canvas_list_enrollments."
        ),
    )
    subject: str = Field(..., min_length=1, max_length=255, description="Message subject line.")
    body: str = Field(..., min_length=1, description="Message body text.")
    group_conversation: bool = Field(
        default=False,
        description=(
            "True: creates one group thread everyone can see each other in. "
            "False (default): sends a separate private conversation to each recipient."
        ),
    )
    bulk_message: bool = Field(
        default=False,
        description=(
            "Required to be True when messaging a whole course/section with more than 100 members."
        ),
    )


class ListConversationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Optional[str] = Field(
        default=None,
        description="Filter: 'unread', 'starred', 'archived', 'sent'. Leave empty for inbox.",
    )
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="canvas_send_message",
    annotations={
        "title": "Send Canvas Inbox Message",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def canvas_send_message(params: SendMessageInput) -> str:
    """
    Send a Canvas Inbox message to one or more students, a section, or an entire course.

    This creates a Canvas Conversation (Inbox message). For individual students, each
    gets a separate private thread. For course-wide messages use group_conversation=True
    and bulk_message=True.

    Args:
        params (SendMessageInput):
            - recipients (List[str]): User IDs, 'course_ID', 'section_ID', or 'group_ID'.
            - subject (str): Message subject.
            - body (str): Message text.
            - group_conversation (bool): Single group thread vs. individual threads.
            - bulk_message (bool): Required for large course/section sends (>100 members).

    Returns:
        str: Confirmation with conversation IDs created.

    Examples:
        - "Message student 4521 about their assignment":
          canvas_send_message(recipients=['4521'], subject='Re: Assignment 3',
                              body='Hi, please resubmit by Friday.')
        - "Send a class-wide reminder to course 12345":
          canvas_send_message(recipients=['course_12345'], subject='Midterm Reminder',
                              body='Midterm is next week — see the syllabus.',
                              group_conversation=True, bulk_message=True)
    """
    try:
        payload: Dict[str, Any] = {
            "recipients[]": params.recipients,
            "subject": params.subject,
            "body": params.body,
            "group_conversation": params.group_conversation,
            "bulk_message": params.bulk_message,
        }
        # Conversations API uses form-encoded-style params, send as JSON
        data = await _post("/conversations", payload)
        if isinstance(data, list):
            ids = [str(c.get("id")) for c in data]
            return (
                f"✅ Message sent to {len(params.recipients)} recipient(s).\n"
                f"**Subject**: {params.subject}\n"
                f"**Conversation IDs**: {', '.join(ids)}\n"
            )
        return f"✅ Message sent.\n\n{json.dumps(data, indent=2)}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_list_conversations",
    annotations={
        "title": "List Canvas Inbox Conversations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def canvas_list_conversations(params: ListConversationsInput) -> str:
    """
    List conversations in the Canvas Inbox.

    Args:
        params (ListConversationsInput):
            - scope (str, optional): 'unread', 'starred', 'archived', 'sent', or empty for inbox.
            - limit (int): Max conversations to return (default 20).
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Conversations with subject, participants, and last message preview.
    """
    try:
        query: Dict[str, Any] = {}
        if params.scope:
            query["scope"] = params.scope
        convos = await _paginate("/conversations", params=query, limit=params.limit)
        if not convos:
            return "No conversations found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(convos, indent=2)
        lines = [f"# Inbox ({len(convos)} conversations)\n"]
        for c in convos:
            participants = ", ".join(p.get("name", "?") for p in c.get("participants", []))
            lines.append(
                f"### {c.get('subject') or '(no subject)'} (ID: {c.get('id')})\n"
                f"- **Participants**: {participants}\n"
                f"- **Last Message**: {c.get('last_message', '')[:120]}\n"
                f"- **Last At**: {c.get('last_message_at', 'N/A')}\n"
                f"- **Unread**: {c.get('workflow_state') == 'unread'}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Calendar Events
# ---------------------------------------------------------------------------

class CalendarEventListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0, description="Canvas course ID — events for this course.")
    start_date: Optional[str] = Field(default=None, description="ISO 8601 date (e.g. '2025-09-01').")
    end_date: Optional[str] = Field(default=None, description="ISO 8601 date (e.g. '2025-12-31').")
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CalendarEventCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    start_at: str = Field(..., description="Event start, ISO 8601 (e.g. '2025-10-15T14:00:00Z').")
    end_at: Optional[str] = Field(default=None, description="Event end, ISO 8601.")
    description: Optional[str] = Field(default=None, description="Event description as HTML or plain text.")
    location_name: Optional[str] = Field(default=None, description="Location name (e.g. 'Room 301', 'Zoom').")
    location_address: Optional[str] = Field(default=None, description="Physical or meeting URL address.")
    all_day: bool = Field(default=False, description="True for an all-day event.")


class CalendarEventUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(..., gt=0, description="Calendar event ID to update.")
    title: Optional[str] = Field(default=None, max_length=255)
    start_at: Optional[str] = Field(default=None)
    end_at: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    location_name: Optional[str] = Field(default=None)


class CalendarEventDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(..., gt=0)
    reason: Optional[str] = Field(default=None, description="Optional cancellation reason shown to students.")


@mcp.tool(
    name="canvas_list_calendar_events",
    annotations={"title": "List Course Calendar Events", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_list_calendar_events(params: CalendarEventListInput) -> str:
    """
    List calendar events for a Canvas course.

    Args:
        params (CalendarEventListInput):
            - course_id (int): Canvas course ID.
            - start_date / end_date (str, optional): ISO 8601 date range filter.
            - limit (int): Max events to return.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Events with titles, dates, and locations.
    """
    try:
        query: Dict[str, Any] = {
            "context_codes[]": f"course_{params.course_id}",
            "type": "event",
        }
        if params.start_date:
            query["start_date"] = params.start_date
        if params.end_date:
            query["end_date"] = params.end_date
        events = await _paginate("/calendar_events", params=query, limit=params.limit)
        if not events:
            return f"No calendar events found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(events, indent=2)
        lines = [f"# Calendar Events — Course {params.course_id} ({len(events)} found)\n"]
        for ev in events:
            lines.append(
                f"### {ev.get('title', 'Untitled')} (ID: {ev.get('id')})\n"
                f"- **Start**: {ev.get('start_at', 'N/A')}\n"
                f"- **End**: {ev.get('end_at', 'N/A')}\n"
                f"- **Location**: {ev.get('location_name') or '—'}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_calendar_event",
    annotations={"title": "Create Calendar Event", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_calendar_event(params: CalendarEventCreateInput) -> str:
    """
    Create a new calendar event on a Canvas course calendar.

    Use for scheduling office hours, exam sessions, synchronous meetings,
    or any course-wide event students can see on their Canvas calendar.

    Args:
        params (CalendarEventCreateInput):
            - course_id (int): Canvas course ID.
            - title (str): Event title.
            - start_at (str): ISO 8601 start datetime.
            - end_at (str, optional): ISO 8601 end datetime.
            - description (str, optional): Event description.
            - location_name (str, optional): Location (room number, Zoom, etc.).
            - location_address (str, optional): Full address or meeting URL.
            - all_day (bool): All-day event flag.

    Returns:
        str: Confirmation with event ID and calendar link.

    Examples:
        - "Create office hours on Oct 10 from 2–4pm in room 301":
          canvas_create_calendar_event(course_id=12345, title='Office Hours',
              start_at='2025-10-10T14:00:00Z', end_at='2025-10-10T16:00:00Z',
              location_name='Room 301')
    """
    try:
        event: Dict[str, Any] = {
            "context_code": f"course_{params.course_id}",
            "title": params.title,
            "start_at": params.start_at,
            "all_day": params.all_day,
        }
        if params.end_at:
            event["end_at"] = params.end_at
        if params.description:
            event["description"] = params.description
        if params.location_name:
            event["location_name"] = params.location_name
        if params.location_address:
            event["location_address"] = params.location_address

        data = await _post("/calendar_events", {"calendar_event": event})
        return (
            f"✅ Calendar event created.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Start**: {data.get('start_at')}\n"
            f"**End**: {data.get('end_at') or '—'}\n"
            f"**Location**: {data.get('location_name') or '—'}\n"
            f"**URL**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_calendar_event",
    annotations={"title": "Update Calendar Event", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_update_calendar_event(params: CalendarEventUpdateInput) -> str:
    """
    Update an existing Canvas calendar event (title, time, location, description).

    Args:
        params (CalendarEventUpdateInput):
            - event_id (int): Calendar event ID (from canvas_list_calendar_events).
            - title / start_at / end_at / description / location_name: Fields to update.

    Returns:
        str: Updated event details.
    """
    try:
        event: Dict[str, Any] = {}
        if params.title is not None:
            event["title"] = params.title
        if params.start_at is not None:
            event["start_at"] = params.start_at
        if params.end_at is not None:
            event["end_at"] = params.end_at
        if params.description is not None:
            event["description"] = params.description
        if params.location_name is not None:
            event["location_name"] = params.location_name

        data = await _put(f"/calendar_events/{params.event_id}", {"calendar_event": event})
        return (
            f"✅ Event updated.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**Start**: {data.get('start_at')}\n"
            f"**End**: {data.get('end_at') or '—'}\n"
            f"**Location**: {data.get('location_name') or '—'}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_delete_calendar_event",
    annotations={"title": "Delete Calendar Event", "readOnlyHint": False,
                  "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_delete_calendar_event(params: CalendarEventDeleteInput) -> str:
    """
    Delete a Canvas calendar event.

    Args:
        params (CalendarEventDeleteInput):
            - event_id (int): Calendar event ID.
            - reason (str, optional): Cancellation message shown to students.

    Returns:
        str: Confirmation of deletion.
    """
    try:
        endpoint = f"/calendar_events/{params.event_id}"
        if params.reason:
            endpoint += f"?cancel_reason={params.reason}"
        data = await _delete(endpoint)
        return f"✅ Calendar event '{data.get('title', params.event_id)}' deleted."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Module Write Operations
# ---------------------------------------------------------------------------

class ModuleCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    position: Optional[int] = Field(default=None, ge=1, description="Position in module list (1-indexed).")
    unlock_at: Optional[str] = Field(default=None, description="ISO 8601 date when module unlocks.")
    require_sequential_progress: bool = Field(
        default=False,
        description="Students must complete items in order.",
    )
    published: bool = Field(default=False)


class ModuleUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    position: Optional[int] = Field(default=None, ge=1)
    unlock_at: Optional[str] = Field(default=None)
    require_sequential_progress: Optional[bool] = Field(default=None)
    published: Optional[bool] = Field(default=None)


class ModuleDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)


class ModuleItemCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Display title for the item.")
    type: str = Field(
        ...,
        description=(
            "Item type: 'File', 'Page', 'Discussion', 'Assignment', 'Quiz', "
            "'SubHeader', 'ExternalUrl', 'ExternalTool'."
        ),
    )
    content_id: Optional[int] = Field(
        default=None, gt=0,
        description="ID of the linked content object (assignment_id, page_url, quiz_id, etc.). Not needed for SubHeader or ExternalUrl.",
    )
    page_url: Optional[str] = Field(
        default=None,
        description="Page URL slug (required when type='Page').",
    )
    external_url: Optional[str] = Field(
        default=None,
        description="External URL (required when type='ExternalUrl' or 'ExternalTool').",
    )
    position: Optional[int] = Field(default=None, ge=1, description="Position within the module.")
    indent: int = Field(default=0, ge=0, le=5, description="Visual indent level (0–5).")
    new_tab: bool = Field(default=False, description="Open external links in new tab.")


class ModuleItemDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    item_id: int = Field(..., gt=0)


@mcp.tool(
    name="canvas_create_module",
    annotations={"title": "Create Course Module", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_module(params: ModuleCreateInput) -> str:
    """
    Create a new module in a Canvas course (requires Teacher/TA access).

    Args:
        params (ModuleCreateInput):
            - course_id (int): Canvas course ID.
            - name (str): Module name.
            - position (int, optional): Position in module list.
            - unlock_at (str, optional): ISO 8601 unlock date.
            - require_sequential_progress (bool): Force sequential item completion.
            - published (bool): Publish immediately (default False).

    Returns:
        str: Confirmation with new module ID.
    """
    try:
        module: Dict[str, Any] = {
            "name": params.name,
            "published": params.published,
            "require_sequential_progress": params.require_sequential_progress,
        }
        if params.position is not None:
            module["position"] = params.position
        if params.unlock_at is not None:
            module["unlock_at"] = params.unlock_at

        data = await _post(f"/courses/{params.course_id}/modules", {"module": module})
        return (
            f"✅ Module created.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Position**: {data.get('position')}\n"
            f"**Published**: {data.get('published')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_module",
    annotations={"title": "Update Course Module", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_update_module(params: ModuleUpdateInput) -> str:
    """
    Update a Canvas module — rename it, reposition it, publish/unpublish, or set unlock date.

    Args:
        params (ModuleUpdateInput):
            - course_id / module_id (int): Identifiers.
            - name / position / unlock_at / require_sequential_progress / published: Fields to change.

    Returns:
        str: Updated module details.
    """
    try:
        module: Dict[str, Any] = {}
        if params.name is not None:
            module["name"] = params.name
        if params.position is not None:
            module["position"] = params.position
        if params.unlock_at is not None:
            module["unlock_at"] = params.unlock_at
        if params.require_sequential_progress is not None:
            module["require_sequential_progress"] = params.require_sequential_progress
        if params.published is not None:
            module["published"] = params.published

        data = await _put(f"/courses/{params.course_id}/modules/{params.module_id}", {"module": module})
        return (
            f"✅ Module updated.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Position**: {data.get('position')}\n"
            f"**Published**: {data.get('published')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_delete_module",
    annotations={"title": "Delete Course Module", "readOnlyHint": False,
                  "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_delete_module(params: ModuleDeleteInput) -> str:
    """
    Delete a Canvas module. The module's content items (assignments, pages, etc.)
    are NOT deleted — only the module container is removed.

    Args:
        params (ModuleDeleteInput):
            - course_id (int): Canvas course ID.
            - module_id (int): Module ID to delete.

    Returns:
        str: Confirmation of deletion.
    """
    try:
        data = await _delete(f"/courses/{params.course_id}/modules/{params.module_id}")
        return f"✅ Module '{data.get('name', params.module_id)}' deleted."
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_module_item",
    annotations={"title": "Add Item to Module", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_module_item(params: ModuleItemCreateInput) -> str:
    """
    Add a content item to a Canvas module (assignment, page, quiz, external URL, etc.).

    Args:
        params (ModuleItemCreateInput):
            - course_id / module_id (int): Target course and module.
            - title (str): Display title.
            - type (str): 'Assignment', 'Page', 'Quiz', 'Discussion', 'File',
                          'ExternalUrl', 'ExternalTool', 'SubHeader'.
            - content_id (int, optional): ID of the linked object.
            - page_url (str, optional): Slug for Page items.
            - external_url (str, optional): URL for ExternalUrl/ExternalTool.
            - position / indent / new_tab: Layout options.

    Returns:
        str: Confirmation with new item ID.

    Examples:
        - Add assignment 789 to module 456:
          canvas_create_module_item(course_id=12345, module_id=456, title='Assignment 1',
                                    type='Assignment', content_id=789)
        - Add an external link:
          canvas_create_module_item(course_id=12345, module_id=456, title='Course Website',
                                    type='ExternalUrl', external_url='https://example.com')
    """
    try:
        item: Dict[str, Any] = {
            "title": params.title,
            "type": params.type,
            "indent": params.indent,
            "new_tab": params.new_tab,
        }
        if params.content_id is not None:
            item["content_id"] = params.content_id
        if params.page_url is not None:
            item["page_url"] = params.page_url
        if params.external_url is not None:
            item["external_url"] = params.external_url
        if params.position is not None:
            item["position"] = params.position

        data = await _post(
            f"/courses/{params.course_id}/modules/{params.module_id}/items",
            {"module_item": item},
        )
        return (
            f"✅ Module item added.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**Type**: {data.get('type')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Position**: {data.get('position')}\n"
            f"**URL**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_delete_module_item",
    annotations={"title": "Remove Item from Module", "readOnlyHint": False,
                  "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_delete_module_item(params: ModuleItemDeleteInput) -> str:
    """
    Remove an item from a Canvas module. The underlying content (assignment, page, etc.)
    is NOT deleted — only the module link is removed.

    Args:
        params (ModuleItemDeleteInput):
            - course_id / module_id / item_id (int): Identifiers.

    Returns:
        str: Confirmation of removal.
    """
    try:
        data = await _delete(
            f"/courses/{params.course_id}/modules/{params.module_id}/items/{params.item_id}"
        )
        return f"✅ Module item '{data.get('title', params.item_id)}' removed from module."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Assignment Groups
# ---------------------------------------------------------------------------

class AssignmentGroupListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AssignmentGroupCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255, description="Group name (e.g. 'Discussions', 'Final Project').")
    group_weight: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage weight if the course uses weighted assignment groups (0–100).",
    )
    position: Optional[int] = Field(default=None, ge=1, description="Display order (1-indexed).")


class AssignmentGroupUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    group_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    group_weight: Optional[float] = Field(default=None, ge=0, le=100)
    position: Optional[int] = Field(default=None, ge=1)


class AssignmentGroupDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    group_id: int = Field(..., gt=0)
    move_assignments_to: Optional[int] = Field(
        default=None, gt=0,
        description="Move assignments in this group to another group ID before deleting.",
    )


@mcp.tool(
    name="canvas_list_assignment_groups",
    annotations={"title": "List Assignment Groups", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_list_assignment_groups(params: AssignmentGroupListInput) -> str:
    """
    List assignment groups (gradebook categories) and their weights for a course.

    Assignment groups organize assignments into weighted categories (e.g. Discussions 20%,
    Project 60%, Participation 20%).

    Args:
        params (AssignmentGroupListInput):
            - course_id (int): Canvas course ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Groups with IDs, names, weights, and assignment counts.
    """
    try:
        groups = await _paginate(
            f"/courses/{params.course_id}/assignment_groups",
            params={"include[]": ["assignments"]},
            limit=100,
        )
        if not groups:
            return f"No assignment groups found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(groups, indent=2)
        lines = [f"# Assignment Groups — Course {params.course_id}\n"]
        for g in groups:
            assignments = g.get("assignments") or []
            weight = g.get("group_weight")
            weight_str = f" | Weight: {weight}%" if weight else ""
            lines.append(
                f"- **{g.get('name', 'Untitled')}** (group_id: {g.get('id')})"
                f"{weight_str} | Assignments: {len(assignments)}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_assignment_group",
    annotations={"title": "Create Assignment Group", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_assignment_group(params: AssignmentGroupCreateInput) -> str:
    """
    Create a new assignment group (gradebook category) in a Canvas course.

    Args:
        params (AssignmentGroupCreateInput):
            - course_id (int): Canvas course ID.
            - name (str): Group name.
            - group_weight (float, optional): Percentage weight (0–100).
            - position (int, optional): Display order.

    Returns:
        str: Confirmation with new group ID.
    """
    try:
        payload: Dict[str, Any] = {"name": params.name}
        if params.group_weight is not None:
            payload["group_weight"] = params.group_weight
        if params.position is not None:
            payload["position"] = params.position

        data = await _post(f"/courses/{params.course_id}/assignment_groups", payload)
        return (
            f"✅ Assignment group created.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Weight**: {data.get('group_weight') or '(not weighted)'}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_assignment_group",
    annotations={"title": "Update Assignment Group", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_update_assignment_group(params: AssignmentGroupUpdateInput) -> str:
    """
    Update an assignment group's name, weight, or position.

    Args:
        params (AssignmentGroupUpdateInput):
            - course_id / group_id (int): Identifiers.
            - name / group_weight / position: Fields to update.

    Returns:
        str: Updated group details.
    """
    try:
        payload: Dict[str, Any] = {}
        if params.name is not None:
            payload["name"] = params.name
        if params.group_weight is not None:
            payload["group_weight"] = params.group_weight
        if params.position is not None:
            payload["position"] = params.position

        data = await _put(f"/courses/{params.course_id}/assignment_groups/{params.group_id}", payload)
        return (
            f"✅ Assignment group updated.\n\n"
            f"**Name**: {data.get('name')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Weight**: {data.get('group_weight') or '—'}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_delete_assignment_group",
    annotations={"title": "Delete Assignment Group", "readOnlyHint": False,
                  "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_delete_assignment_group(params: AssignmentGroupDeleteInput) -> str:
    """
    Delete an assignment group. Optionally move its assignments to another group first.

    Args:
        params (AssignmentGroupDeleteInput):
            - course_id / group_id (int): Identifiers.
            - move_assignments_to (int, optional): Move assignments to this group ID before deleting.

    Returns:
        str: Confirmation.
    """
    try:
        endpoint = f"/courses/{params.course_id}/assignment_groups/{params.group_id}"
        if params.move_assignments_to:
            endpoint += f"?move_assignments_to={params.move_assignments_to}"
        data = await _delete(endpoint)
        return f"✅ Assignment group '{data.get('name', params.group_id)}' deleted."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Analytics
# ---------------------------------------------------------------------------

class CourseAnalyticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class StudentAnalyticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0, description="Student's Canvas user ID.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="canvas_get_course_analytics",
    annotations={"title": "Get Course Student Analytics", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_get_course_analytics(params: CourseAnalyticsInput) -> str:
    """
    Get per-student participation and activity summaries for a course.

    Returns page views, participations, missing/late/on-time assignment breakdown
    per student. Useful for spotting struggling or disengaged students.

    Args:
        params (CourseAnalyticsInput):
            - course_id (int): Canvas course ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Per-student analytics with participation scores and tardiness breakdown.

    Examples:
        - "Which students have the most missing assignments in course 12345?"
          → canvas_get_course_analytics(course_id=12345)
    """
    try:
        data = await _paginate(
            f"/courses/{params.course_id}/analytics/student_summaries",
            limit=200,
        )
        if not data:
            return f"No analytics data available for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)

        lines = [f"# Student Analytics — Course {params.course_id} ({len(data)} students)\n"]
        # Sort by missing assignments descending to surface at-risk students
        data_sorted = sorted(data, key=lambda s: s.get("tardiness_breakdown", {}).get("missing", 0), reverse=True)
        for s in data_sorted:
            tb = s.get("tardiness_breakdown", {})
            lines.append(
                f"- **{s.get('name', 'Unknown')}** (user_id: {s.get('id')})\n"
                f"  Views: {s.get('page_views', 0)} | Participations: {s.get('participations', 0)} | "
                f"Missing: {tb.get('missing', 0)} | Late: {tb.get('late', 0)} | "
                f"On-time: {tb.get('on_time', 0)}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_student_analytics",
    annotations={"title": "Get Individual Student Analytics", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_get_student_analytics(params: StudentAnalyticsInput) -> str:
    """
    Get assignment-level analytics for a specific student in a course.

    Shows per-assignment submission status, score, and submission time
    relative to the due date.

    Args:
        params (StudentAnalyticsInput):
            - course_id (int): Canvas course ID.
            - user_id (int): Student's Canvas user ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Per-assignment breakdown for the student.

    Examples:
        - "How is student 4521 doing in course 12345?"
          → canvas_get_student_analytics(course_id=12345, user_id=4521)
    """
    try:
        data = await _paginate(
            f"/courses/{params.course_id}/analytics/users/{params.user_id}/assignments",
            limit=200,
        )
        if not data:
            return f"No analytics data found for user {params.user_id} in course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)

        lines = [f"# Assignment Analytics — User {params.user_id} in Course {params.course_id}\n"]
        for a in data:
            sub = a.get("submission", {}) or {}
            status = sub.get("workflow_state", "unsubmitted")
            score = sub.get("score")
            lines.append(
                f"- **{a.get('title', 'Untitled')}**\n"
                f"  Status: {status} | Score: {score if score is not None else '—'} / {a.get('points_possible', '?')} | "
                f"Due: {a.get('due_at') or '—'} | Submitted: {sub.get('submitted_at') or '—'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Rubrics
# ---------------------------------------------------------------------------

class RubricCriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(..., min_length=1, description="Criterion name/description.")
    long_description: Optional[str] = Field(default=None, description="Detailed criterion explanation.")
    points: float = Field(..., ge=0, description="Maximum points for this criterion.")
    ratings: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Rating scale for this criterion. Each rating: {description, points}. "
            "Example: [{'description': 'Excellent', 'points': 10}, "
            "{'description': 'Satisfactory', 'points': 7}, "
            "{'description': 'Needs Work', 'points': 3}]. "
            "If omitted, Canvas creates a default 3-rating scale."
        ),
    )


class RubricCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Rubric title.")
    criteria: List[RubricCriterionInput] = Field(
        ...,
        min_length=1,
        description="List of rubric criteria. Each needs a description and points value.",
    )
    free_form_criterion_comments: bool = Field(
        default=True,
        description="Allow free-text comments per criterion (recommended: True).",
    )
    assignment_id: Optional[int] = Field(
        default=None, gt=0,
        description="If provided, immediately associates the rubric with this assignment for grading.",
    )
    use_for_grading: bool = Field(
        default=True,
        description="Whether this rubric drives the gradebook score (only applies if assignment_id given).",
    )


class RubricListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RubricAssociateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    rubric_id: int = Field(..., gt=0, description="Rubric ID (from canvas_list_rubrics or canvas_create_rubric).")
    assignment_id: int = Field(..., gt=0, description="Assignment to attach the rubric to.")
    use_for_grading: bool = Field(
        default=True,
        description="True: rubric score feeds into the gradebook. False: for feedback only.",
    )


@mcp.tool(
    name="canvas_list_rubrics",
    annotations={"title": "List Course Rubrics", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_list_rubrics(params: RubricListInput) -> str:
    """
    List all rubrics available in a Canvas course.

    Args:
        params (RubricListInput):
            - course_id (int): Canvas course ID.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Rubrics with IDs, titles, and criterion summaries.
    """
    try:
        rubrics = await _paginate(
            f"/courses/{params.course_id}/rubrics",
            params={"include[]": ["course_associations"]},
            limit=100,
        )
        if not rubrics:
            return f"No rubrics found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(rubrics, indent=2)
        lines = [f"# Rubrics — Course {params.course_id} ({len(rubrics)} found)\n"]
        for r in rubrics:
            criteria = r.get("data", []) or []
            total_pts = sum(c.get("points", 0) for c in criteria)
            lines.append(
                f"### {r.get('title', 'Untitled')} (rubric_id: {r.get('id')})\n"
                f"- Criteria: {len(criteria)} | Total Points: {total_pts}\n"
            )
            for c in criteria:
                lines.append(f"  - {c.get('description', '?')} ({c.get('points', '?')} pts)")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_rubric",
    annotations={"title": "Create Rubric", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_rubric(params: RubricCreateInput) -> str:
    """
    Create a new rubric in a Canvas course, optionally linking it to an assignment.

    Args:
        params (RubricCreateInput):
            - course_id (int): Canvas course ID.
            - title (str): Rubric name.
            - criteria (List): Each criterion needs description and points. Optionally add ratings.
            - free_form_criterion_comments (bool): Allow per-criterion text feedback (default True).
            - assignment_id (int, optional): Associate with this assignment immediately.
            - use_for_grading (bool): Drive gradebook score (only if assignment_id provided).

    Returns:
        str: Confirmation with rubric ID and criterion summary.

    Examples:
        - Create a 3-criterion rubric and attach to assignment 789:
          canvas_create_rubric(
              course_id=12345,
              title='Discussion Rubric',
              criteria=[
                  {'description': 'Content Quality', 'points': 40,
                   'ratings': [{'description': 'Excellent', 'points': 40},
                                {'description': 'Satisfactory', 'points': 25},
                                {'description': 'Insufficient', 'points': 0}]},
                  {'description': 'Critical Thinking', 'points': 35},
                  {'description': 'Peer Engagement', 'points': 25},
              ],
              assignment_id=789
          )
    """
    try:
        # Build criteria in Canvas's indexed-hash format
        criteria_payload: Dict[str, Any] = {}
        for i, crit in enumerate(params.criteria):
            entry: Dict[str, Any] = {
                "description": crit.description,
                "points": crit.points,
                "criterion_use_range": False,
            }
            if crit.long_description:
                entry["long_description"] = crit.long_description
            if crit.ratings:
                ratings: Dict[str, Any] = {}
                for j, rating in enumerate(crit.ratings):
                    ratings[str(j)] = {
                        "description": rating.get("description", f"Rating {j}"),
                        "points": rating.get("points", 0),
                    }
                entry["ratings"] = ratings
            criteria_payload[str(i)] = entry

        rubric_payload: Dict[str, Any] = {
            "title": params.title,
            "free_form_criterion_comments": params.free_form_criterion_comments,
            "criteria": criteria_payload,
        }

        body: Dict[str, Any] = {
            "rubric": rubric_payload,
            "rubric_association": {
                "association_id": params.assignment_id if params.assignment_id else params.course_id,
                "association_type": "Assignment" if params.assignment_id else "Course",
                "use_for_grading": params.use_for_grading if params.assignment_id else False,
                "purpose": "grading",
            },
        }

        data = await _post(f"/courses/{params.course_id}/rubrics", body)
        rubric = data.get("rubric", data)
        return (
            f"✅ Rubric created.\n\n"
            f"**Title**: {rubric.get('title')}\n"
            f"**ID**: {rubric.get('id')}\n"
            f"**Criteria**: {len(params.criteria)}\n"
            f"**Total Points**: {sum(c.points for c in params.criteria)}\n"
            + (f"**Linked to Assignment**: {params.assignment_id}\n" if params.assignment_id else "")
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_associate_rubric",
    annotations={"title": "Associate Rubric with Assignment", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_associate_rubric(params: RubricAssociateInput) -> str:
    """
    Attach an existing rubric to a Canvas assignment so it appears in SpeedGrader.

    Use this when the rubric already exists (from canvas_list_rubrics) and you want
    to link it to an assignment, or change whether it drives the gradebook score.

    Args:
        params (RubricAssociateInput):
            - course_id / assignment_id / rubric_id (int): Identifiers.
            - use_for_grading (bool): True = rubric score updates the gradebook grade.

    Returns:
        str: Confirmation with association details.
    """
    try:
        data = await _post(
            f"/courses/{params.course_id}/rubric_associations",
            {
                "rubric_association": {
                    "rubric_id": params.rubric_id,
                    "association_id": params.assignment_id,
                    "association_type": "Assignment",
                    "use_for_grading": params.use_for_grading,
                    "purpose": "grading",
                }
            },
        )
        return (
            f"✅ Rubric {params.rubric_id} linked to assignment {params.assignment_id}.\n\n"
            f"**Association ID**: {data.get('id')}\n"
            f"**Use for Grading**: {data.get('use_for_grading')}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Quizzes
# ---------------------------------------------------------------------------

class QuizListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class QuizGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    quiz_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class QuizCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    quiz_type: str = Field(
        default="assignment",
        description=(
            "Quiz type: 'practice_quiz' (ungraded practice), 'assignment' (graded), "
            "'graded_survey', 'survey'."
        ),
    )
    description: Optional[str] = Field(default=None, description="Quiz instructions as HTML.")
    time_limit: Optional[int] = Field(default=None, ge=1, description="Time limit in minutes.")
    allowed_attempts: int = Field(
        default=1, ge=-1,
        description="Number of allowed attempts. -1 = unlimited.",
    )
    shuffle_answers: bool = Field(default=False, description="Randomize answer order.")
    show_correct_answers: bool = Field(default=True, description="Show correct answers after submission.")
    due_at: Optional[str] = Field(default=None, description="Due date ISO 8601.")
    unlock_at: Optional[str] = Field(default=None, description="Available from date ISO 8601.")
    lock_at: Optional[str] = Field(default=None, description="Locks after this date ISO 8601.")
    published: bool = Field(default=False)
    assignment_group_id: Optional[int] = Field(
        default=None, gt=0,
        description="Assignment group to place this quiz in.",
    )


class QuizUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    quiz_id: int = Field(..., gt=0)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    time_limit: Optional[int] = Field(default=None, ge=1)
    allowed_attempts: Optional[int] = Field(default=None, ge=-1)
    shuffle_answers: Optional[bool] = Field(default=None)
    due_at: Optional[str] = Field(default=None)
    unlock_at: Optional[str] = Field(default=None)
    lock_at: Optional[str] = Field(default=None)
    published: Optional[bool] = Field(default=None)


@mcp.tool(
    name="canvas_list_quizzes",
    annotations={"title": "List Course Quizzes", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_list_quizzes(params: QuizListInput) -> str:
    """
    List all quizzes in a Canvas course.

    Args:
        params (QuizListInput):
            - course_id (int): Canvas course ID.
            - limit (int): Max quizzes to return.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Quizzes with IDs, types, due dates, and attempt limits.
    """
    try:
        quizzes = await _paginate(f"/courses/{params.course_id}/quizzes", limit=params.limit)
        if not quizzes:
            return f"No quizzes found for course {params.course_id}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(quizzes, indent=2)
        lines = [f"# Quizzes — Course {params.course_id} ({len(quizzes)} found)\n"]
        for q in quizzes:
            attempts = q.get("allowed_attempts", 1)
            attempts_str = "unlimited" if attempts == -1 else str(attempts)
            lines.append(
                f"### {q.get('title', 'Untitled')} (quiz_id: {q.get('id')})\n"
                f"- Type: {q.get('quiz_type')} | Points: {q.get('points_possible')} "
                f"| Attempts: {attempts_str} | Published: {q.get('published')}\n"
                f"- Due: {q.get('due_at') or '—'} | Link: {q.get('html_url', 'N/A')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_get_quiz",
    annotations={"title": "Get Quiz Details", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_get_quiz(params: QuizGetInput) -> str:
    """
    Get full details for a specific Canvas quiz.

    Args:
        params (QuizGetInput):
            - course_id / quiz_id (int): Identifiers.
            - response_format: 'markdown' or 'json'.

    Returns:
        str: Quiz settings, timing, and availability details.
    """
    try:
        data = await _get(f"/courses/{params.course_id}/quizzes/{params.quiz_id}")
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        attempts = data.get("allowed_attempts", 1)
        return (
            f"# {data.get('title', 'Untitled')} (quiz_id: {data.get('id')})\n\n"
            f"**Type**: {data.get('quiz_type')}\n"
            f"**Points**: {data.get('points_possible')}\n"
            f"**Attempts**: {'unlimited' if attempts == -1 else attempts}\n"
            f"**Time Limit**: {data.get('time_limit') or 'none'} min\n"
            f"**Shuffle Answers**: {data.get('shuffle_answers')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Due**: {data.get('due_at') or '—'}\n"
            f"**Unlock**: {data.get('unlock_at') or '—'}\n"
            f"**Lock**: {data.get('lock_at') or '—'}\n"
            f"**Link**: {data.get('html_url', 'N/A')}\n\n"
            f"## Description\n{data.get('description') or '(none)'}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_create_quiz",
    annotations={"title": "Create Quiz", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def canvas_create_quiz(params: QuizCreateInput) -> str:
    """
    Create a new quiz in a Canvas course (requires Teacher/TA access).

    Note: This creates the quiz shell. Add questions manually in Canvas or via the
    Quiz Questions API.

    Args:
        params (QuizCreateInput):
            - course_id (int): Canvas course ID.
            - title (str): Quiz title.
            - quiz_type: 'assignment', 'practice_quiz', 'graded_survey', 'survey'.
            - description (str, optional): HTML instructions.
            - time_limit (int, optional): Minutes. Omit for no limit.
            - allowed_attempts (int): 1 by default, -1 for unlimited.
            - shuffle_answers / show_correct_answers (bool): Answer display settings.
            - due_at / unlock_at / lock_at (str): ISO 8601 dates.
            - published (bool): Publish immediately.
            - assignment_group_id (int, optional): Gradebook category.

    Returns:
        str: Confirmation with quiz ID and edit link.
    """
    try:
        quiz: Dict[str, Any] = {
            "title": params.title,
            "quiz_type": params.quiz_type,
            "allowed_attempts": params.allowed_attempts,
            "shuffle_answers": params.shuffle_answers,
            "show_correct_answers": params.show_correct_answers,
            "published": params.published,
        }
        for field, val in [
            ("description", params.description),
            ("time_limit", params.time_limit),
            ("due_at", params.due_at),
            ("unlock_at", params.unlock_at),
            ("lock_at", params.lock_at),
            ("assignment_group_id", params.assignment_group_id),
        ]:
            if val is not None:
                quiz[field] = val

        data = await _post(f"/courses/{params.course_id}/quizzes", {"quiz": quiz})
        return (
            f"✅ Quiz created.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**ID**: {data.get('id')}\n"
            f"**Type**: {data.get('quiz_type')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Due**: {data.get('due_at') or '—'}\n"
            f"**Edit Link**: {data.get('html_url', 'N/A')}\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_quiz",
    annotations={"title": "Update Quiz", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_update_quiz(params: QuizUpdateInput) -> str:
    """
    Update an existing Canvas quiz's settings, dates, or publish status.

    Args:
        params (QuizUpdateInput):
            - course_id / quiz_id (int): Identifiers.
            - title / description / time_limit / allowed_attempts / shuffle_answers /
              due_at / unlock_at / lock_at / published: Fields to update.

    Returns:
        str: Updated quiz details.
    """
    try:
        quiz: Dict[str, Any] = {}
        for field, val in [
            ("title", params.title),
            ("description", params.description),
            ("time_limit", params.time_limit),
            ("allowed_attempts", params.allowed_attempts),
            ("shuffle_answers", params.shuffle_answers),
            ("due_at", params.due_at),
            ("unlock_at", params.unlock_at),
            ("lock_at", params.lock_at),
            ("published", params.published),
        ]:
            if val is not None:
                quiz[field] = val

        data = await _put(f"/courses/{params.course_id}/quizzes/{params.quiz_id}", {"quiz": quiz})
        return (
            f"✅ Quiz updated.\n\n"
            f"**Title**: {data.get('title')}\n"
            f"**Published**: {data.get('published')}\n"
            f"**Due**: {data.get('due_at') or '—'}\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# TOOLS — Late Policy
# ---------------------------------------------------------------------------

class LatePolicyGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)


class LatePolicyUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    late_submission_deduction_enabled: Optional[bool] = Field(
        default=None,
        description="Enable automatic point deduction for late submissions.",
    )
    late_submission_deduction: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage points deducted per late_submission_interval.",
    )
    late_submission_interval: Optional[str] = Field(
        default=None,
        description="Deduction interval: 'day' or 'hour'.",
    )
    late_submission_minimum_percent_enabled: Optional[bool] = Field(
        default=None,
        description="Enable a floor so late deductions don't drop the grade below a minimum.",
    )
    late_submission_minimum_percent: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Minimum grade percentage after late deductions.",
    )
    missing_submission_deduction_enabled: Optional[bool] = Field(
        default=None,
        description="Enable automatic score for missing (never-submitted) assignments.",
    )
    missing_submission_deduction: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage of points to award for missing submissions (usually 0).",
    )


@mcp.tool(
    name="canvas_get_late_policy",
    annotations={"title": "Get Course Late Policy", "readOnlyHint": True,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_get_late_policy(params: LatePolicyGetInput) -> str:
    """
    Get the late submission policy for a Canvas course.

    Shows automatic deduction settings for late and missing submissions.

    Args:
        params (LatePolicyGetInput):
            - course_id (int): Canvas course ID.

    Returns:
        str: Late policy settings including deduction rates and minimums.
    """
    try:
        data = await _get(f"/courses/{params.course_id}/late_policy")
        lp = data.get("late_policy", data)
        return (
            f"# Late Policy — Course {params.course_id}\n\n"
            f"## Late Submissions\n"
            f"- **Enabled**: {lp.get('late_submission_deduction_enabled', False)}\n"
            f"- **Deduction**: {lp.get('late_submission_deduction', 0)}% per {lp.get('late_submission_interval', 'day')}\n"
            f"- **Minimum Grade Floor Enabled**: {lp.get('late_submission_minimum_percent_enabled', False)}\n"
            f"- **Minimum Grade**: {lp.get('late_submission_minimum_percent', 0)}%\n\n"
            f"## Missing Submissions\n"
            f"- **Enabled**: {lp.get('missing_submission_deduction_enabled', False)}\n"
            f"- **Score Awarded**: {lp.get('missing_submission_deduction', 0)}%\n"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="canvas_update_late_policy",
    annotations={"title": "Update Course Late Policy", "readOnlyHint": False,
                  "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def canvas_update_late_policy(params: LatePolicyUpdateInput) -> str:
    """
    Update the late submission policy for a Canvas course (requires Teacher access).

    Configure automatic grade deductions for late submissions and scores for
    missing submissions directly from Claude.

    Args:
        params (LatePolicyUpdateInput):
            - course_id (int): Canvas course ID.
            - late_submission_deduction_enabled (bool): Turn on/off late deductions.
            - late_submission_deduction (float): % deducted per interval (0–100).
            - late_submission_interval (str): 'day' or 'hour'.
            - late_submission_minimum_percent_enabled (bool): Enable grade floor.
            - late_submission_minimum_percent (float): Minimum grade after deductions.
            - missing_submission_deduction_enabled (bool): Enable missing score.
            - missing_submission_deduction (float): % awarded for missing work.

    Returns:
        str: Updated policy summary.

    Examples:
        - "Deduct 10% per day for late work, minimum grade 50%":
          canvas_update_late_policy(course_id=12345,
              late_submission_deduction_enabled=True,
              late_submission_deduction=10,
              late_submission_interval='day',
              late_submission_minimum_percent_enabled=True,
              late_submission_minimum_percent=50)
        - "Set missing submissions to 0%":
          canvas_update_late_policy(course_id=12345,
              missing_submission_deduction_enabled=True,
              missing_submission_deduction=0)
    """
    try:
        lp: Dict[str, Any] = {}
        for field, val in [
            ("late_submission_deduction_enabled", params.late_submission_deduction_enabled),
            ("late_submission_deduction", params.late_submission_deduction),
            ("late_submission_interval", params.late_submission_interval),
            ("late_submission_minimum_percent_enabled", params.late_submission_minimum_percent_enabled),
            ("late_submission_minimum_percent", params.late_submission_minimum_percent),
            ("missing_submission_deduction_enabled", params.missing_submission_deduction_enabled),
            ("missing_submission_deduction", params.missing_submission_deduction),
        ]:
            if val is not None:
                lp[field] = val

        if not lp:
            return "Error: No fields provided to update. Specify at least one late policy setting."

        data = await _patch(f"/courses/{params.course_id}/late_policy", {"late_policy": lp})
        lp_out = data.get("late_policy", data)
        return (
            f"✅ Late policy updated for course {params.course_id}.\n\n"
            f"**Late Deductions**: {'on' if lp_out.get('late_submission_deduction_enabled') else 'off'} "
            f"— {lp_out.get('late_submission_deduction', 0)}% per {lp_out.get('late_submission_interval', 'day')}\n"
            f"**Grade Floor**: {lp_out.get('late_submission_minimum_percent', 0)}% "
            f"({'enabled' if lp_out.get('late_submission_minimum_percent_enabled') else 'disabled'})\n"
            f"**Missing Score**: {lp_out.get('missing_submission_deduction', 0)}% "
            f"({'enabled' if lp_out.get('missing_submission_deduction_enabled') else 'disabled'})\n"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Canvas LMS MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run with streamable-HTTP transport on port 8080 instead of stdio.",
    )
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="streamable-http", port=8080)
    else:
        mcp.run()
