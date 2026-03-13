from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import LatePolicyGetInput, LatePolicyUpdateInput
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_get_late_policy",
        annotations={"title": "Get Course Late Policy", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_get_late_policy(params: LatePolicyGetInput) -> str:
        """Get the late submission policy for a Canvas course."""
        try:
            data = await client.get(f"/courses/{params.course_id}/late_policy")
            lp = data.get("late_policy", data)
            return (
                f"# Late Policy — Course {params.course_id}\n\n"
                f"## Late Submissions\n"
                f"- **Enabled**: {lp.get('late_submission_deduction_enabled', False)}\n"
                f"- **Deduction**: {lp.get('late_submission_deduction', 0)}% per {lp.get('late_submission_interval', 'day')}\n"
                f"- **Minimum Grade Floor Enabled**: {lp.get('late_submission_minimum_percent_enabled', False)}\n"
                f"- **Minimum Grade**: {lp.get('late_submission_minimum_percent', 0)}%\n\n"
                f"## Missing Submissions\n"
                f"- **Enabled**: {lp.get('missing_submission_deduction_enabled', False)}\n"
                f"- **Score Awarded**: {lp.get('missing_submission_deduction', 0)}%\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_late_policy",
        annotations={"title": "Update Course Late Policy", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_late_policy(params: LatePolicyUpdateInput) -> str:
        """Update the late submission policy for a Canvas course (requires Teacher access)."""
        try:
            lp: Dict[str, Any] = {}
            for field, val in [
                ("late_submission_deduction_enabled", params.late_submission_deduction_enabled),
                ("late_submission_deduction", params.late_submission_deduction),
                ("late_submission_interval", params.late_submission_interval),
                ("late_submission_minimum_percent_enabled", params.late_submission_minimum_percent_enabled),
                ("late_submission_minimum_percent", params.late_submission_minimum_percent),
                ("missing_submission_deduction_enabled", params.missing_submission_deduction_enabled),
                ("missing_submission_deduction", params.missing_submission_deduction),
            ]:
                if val is not None:
                    lp[field] = val

            if not lp:
                return "Error: No fields provided to update. Specify at least one late policy setting."

            data = await client.patch(f"/courses/{params.course_id}/late_policy", {"late_policy": lp})
            lp_out = data.get("late_policy", data)
            return (
                f"Late policy updated for course {params.course_id}.\n\n"
                f"**Late Deductions**: {'on' if lp_out.get('late_submission_deduction_enabled') else 'off'} "
                f"— {lp_out.get('late_submission_deduction', 0)}% per {lp_out.get('late_submission_interval', 'day')}\n"
                f"**Grade Floor**: {lp_out.get('late_submission_minimum_percent', 0)}% "
                f"({'enabled' if lp_out.get('late_submission_minimum_percent_enabled') else 'disabled'})\n"
                f"**Missing Score**: {lp_out.get('missing_submission_deduction', 0)}% "
                f"({'enabled' if lp_out.get('missing_submission_deduction_enabled') else 'disabled'})\n"
            )
        except Exception as e:
            return client.handle_error(e)
