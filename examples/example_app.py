"""
Minimal example showing Flask-IP2Location in use.

Before running, from the project root:
1. pip install -e .
2. Download a free .BIN database from https://lite.ip2location.com
   (e.g. "IP2LOCATION-LITE-DB11.BIN" for country/region/city/coords)
   and update IP2LOCATION_DB_PATH below to point at it.
3. python examples/example_app.py, then visit http://127.0.0.1:5000/
"""
from flask import Flask, render_template_string

from flask_ip2location import IP2LocationFlask, current_location

app = Flask(__name__)
app.config.update(
    SECRET_KEY="dev-secret-change-me",
    IP2LOCATION_DB_PATH="IP2LOCATION-LITE-DB11.BIN",  # <-- point this at your .BIN file
)

# If you're behind a reverse proxy (nginx, a load balancer, etc.) so that
# request.remote_addr would otherwise be the proxy's own IP, uncomment:
#
# from werkzeug.middleware.proxy_fix import ProxyFix
# app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

ip2loc = IP2LocationFlask(app)

PAGE = """
<h1>{{ title }}</h1>
{% if current_location %}
  <p>Looked up once, reused on every page via the session:</p>
  <ul>
    {% for key, value in current_location.items() %}
      <li><b>{{ key }}</b>: {{ value }}</li>
    {% endfor %}
  </ul>
{% else %}
  <p>No location data available (private/local IP, or the lookup failed).</p>
{% endif %}
<p><a href="/">Home</a> &middot; <a href="/other-page">Other page</a></p>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, title="Home", current_location=current_location)


@app.route("/other-page")
def other_page():
    # Same visitor, same session -> same data, with no second lookup.
    return render_template_string(PAGE, title="Other page", current_location=current_location)


if __name__ == "__main__":
    app.run(debug=True)
