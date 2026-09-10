# Flask-IP2Location

A small Flask extension that looks up each visitor's IP address with the
[IP2Location](https://pypi.org/project/IP2Location/) Python library and
stores the result in the Flask **session** — so any other view or template
in the app can reuse it without repeating the lookup.

## Installing

From PyPI, once published:

```bash
pip install flask-ip2location
```

From this source tree (editable install, for development):

```bash
pip install -e ".[dev]"
```

`IP2Location` and `Flask` are declared as dependencies in `pyproject.toml`
and install automatically either way.

## How it works

- On the first request in a session, a `before_request` hook resolves the
  visitor's IP against your local IP2Location `.BIN` database and stores
  the result under `session["ip2location"]`.
- On later requests, if the visitor's IP hasn't changed, the cached value
  is reused — no repeat database queries.
- Any view or Jinja template can read `session["ip2location"]` directly,
  or import the `current_location` proxy for convenience.

## Quick start

1. **Get a database file.** This extension requires a IP2Location database BIN file to work. You may obtain a free LITE database or purchase a commercial database as below:
   - Free, self-updating "LITE" editions: https://www.ip2location.com/database/lite
   - Full commercial editions with ISP/domain/etc: https://www.ip2location.com/database/ip2location

   Save the `.BIN` file somewhere your app can read it.

2. **Wire it up**

   ```python
   from flask import Flask
   from flask_ip2location import IP2LocationFlask, current_location

   app = Flask(__name__)
   app.config["SECRET_KEY"] = "change-me"
   app.config["IP2LOCATION_DB_PATH"] = "/path/to/IP2LOCATION-LITE-DB11.BIN"

   ip2loc = IP2LocationFlask(app)

   @app.route("/")
   def index():
       return current_location["country_long"]

   @app.route("/other-page")
   def other_page():
       # Same session, same data, no extra lookup:
       return current_location["city"]
   ```

   Or with the application-factory pattern:

   ```python
   ip2loc = IP2LocationFlask()

   def create_app():
       app = Flask(__name__)
       app.config["IP2LOCATION_DB_PATH"] = "..."
       ip2loc.init_app(app)
       return app
   ```

3. Try the full demo:

   ```bash
   pip install -e .
   # edit examples/example_app.py to point at your .BIN file
   python examples/example_app.py
   ```

## Reading the data elsewhere

Three equivalent ways to get the visitor's location in any view/template:

```python
from flask import session
session["ip2location"]              # plain dict, or None
```

```python
from flask_ip2location import current_location
current_location["country_long"]     # LocalProxy, behaves like the dict
```

```jinja2
{# register current_location as a Jinja global once, e.g.
   app.jinja_env.globals["current_location"] = current_location #}
{{ current_location.country_long }}
```

The stored value is a plain `dict` (or `None` if the lookup failed or was
skipped), so it's JSON-serializable for AJAX endpoints too.

## Configuration reference

| Config key | Default | Description |
|---|---|---|
| `IP2LOCATION_DB_PATH` | *required* | Path to the `.BIN` database file. |
| `IP2LOCATION_MODE` | `None` | Passed to the underlying `IP2Location.IP2Location()` constructor, e.g. `"SHARED_MEMORY"` to load the whole file into memory for faster lookups. |
| `IP2LOCATION_SESSION_KEY` | `"ip2location"` | Session dict key the result is stored under. |
| `IP2LOCATION_FIELDS` | `None` (auto) | Optional allow-list restricting which auto-detected fields are kept, e.g. `["country_long", "city"]`. By default every column your `.BIN` edition actually supports is kept automatically — see below. |
| `IP2LOCATION_AUTO_LOOKUP` | `True` | Automatically look up on every request via `before_request`. Set `False` and call `ip2loc.refresh()` yourself if you'd rather trigger it manually (e.g. only after login). |
| `IP2LOCATION_SKIP_PRIVATE_IPS` | `True` | Skip the database query entirely for loopback/private/reserved IPs (e.g. `127.0.0.1` during local dev), storing `None` instead of erroring. |
| `IP2LOCATION_TRUST_PROXY_HEADER` | `False` | Trust the client-supplied `X-Forwarded-For` header for the visitor IP. See the caveat below before turning this on. |

## Automatic column detection

You don't need to know which `.BIN` edition you're using or list its fields
by hand — the extension detects them from the query result itself. Every
possible IP2Location field (country, region, city, isp, asn, ...) is only
ever populated by the library when your specific database edition supports
it; unsupported fields never even get set on the result object. The
extension keeps exactly the fields that came back populated, so:

- A free `DB1` (country-only) LITE database gives you a session dict with
  just `ip`, `country_short`, `country_long`.
- A `DB11` LITE database additionally gives you `region`, `city`,
  `latitude`, `longitude`, `zipcode`, `timezone`.
- A commercial edition with ISP/ASN data gives you those too, automatically
  — nothing to configure, and nothing to update if you later upgrade your
  database edition.

If you want to keep only a subset regardless of what's available (e.g. to
keep the session cookie small, or for privacy), set `IP2LOCATION_FIELDS` to
an explicit list and it's applied as a filter on top of auto-detection.

## Notes and caveats

- **Proxies/load balancers.** If your app runs behind one, `request.remote_addr`
  will be the proxy's IP, not the visitor's. The correct fix is
  [`werkzeug.middleware.proxy_fix.ProxyFix`](https://werkzeug.palletsprojects.com/en/latest/middleware/proxy_fix/)
  configured for exactly as many trusted hops as you have, shown
  commented-out in `examples/example_app.py`. `IP2LOCATION_TRUST_PROXY_HEADER`
  is a blunter alternative that trusts whatever `X-Forwarded-For` value
  shows up, which a visitor can forge if nothing upstream is sanitizing it —
  only use it if you understand your deployment's proxy setup.
- **Session storage.** Flask's default session is a signed-but-not-encrypted
  cookie: don't store anything sensitive in it. City/country/ISP data is
  usually fine, but if you widen `IP2LOCATION_FIELDS` or have privacy
  requirements, consider pairing this with a server-side session backend
  like [Flask-Session](https://flask-session.readthedocs.io/).
- **LITE database fields.** Free LITE editions only populate the fields
  their tier covers (e.g. `DB1` is country-only). As described above, this
  is detected automatically per lookup rather than assumed from config.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

Tests monkeypatch `IP2Location.IP2Location` with a fake in `tests/conftest.py`,
so no real `.BIN` database file is needed to run the suite.

## License

See the LICENSE file.