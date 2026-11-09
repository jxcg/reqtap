# reqtap
Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response. It is intended to be a **dev** tool that developers can use to look at API contracts for debugging.

reqtap watches your application’s request timeline, without interfering and becoming a temporal criminal.

## Flask

Getting started on Flask is easy!

### Step 1
```sh
pip install reqtap[flask]
```

### Step 2
```python
from flask import Flask
from reqtap import ReqTap

app = Flask(__name__)
ReqTap(app, live_reqtap_requests=True)
```
---

Run your app as normal. Requests/responses are captured in memory only, precisely **nothing** is written to persistent storage.

`live_reqtap_requests` must be set to `True` for logging. Without this, reqtap does absolutely nothing.
**I would advise against enabling this in production :)**

### What gets hidden

Matched by name and swapped for `<redacted by reqtap>` before anything is stored.

| Where | Hidden | Kept |
| --- | --- | --- |
| Headers | `Authorization`, `Cookie`, `X-Api-Key` | `Accept` |
| Caller's IP headers | `X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `CF-Connecting-IP` | `X-Forwarded-Proto` |
| Query strings | `?token=`, `?client_secret=` | `?page=2` |
| JSON and form bodies, at any depth | `{"password":"..."}` | `{"item":"coffee"}` |

| Case | What is stored |
| --- | --- |
| Address of whatever connected | Nothing |
| JSON or form body that is malformed or over the preview limit | A marker, never part of the body |
| Secret under an ordinary name, in a plain-text body, or in the URL path | **The secret. Name matching can't catch these.** |

`redact_headers=["X-My-Header"]` hides more, on top of the automatic matches.

### Dashboard

Once active, reqtap mounts a dashboard at **`/_reqtap/`** (or the shorter **`/_rq/`**). Open it from the same machine to see captured requests newest first — time, method, path, status, duration. 4xx shows amber; 5xx and unhandled exceptions show red. Reload the page to see new requests.

The dashboard and API answer only when three things hold: the client is on this machine, the address you asked for is a local one (`localhost`, anything under `.localhost`, or any `127.x` / `::1` address, in any capitalisation and with or without a port), and the request was not started by another website. That last check matters because a website can point one of its own names at `127.0.0.1` and have your browser fetch the dashboard for it — the request looks local, but the name in it does not. Clicking a link to the dashboard still works; a script on another page reading it does not.

Responses are never cached, the dashboard never captures its own traffic, the page runs no JavaScript, and it is served with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'`, so captured data cannot be executed, exfiltrated, or loaded into a frame on someone else's page.

Do not publish the dashboard through a reverse proxy. A proxy on the same machine makes outside visitors look local, so they can get in.

For full headers, bodies and tracebacks, use the JSON API below.

### JSON API

A small JSON API sits alongside the dashboard under the same `/_reqtap` prefix. The dashboard renders server-side and does not use it, so these are yours to script against:

| Method   | Path                          | Description                                                                                     |
| -------- | ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET`    | `/_reqtap/api/requests`       | Captured requests as lightweight summaries, newest first. Pass `?since=<id>` to get only records newer than an id you already hold (incremental polling). |
| `GET`    | `/_reqtap/api/requests/<id>`  | Full detail for one captured request. `404` once it has been evicted from the ring buffer.      |
| `DELETE` | `/_reqtap/api/requests`       | Clear the buffer.                                                                                |

Responses are `application/json`. The buffer is in-memory and bounded (`buffer_size`, default 200), so old records are evicted as new ones arrive.

## FastAPI

TODO

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
