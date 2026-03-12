from mcp.server.fastmcp import FastMCP
import json
from models import (
    ModuleListInput, ModuleItemsInput, ResponseFormat
)
import client

def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_modules",
        annotations={
            "title": "List Course Modules",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_modules(params: ModuleListInput) -> str:
        try:
            modules = await client.paginate(
                f"/courses/{params.course_id}/modules",
                limit=params.limit,
            )
            if not modules:
                return f"No modules found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(modules, indent=2)
            lines = [f"# Modules — Course {params.course_id}\n"]
            for m in modules:
                lines.append(f"### {m.get('name', 'Untitled')} (ID: {m.get('id')})")
                lines.append(f"- **Published**: {m.get('published', False)}")
                lines.append(f"- **Items**: {m.get('items_count', 0)}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_module_items",
        annotations={
            "title": "List Module Items",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_module_items(params: ModuleItemsInput) -> str:
        try:
            items = await client.paginate(
                f"/courses/{params.course_id}/modules/{params.module_id}/items",
                limit=100,
            )
            if not items:
                return f"No items found for module {params.module_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(items, indent=2)
            lines = [f"# Items in Module {params.module_id}\n"]
            for i in items:
                lines.append(f"- **{i.get('title', 'Untitled')}** ({i.get('type')})")
                if i.get('html_url'):
                    lines.append(f"  Link: {i['html_url']}")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)
