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

Anything that looks like a password or a key is swapped for
`<redacted by reqtap>` before it is stored. That covers `Authorization`,
`Cookie`, `X-Api-Key`, `?token=`, `?client_secret=`, and anything else named
like them. reqtap goes by the name, so it also catches ones it has never seen
before, such as `X-Shopify-Access-Token`. Harmless names are kept as they are,
so `?page=2` still shows up. The caller's IP address is not stored at all.

Two things to watch:

- **What you send in the body is kept exactly as sent.** POST
  `{"password": "..."}` and that password is stored. reqtap only reads names,
  and the body isn't one.
- `redact_headers=["X-My-Header"]` hides that header **on top of** the ones
  above. It does not switch the rest off.

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
