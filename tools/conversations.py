from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import SendMessageInput, ListConversationsInput, ResponseFormat
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_send_message",
        annotations={"title": "Send Canvas Inbox Message", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_send_message(params: SendMessageInput) -> str:
        """
        Send a Canvas Inbox message to one or more students, a section, or an entire course.
        """
        try:
            payload: Dict[str, Any] = {
                "recipients[]": params.recipients,
                "subject": params.subject,
                "body": params.body,
                "group_conversation": params.group_conversation,
                "bulk_message": params.bulk_message,
            }
            data = await client.post("/conversations", payload)
            if isinstance(data, list):
                ids = [str(c.get("id")) for c in data]
                return (
                    f"Message sent to {len(params.recipients)} recipient(s).\n"
                    f"**Subject**: {params.subject}\n"
                    f"**Conversation IDs**: {', '.join(ids)}\n"
                )
            return f"Message sent.\n\n{json.dumps(data, indent=2)}"
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_conversations",
        annotations={"title": "List Canvas Inbox Conversations", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_conversations(params: ListConversationsInput) -> str:
        """List conversations in the Canvas Inbox."""
        try:
            query: Dict[str, Any] = {}
            if params.scope:
                query["scope"] = params.scope
            convos = await client.paginate("/conversations", params=query, limit=params.limit)
            if not convos:
                return "No conversations found."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(convos, indent=2)
            lines = [f"# Inbox ({len(convos)} conversations)\n"]
            for c in convos:
                participants = ", ".join(p.get("name", "?") for p in c.get("participants", []))
                lines.append(
                    f"### {c.get('subject') or '(no subject)'} (ID: {c.get('id')})\n"
                    f"- **Participants**: {participants}\n"
                    f"- **Last Message**: {c.get('last_message', '')[:120]}\n"
                    f"- **Last At**: {c.get('last_message_at', 'N/A')}\n"
                    f"- **Unread**: {c.get('workflow_state') == 'unread'}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)
