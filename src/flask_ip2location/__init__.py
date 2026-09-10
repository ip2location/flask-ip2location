"""
Flask-IP2Location
~~~~~~~~~~~~~~~~~~

A small Flask extension that looks up a visitor's IP address using the
IP2Location Python library and stores the result in the Flask session,
so any view (or template) in the app can reuse it without repeating
the lookup.

Basic usage
-----------

    from flask import Flask
    from flask_ip2location import IP2LocationFlask, current_location

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-me"
    app.config["IP2LOCATION_DB_PATH"] = "IP2LOCATION-LITE-DB11.BIN"

    ip2loc = IP2LocationFlask(app)

    @app.route("/")
    def index():
        return current_location["country_long"]

The lookup runs once automatically before each request (via
``before_request``) and is cached in the session, so later views and
templates just read ``current_location`` or ``session["ip2location"]``
for free.
"""

import ipaddress
import logging

from flask import current_app, request, session
from werkzeug.local import LocalProxy

try:
    import IP2Location
except ImportError as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "Flask-IP2Location requires the 'IP2Location' package. "
        "Install it with: pip install IP2Location"
    ) from exc


__all__ = ["IP2LocationFlask", "current_location"]
# _record_to_dict is intentionally left out of __all__ (it's an internal
# helper) but is still importable directly for tests: from
# flask_ip2location import _record_to_dict
__version__ = "1.0.0"

log = logging.getLogger(__name__)

#: Marker string the IP2Location library returns for fields that the
#: loaded database edition doesn't support (e.g. asking for ISP on a
#: country-only LITE DB). Kept only as a defensive fallback — see
#: _record_to_dict for why it's normally not needed.
_UNAVAILABLE_MARKER = "This parameter is unavailable"


def _is_lookupable(ip):
    """False for loopback/private/reserved addresses, which will
    never have a meaningful entry in an IP2Location database (this is
    the common case in local development, where remote_addr is
    127.0.0.1)."""
    try:
        addr = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return False
    return not (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_unspecified
    )


def _record_to_dict(record, fields=None):
    """Build a plain dict from an IP2Location record, auto-detecting
    which columns the loaded .BIN database edition actually supports.

    IP2Location's IP2LocationRecord class defines every possible field
    (country, city, isp, asn, ...) as a class attribute defaulting to
    an "unavailable" placeholder string. Its lookup code then only
    ever *sets an instance attribute* for the columns your specific
    database edition contains — everything else is left to fall back
    to the class default. That means the record's own ``__dict__`` is
    already exactly the set of available columns for this database;
    there's no need to hardcode field names or guess the DB edition.

    ``fields``, if given, is an allow-list: only keys in it are kept
    (still restricted to whatever was actually available). Leave it
    as None to keep every auto-detected column.
    """
    if record is None:  # get_all() returns None for an unresolvable IP
        return None
    data = {
        key: value
        for key, value in vars(record).items()
        # Defensive: shouldn't trigger given the above, but guards
        # against a future library version setting the placeholder
        # as an instance attribute instead of leaving it at the class
        # default.
        if not (isinstance(value, str) and value.startswith(_UNAVAILABLE_MARKER))
    }
    if fields is not None:
        data = {key: value for key, value in data.items() if key in fields}
    return data


