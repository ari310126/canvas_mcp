from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import (
    AssignmentListInput, AssignmentGetInput, AssignmentCreateInput, AssignmentUpdateInput, 
    ResponseFormat, fmt_assignment
)
import client

def register(mcp: FastMCP):
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
        try:
            query: Dict[str, Any] = {
                "include[]": ["rubric", "score_statistics"],
                "order_by": "due_at",
            }
            if params.bucket:
                query["bucket"] = params.bucket

            assignments = await client.paginate(
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
                lines.append(fmt_assignment(a))
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

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
        try:
            data = await client.get(
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
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_assignment",
        annotations={
            "title": "Create Course Assignment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def canvas_create_assignment(params: AssignmentCreateInput) -> str:
        try:
            payload = {
                "assignment": {
                    "name": params.name,
                    "submission_types": params.submission_types,
                    "published": params.published,
                }
            }
            if params.description is not None:
                payload["assignment"]["description"] = params.description
            if params.points_possible is not None:
                payload["assignment"]["points_possible"] = params.points_possible
            if params.due_at is not None:
                payload["assignment"]["due_at"] = params.due_at

            data = await client.post(f"/courses/{params.course_id}/assignments", payload)
            
            # Simple markdown response for writes
            return (
                f"Successfully created assignment **{data.get('name')}** (ID: {data.get('id')}).\n"
                f"Link: {data.get('html_url')}"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_assignment",
        annotations={
            "title": "Update Course Assignment",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def canvas_update_assignment(params: AssignmentUpdateInput) -> str:
        try:
            payload = {"assignment": {}}
            if params.name is not None:
                payload["assignment"]["name"] = params.name
            if params.description is not None:
                payload["assignment"]["description"] = params.description
            if params.points_possible is not None:
                payload["assignment"]["points_possible"] = params.points_possible
            if params.due_at is not None:
                payload["assignment"]["due_at"] = params.due_at
            if params.published is not None:
                payload["assignment"]["published"] = params.published

            if not payload["assignment"]:
                return "No update fields provided."

            data = await client.put(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}", 
                payload
            )
            
            return (
                f"Successfully updated assignment **{data.get('name')}** (ID: {data.get('id')}).\n"
                f"Link: {data.get('html_url')}"
            )
        except Exception as e:
            return client.handle_error(e)

