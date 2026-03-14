# Canvas LMS MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude read and write
Canvas LMS course content — **without a Canvas developer key or OAuth2 registration**.

## How it works

This MCP server authenticates to Canvas using your browser's existing session cookies —
the same approach used by the AI Tutor browser extension. No API key or OAuth2 setup
is needed. By default, cookies are extracted automatically from your browser. See
[SECURITY.md](SECURITY.md) for details on the authentication model.

> **Session lifetime**: Canvas sessions typically last days to weeks. When they expire
> you'll get a 401 error — just log back into Canvas in your browser and restart the
> server.

---

## Setup

### 1. Install dependencies

Requires **Python 3.10+**.

```bash
cd canvas_mcp
pip3 install -r requirements.txt
```

### 2. Set your Canvas URL

```bash
export CANVAS_BASE_URL="https://yourschool.instructure.com"
```

This must be an `https://` URL — the server will refuse to start with plain HTTP.

### 3. Authenticate

**Automatic (recommended)**: Just log into Canvas in your browser. The server
automatically extracts cookies from your default browser at startup. Supported
browsers: Chrome, Safari, Edge, Firefox, Brave, Chromium, Arc, Opera, Vivaldi,
LibreWolf.

To force a specific browser:

```bash
export BROWSER=firefox  # or chrome, edge, brave, safari, etc.
```

**Manual fallback**: If automatic extraction fails, copy the `Cookie` header from
your browser DevTools (Network tab → any Canvas request → Request Headers) and set:

```bash
export CANVAS_COOKIE="canvas_session=AbCdEfGh...; _csrf_token=...; log_session_id=..."
```

Make sure the cookie string includes `_csrf_token=...` — without it, all write
operations will fail with HTTP 422.

### 4. Run the server

```bash
python3 server.py            # stdio mode (for Claude Desktop)
python3 server.py --http     # HTTP mode on localhost:8080
```

---

## Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "python3",
      "args": ["/absolute/path/to/canvas_mcp/server.py"],
      "env": {
        "CANVAS_BASE_URL": "https://yourschool.instructure.com"
      }
    }
  }
}
```

> **Tip**: Use the absolute path to `server.py`. Relative paths may not resolve
> correctly depending on how Claude Desktop launches the process.

---

## Available tools (58)

### General (students & instructors)

| Tool | Description |
|------|-------------|
| `canvas_get_profile` | Current user's name, ID, email, avatar, bio |
| `canvas_list_courses` | All enrolled courses with current scores |
| `canvas_get_course` | Course details including syllabus body |
| `canvas_get_activity_stream` | Recent notifications, submissions, and messages |
| `canvas_get_planner` | Upcoming assignments/events from the Canvas planner |

### Assignments

| Tool | Description |
|------|-------------|
| `canvas_list_assignments` | Assignments with due dates, points, rubrics; filterable by bucket |
| `canvas_get_assignment` | Full assignment details + rubric criteria |
| `canvas_create_assignment` | Create a new assignment with points, due date, submission types |
| `canvas_update_assignment` | Edit an existing assignment (partial update) |

### Pages

| Tool | Description |
|------|-------------|
| `canvas_list_pages` | Wiki pages in a course with published status |
| `canvas_get_page` | Full page content (HTML body) by URL slug |
| `canvas_create_page` | Create a new wiki page (optionally publish immediately) |
| `canvas_update_page` | Edit an existing page's title, body, or publish status |

### Modules

| Tool | Description |
|------|-------------|
| `canvas_list_modules` | Course modules with item counts |
| `canvas_list_module_items` | Items inside a specific module |
| `canvas_create_module` | Create a new module (with optional unlock date) |
| `canvas_update_module` | Rename, reposition, publish/unpublish a module |
| `canvas_delete_module` | Delete a module (content items are NOT deleted) |
| `canvas_create_module_item` | Add an item to a module (assignment, page, quiz, URL, etc.) |
| `canvas_delete_module_item` | Remove an item from a module (underlying content is NOT deleted) |

### Communication

| Tool | Description |
|------|-------------|
| `canvas_list_announcements` | Recent course announcements |
| `canvas_create_announcement` | Post an announcement, with optional scheduled delivery |
| `canvas_list_discussions` | Discussion topics with reply counts and last activity |
| `canvas_post_discussion_reply` | Reply to a discussion topic |
| `canvas_send_message` | Send a Canvas Inbox message to students, sections, or a course |
| `canvas_list_conversations` | List Canvas Inbox conversations |

### Calendar

| Tool | Description |
|------|-------------|
| `canvas_list_calendar_events` | Calendar events for a course (filterable by date range) |
| `canvas_create_calendar_event` | Create a calendar event (office hours, exam, meeting) |
| `canvas_update_calendar_event` | Update an event's title, time, or location |
| `canvas_delete_calendar_event` | Delete a calendar event |

### Grading & submissions

| Tool | Description |
|------|-------------|
| `canvas_list_submissions` | Student submissions for an assignment |
| `canvas_get_submission` | Single submission with score, comments, rubric assessment |
| `canvas_list_gradeable_students` | Students eligible to be graded for an assignment |
| `canvas_get_submission_counts` | Grading progress: graded / ungraded / not submitted |
| `canvas_grade_submission` | Grade a submission (score, rubric, comment, excuse) |

### Overrides

| Tool | Description |
|------|-------------|
| `canvas_list_assignment_overrides` | Date overrides for an assignment (per-student/section/group) |
| `canvas_get_assignment_override` | Single override details |
| `canvas_create_assignment_override` | Create a date override for students, a section, or a group |
| `canvas_update_assignment_override` | Update an existing override |
| `canvas_delete_assignment_override` | Delete an override (reverts to default dates) |

### Enrollments & sections

| Tool | Description |
|------|-------------|
| `canvas_list_enrollments` | Course roster, filterable by role and section |
| `canvas_list_sections` | Course sections with enrollment counts |

### Quizzes

| Tool | Description |
|------|-------------|
| `canvas_list_quizzes` | All quizzes in a course |
| `canvas_get_quiz` | Full quiz details (type, attempts, time limit, dates) |
| `canvas_create_quiz` | Create a quiz shell (add questions in Canvas UI) |
| `canvas_update_quiz` | Update quiz settings, dates, or publish status |

### Rubrics

| Tool | Description |
|------|-------------|
| `canvas_list_rubrics` | Rubrics available in a course with criteria breakdown |
| `canvas_create_rubric` | Create a rubric with criteria and rating scales |
| `canvas_associate_rubric` | Attach a rubric to an assignment for grading |

### Assignment groups

| Tool | Description |
|------|-------------|
| `canvas_list_assignment_groups` | Gradebook categories with weights and assignment counts |
| `canvas_create_assignment_group` | Create a new gradebook category |
| `canvas_update_assignment_group` | Update a group's name, weight, or position |
| `canvas_delete_assignment_group` | Delete a group (optionally move assignments first) |

### Late policy

| Tool | Description |
|------|-------------|
| `canvas_get_late_policy` | Current late/missing submission policy for a course |
| `canvas_update_late_policy` | Update late deductions, grade floors, and missing scores |

### Analytics

| Tool | Description |
|------|-------------|
| `canvas_get_course_analytics` | Per-student participation, page views, and tardiness |
| `canvas_get_student_analytics` | Per-assignment submission and score breakdown for a student |

### Files

| Tool | Description |
|------|-------------|
| `canvas_list_files` | Files uploaded to a course with download URLs |

---

## Example prompts

```
What courses am I enrolled in?

Show me upcoming assignments for course 12345.

Get the syllabus for my CS 101 course (ID 9988).

Create a page called "Week 5 Overview" in course 12345 with a brief intro.

Post an announcement to course 12345: "Midterm is next Thursday -- review chapters 4-7."

What's on my Canvas planner this week?

Grade student 789's submission for assignment 456 in course 123 with a score of 95.

Create an office hours event for course 12345 on Friday from 2-4pm.

Show me the class roster for course 12345.

Send a message to all students in section 678: "Don't forget to submit your project."
```

---

## Security

See [SECURITY.md](SECURITY.md) for the full security model. Key points:

- **Your Canvas session cookie is equivalent to your password** — never commit it or share it.
- The server **only communicates with your Canvas instance** — no other external requests.
- **HTTPS is enforced** — the server refuses to start with an `http://` URL.
- **Single-user design** — one server instance = one Canvas account. Do not expose
  the HTTP server to the public internet.
- Write operations require Teacher or TA enrollment; student accounts are read-only.
- The `X-CSRF-Token` is automatically extracted from your cookies for write requests.

## License

[MIT](LICENSE)
