from flask import Flask, session
from IP2Location.database import IP2LocationRecord

import flask_ip2location as fil
from flask_ip2location import _record_to_dict


def test_record_to_dict_autodetects_only_populated_fields():
    # Simulate what a real DB1 (country-only) lookup leaves on the record:
    # only the fields that column position != 0 for get set as instance
    # attributes; everything else stays at the class-level "unavailable"
    # default and must NOT show up in the result.
    rec = IP2LocationRecord()
    rec.ip = "8.8.8.8"
    rec.country_short = "US"
    rec.country_long = "United States of America"

    data = _record_to_dict(rec)

    assert data == {
        "ip": "8.8.8.8",
        "country_short": "US",
        "country_long": "United States of America",
    }
    assert "city" not in data
    assert "isp" not in data
    assert "asn" not in data


def test_record_to_dict_detects_wider_column_set_automatically():
    # Simulate a higher-tier DB (e.g. DB11) that also populates
    # city/region/coords -- no config change needed to pick these up.
    rec = IP2LocationRecord()
    rec.ip = "8.8.8.8"
    rec.country_short = "US"
    rec.country_long = "United States of America"
    rec.region = "California"
    rec.city = "Mountain View"
    rec.latitude = "37.406"
    rec.longitude = "-122.079"

    data = _record_to_dict(rec)

    assert data["city"] == "Mountain View"
    assert data["region"] == "California"
    assert "isp" not in data  # still not set on this record -> still excluded


def test_record_to_dict_fields_allowlist_still_applies():
    rec = IP2LocationRecord()
    rec.ip = "8.8.8.8"
    rec.country_short = "US"
    rec.country_long = "United States of America"

    data = _record_to_dict(rec, fields=("country_long",))
    assert data == {"country_long": "United States of America"}


def test_record_to_dict_handles_none_result():
    # get_all() returns None when the IP isn't found in the file at all.
    assert _record_to_dict(None) is None


def test_missing_db_path_raises(fake_db_class):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    # No IP2LOCATION_DB_PATH set.
    try:
        fil.IP2LocationFlask(app)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "IP2LOCATION_DB_PATH" in str(exc)


def test_auto_lookup_caches_and_filters_unavailable_fields(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "8.8.8.8"}):
        app.preprocess_request()
        data = session["ip2location"]
        assert data["country_short"] == "US"
        assert data["city"] == "Mountain View"
        assert "isp" not in data  # filtered because DB marked it unavailable
        assert app.ip2loc.db.calls == 1


def test_cache_reused_when_ip_unchanged(app, client=None):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["ip2location"] = {"country_short": "US"}
        sess["_ip2location_ip"] = "8.8.8.8"

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "8.8.8.8"}):
        session.update({"ip2location": {"country_short": "US"}, "_ip2location_ip": "8.8.8.8"})
        calls_before = app.ip2loc.db.calls
        app.preprocess_request()
        assert app.ip2loc.db.calls == calls_before  # no new lookup


def test_ip_change_triggers_new_lookup(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "1.1.1.1"}):
        app.preprocess_request()
        assert app.ip2loc.db.calls == 1

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "2.2.2.2"}):
        session["_ip2location_ip"] = "1.1.1.1"
        session["ip2location"] = {"country_short": "US"}
        app.preprocess_request()
        assert app.ip2loc.db.calls == 2  # IP changed -> re-looked-up


def test_private_ip_is_skipped(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        calls_before = app.ip2loc.db.calls
        app.preprocess_request()
        assert session["ip2location"] is None
        assert app.ip2loc.db.calls == calls_before  # never hit the db


def test_current_location_proxy(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "1.2.3.4"}):
        app.preprocess_request()
        assert fil.current_location["country_long"] == "United States of America"


def test_manual_lookup_does_not_touch_session(app):
    with app.test_request_context("/"):
        result = app.ip2loc.lookup("1.1.1.1")
        assert result["city"] == "Mountain View"
        assert "ip2location" not in session


def test_disabling_auto_lookup(fake_db_class):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test",
        IP2LOCATION_DB_PATH="/fake/path.BIN",
        IP2LOCATION_AUTO_LOOKUP=False,
    )
    ip2loc = fil.IP2LocationFlask(app)

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "8.8.8.8"}):
        app.preprocess_request()
        assert "ip2location" not in session  # auto lookup was off

        data = ip2loc.refresh()  # manual trigger
        assert data["country_short"] == "US"
        assert session["ip2location"] == data
