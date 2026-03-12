from mcp.server.fastmcp import FastMCP
import json
from models import (
    PlannerInput, ResponseFormat
)
import client

def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_get_planner",
        annotations={
            "title": "Get Canvas Planner Items",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_get_planner(params: PlannerInput) -> str:
        try:
            query = {}
            if params.start_date:
                query["start_date"] = params.start_date
            if params.end_date:
                query["end_date"] = params.end_date

            items = await client.paginate(
                "/planner/items",
                params=query,
                limit=params.limit,
            )
            if not items:
                return "No planner items found for the given dates."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(items, indent=2)
            lines = [f"# Canvas Planner ({len(items)} items)\n"]
            for i in items:
                lines.append(f"### {i.get('plannable', {}).get('title', 'Untitled')}")
                lines.append(f"- **Course**: {i.get('context_name', 'N/A')}")
                lines.append(f"- **Type**: {i.get('plannable_type', 'N/A')}")
                lines.append(f"- **Date**: {i.get('plannable_date', 'N/A')}")
                lines.append(f"- **Link**: {i.get('html_url', 'N/A')}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)
