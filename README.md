# reqtap
Req(uest) tap is a tool that lets you tap into your app's traffic, allowing you to see what requests were made, how your code reacted, and what was sent out as the response.

## Flask

Getting started on Flask is easy!

```sh
pip install reqtap[flask]
```

```python
from flask import Flask
from reqtap import ReqTap

app = Flask(__name__)
ReqTap(app, live_reqtap_requests=True)
```

Run your app as normal (e.g. `flask run`). Requests/responses are captured in memory only, precisely **nothing** is written to persistent storage.

`live_reqtap_requests` must be explicitly `True`; without it, reqtap does nothing. **I would advise against enabling this in production :)**


## FastAPI

TODO