from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import EnrollmentListInput, SectionListInput, ResponseFormat
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_enrollments",
        annotations={"title": "List Course Enrollments / Roster", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_enrollments(params: EnrollmentListInput) -> str:
        """
        List enrollments for a Canvas course — the full class roster, filterable by role and section.
        Use this to get student user IDs needed for grading/messaging/overrides.
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

            enrollments = await client.paginate(
                f"/courses/{params.course_id}/enrollments", params=query, limit=params.limit
            )
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
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_sections",
        annotations={"title": "List Course Sections", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_sections(params: SectionListInput) -> str:
        """List all sections in a Canvas course with enrollment counts."""
        try:
            sections = await client.paginate(
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
            return client.handle_error(e)
