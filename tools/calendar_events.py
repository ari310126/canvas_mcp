from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import (
    PlannerInput, CalendarEventListInput, CalendarEventCreateInput,
    CalendarEventUpdateInput, CalendarEventDeleteInput, EmptyInput,
    ResponseFormat,
)
import client


def register(mcp: FastMCP):
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
        try:
            query = {}
            if params.start_date:
                query["start_date"] = params.start_date
            if params.end_date:
                query["end_date"] = params.end_date

            items = await client.paginate(
                "/planner/items",
                params=query,
                limit=params.limit,
            )
            if not items:
                return "No planner items found for the given dates."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(items, indent=2)
            lines = [f"# Canvas Planner ({len(items)} items)\n"]
            for i in items:
                lines.append(f"### {i.get('plannable', {}).get('title', 'Untitled')}")
                lines.append(f"- **Course**: {i.get('context_name', 'N/A')}")
                lines.append(f"- **Type**: {i.get('plannable_type', 'N/A')}")
                lines.append(f"- **Date**: {i.get('plannable_date', 'N/A')}")
                lines.append(f"- **Link**: {i.get('html_url', 'N/A')}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_activity_stream",
        annotations={
            "title": "Get Activity Stream",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_get_activity_stream(params: EmptyInput) -> str:
        """Get the current user's Canvas activity stream (recent notifications, submissions, messages)."""
        try:
            items = await client.paginate(
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
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_calendar_events",
        annotations={
            "title": "List Calendar Events",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_calendar_events(params: CalendarEventListInput) -> str:
        """List calendar events for a Canvas course."""
        try:
            query: Dict[str, Any] = {
                "context_codes[]": f"course_{params.course_id}",
                "type": "event",
            }
            if params.start_date:
                query["start_date"] = params.start_date
            if params.end_date:
                query["end_date"] = params.end_date
            events = await client.paginate("/calendar_events", params=query, limit=params.limit)
            if not events:
                return f"No calendar events found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(events, indent=2)
            lines = [f"# Calendar Events -- Course {params.course_id} ({len(events)} found)\n"]
            for ev in events:
                lines.append(
                    f"### {ev.get('title', 'Untitled')} (ID: {ev.get('id')})\n"
                    f"- **Start**: {ev.get('start_at', 'N/A')}\n"
                    f"- **End**: {ev.get('end_at', 'N/A')}\n"
                    f"- **Location**: {ev.get('location_name') or '--'}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_calendar_event",
        annotations={"title": "Create Calendar Event", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_calendar_event(params: CalendarEventCreateInput) -> str:
        """Create a new calendar event on a Canvas course calendar."""
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

            data = await client.post("/calendar_events", {"calendar_event": event})
            return (
                f"Calendar event created.\n\n"
                f"**Title**: {data.get('title')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Start**: {data.get('start_at')}\n"
                f"**End**: {data.get('end_at') or '--'}\n"
                f"**Location**: {data.get('location_name') or '--'}\n"
                f"**URL**: {data.get('html_url', 'N/A')}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_calendar_event",
        annotations={"title": "Update Calendar Event", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_calendar_event(params: CalendarEventUpdateInput) -> str:
        """Update an existing Canvas calendar event."""
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

            data = await client.put(f"/calendar_events/{params.event_id}", {"calendar_event": event})
            return (
                f"Event updated.\n\n"
                f"**Title**: {data.get('title')}\n"
                f"**Start**: {data.get('start_at')}\n"
                f"**End**: {data.get('end_at') or '--'}\n"
                f"**Location**: {data.get('location_name') or '--'}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_delete_calendar_event",
        annotations={"title": "Delete Calendar Event", "readOnlyHint": False,
                      "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_delete_calendar_event(params: CalendarEventDeleteInput) -> str:
        """Delete a Canvas calendar event."""
        try:
            query = {}
            if params.reason:
                query["cancel_reason"] = params.reason
            data = await client.delete(f"/calendar_events/{params.event_id}", params=query)
            return f"Calendar event '{data.get('title', params.event_id)}' deleted."
        except Exception as e:
            return client.handle_error(e)
