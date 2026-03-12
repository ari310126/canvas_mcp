import re
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"

class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable.",
    )

class CourseListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enrollment_state: Optional[str] = Field(
        default="active",
        description="Filter by enrollment state: 'active', 'completed', 'invited', or 'current_and_invited'.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of courses to return.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class CourseIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., description="The Canvas numeric course ID.", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class AssignmentListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., description="Canvas course ID.", gt=0)
    bucket: Optional[str] = Field(
        default=None,
        description="Filter by bucket: 'past', 'overdue', 'undated', 'ungraded', 'upcoming', 'future'.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class AssignmentGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class PageListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class PageGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    page_url: str = Field(
        ...,
        description="The URL slug of the page (e.g. 'week-1-overview'), not a full URL.",
        min_length=1,
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @field_validator("page_url")
    @classmethod
    def validate_page_url(cls, v: str) -> str:
        if re.search(r"[/\\]|\.\.", v):
            raise ValueError("page_url must be a URL slug (no '/', '\\', or '..')")
        return v

class PageCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Page title.")
    body: str = Field(..., description="Page body as HTML.")
    published: bool = Field(default=False, description="Whether to publish immediately.")

class PageUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    page_url: str = Field(..., min_length=1, description="Existing page URL slug to update.")
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, description="New HTML body. Replaces existing content.")
    published: Optional[bool] = Field(default=None)

    @field_validator("page_url")
    @classmethod
    def validate_page_url(cls, v: str) -> str:
        if re.search(r"[/\\]|\.\.", v):
            raise ValueError("page_url must be a URL slug (no '/', '\\', or '..')")
        return v

class ModuleListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class ModuleItemsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class AnnouncementListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class AnnouncementCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., description="Announcement body as HTML.")
    delayed_post_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 datetime to schedule the announcement (e.g. '2025-09-01T08:00:00Z').",
    )

class DiscussionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class DiscussionReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    topic_id: int = Field(..., gt=0, description="The discussion topic ID.")
    message: str = Field(..., min_length=1, description="Reply body as HTML or plain text.")

class AssignmentCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, description="Assignment instructions as HTML.")
    points_possible: Optional[float] = Field(default=None, ge=0)
    due_at: Optional[str] = Field(
        default=None,
        description="Due date as ISO 8601 (e.g. '2025-10-15T23:59:00Z').",
    )
    submission_types: List[str] = Field(
        default_factory=lambda: ["online_text_entry"],
        description="List of submission types: 'online_text_entry', 'online_upload', 'online_url', 'none', etc.",
    )
    published: bool = Field(default=False)

class AssignmentUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    points_possible: Optional[float] = Field(default=None, ge=0)
    due_at: Optional[str] = Field(default=None)
    published: Optional[bool] = Field(default=None)

class PlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (e.g. '2025-09-01'). Defaults to today.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (e.g. '2025-12-31'). Defaults to 4 weeks out.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class SubmissionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

class FileListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

# --- Formatters migrated from server.py ---

def fmt_course(c: Dict) -> str:
    score = c.get("enrollments", [{}])[0].get("computed_current_score")
    score_str = f" | Score: {score}%" if score is not None else ""
    return (
        f"### {c.get('name', 'Untitled')} (ID: {c.get('id')})\n"
        f"- Code: {c.get('course_code', 'N/A')}{score_str}\n"
    )

def fmt_assignment(a: Dict) -> str:
    parts = [f"### {a.get('name', 'Untitled')} (ID: {a.get('id')})"]
    if a.get("due_at"):
        parts.append(f"- **Due**: {a['due_at']}")
    if a.get("points_possible") is not None:
        parts.append(f"- **Points**: {a['points_possible']}")
    if a.get("submission_types"):
        parts.append(f"- **Submission**: {', '.join(a['submission_types'])}")
    if a.get("html_url"):
        parts.append(f"- **Link**: {a['html_url']}")
    if a.get("description"):
        desc = a["description"][:300].replace("\n", " ")
        parts.append(f"- **Description** (excerpt): {desc}…")
    return "\n".join(parts)
