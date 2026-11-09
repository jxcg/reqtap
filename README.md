# reqtap
Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response. It is intended to be a **dev** tool that developers can use to look at API contracts for debugging.

reqtap watches your application’s request timeline, without interfering and becoming a temporal criminal.

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

Run your app, then open **`/_reqtap/`** from the same machine.

Requests are kept in memory only. Without `live_reqtap_requests=True`, reqtap does nothing. **Never enable it in production.**

## What gets hidden

| | Hidden | Kept |
| --- | --- | --- |
| Headers | `Authorization` | `Accept` |
| Caller's IP | `X-Forwarded-For` | `X-Forwarded-Proto` |
| Query strings | `?token=` | `?page=2` |
| JSON and form bodies | `{"password":"..."}` | `{"item":"coffee"}` |

reqtap goes by name, so a secret under an ordinary name is still stored. Use `redact_headers=["X-My-Header"]` to hide more headers.

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
