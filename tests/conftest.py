import pytest
from flask import Flask

import flask_ip2location as fil


class FakeRecord:
    """Stands in for the object IP2Location.IP2Location.get_all() returns."""

    def __init__(self, ip):
        self.country_short = "US"
        self.country_long = "United States of America"
        self.region = "California"
        self.city = "Mountain View"
        self.latitude = 37.406
        self.longitude = -122.079
        self.zipcode = "94043"
        self.timezone = "-07:00"
        # Simulates a field the loaded DB edition doesn't support.
        self.isp = "This parameter is unavailable for selected data file."


class FakeDB:
    """Stands in for IP2Location.IP2Location so tests don't need a real .BIN file."""

    def __init__(self, path, mode=None):
        self.path = path
        self.mode = mode
        self.calls = 0

    def get_all(self, ip):
        self.calls += 1
        return FakeRecord(ip)


@pytest.fixture
def fake_db_class(monkeypatch):
    monkeypatch.setattr(fil.IP2Location, "IP2Location", FakeDB)
    return FakeDB


@pytest.fixture
def app(fake_db_class):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", IP2LOCATION_DB_PATH="/fake/path.BIN")
    ip2loc = fil.IP2LocationFlask(app)
    app.extensions["ip2location"]  # sanity: registered
    app.ip2loc = ip2loc  # convenience handle for tests
    return app
