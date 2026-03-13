from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import RubricListInput, RubricCreateInput, RubricAssociateInput, ResponseFormat
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_rubrics",
        annotations={"title": "List Course Rubrics", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_rubrics(params: RubricListInput) -> str:
        """List all rubrics available in a Canvas course."""
        try:
            rubrics = await client.paginate(
                f"/courses/{params.course_id}/rubrics",
                params={"include[]": ["course_associations"]},
                limit=100,
            )
            if not rubrics:
                return f"No rubrics found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(rubrics, indent=2)
            lines = [f"# Rubrics — Course {params.course_id} ({len(rubrics)} found)\n"]
            for r in rubrics:
                criteria = r.get("data", []) or []
                total_pts = sum(c.get("points", 0) for c in criteria)
                lines.append(
                    f"### {r.get('title', 'Untitled')} (rubric_id: {r.get('id')})\n"
                    f"- Criteria: {len(criteria)} | Total Points: {total_pts}\n"
                )
                for c in criteria:
                    lines.append(f"  - {c.get('description', '?')} ({c.get('points', '?')} pts)")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_rubric",
        annotations={"title": "Create Rubric", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_rubric(params: RubricCreateInput) -> str:
        """
        Create a new rubric in a Canvas course, optionally linking it to an assignment.
        """
        try:
            criteria_payload: Dict[str, Any] = {}
            for i, crit in enumerate(params.criteria):
                entry: Dict[str, Any] = {
                    "description": crit.description,
                    "points": crit.points,
                    "criterion_use_range": False,
                }
                if crit.long_description:
                    entry["long_description"] = crit.long_description
                if crit.ratings:
                    ratings: Dict[str, Any] = {}
                    for j, rating in enumerate(crit.ratings):
                        ratings[str(j)] = {
                            "description": rating.get("description", f"Rating {j}"),
                            "points": rating.get("points", 0),
                        }
                    entry["ratings"] = ratings
                criteria_payload[str(i)] = entry

            rubric_payload: Dict[str, Any] = {
                "title": params.title,
                "free_form_criterion_comments": params.free_form_criterion_comments,
                "criteria": criteria_payload,
            }

            body: Dict[str, Any] = {
                "rubric": rubric_payload,
                "rubric_association": {
                    "association_id": params.assignment_id if params.assignment_id else params.course_id,
                    "association_type": "Assignment" if params.assignment_id else "Course",
                    "use_for_grading": params.use_for_grading if params.assignment_id else False,
                    "purpose": "grading",
                },
            }

            data = await client.post(f"/courses/{params.course_id}/rubrics", body)
            rubric = data.get("rubric", data)
            return (
                f"Rubric created.\n\n"
                f"**Title**: {rubric.get('title')}\n"
                f"**ID**: {rubric.get('id')}\n"
                f"**Criteria**: {len(params.criteria)}\n"
                f"**Total Points**: {sum(c.points for c in params.criteria)}\n"
                + (f"**Linked to Assignment**: {params.assignment_id}\n" if params.assignment_id else "")
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_associate_rubric",
        annotations={"title": "Associate Rubric with Assignment", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_associate_rubric(params: RubricAssociateInput) -> str:
        """Attach an existing rubric to a Canvas assignment so it appears in SpeedGrader."""
        try:
            data = await client.post(
                f"/courses/{params.course_id}/rubric_associations",
                {
                    "rubric_association": {
                        "rubric_id": params.rubric_id,
                        "association_id": params.assignment_id,
                        "association_type": "Assignment",
                        "use_for_grading": params.use_for_grading,
                        "purpose": "grading",
                    }
                },
            )
            return (
                f"Rubric {params.rubric_id} linked to assignment {params.assignment_id}.\n\n"
                f"**Association ID**: {data.get('id')}\n"
                f"**Use for Grading**: {data.get('use_for_grading')}\n"
            )
        except Exception as e:
            return client.handle_error(e)
