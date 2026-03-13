from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any, Optional
from models import (
    OverrideListInput, OverrideGetInput, OverrideCreateInput,
    OverrideUpdateInput, OverrideDeleteInput, ResponseFormat
)
import client


def _fmt_override(o: Dict) -> str:
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


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_assignment_overrides",
        annotations={"title": "List Assignment Overrides", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_assignment_overrides(params: OverrideListInput) -> str:
        """List all date overrides for a Canvas assignment (per-student, per-section, per-group)."""
        try:
            overrides = await client.paginate(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}/overrides",
                limit=200,
            )
            if not overrides:
                return f"No overrides found for assignment {params.assignment_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(overrides, indent=2)
            lines = [f"# Assignment Overrides — Assignment {params.assignment_id} ({len(overrides)} found)\n"]
            for o in overrides:
                lines.append(_fmt_override(o))
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_assignment_override",
        annotations={"title": "Get Assignment Override", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_get_assignment_override(params: OverrideGetInput) -> str:
        """Get a single assignment date override by its ID."""
        try:
            data = await client.get(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/overrides/{params.override_id}"
            )
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(data, indent=2)
            return f"# Override Details\n\n{_fmt_override(data)}"
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_assignment_override",
        annotations={"title": "Create Assignment Override", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_assignment_override(params: OverrideCreateInput) -> str:
        """
        Create a new assignment date override for specific students, a section, or a group.
        Provide exactly one of: student_ids, course_section_id, or group_id.
        """
        try:
            target_count = sum([
                bool(params.student_ids),
                bool(params.course_section_id),
                bool(params.group_id),
            ])
            if target_count == 0:
                return "Error: You must specify exactly one target — student_ids, course_section_id, or group_id."
            if target_count > 1:
                return "Error: Specify only one target type — student_ids, course_section_id, or group_id (not multiple)."
            if params.student_ids and not params.title:
                return "Error: title is required when targeting specific students."

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

            data = await client.post(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}/overrides",
                {"assignment_override": override},
            )
            return f"Assignment override created.\n\n{_fmt_override(data)}"
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_assignment_override",
        annotations={"title": "Update Assignment Override", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_assignment_override(params: OverrideUpdateInput) -> str:
        """
        Update an existing assignment date override. Fetches existing override first
        and merges changes so omitted fields are preserved.
        """
        try:
            existing = await client.get(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/overrides/{params.override_id}"
            )

            override: Dict[str, Any] = {}
            if existing.get("student_ids"):
                override["student_ids"] = existing["student_ids"]
            if existing.get("course_section_id"):
                override["course_section_id"] = existing["course_section_id"]
            if existing.get("group_id"):
                override["group_id"] = existing["group_id"]

            override["title"] = params.title if params.title is not None else existing.get("title", "")

            if params.student_ids is not None:
                override["student_ids"] = params.student_ids

            def _resolve_date(new_val: Optional[str], existing_val: Optional[str]) -> Optional[str]:
                if new_val is None:
                    return existing_val
                if new_val.lower() == "null":
                    return None
                return new_val

            override["due_at"] = _resolve_date(params.due_at, existing.get("due_at"))
            override["unlock_at"] = _resolve_date(params.unlock_at, existing.get("unlock_at"))
            override["lock_at"] = _resolve_date(params.lock_at, existing.get("lock_at"))

            data = await client.put(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/overrides/{params.override_id}",
                {"assignment_override": override},
            )
            return f"Assignment override updated.\n\n{_fmt_override(data)}"
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_delete_assignment_override",
        annotations={"title": "Delete Assignment Override", "readOnlyHint": False,
                      "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_delete_assignment_override(params: OverrideDeleteInput) -> str:
        """Delete an assignment date override. Affected students revert to default dates."""
        try:
            data = await client.delete(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/overrides/{params.override_id}"
            )
            return (
                f"Override deleted. The affected students/section now use the assignment's "
                f"default dates.\n\n"
                f"Deleted override: **{data.get('title', 'Untitled')}** (ID: {data.get('id')})"
            )
        except Exception as e:
            return client.handle_error(e)
