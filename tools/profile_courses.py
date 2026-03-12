from mcp.server.fastmcp import FastMCP
import json
from models import EmptyInput, CourseListInput, CourseIdInput, ResponseFormat, fmt_course
import client

def register(mcp: FastMCP):
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
        try:
            data = await client.get("/users/self")
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
            return client.handle_error(e)

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
        try:
            courses = await client.paginate(
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
                lines.append(fmt_course(c))
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

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
        try:
            data = await client.get(
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
            return client.handle_error(e)
