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

import sys
from mcp.server.fastmcp import FastMCP
from config import CANVAS_BASE_URL, CANVAS_COOKIE

if not CANVAS_BASE_URL:
    print(
        "WARNING: CANVAS_BASE_URL is not set. Set it to your Canvas instance URL "
        "(e.g. https://uvu.instructure.com).",
        file=sys.stderr,
    )


mcp = FastMCP("canvas_mcp")

# Register tools from domain modules
import tools.profile_courses
import tools.assignments
import tools.pages
import tools.modules
import tools.communication
import tools.calendar_events
import tools.misc
import tools.grading
import tools.overrides
import tools.enrollments
import tools.conversations
import tools.analytics
import tools.rubrics
import tools.quizzes
import tools.late_policy
import tools.assignment_groups

tools.profile_courses.register(mcp)
tools.assignments.register(mcp)
tools.pages.register(mcp)
tools.modules.register(mcp)
tools.communication.register(mcp)
tools.calendar_events.register(mcp)
tools.misc.register(mcp)
tools.grading.register(mcp)
tools.overrides.register(mcp)
tools.enrollments.register(mcp)
tools.conversations.register(mcp)
tools.analytics.register(mcp)
tools.rubrics.register(mcp)
tools.quizzes.register(mcp)
tools.late_policy.register(mcp)
tools.assignment_groups.register(mcp)

if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run("http", host="127.0.0.1", port=8080)
    else:
        mcp.run("stdio")
