from mcp.server.fastmcp import FastMCP
import json
from models import CourseAnalyticsInput, StudentAnalyticsInput, ResponseFormat
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_get_course_analytics",
        annotations={"title": "Get Course Student Analytics", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_get_course_analytics(params: CourseAnalyticsInput) -> str:
        """
        Get per-student participation and activity summaries for a course.
        Returns page views, participations, missing/late/on-time assignment breakdown per student.
        """
        try:
            data = await client.paginate(
                f"/courses/{params.course_id}/analytics/student_summaries",
                limit=200,
            )
            if not data:
                return f"No analytics data available for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(data, indent=2)

            lines = [f"# Student Analytics — Course {params.course_id} ({len(data)} students)\n"]
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
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_student_analytics",
        annotations={"title": "Get Individual Student Analytics", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_get_student_analytics(params: StudentAnalyticsInput) -> str:
        """
        Get assignment-level analytics for a specific student in a course.
        Shows per-assignment submission status, score, and submission time relative to due date.
        """
        try:
            data = await client.paginate(
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
            return client.handle_error(e)
