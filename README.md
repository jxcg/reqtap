# reqtap

Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response. It is intended to be a **dev** tool that developers can use to look at API contracts for debugging.

> **Never turn reqtap on in production.** It keeps request and response bodies, headers and error details in memory, and records traffic from everyone who reaches your app.

## Flask

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

## What gets hidden

| Where | Hidden | Kept |
| --- | --- | --- |
| Headers | `Authorization` | `Accept` |
| Caller's IP | `X-Forwarded-For` | `X-Forwarded-Proto` |
| Query strings | `?token=` | `?page=2` |
| JSON and form bodies | `{"password":"..."}` | `{"item":"coffee"}` |

| Case | What is stored |
| --- | --- |
| Malformed or oversized JSON or form body | A marker, never part of the body |
| Secret under an ordinary name, in plain text, or in the URL path | **The secret** |

Use `redact_headers=["X-My-Header"]` to hide more headers.

## Dashboard

Open **`/_reqtap/`** or **`/_rq/`** to see captured requests, newest first.

It only answers on the same machine. Do not publish it through a reverse proxy.

## JSON API

| Method | Path | |
| --- | --- | --- |
| `GET` | `/_reqtap/api/requests` | List requests |
| `GET` | `/_reqtap/api/requests/<id>` | One request in full |
| `DELETE` | `/_reqtap/api/requests` | Clear them |

## Development

```sh
pip install -e ".[dev]"
ruff check . && mypy . && pytest
```
