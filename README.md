# Canvas LMS MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude read and write
Canvas LMS course content — **without a Canvas developer key or OAuth2 registration**.

## How authentication works (same approach as the AI Tutor extension)

The AI Tutor browser extension works by running JavaScript directly on the Canvas domain while
the student is already logged in. The browser's existing session cookies are automatically sent
with every `fetch()` call, so no API key is needed.

This MCP server replicates the exact same trick at the Python level: you copy your Canvas session
cookies from your browser and paste them into an environment variable. The MCP server then sends
those cookies in the `Cookie` header of every API request, impersonating your authenticated
browser session.

> **Session lifetime**: Canvas session cookies typically last as long as your browser session
> (often days to weeks with "remember me" enabled). When they expire, you'll get a 401 error
> and will need to refresh them — just log in again and re-copy the cookie header.

---

## Setup

### 1. Install dependencies

```bash
cd canvas_mcp
pip install -r requirements.txt
```

### 2. Automatic Cookie Extraction

The easiest way to authenticate is to let the MCP server automatically extract your Canvas session cookie from your browser. It detects your default browser and tries it first, then falls back through other installed browsers (Chrome, Safari, Edge, Firefox, Brave, Chromium, Arc, Opera, Vivaldi, LibreWolf).

1. Log in to Canvas in your browser.
2. Keep the browser open or closed — the MCP server reads the stored cookies in the background.

Whenever your Canvas session expires (usually after a few days or weeks), simply log back into Canvas in your browser.

> **Tip**: To force a specific browser, set `BROWSER=firefox` (or `chrome`, `edge`, `brave`, `safari`, etc.) before starting the server.

### 3. Set environment variables

All you need is the base URL.

```bash
export CANVAS_BASE_URL="https://yourschool.instructure.com"
```

*(Optional fallback)*: If automatic extraction fails, you can manually copy the `Cookie` header from your browser DevTools (ensure it includes `_csrf_token=...`) and set it explicitly:

```bash
export CANVAS_COOKIE="canvas_session=AbCdEfGh...; _csrf_token=...; log_session_id=..."
```

### 4. Run the server

**stdio mode** (for Claude Desktop / local use):
```bash
python server.py
```

**HTTP mode** (for remote / multi-client use):
```bash
python server.py --http
# Listens on http://localhost:8080
```

---

## Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "python",
      "args": ["/path/to/canvas_mcp/server.py"],
      "env": {
        "CANVAS_BASE_URL": "https://yourschool.instructure.com"
      }
    }
  }
}
```

---

## Available tools (58 total)

### Read — students & instructors

| Tool | Description |
|------|-------------|
| `canvas_get_profile` | Current user's name, ID, email, avatar, bio |
| `canvas_list_courses` | All enrolled courses with current scores |
| `canvas_get_course` | Course details including syllabus body |
| `canvas_list_assignments` | Assignments with due dates, points, rubrics; filterable by bucket |
| `canvas_get_assignment` | Full assignment details + rubric criteria |
| `canvas_list_pages` | Wiki pages in a course with published status |
| `canvas_get_page` | Full page content (HTML body) by URL slug |
| `canvas_list_modules` | Course modules with item counts |
| `canvas_list_module_items` | Items inside a specific module |
| `canvas_list_announcements` | Recent course announcements |
| `canvas_list_discussions` | Discussion topics with reply counts and last activity |
| `canvas_get_planner` | Upcoming assignments/events from the Canvas planner |
| `canvas_get_activity_stream` | Recent activity notifications |
| `canvas_list_files` | Files uploaded to a course with download URLs |
| `canvas_list_submissions` | Student submissions for an assignment (instructor/TA only) |

### Pages & assignments (instructors & TAs)

| Tool | Description |
|------|-------------|
| `canvas_create_page` | Create a new wiki page (optionally publish immediately) |
| `canvas_update_page` | Edit an existing page's title, body, or publish status |
| `canvas_create_assignment` | Create a new assignment with points, due date, submission types |
| `canvas_update_assignment` | Edit an existing assignment (partial update — only provided fields change) |
| `canvas_create_announcement` | Post an announcement, with optional scheduled delivery |
| `canvas_post_discussion_reply` | Reply to a discussion topic |

### Grading (instructors & TAs)

| Tool | Description |
|------|-------------|
| `canvas_get_submission` | Full submission details — score, grade, content, rubric, comments |
| `canvas_list_gradeable_students` | Students eligible to be graded on an assignment |
| `canvas_get_submission_counts` | Grading progress: how many are graded / ungraded / not submitted |
| `canvas_grade_submission` | Assign a score, fill in rubric criteria, leave a comment, or excuse |

### Assignment overrides (per-student / per-section due dates)

| Tool | Description |
|------|-------------|
| `canvas_list_assignment_overrides` | List all date overrides for an assignment |
| `canvas_get_assignment_override` | Get a single override by ID |
| `canvas_create_assignment_override` | Create an override for specific students, a section, or a group |
| `canvas_update_assignment_override` | Update override dates (fetches existing first to merge changes) |
| `canvas_delete_assignment_override` | Delete an override (students revert to default dates) |

### Enrollments & sections

| Tool | Description |
|------|-------------|
| `canvas_list_enrollments` | List enrollments for a course, filterable by role and state |
| `canvas_list_sections` | List sections in a course with enrollment counts |

### Conversations (Canvas Inbox)

| Tool | Description |
|------|-------------|
| `canvas_send_message` | Send a Canvas inbox message to one or more recipients |
| `canvas_list_conversations` | List inbox conversations, filterable by scope and course |

### Calendar events

| Tool | Description |
|------|-------------|
| `canvas_list_calendar_events` | List calendar events for a course or the current user |
| `canvas_create_calendar_event` | Create a new calendar event |
| `canvas_update_calendar_event` | Update an existing calendar event |
| `canvas_delete_calendar_event` | Delete a calendar event |

### Modules (write operations)

| Tool | Description |
|------|-------------|
| `canvas_create_module` | Create a new module in a course |
| `canvas_update_module` | Update module name, publish/lock status, or prerequisites |
| `canvas_delete_module` | Delete a module |
| `canvas_create_module_item` | Add a page, assignment, quiz, or external URL to a module |
| `canvas_delete_module_item` | Remove an item from a module |

### Assignment groups

| Tool | Description |
|------|-------------|
| `canvas_list_assignment_groups` | List assignment groups with weights and rules |
| `canvas_create_assignment_group` | Create a new assignment group |
| `canvas_update_assignment_group` | Update group name, weight, or drop rules |
| `canvas_delete_assignment_group` | Delete an assignment group |

### Analytics

| Tool | Description |
|------|-------------|
| `canvas_get_course_analytics` | Course-level analytics: participation, submissions, grades summary |
| `canvas_get_student_analytics` | Per-student activity and submission analytics |

### Rubrics

| Tool | Description |
|------|-------------|
| `canvas_list_rubrics` | List rubrics in a course |
| `canvas_create_rubric` | Create a new rubric with custom criteria and ratings |
| `canvas_associate_rubric` | Associate an existing rubric with an assignment |

### Quizzes

| Tool | Description |
|------|-------------|
| `canvas_list_quizzes` | List quizzes in a course |
| `canvas_get_quiz` | Get full quiz details including question count and settings |
| `canvas_create_quiz` | Create a new quiz |
| `canvas_update_quiz` | Update quiz settings, due dates, time limits, etc. |

### Late policy

| Tool | Description |
|------|-------------|
| `canvas_get_late_policy` | Get the course late submission / missing policy |
| `canvas_update_late_policy` | Update late deduction rates or missing submission policies |

---

## Example prompts

```
What courses am I enrolled in?

Show me upcoming assignments for course 12345.

Get the syllabus for my CS 101 course (ID 9988).

Create a page called "Week 5 Overview" in course 12345 with a brief intro.

Post an announcement to course 12345: "Midterm is next Thursday — review chapters 4–7."

What's on my Canvas planner this week?

Grade student 4521's submission for assignment 789 in course 12345 with 87 points and the comment "Great analysis!"

Give student 4521 a one-week extension on assignment 789 in course 12345.

Show me grading progress for assignment 789 — how many submissions are still ungraded?

List all sections in course 12345.

Create a rubric with three criteria (thesis, evidence, style) in course 12345.

What is the late policy for course 12345?

Create a calendar event "Office Hours" for course 12345 on Friday at 2pm.
```

---

## Security notes

- The Canvas cookie value is equivalent to your Canvas password — keep it secret.
- If you manually use `CANVAS_COOKIE`, never commit it to git; always pass it via environment variables or a secrets manager.
- The server only communicates with the Canvas domain specified in `CANVAS_BASE_URL`.
- Write operations (create/update/delete) require your Canvas account to have Teacher or TA
  enrollment in the relevant course; student accounts can only use the read tools.
- The `X-CSRF-Token` is automatically extracted from your cookie string. If it is absent,
  a warning is printed at startup and all write operations will fail with HTTP 422.
