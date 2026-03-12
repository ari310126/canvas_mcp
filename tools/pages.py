from mcp.server.fastmcp import FastMCP
import json
from models import (
    PageListInput, PageGetInput, PageCreateInput, PageUpdateInput, ResponseFormat
)
import client

def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_pages",
        annotations={
            "title": "List Course Pages",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_pages(params: PageListInput) -> str:
        try:
            pages = await client.paginate(f"/courses/{params.course_id}/pages", limit=params.limit)
            if not pages:
                return f"No pages found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(pages, indent=2)
            lines = [f"# Pages — Course {params.course_id} ({len(pages)} found)\n"]
            for p in pages:
                pub = "✓" if p.get("published") else "✗"
                lines.append(f"- [{p.get('title', 'Untitled')}] slug: `{p.get('url')}` | Published: {pub}")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_page",
        annotations={
            "title": "Get Page Content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_get_page(params: PageGetInput) -> str:
        try:
            data = await client.get(f"/courses/{params.course_id}/pages/{params.page_url}")
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(data, indent=2)
            return (
                f"# {data.get('title', 'Untitled')} (slug: {data.get('url')})\n\n"
                f"**Published**: {data.get('published', False)}\n"
                f"**Updated**: {data.get('updated_at', 'N/A')}\n"
                f"**Editor**: {data.get('last_edited_by', {}).get('display_name', 'N/A')}\n\n"
                f"## Body\n{data.get('body') or '(empty page)'}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_page",
        annotations={
            "title": "Create Course Page",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def canvas_create_page(params: PageCreateInput) -> str:
        try:
            payload = {
                "wiki_page": {
                    "title": params.title,
                    "body": params.body,
                    "published": params.published,
                }
            }
            data = await client.post(f"/courses/{params.course_id}/pages", payload)
            return (
                f"Successfully created page **{data.get('title')}**.\n"
                f"URL slug: `{data.get('url')}`\n"
                f"Link: {data.get('html_url')}"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_page",
        annotations={
            "title": "Update Course Page",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def canvas_update_page(params: PageUpdateInput) -> str:
        try:
            payload = {"wiki_page": {}}
            if params.title is not None:
                payload["wiki_page"]["title"] = params.title
            if params.body is not None:
                payload["wiki_page"]["body"] = params.body
            if params.published is not None:
                payload["wiki_page"]["published"] = params.published

            if not payload["wiki_page"]:
                return "No update fields provided."

            data = await client.put(
                f"/courses/{params.course_id}/pages/{params.page_url}",
                payload
            )
            return (
                f"Successfully updated page **{data.get('title')}**.\n"
                f"URL slug: `{data.get('url')}`\n"
                f"Link: {data.get('html_url')}"
            )
        except Exception as e:
            return client.handle_error(e)

