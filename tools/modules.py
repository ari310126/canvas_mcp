from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import (
    ModuleListInput, ModuleItemsInput, ModuleCreateInput, ModuleUpdateInput,
    ModuleDeleteInput, ModuleItemCreateInput, ModuleItemDeleteInput, ResponseFormat,
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
            lines = [f"# Modules -- Course {params.course_id}\n"]
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

    @mcp.tool(
        name="canvas_create_module",
        annotations={"title": "Create Course Module", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_module(params: ModuleCreateInput) -> str:
        """Create a new module in a Canvas course (requires Teacher/TA access)."""
        try:
            module: Dict[str, Any] = {
                "name": params.name,
                "published": params.published,
                "require_sequential_progress": params.require_sequential_progress,
            }
            if params.position is not None:
                module["position"] = params.position
            if params.unlock_at is not None:
                module["unlock_at"] = params.unlock_at

            data = await client.post(f"/courses/{params.course_id}/modules", {"module": module})
            return (
                f"Module created.\n\n"
                f"**Name**: {data.get('name')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Position**: {data.get('position')}\n"
                f"**Published**: {data.get('published')}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_module",
        annotations={"title": "Update Course Module", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_module(params: ModuleUpdateInput) -> str:
        """Update a Canvas module -- rename, reposition, publish/unpublish, or set unlock date."""
        try:
            module: Dict[str, Any] = {}
            if params.name is not None:
                module["name"] = params.name
            if params.position is not None:
                module["position"] = params.position
            if params.unlock_at is not None:
                module["unlock_at"] = params.unlock_at
            if params.require_sequential_progress is not None:
                module["require_sequential_progress"] = params.require_sequential_progress
            if params.published is not None:
                module["published"] = params.published

            data = await client.put(
                f"/courses/{params.course_id}/modules/{params.module_id}",
                {"module": module},
            )
            return (
                f"Module updated.\n\n"
                f"**Name**: {data.get('name')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Position**: {data.get('position')}\n"
                f"**Published**: {data.get('published')}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_delete_module",
        annotations={"title": "Delete Course Module", "readOnlyHint": False,
                      "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_delete_module(params: ModuleDeleteInput) -> str:
        """Delete a Canvas module. Content items (assignments, pages, etc.) are NOT deleted."""
        try:
            data = await client.delete(f"/courses/{params.course_id}/modules/{params.module_id}")
            return f"Module '{data.get('name', params.module_id)}' deleted."
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_module_item",
        annotations={"title": "Add Item to Module", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_module_item(params: ModuleItemCreateInput) -> str:
        """Add a content item to a Canvas module (assignment, page, quiz, external URL, etc.)."""
        try:
            item: Dict[str, Any] = {
                "title": params.title,
                "type": params.type,
                "indent": params.indent,
                "new_tab": params.new_tab,
            }
            if params.content_id is not None:
                item["content_id"] = params.content_id
            if params.page_url is not None:
                item["page_url"] = params.page_url
            if params.external_url is not None:
                item["external_url"] = params.external_url
            if params.position is not None:
                item["position"] = params.position

            data = await client.post(
                f"/courses/{params.course_id}/modules/{params.module_id}/items",
                {"module_item": item},
            )
            return (
                f"Module item added.\n\n"
                f"**Title**: {data.get('title')}\n"
                f"**Type**: {data.get('type')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Position**: {data.get('position')}\n"
                f"**URL**: {data.get('html_url', 'N/A')}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_delete_module_item",
        annotations={"title": "Remove Item from Module", "readOnlyHint": False,
                      "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_delete_module_item(params: ModuleItemDeleteInput) -> str:
        """Remove an item from a Canvas module. The underlying content is NOT deleted."""
        try:
            data = await client.delete(
                f"/courses/{params.course_id}/modules/{params.module_id}/items/{params.item_id}"
            )
            return f"Module item '{data.get('title', params.item_id)}' removed from module."
        except Exception as e:
            return client.handle_error(e)
