from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, Any
from models import QuizListInput, QuizGetInput, QuizCreateInput, QuizUpdateInput, ResponseFormat
import client


def register(mcp: FastMCP):
    @mcp.tool(
        name="canvas_list_quizzes",
        annotations={"title": "List Course Quizzes", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_list_quizzes(params: QuizListInput) -> str:
        """List all quizzes in a Canvas course."""
        try:
            quizzes = await client.paginate(f"/courses/{params.course_id}/quizzes", limit=params.limit)
            if not quizzes:
                return f"No quizzes found for course {params.course_id}."
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(quizzes, indent=2)
            lines = [f"# Quizzes — Course {params.course_id} ({len(quizzes)} found)\n"]
            for q in quizzes:
                attempts = q.get("allowed_attempts", 1)
                attempts_str = "unlimited" if attempts == -1 else str(attempts)
                lines.append(
                    f"### {q.get('title', 'Untitled')} (quiz_id: {q.get('id')})\n"
                    f"- Type: {q.get('quiz_type')} | Points: {q.get('points_possible')} "
                    f"| Attempts: {attempts_str} | Published: {q.get('published')}\n"
                    f"- Due: {q.get('due_at') or '—'} | Link: {q.get('html_url', 'N/A')}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_get_quiz",
        annotations={"title": "Get Quiz Details", "readOnlyHint": True,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_get_quiz(params: QuizGetInput) -> str:
        """Get full details for a specific Canvas quiz."""
        try:
            data = await client.get(f"/courses/{params.course_id}/quizzes/{params.quiz_id}")
            if params.response_format == ResponseFormat.JSON:
                return json.dumps(data, indent=2)
            attempts = data.get("allowed_attempts", 1)
            return (
                f"# {data.get('title', 'Untitled')} (quiz_id: {data.get('id')})\n\n"
                f"**Type**: {data.get('quiz_type')}\n"
                f"**Points**: {data.get('points_possible')}\n"
                f"**Attempts**: {'unlimited' if attempts == -1 else attempts}\n"
                f"**Time Limit**: {data.get('time_limit') or 'none'} min\n"
                f"**Shuffle Answers**: {data.get('shuffle_answers')}\n"
                f"**Published**: {data.get('published')}\n"
                f"**Due**: {data.get('due_at') or '—'}\n"
                f"**Unlock**: {data.get('unlock_at') or '—'}\n"
                f"**Lock**: {data.get('lock_at') or '—'}\n"
                f"**Link**: {data.get('html_url', 'N/A')}\n\n"
                f"## Description\n{data.get('description') or '(none)'}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_create_quiz",
        annotations={"title": "Create Quiz", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    )
    async def canvas_create_quiz(params: QuizCreateInput) -> str:
        """
        Create a new quiz in a Canvas course (requires Teacher/TA access).
        This creates the quiz shell. Add questions manually in Canvas or via the Quiz Questions API.
        """
        try:
            quiz: Dict[str, Any] = {
                "title": params.title,
                "quiz_type": params.quiz_type,
                "allowed_attempts": params.allowed_attempts,
                "shuffle_answers": params.shuffle_answers,
                "show_correct_answers": params.show_correct_answers,
                "published": params.published,
            }
            for field, val in [
                ("description", params.description),
                ("time_limit", params.time_limit),
                ("due_at", params.due_at),
                ("unlock_at", params.unlock_at),
                ("lock_at", params.lock_at),
                ("assignment_group_id", params.assignment_group_id),
            ]:
                if val is not None:
                    quiz[field] = val

            data = await client.post(f"/courses/{params.course_id}/quizzes", {"quiz": quiz})
            return (
                f"Quiz created.\n\n"
                f"**Title**: {data.get('title')}\n"
                f"**ID**: {data.get('id')}\n"
                f"**Type**: {data.get('quiz_type')}\n"
                f"**Published**: {data.get('published')}\n"
                f"**Due**: {data.get('due_at') or '—'}\n"
                f"**Edit Link**: {data.get('html_url', 'N/A')}\n"
            )
        except Exception as e:
            return client.handle_error(e)

    @mcp.tool(
        name="canvas_update_quiz",
        annotations={"title": "Update Quiz", "readOnlyHint": False,
                      "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    )
    async def canvas_update_quiz(params: QuizUpdateInput) -> str:
        """Update an existing Canvas quiz's settings, dates, or publish status."""
        try:
            quiz: Dict[str, Any] = {}
            for field, val in [
                ("title", params.title),
                ("description", params.description),
                ("time_limit", params.time_limit),
                ("allowed_attempts", params.allowed_attempts),
                ("shuffle_answers", params.shuffle_answers),
                ("due_at", params.due_at),
                ("unlock_at", params.unlock_at),
                ("lock_at", params.lock_at),
                ("published", params.published),
            ]:
                if val is not None:
                    quiz[field] = val

            data = await client.put(f"/courses/{params.course_id}/quizzes/{params.quiz_id}", {"quiz": quiz})
            return (
                f"Quiz updated.\n\n"
                f"**Title**: {data.get('title')}\n"
                f"**Published**: {data.get('published')}\n"
                f"**Due**: {data.get('due_at') or '—'}\n"
            )
        except Exception as e:
            return client.handle_error(e)