class IP2LocationFlask:
    """Flask extension that resolves the visitor's IP on each request
    (once per session, cached thereafter) and stores the result under
    ``session[app.config["IP2LOCATION_SESSION_KEY"]]``.

    Supports both direct-init and the application-factory pattern::

        ip2loc = IP2LocationFlask()
        ip2loc.init_app(app)

    Config keys (all optional except IP2LOCATION_DB_PATH):

    ============================ ==================================================
    IP2LOCATION_DB_PATH          Path to the .BIN database file. Required.
    IP2LOCATION_MODE             IP2Location access mode, e.g. "SHARED_MEMORY"
                                  to load the whole file into memory for speed.
                                  Default: library default (file I/O).
    IP2LOCATION_SESSION_KEY      Session dict key to store results under.
                                  Default: "ip2location".
    IP2LOCATION_FIELDS           Optional iterable restricting which
                                  auto-detected fields are kept, e.g.
                                  ["country_long", "city"]. Default: None,
                                  meaning every column the loaded database
                                  edition actually supports is kept —
                                  detected automatically per lookup, no
                                  need to know the DB edition in advance.
    IP2LOCATION_AUTO_LOOKUP      Run the lookup automatically via
                                  before_request. Default: True. Set False
                                  to call ip2loc.refresh() manually instead.
    IP2LOCATION_SKIP_PRIVATE_IPS Don't bother querying the DB for
                                  loopback/private/reserved IPs.
                                  Default: True.
    IP2LOCATION_TRUST_PROXY_HEADER
                                  Trust the client-supplied X-Forwarded-For
                                  header. Default: False — see
                                  get_client_ip() docstring before enabling.
    ============================ ==================================================
    """

    def __init__(self, app=None, db_path=None):
        self.db = None
        self.db_path = db_path
        self.session_key = "ip2location"
        self.fields = None  # None => auto-detect every available column
        self.auto_lookup = True
        self.skip_private_ips = True
        self.trust_proxy_header = False
        if app is not None:
            self.init_app(app, db_path)

    def init_app(self, app, db_path=None):
        db_path = db_path or app.config.get("IP2LOCATION_DB_PATH")
        if not db_path:
            raise RuntimeError(
                "IP2LOCATION_DB_PATH is not set. Point it at a .BIN "
                "database file downloaded from https://lite.ip2location.com "
                "(free LITE editions) or https://www.ip2location.com "
                "(commercial editions with more fields)."
            )

        mode = app.config.get("IP2LOCATION_MODE")  # e.g. "SHARED_MEMORY"
        self.db = (
            IP2Location.IP2Location(db_path, mode)
            if mode
            else IP2Location.IP2Location(db_path)
        )

        self.session_key = app.config.get("IP2LOCATION_SESSION_KEY", self.session_key)
        self.fields = app.config.get("IP2LOCATION_FIELDS", self.fields)
        self.auto_lookup = app.config.get("IP2LOCATION_AUTO_LOOKUP", self.auto_lookup)
        self.skip_private_ips = app.config.get(
            "IP2LOCATION_SKIP_PRIVATE_IPS", self.skip_private_ips
        )
        self.trust_proxy_header = app.config.get(
            "IP2LOCATION_TRUST_PROXY_HEADER", self.trust_proxy_header
        )

        app.extensions = getattr(app, "extensions", {})
        app.extensions["ip2location"] = self

        if self.auto_lookup:
            app.before_request(self._auto_lookup)

    # -- IP resolution -----------------------------------------------

    def get_client_ip(self):
        """Best-effort visitor IP for the current request.

        By default this trusts only ``request.remote_addr``, which is
        correct when Flask sees the real client socket directly. If
        your app sits behind a reverse proxy or load balancer,
        prefer wrapping your WSGI app with
        ``werkzeug.middleware.proxy_fix.ProxyFix`` so that
        ``remote_addr`` is already corrected for you, rather than
        turning on IP2LOCATION_TRUST_PROXY_HEADER — that setting
        trusts the client-supplied X-Forwarded-For header as-is,
        which a visitor can spoof unless something upstream of your
        app is already sanitizing/overwriting it.
        """
        if self.trust_proxy_header:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.remote_addr

    def lookup(self, ip):
        """Run a lookup for an arbitrary IP and return a dict, or
        None if it can't be resolved. Doesn't touch the session —
        use this for one-off/manual lookups, e.g. from an API route
        or a background job."""
        if self.skip_private_ips and not _is_lookupable(ip):
            return None
        try:
            record = self.db.get_all(ip)
        except Exception:
            log.warning("IP2Location lookup failed for %s", ip, exc_info=True)
            return None
        return _record_to_dict(record, self.fields)

    def refresh(self):
        """Force a fresh lookup for the current request's visitor and
        store it in the session, overwriting any cached value. Call
        this yourself if IP2LOCATION_AUTO_LOOKUP is False."""
        ip = self.get_client_ip()
        session[self.session_key] = self.lookup(ip)
        session[f"_{self.session_key}_ip"] = ip
        return session[self.session_key]

    # -- before_request hook ------------------------------------------

    def _auto_lookup(self):
        ip = self.get_client_ip()
        cached_ip = session.get(f"_{self.session_key}_ip")
        if cached_ip == ip and self.session_key in session:
            return  # already resolved this visitor's current IP
        session[self.session_key] = self.lookup(ip)
        session[f"_{self.session_key}_ip"] = ip


def _get_current_location():
    ext = current_app.extensions.get("ip2location")
    if ext is None:
        return None
    return session.get(ext.session_key)


#: Proxy for the current visitor's location dict, usable in views and
#: Jinja templates once the extension has run for the request, e.g.
#: ``current_location["country_long"]`` in Python, or
#: ``{{ current_location.country_long }}`` in Jinja. Evaluates to
#: None if no lookup has happened yet or it failed.
current_location = LocalProxy(_get_current_location)
