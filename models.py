import re
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_iso_datetime(v: str) -> str:
    """Validate that a string is a valid ISO 8601 datetime."""
    try:
        datetime.fromisoformat(v)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid ISO 8601 datetime: {v!r}")
    return v

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

    @field_validator("delayed_post_at")
    @classmethod
    def check_delayed_post_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v

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

    @field_validator("due_at")
    @classmethod
    def check_due_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v

class AssignmentUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    points_possible: Optional[float] = Field(default=None, ge=0)
    due_at: Optional[str] = Field(default=None)
    published: Optional[bool] = Field(default=None)

    @field_validator("due_at")
    @classmethod
    def check_due_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v

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

    @field_validator("start_date", "end_date")
    @classmethod
    def check_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v

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

# ---------------------------------------------------------------------------
# Grading models
# ---------------------------------------------------------------------------

class RubricCriterionGrade(BaseModel):
    """Grade for a single rubric criterion."""
    model_config = ConfigDict(extra="forbid")
    criterion_id: str = Field(
        ...,
        description=(
            "The Canvas criterion ID from the assignment rubric "
            "(e.g. '_4521', 'crit_abc123'). "
            "Retrieve it via canvas_get_assignment."
        ),
    )
    points: Optional[float] = Field(
        default=None,
        ge=0,
        description="Points awarded for this criterion.",
    )
    rating_id: Optional[str] = Field(
        default=None,
        description="ID of the selected rating (optional; use with rubric rating scales).",
    )
    comments: Optional[str] = Field(
        default=None,
        description="Free-text feedback for this specific criterion.",
    )


class SubmissionGradeInput(BaseModel):
    """Input for grading a student submission."""
    model_config = ConfigDict(extra="forbid")

    course_id: int = Field(..., gt=0, description="Canvas course ID.")
    assignment_id: int = Field(..., gt=0, description="Canvas assignment ID.")
    user_id: int = Field(
        ..., gt=0,
        description="Canvas user ID of the student whose submission is being graded.",
    )
    posted_grade: Optional[str] = Field(
        default=None,
        description=(
            "The grade to assign. Accepts multiple formats depending on the assignment's "
            "grading type:\n"
            "  - Points: '87' or '87.5'\n"
            "  - Percentage: '92%'\n"
            "  - Letter: 'A-', 'B+'\n"
            "  - Pass/Fail: 'pass' or 'fail'\n"
            "  - Complete/Incomplete: 'complete' or 'incomplete'\n"
            "Leave null to only add a comment or rubric assessment without changing the grade."
        ),
    )
    excuse: Optional[bool] = Field(
        default=None,
        description="Set to true to mark the submission as excused (exempt from grading).",
    )
    late_policy_status: Optional[str] = Field(
        default=None,
        description=(
            "Override the late policy status: 'late', 'missing', 'extended', 'none', or null "
            "to clear an override."
        ),
    )
    seconds_late_override: Optional[int] = Field(
        default=None,
        ge=0,
        description="If late_policy_status='late', specify how many seconds late the submission is.",
    )
    text_comment: Optional[str] = Field(
        default=None,
        description="Text comment to add to the submission (visible to the student).",
    )
    group_comment: Optional[bool] = Field(
        default=None,
        description="If true and this is a group assignment, the comment applies to all group members.",
    )
    rubric_criteria: Optional[List[RubricCriterionGrade]] = Field(
        default=None,
        description=(
            "List of per-criterion rubric grades. Each item must include criterion_id "
            "(from the assignment rubric) and at least one of: points, rating_id, comments. "
            "Use canvas_get_assignment to retrieve criterion IDs first."
        ),
    )


class SubmissionGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0, description="Canvas user ID of the student.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GradeableStudentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SubmissionCountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Override models
# ---------------------------------------------------------------------------

class OverrideTarget(str, Enum):
    """What the override targets."""
    STUDENTS = "students"
    SECTION = "section"
    GROUP = "group"


class OverrideListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class OverrideGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0, description="Canvas assignment override ID.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class OverrideCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)

    # Target -- exactly one must be provided
    student_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "List of Canvas user IDs to include in this override. "
            "Use when setting different dates for specific students. "
            "Get user IDs from canvas_list_gradeable_students."
        ),
    )
    course_section_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Canvas section ID. Use to override dates for an entire section.",
    )
    group_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Canvas group ID. Use to override dates for a group assignment group.",
    )

    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description=(
            "Human-readable label for this override (required when targeting student_ids). "
            "Example: 'Extended deadline -- Smith, Jones'."
        ),
    )
    due_at: Optional[str] = Field(
        default=None,
        description=(
            "New due date as ISO 8601 (e.g. '2025-10-20T23:59:00Z'). "
            "Pass null to remove a due date override."
        ),
    )
    unlock_at: Optional[str] = Field(
        default=None,
        description="Date the assignment becomes available to the target (ISO 8601). Null to remove.",
    )
    lock_at: Optional[str] = Field(
        default=None,
        description=(
            "Date the assignment locks for the target (ISO 8601). "
            "This is the 'Until' date students see. Null to remove."
        ),
    )

    @field_validator("due_at", "unlock_at", "lock_at")
    @classmethod
    def check_override_create_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class OverrideUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0, description="ID of the override to update.")

    student_ids: Optional[List[int]] = Field(
        default=None,
        description="Replace the list of targeted student IDs.",
    )
    title: Optional[str] = Field(default=None, max_length=255)
    due_at: Optional[str] = Field(
        default=None,
        description=(
            "New due date (ISO 8601). Pass the string 'null' to explicitly remove the due date override."
        ),
    )
    unlock_at: Optional[str] = Field(
        default=None,
        description="New unlock date (ISO 8601). Pass 'null' to remove.",
    )
    lock_at: Optional[str] = Field(
        default=None,
        description="New lock/Until date (ISO 8601). Pass 'null' to remove.",
    )

    @field_validator("due_at", "unlock_at", "lock_at")
    @classmethod
    def check_override_update_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "null":
            return _validate_iso_datetime(v)
        return v


class OverrideDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    assignment_id: int = Field(..., gt=0)
    override_id: int = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Enrollment models
# ---------------------------------------------------------------------------

class EnrollmentListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    role: Optional[str] = Field(
        default=None,
        description=(
            "Filter by enrollment role. Common values: 'StudentEnrollment', "
            "'TeacherEnrollment', 'TaEnrollment', 'ObserverEnrollment', 'DesignerEnrollment'. "
            "Leave empty to return all roles."
        ),
    )
    section_id: Optional[int] = Field(
        default=None, gt=0,
        description="Filter to a specific section ID.",
    )
    state: Optional[str] = Field(
        default="active",
        description="Enrollment state: 'active', 'invited', 'creation_pending', 'deleted', 'rejected', 'completed', 'inactive'.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SectionListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# Conversation models
# ---------------------------------------------------------------------------

class SendMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipients: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "List of recipient identifiers. Can be:\n"
            "  - Canvas user IDs as strings: ['4521', '4522']\n"
            "  - A whole course: ['course_12345']\n"
            "  - A section: ['section_678']\n"
            "  - A group: ['group_90']\n"
            "Get user IDs from canvas_list_enrollments."
        ),
    )
    subject: str = Field(..., min_length=1, max_length=255, description="Message subject line.")
    body: str = Field(..., min_length=1, description="Message body text.")
    group_conversation: bool = Field(
        default=False,
        description=(
            "True: creates one group thread everyone can see each other in. "
            "False (default): sends a separate private conversation to each recipient."
        ),
    )
    bulk_message: bool = Field(
        default=False,
        description=(
            "Required to be True when messaging a whole course/section with more than 100 members."
        ),
    )


class ListConversationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Optional[str] = Field(
        default=None,
        description="Filter: 'unread', 'starred', 'archived', 'sent'. Leave empty for inbox.",
    )
    limit: int = Field(default=20, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# Calendar event models
# ---------------------------------------------------------------------------

class CalendarEventListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0, description="Canvas course ID -- events for this course.")
    start_date: Optional[str] = Field(default=None, description="ISO 8601 date (e.g. '2025-09-01').")
    end_date: Optional[str] = Field(default=None, description="ISO 8601 date (e.g. '2025-12-31').")
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @field_validator("start_date", "end_date")
    @classmethod
    def check_calendar_list_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class CalendarEventCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    start_at: str = Field(..., description="Event start, ISO 8601 (e.g. '2025-10-15T14:00:00Z').")
    end_at: Optional[str] = Field(default=None, description="Event end, ISO 8601.")
    description: Optional[str] = Field(default=None, description="Event description as HTML or plain text.")
    location_name: Optional[str] = Field(default=None, description="Location name (e.g. 'Room 301', 'Zoom').")
    location_address: Optional[str] = Field(default=None, description="Physical or meeting URL address.")
    all_day: bool = Field(default=False, description="True for an all-day event.")

    @field_validator("start_at", "end_at")
    @classmethod
    def check_calendar_create_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class CalendarEventUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(..., gt=0, description="Calendar event ID to update.")
    title: Optional[str] = Field(default=None, max_length=255)
    start_at: Optional[str] = Field(default=None)
    end_at: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    location_name: Optional[str] = Field(default=None)

    @field_validator("start_at", "end_at")
    @classmethod
    def check_calendar_update_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class CalendarEventDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(..., gt=0)
    reason: Optional[str] = Field(default=None, description="Optional cancellation reason shown to students.")


