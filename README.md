# reqtap

See what requests hit your app, how your code reacted, and what went out. A **dev** tool: never enable it in production.

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

Then open **`/_reqtap/`** on the same machine, or get JSON from **`/_reqtap/api/requests`**.

Anything named like a password, token or key is hidden, and so are callers' IP addresses.
