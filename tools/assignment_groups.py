from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import (
    AssignmentGroupListInput, AssignmentGroupCreateInput,
    AssignmentGroupUpdateInput, AssignmentGroupDeleteInput, ResponseFormat,
)
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_assignment_groups",
        annotations={"title": "List Assignment Groups", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_assignment_groups(params: AssignmentGroupListInput) -> str:
        """List assignment groups (gradebook categories) and their weights for a course."""
        try:
            groups = await client.paginate(
                f"/courses/{params.course_id}/assignment_groups",
                params={"include[]": ["assignments"]},
                limit=100,
            )
            if not groups:
                return f"No assignment groups found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(groups, indent=2)
            lines = [f"# Assignment Groups -- Course {params.course_id}\n"]
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
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_assignment_group",
        annotations={"title": "Create Assignment Group", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_assignment_group(params: AssignmentGroupCreateInput) -> str:
        """Create a new assignment group (gradebook category) in a Canvas course."""
        try:
            payload: Dict[str, Any] = {"name": params.name}
            if params.group_weight is not None:
                payload["group_weight"] = params.group_weight
            if params.position is not None:
                payload["position"] = params.position

            data = await client.post(f"/courses/{params.course_id}/assignment_groups", payload)
            return (
                f"Assignment group created.\n\n"
                f"**Name**: {data.get('name')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Weight**: {data.get('group_weight') or '(not weighted)'}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_assignment_group",
        annotations={"title": "Update Assignment Group", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_assignment_group(params: AssignmentGroupUpdateInput) -> str:
        """Update an assignment group's name, weight, or position."""
        try:
            payload: Dict[str, Any] = {}
            if params.name is not None:
                payload["name"] = params.name
            if params.group_weight is not None:
                payload["group_weight"] = params.group_weight
            if params.position is not None:
                payload["position"] = params.position

            data = await client.put(
                f"/courses/{params.course_id}/assignment_groups/{params.group_id}",
                payload,
            )
            return (
                f"Assignment group updated.\n\n"
                f"**Name**: {data.get('name')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Weight**: {data.get('group_weight') or '--'}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_delete_assignment_group",
        annotations={"title": "Delete Assignment Group", "readOnlyHint": False,
                      "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_delete_assignment_group(params: AssignmentGroupDeleteInput) -> str:
        """Delete an assignment group. Optionally move its assignments to another group first."""
        try:
            query = {}
            if params.move_assignments_to:
                query["move_assignments_to"] = params.move_assignments_to
            data = await client.delete(
                f"/courses/{params.course_id}/assignment_groups/{params.group_id}",
                params=query,
            )
            return f"Assignment group '{data.get('name', params.group_id)}' deleted."
        except Exception as e:
            return client.handle_error(e)
