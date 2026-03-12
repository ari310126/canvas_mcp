from mcp.server.fastmcp import FastMCP
import json
from models import (
    AnnouncementListInput, AnnouncementCreateInput, DiscussionListInput, DiscussionReplyInput, ResponseFormat
)
import client

def register(mcp: FastMCP):
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
        try:
            announcements = await client.paginate(
                f"/courses/{params.course_id}/discussion_topics",
                params={"only_announcements": True},
                limit=params.limit,
            )
            if not announcements:
                return f"No announcements found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(announcements, indent=2)
            lines = [f"# Announcements — Course {params.course_id}\n"]
            for a in announcements:
                lines.append(f"### {a.get('title', 'Untitled')} (ID: {a.get('id')})")
                lines.append(f"- **Posted**: {a.get('posted_at', 'N/A')}")
                lines.append(f"- **Author**: {a.get('author', {}).get('display_name', 'N/A')}")
                lines.append(f"- **Unread**: {a.get('unread_count', 0)}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

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
        try:
            topics = await client.paginate(
                f"/courses/{params.course_id}/discussion_topics",
                limit=params.limit,
            )
            if not topics:
                return f"No discussions found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(topics, indent=2)
            lines = [f"# Discussions — Course {params.course_id}\n"]
            for t in topics:
                lines.append(f"### {t.get('title', 'Untitled')} (ID: {t.get('id')})")
                lines.append(f"- **Author**: {t.get('author', {}).get('display_name', 'N/A')}")
                lines.append(f"- **Replies**: {t.get('discussion_subentry_count', 0)}")
                lines.append(f"- **Last Reply at**: {t.get('last_reply_at', 'N/A')}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

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
        try:
            payload = {
                "title": params.title,
                "message": params.message,
                "is_announcement": True,
                "published": True,
            }
            if params.delayed_post_at:
                payload["delayed_post_at"] = params.delayed_post_at

            data = await client.post(
                f"/courses/{params.course_id}/discussion_topics",
                payload
            )
            return (
                f"Successfully posted announcement **{data.get('title')}**.\n"
                f"Link: {data.get('html_url')}"
            )
        except Exception as e:
            return client.handle_error(e)

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
        try:
            payload = {"message": params.message}
            data = await client.post(
                f"/courses/{params.course_id}/discussion_topics/{params.topic_id}/entries",
                payload
            )
            return f"Successfully replied to topic {params.topic_id}. Reply ID: {data.get('id')}"
        except Exception as e:
            return client.handle_error(e)
