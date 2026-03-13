# Security

## Authentication model

This MCP server authenticates to Canvas LMS using **browser session cookies** — the
same approach used by the AI Tutor browser extension. No Canvas developer API key or
OAuth2 registration is required.

**Your Canvas session cookie is equivalent to your password.** Anyone who possesses it
can perform any action your Canvas account is authorized to do, until the session expires.

### How cookies are obtained

1. **Automatic extraction** (default): The server uses
   [`browser-cookie3`](https://github.com/borisbabic/browser_cookie3) to read your
   Canvas session cookie from your browser's local cookie store. This requires the
   server to have filesystem access to your browser's cookie database.
2. **Manual override**: You can set the `CANVAS_COOKIE` environment variable with a
   cookie string copied from your browser DevTools.

### Cookie safety guidelines

- **Never commit cookies to version control.** The `.gitignore` excludes `.env`,
  `.env.*`, and `*.cookie` files, but always double-check before pushing.
- **Never share your cookie value** with anyone — treat it like a password.
- **Use HTTPS only.** The server enforces `https://` for `CANVAS_BASE_URL` and will
  refuse to start if an `http://` URL is provided.
- **Cookies expire.** Canvas sessions typically last days to weeks. When your session
  expires, log back into Canvas in your browser and restart the server.

## Single-user design

This server is designed for **single-user, local use** (e.g., Claude Desktop on your
own machine). It is **not suitable for multi-user or shared deployments**:

- A single session cookie is shared across all connected clients.
- There is no per-user authentication, isolation, or audit trail.
- All requests are made as the same Canvas account.

If you run the server in HTTP mode (`--http`), it binds to `127.0.0.1` (localhost only)
by default. **Do not expose it to the public internet** — anyone who can reach the
server can act as your Canvas account.

## What the server can access

- The server **only communicates with the Canvas instance** specified in
  `CANVAS_BASE_URL`. It makes no other external network requests.
- Write operations (create/update/delete) require your Canvas account to have
  Teacher or TA enrollment in the relevant course. Student accounts can only use
  read-only tools.
- The `X-CSRF-Token` is automatically extracted from your cookie string and sent with
  all write requests.

## Security measures

- **HTTPS enforced** at startup — cookies are never sent over cleartext.
- **Redirect following disabled** — prevents credential leakage to unintended hosts.
- **Input validation** via Pydantic — all IDs are positive integers, page URL slugs
  are checked for path traversal (`/`, `\`, `..`), dates are validated as ISO 8601.
- **Error messages sanitized** — Canvas API response bodies are never included in
  error output.
- **Log output sanitized** — no domain names, cookie values, or exception details are
  written to stderr.
- **Rate limit handling** — the server retries with exponential backoff on HTTP 429
  responses to avoid overwhelming the Canvas API.

## Reporting a vulnerability

If you discover a security issue, please open a GitHub issue or contact the maintainer
directly. Do not include sensitive information (cookies, tokens) in public reports.