# ---------------------------------------------------------------------------
# Module write models
# ---------------------------------------------------------------------------

class ModuleCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    position: Optional[int] = Field(default=None, ge=1, description="Position in module list (1-indexed).")
    unlock_at: Optional[str] = Field(default=None, description="ISO 8601 date when module unlocks.")
    require_sequential_progress: bool = Field(
        default=False,
        description="Students must complete items in order.",
    )
    published: bool = Field(default=False)

    @field_validator("unlock_at")
    @classmethod
    def check_module_create_unlock_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class ModuleUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    position: Optional[int] = Field(default=None, ge=1)
    unlock_at: Optional[str] = Field(default=None)
    require_sequential_progress: Optional[bool] = Field(default=None)
    published: Optional[bool] = Field(default=None)

    @field_validator("unlock_at")
    @classmethod
    def check_module_update_unlock_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class ModuleDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)


class ModuleItemCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Display title for the item.")
    type: str = Field(
        ...,
        description=(
            "Item type: 'File', 'Page', 'Discussion', 'Assignment', 'Quiz', "
            "'SubHeader', 'ExternalUrl', 'ExternalTool'."
        ),
    )
    content_id: Optional[int] = Field(
        default=None, gt=0,
        description="ID of the linked content object (assignment_id, page_url, quiz_id, etc.). Not needed for SubHeader or ExternalUrl.",
    )
    page_url: Optional[str] = Field(
        default=None,
        description="Page URL slug (required when type='Page').",
    )
    external_url: Optional[str] = Field(
        default=None,
        description="External URL (required when type='ExternalUrl' or 'ExternalTool').",
    )
    position: Optional[int] = Field(default=None, ge=1, description="Position within the module.")
    indent: int = Field(default=0, ge=0, le=5, description="Visual indent level (0-5).")
    new_tab: bool = Field(default=False, description="Open external links in new tab.")


class ModuleItemDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    module_id: int = Field(..., gt=0)
    item_id: int = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Assignment group models
# ---------------------------------------------------------------------------

class AssignmentGroupListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AssignmentGroupCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255, description="Group name (e.g. 'Discussions', 'Final Project').")
    group_weight: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage weight if the course uses weighted assignment groups (0-100).",
    )
    position: Optional[int] = Field(default=None, ge=1, description="Display order (1-indexed).")


class AssignmentGroupUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    group_id: int = Field(..., gt=0)
    name: Optional[str] = Field(default=None, max_length=255)
    group_weight: Optional[float] = Field(default=None, ge=0, le=100)
    position: Optional[int] = Field(default=None, ge=1)


class AssignmentGroupDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    group_id: int = Field(..., gt=0)
    move_assignments_to: Optional[int] = Field(
        default=None, gt=0,
        description="Move assignments in this group to another group ID before deleting.",
    )


# ---------------------------------------------------------------------------
# Analytics models
# ---------------------------------------------------------------------------

class CourseAnalyticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class StudentAnalyticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0, description="Student's Canvas user ID.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# Rubric models
# ---------------------------------------------------------------------------

class RubricCriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(..., min_length=1, description="Criterion name/description.")
    long_description: Optional[str] = Field(default=None, description="Detailed criterion explanation.")
    points: float = Field(..., ge=0, description="Maximum points for this criterion.")
    ratings: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Rating scale for this criterion. Each rating: {description, points}. "
            "Example: [{'description': 'Excellent', 'points': 10}, "
            "{'description': 'Satisfactory', 'points': 7}, "
            "{'description': 'Needs Work', 'points': 3}]. "
            "If omitted, Canvas creates a default 3-rating scale."
        ),
    )


class RubricCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255, description="Rubric title.")
    criteria: List[RubricCriterionInput] = Field(
        ...,
        min_length=1,
        description="List of rubric criteria. Each needs a description and points value.",
    )
    free_form_criterion_comments: bool = Field(
        default=True,
        description="Allow free-text comments per criterion (recommended: True).",
    )
    assignment_id: Optional[int] = Field(
        default=None, gt=0,
        description="If provided, immediately associates the rubric with this assignment for grading.",
    )
    use_for_grading: bool = Field(
        default=True,
        description="Whether this rubric drives the gradebook score (only applies if assignment_id given).",
    )


class RubricListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RubricAssociateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    rubric_id: int = Field(..., gt=0, description="Rubric ID (from canvas_list_rubrics or canvas_create_rubric).")
    assignment_id: int = Field(..., gt=0, description="Assignment to attach the rubric to.")
    use_for_grading: bool = Field(
        default=True,
        description="True: rubric score feeds into the gradebook. False: for feedback only.",
    )


# ---------------------------------------------------------------------------
# Quiz models
# ---------------------------------------------------------------------------

class QuizListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class QuizGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    quiz_id: int = Field(..., gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class QuizCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    quiz_type: str = Field(
        default="assignment",
        description=(
            "Quiz type: 'practice_quiz' (ungraded practice), 'assignment' (graded), "
            "'graded_survey', 'survey'."
        ),
    )
    description: Optional[str] = Field(default=None, description="Quiz instructions as HTML.")
    time_limit: Optional[int] = Field(default=None, ge=1, description="Time limit in minutes.")
    allowed_attempts: int = Field(
        default=1, ge=-1,
        description="Number of allowed attempts. -1 = unlimited.",
    )
    shuffle_answers: bool = Field(default=False, description="Randomize answer order.")
    show_correct_answers: bool = Field(default=True, description="Show correct answers after submission.")
    due_at: Optional[str] = Field(default=None, description="Due date ISO 8601.")
    unlock_at: Optional[str] = Field(default=None, description="Available from date ISO 8601.")
    lock_at: Optional[str] = Field(default=None, description="Locks after this date ISO 8601.")
    published: bool = Field(default=False)
    assignment_group_id: Optional[int] = Field(
        default=None, gt=0,
        description="Assignment group to place this quiz in.",
    )

    @field_validator("due_at", "unlock_at", "lock_at")
    @classmethod
    def check_quiz_create_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


class QuizUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    quiz_id: int = Field(..., gt=0)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    time_limit: Optional[int] = Field(default=None, ge=1)
    allowed_attempts: Optional[int] = Field(default=None, ge=-1)
    shuffle_answers: Optional[bool] = Field(default=None)
    due_at: Optional[str] = Field(default=None)
    unlock_at: Optional[str] = Field(default=None)
    lock_at: Optional[str] = Field(default=None)
    published: Optional[bool] = Field(default=None)

    @field_validator("due_at", "unlock_at", "lock_at")
    @classmethod
    def check_quiz_update_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_iso_datetime(v)
        return v


# ---------------------------------------------------------------------------
# Late policy models
# ---------------------------------------------------------------------------

class LatePolicyGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)


class LatePolicyUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int = Field(..., gt=0)
    late_submission_deduction_enabled: Optional[bool] = Field(
        default=None,
        description="Enable automatic point deduction for late submissions.",
    )
    late_submission_deduction: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage points deducted per late_submission_interval.",
    )
    late_submission_interval: Optional[str] = Field(
        default=None,
        description="Deduction interval: 'day' or 'hour'.",
    )
    late_submission_minimum_percent_enabled: Optional[bool] = Field(
        default=None,
        description="Enable a floor so late deductions don't drop the grade below a minimum.",
    )
    late_submission_minimum_percent: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Minimum grade percentage after late deductions.",
    )
    missing_submission_deduction_enabled: Optional[bool] = Field(
        default=None,
        description="Enable automatic score for missing (never-submitted) assignments.",
    )
    missing_submission_deduction: Optional[float] = Field(
        default=None, ge=0, le=100,
        description="Percentage of points to award for missing submissions (usually 0).",
    )


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
