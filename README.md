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

Once active, reqtap mounts a dashboard at **`/_reqtap/`**. Open it in a browser to watch traffic live. reqtap never captures its own dashboard traffic.

### JSON API

The dashboard is a thin client over a small JSON API, all under the `/_reqtap` prefix. You can hit these directly (e.g. to script against captured traffic):

| Method   | Path                          | Description                                                                                     |
| -------- | ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `GET`    | `/_reqtap/api/requests`       | Captured requests as lightweight summaries, newest first. Pass `?since=<id>` to get only records newer than an id you already hold (incremental polling). |
| `GET`    | `/_reqtap/api/requests/<id>`  | Full detail for one captured request. `404` once it has been evicted from the ring buffer.      |
| `DELETE` | `/_reqtap/api/requests`       | Clear the buffer — the dashboard's "clear feed" action.                                          |

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