from mcp.server.fastmcp import FastMCP
import json
from models import (
    FileListInput, SubmissionListInput, ResponseFormat
)
import client

def register(mcp: FastMCP):
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
        try:
            files = await client.paginate(
                f"/courses/{params.course_id}/files",
                params={"sort": "updated_at", "order": "desc"},
                limit=params.limit,
            )
            if not files:
                return f"No files found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(files, indent=2)
            lines = [f"# Files — Course {params.course_id} ({len(files)} found)\n"]
            for f in files:
                lines.append(f"### {f.get('display_name', 'Untitled')} (ID: {f.get('id')})")
                lines.append(f"- **Size**: {f.get('size', 0)} bytes")
                lines.append(f"- **Created**: {f.get('created_at', 'N/A')}")
                lines.append(f"- **URL**: {f.get('url', 'N/A')}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_submissions",
        annotations={
            "title": "List Submissions",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_submissions(params: SubmissionListInput) -> str:
        try:
            subs = await client.paginate(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}/submissions",
                params={"include[]": ["user", "submission_comments", "rubric_assessment"]},
                limit=params.limit,
            )
            if not subs:
                return f"No submissions found for assignment {params.assignment_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(subs, indent=2)
            lines = [f"# Submissions — Assignment {params.assignment_id} ({len(subs)} found)\n"]
            for s in subs:
                user = s.get("user", {})
                name = user.get("name") or user.get("short_name") or f"User {s.get('user_id')}"
                bdate = s.get("submitted_at") or "Not submitted"
                lines.append(f"### {name} (ID: {s.get('user_id')})")
                lines.append(f"- **Score**: {s.get('score', 'N/A')} / {s.get('grade', 'N/A')}")
                lines.append(f"- **Submitted**: {bdate}")
                lines.append(f"- **Late**: {s.get('late', False)}")
                lines.append(f"- **Excused**: {s.get('excused', False)}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)
