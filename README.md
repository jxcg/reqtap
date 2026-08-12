# reqtap
Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response. It is intended to be a **dev** tool that developers can use to look at API contracts for debugging.

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

### Dashboard

Once active, reqtap mounts a dashboard at **`/_reqtap/`** (or the shorter **`/_rq/`**). Open it from the same machine to see captured requests newest first — time, method, path, status, duration. 4xx shows amber; 5xx and unhandled exceptions show red. Reload the page to see new requests.

The dashboard and API only accept loopback clients, never cache their responses, and never capture their own traffic. The page runs no JavaScript and is served with `Content-Security-Policy: default-src 'none'`, so captured data cannot be executed or exfiltrated by anything that reaches it. Do not publish the dashboard through a reverse proxy: proxied clients may appear to reqtap as the proxy's loopback address.

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
