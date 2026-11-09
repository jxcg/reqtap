# reqtap
Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response. It is intended to be a **dev** tool that developers can use to look at API contracts for debugging.

reqtap watches your application’s request timeline, without interfering and becoming a temporal criminal.

> **Never turn reqtap on in production.** It keeps request and response bodies, headers and error details in memory, and records traffic from everyone who reaches your app.

## Flask

reqtap supports Flask for now. FastAPI support is tracked in [#61](https://github.com/jxcg/reqtap/issues/61).

### Install

reqtap is not on PyPI yet, so install it from GitHub. Keep the quotes: some shells reject the brackets without them.

```sh
pip install "reqtap[flask] @ git+https://github.com/jxcg/reqtap"
```

### Turn it on

```python
from flask import Flask
from reqtap import ReqTap

app = Flask(__name__)
ReqTap(app, live_reqtap_requests=app.debug)
```

Run your app in debug mode (`flask run --debug`), make some requests, then open **`http://127.0.0.1:5000/_reqtap/`**.

reqtap does absolutely nothing unless `live_reqtap_requests` is exactly `True`. Using `app.debug` keeps it off whenever debug mode is off. A value like `1` or the text `"true"` does not turn it on.

Using an app factory? Create it first and attach it later:

```python
reqtap = ReqTap(live_reqtap_requests=True)

def create_app():
    app = Flask(__name__)
    reqtap.init_app(app)
    return app
```

### Options

| Option                 | Default  | What it does                                                                 |
| ---------------------- | -------- | ---------------------------------------------------------------------------- |
| `live_reqtap_requests` | `False`  | Turns reqtap on.                                                             |
| `buffer_size`          | `200`    | How many requests to keep. The oldest are dropped first.                     |
| `body_preview_bytes`   | `64_000` | How much of each request and response body to keep.                          |
| `redact_headers`       | `None`   | Extra header names to hide, in any capitalisation. Adds to the automatic list. |

### What gets recorded

The method, path, query string, headers, status, duration and any error details are recorded for every request, except requests to the dashboard itself. Bodies depend on what your app did with them, because reqtap never reads anything your app did not already read:

| Body                                                       | What is stored                               |
| ---------------------------------------------------------- | -------------------------------------------- |
| Request read with `request.get_data()`, `.json` or `.form` | The body, up to `body_preview_bytes`         |
| Request your handler never read                            | `<skipped: body not read by handler>`        |
| Request read directly from `request.stream`                | `<skipped: body consumed by handler>`        |
| File upload (`multipart/form-data`)                        | `<skipped: multipart upload>`                |
| Text or JSON response                                      | The body, up to `body_preview_bytes`         |
| Streamed response or `send_file`                           | `<skipped: streamed response>`               |
| Binary response                                            | `<skipped: binary response, N bytes>`        |

Header values are cut off at 1,024 characters.

Everything lives in memory and nothing is written to disk. It is lost when the app restarts, and each server process keeps its own separate list.

### What gets hidden

Values on headers and fields that look like passwords or keys are swapped for `<redacted by reqtap>` before they are stored. That covers `Authorization`, `Cookie`, `X-Api-Key`, `?token=`, `?client_secret=`, JSON bodies, and URL-encoded form bodies. JSON objects are redacted at every level, including objects inside arrays. Harmless fields are kept, so `?page=2` and `{"item":"coffee"}` remain useful while `{"password":"..."}` is masked.

Redaction goes by name. It is not a general secret scanner, so these can still be stored:

- a credential under an ordinary field name
- a credential in a plain-text body
- a credential in the URL path, such as `/reset/abc123`

If a body claims to be JSON or form data but is malformed or larger than `body_preview_bytes`, reqtap stores a marker instead of part of the body.

The address of whatever connected to your app is not stored. The headers a proxy or tunnel adds with the original caller's IP, such as `X-Forwarded-For`, `X-Real-IP`, `Forwarded` and `CF-Connecting-IP`, are hidden too. Other proxy headers, such as `X-Forwarded-Proto`, stay visible.

### Dashboard

Once on, reqtap adds a dashboard at **`/_reqtap/`** (or the shorter **`/_rq/`**). It shows captured requests newest first: time, method, path, status and duration. 4xx shows amber; 5xx and unhandled exceptions show red. Reload the page to see new requests.

For full headers, bodies and tracebacks, use the JSON API below.

The dashboard and API answer only when all three of these are true:

- The connection comes from this machine.
- The address you asked for is a local one: `localhost`, anything ending in `.localhost`, or any `127.x` or `::1` address.
- The request was not started by another website. Clicking a link to the dashboard still works; a script on another page reading it does not.

Responses are never cached, the page runs no JavaScript, and it cannot be loaded in a frame on someone else's page.

**Do not put the dashboard behind a proxy or tunnel on the same machine.** The connection then really does come from this machine, so if the proxy also sends a local address as the `Host` (the name the caller asked for), outside visitors are let in. Faked `X-Forwarded-*` headers alone do not get past these checks.

### JSON API

A small JSON API sits alongside the dashboard under the same `/_reqtap` prefix. The dashboard renders server-side and does not use it, so these are yours to script against:

| Method   | Path                          | Description                                                                                     |
| -------- | ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET`    | `/_reqtap/api/requests`       | Captured requests as short summaries, newest first. Pass `?since=<id>` to get only records newer than an id you already hold. |
| `GET`    | `/_reqtap/api/requests/<id>`  | Full detail for one captured request. `404` once it has been dropped from the buffer.           |
| `DELETE` | `/_reqtap/api/requests`       | Clear the buffer.                                                                               |

Responses are `application/json`.

## Development

```sh
pip install -e ".[dev]"
```

Before committing, run:

```sh
ruff check .
mypy .
pytest
```
