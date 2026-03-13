from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import (
    SubmissionGetInput, GradeableStudentsInput, SubmissionCountInput,
    SubmissionGradeInput, ResponseFormat
)
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_get_submission",
        annotations={
            "title": "Get Single Student Submission",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_get_submission(params: SubmissionGetInput) -> str:
        """
        Get a specific student's submission for an assignment, including score, grade,
        submission content, comments, rubric assessment, and workflow state.
        """
        try:
            data = await client.get(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/submissions/{params.user_id}",
                params={
                    "include[]": [
                        "submission_comments",
                        "rubric_assessment",
                        "user",
                        "assignment",
                    ]
                },
            )
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(data, indent=2)

            user = data.get("user", {})
            comments = data.get("submission_comments", [])
            rubric = data.get("rubric_assessment", {})

            comment_lines = []
            for c in comments:
                comment_lines.append(
                    f"  - [{c.get('created_at', '?')}] **{c.get('author_name', '?')}**: "
                    f"{c.get('comment', '')}"
                )

            rubric_lines = []
            for crit_id, assessment in rubric.items():
                rubric_lines.append(
                    f"  - Criterion `{crit_id}`: "
                    f"{assessment.get('points', '?')} pts — {assessment.get('comments', '(no comment)')}"
                )

            return (
                f"# Submission — {user.get('name', f'User {params.user_id}')}\n\n"
                f"**Assignment ID**: {params.assignment_id}\n"
                f"**Status**: {data.get('workflow_state', 'N/A')}\n"
                f"**Grade**: {data.get('grade') or '(ungraded)'}\n"
                f"**Score**: {data.get('score') or '(ungraded)'}\n"
                f"**Excused**: {data.get('excused', False)}\n"
                f"**Late**: {data.get('late', False)}\n"
                f"**Missing**: {data.get('missing', False)}\n"
                f"**Submitted At**: {data.get('submitted_at') or 'not submitted'}\n"
                f"**Submission Type**: {data.get('submission_type') or 'N/A'}\n\n"
                + (f"## Submitted Content\n{data.get('body') or data.get('url') or '(no content)'}\n\n"
                   if data.get("body") or data.get("url") else "")
                + (f"## Rubric Assessment\n" + "\n".join(rubric_lines) + "\n\n" if rubric_lines else "")
                + (f"## Comments ({len(comments)})\n" + "\n".join(comment_lines) if comments else "")
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_list_gradeable_students",
        annotations={
            "title": "List Gradeable Students",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_list_gradeable_students(params: GradeableStudentsInput) -> str:
        """
        List students eligible to be graded for a specific assignment (instructor/TA only).
        Returns Canvas user IDs needed for canvas_grade_submission.
        """
        try:
            students = await client.paginate(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}/gradeable_students",
                limit=200,
            )
            if not students:
                return "No gradeable students found."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(students, indent=2)
            lines = [f"# Gradeable Students — Assignment {params.assignment_id} ({len(students)} found)\n"]
            for s in students:
                lines.append(f"- **{s.get('display_name', 'Unknown')}** (user_id: {s.get('id')})")
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_submission_counts",
        annotations={
            "title": "Get Submission Grading Counts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_get_submission_counts(params: SubmissionCountInput) -> str:
        """
        Get grading progress counts for an assignment: how many submissions are
        graded, ungraded, or not yet submitted.
        """
        try:
            data = await client.get(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                "/submission_summary"
            )
            graded = data.get("graded", 0)
            ungraded = data.get("ungraded", 0)
            not_submitted = data.get("not_submitted", 0)
            total = graded + ungraded + not_submitted
            return (
                f"# Submission Summary — Assignment {params.assignment_id}\n\n"
                f"- **Graded**: {graded}\n"
                f"- **Ungraded** (submitted but not graded): {ungraded}\n"
                f"- **Not Submitted**: {not_submitted}\n"
                f"- **Total enrolled**: {total}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_grade_submission",
        annotations={
            "title": "Grade Student Submission",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def canvas_grade_submission(params: SubmissionGradeInput) -> str:
        """
        Grade a student's submission — assign a score, fill in a rubric assessment,
        leave a text comment, or mark as excused. Requires Teacher/TA access.

        WORKFLOW: First call canvas_get_assignment to get rubric criterion IDs, then
        canvas_list_gradeable_students to get student user IDs, then this tool to grade.
        """
        try:
            payload: Dict[str, Any] = {}

            submission: Dict[str, Any] = {}
            if params.posted_grade is not None:
                submission["posted_grade"] = params.posted_grade
            if params.excuse is not None:
                submission["excuse"] = params.excuse
            if params.late_policy_status is not None:
                submission["late_policy_status"] = params.late_policy_status
            if params.seconds_late_override is not None:
                submission["seconds_late_override"] = params.seconds_late_override
            if submission:
                payload["submission"] = submission

            comment: Dict[str, Any] = {}
            if params.text_comment is not None:
                comment["text_comment"] = params.text_comment
            if params.group_comment is not None:
                comment["group_comment"] = params.group_comment
            if comment:
                payload["comment"] = comment

            if params.rubric_criteria:
                rubric_payload: Dict[str, Any] = {}
                for crit in params.rubric_criteria:
                    entry: Dict[str, Any] = {}
                    if crit.points is not None:
                        entry["points"] = crit.points
                    if crit.rating_id is not None:
                        entry["rating_id"] = crit.rating_id
                    if crit.comments is not None:
                        entry["comments"] = crit.comments
                    if entry:
                        rubric_payload[crit.criterion_id] = entry
                if rubric_payload:
                    payload["rubric_assessment"] = rubric_payload

            if not payload:
                return (
                    "Error: No grading parameters provided. Specify at least one of: "
                    "posted_grade, excuse, late_policy_status, text_comment, or rubric_criteria."
                )

            data = await client.put(
                f"/courses/{params.course_id}/assignments/{params.assignment_id}"
                f"/submissions/{params.user_id}",
                payload,
            )

            rubric = data.get("rubric_assessment", {})
            rubric_lines = []
            for crit_id, assessment in rubric.items():
                rubric_lines.append(
                    f"  - `{crit_id}`: {assessment.get('points', '?')} pts"
                    + (f" — {assessment.get('comments')}" if assessment.get("comments") else "")
                )

            return (
                f"Submission graded.\n\n"
                f"**Student user_id**: {data.get('user_id')}\n"
                f"**Assignment**: {params.assignment_id}\n"
                f"**Grade**: {data.get('grade') or '(pending)'}\n"
                f"**Score**: {data.get('score') or '(pending)'}\n"
                f"**Excused**: {data.get('excused', False)}\n"
                f"**Workflow State**: {data.get('workflow_state', 'N/A')}\n"
                f"**Grade Matches Current Submission**: {data.get('grade_matches_current_submission', 'N/A')}\n"
                + (f"\n**Rubric Assessment**:\n" + "\n".join(rubric_lines) if rubric_lines else "")
            )
        except Exception as e:
            return client.handle_error(e)
