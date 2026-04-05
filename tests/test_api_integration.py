"""Integration tests: real Flask client, real PostgreSQL.

All tests use fixtures from conftest.py (session-scoped DB with seeded test data).
Tests that create rows clean up after themselves so they don't pollute other tests.
"""

from tests.conftest import TEST_EVENT_ID, TEST_SHORT_CODE, TEST_URL_ID, TEST_USER_ID

# ── Health ─────────────────────────────────────────────────────────────────────


def test_health_ok(client):
    rv = client.get("/health")
    assert rv.status_code == 200
    assert rv.get_json() == {"status": "ok"}


def test_index_lists_endpoints(client):
    rv = client.get("/")
    assert rv.status_code == 200
    data = rv.get_json()
    assert "endpoints" in data


# ── 404 / error handling ───────────────────────────────────────────────────────


def test_unknown_route_returns_404(client):
    rv = client.get("/does-not-exist")
    assert rv.status_code == 404
    assert rv.get_json()["error"] == "not_found"


# ── Users — GET ────────────────────────────────────────────────────────────────


def test_list_users_returns_list(client):
    rv = client.get("/users")
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_list_users_limit(client):
    rv = client.get("/users?limit=1")
    assert rv.status_code == 200
    assert len(rv.get_json()) <= 1


def test_list_users_bad_limit_uses_default(client):
    """?limit=abc must not crash — returns default 100 rows (or all if fewer)."""
    rv = client.get("/users?limit=abc")
    assert rv.status_code == 200


def test_list_users_pagination(client):
    rv = client.get("/users?page=1&per_page=1")
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_get_user_by_id(client):
    rv = client.get(f"/users/{TEST_USER_ID}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["id"] == TEST_USER_ID
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"


def test_get_user_not_found(client):
    rv = client.get("/users/99999999")
    assert rv.status_code == 404


# ── Users — POST ───────────────────────────────────────────────────────────────


def test_create_user(client):
    rv = client.post("/users", json={"username": "newuser", "email": "new@example.com"})
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["username"] == "newuser"
    assert data["email"] == "new@example.com"
    assert "id" in data
    # Verify in DB then clean up
    from app.models import User
    User.delete().where(User.id == data["id"]).execute()


def test_create_user_missing_fields(client):
    rv = client.post("/users", json={"username": "only-name"})
    assert rv.status_code in (400, 422)


def test_create_user_no_body(client):
    rv = client.post("/users", data="not-json", content_type="text/plain")
    assert rv.status_code == 400


# ── Users — PUT ────────────────────────────────────────────────────────────────


def test_update_user(client):
    rv = client.put(f"/users/{TEST_USER_ID}", json={"username": "updated_name"})
    assert rv.status_code == 200
    assert rv.get_json()["username"] == "updated_name"
    # Reset
    client.put(f"/users/{TEST_USER_ID}", json={"username": "testuser"})


def test_update_user_not_found(client):
    rv = client.put("/users/99999999", json={"username": "ghost"})
    assert rv.status_code == 404


# ── URLs — GET ─────────────────────────────────────────────────────────────────


def test_list_urls_returns_list(client):
    rv = client.get("/urls")
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_list_urls_filter_by_user(client):
    rv = client.get(f"/urls?user_id={TEST_USER_ID}")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert isinstance(rows, list)
    assert all(r["user_id"] == TEST_USER_ID for r in rows)


def test_list_urls_filter_active(client):
    rv = client.get("/urls?is_active=true")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert all(r["is_active"] is True for r in rows)


def test_list_urls_filter_inactive(client):
    rv = client.get("/urls?is_active=false")
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_get_url_by_id(client):
    rv = client.get(f"/urls/{TEST_URL_ID}")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["id"] == TEST_URL_ID
    assert data["short_code"] == TEST_SHORT_CODE


def test_get_url_not_found(client):
    rv = client.get("/urls/99999999")
    assert rv.status_code == 404


# ── URLs — POST ────────────────────────────────────────────────────────────────


def test_create_url_success(client):
    """POST /urls creates a row in the DB and returns short_code."""
    rv = client.post("/urls", json={
        "user_id": TEST_USER_ID,
        "original_url": "https://example.com/integration-test",
        "title": "Integration Test",
    })
    assert rv.status_code == 201
    data = rv.get_json()
    assert "short_code" in data
    assert len(data["short_code"]) == 7
    assert data["original_url"] == "https://example.com/integration-test"
    assert data["is_active"] is True

    # Verify the row exists in the DB
    from app.models import Url
    url = Url.get_by_id(data["id"])
    assert url.short_code == data["short_code"]
    url.delete_instance()  # cleanup


def test_create_url_missing_original_url(client):
    rv = client.post("/urls", json={"user_id": TEST_USER_ID, "title": "No URL"})
    assert rv.status_code == 400
    assert "original_url" in rv.get_json()["error"]


def test_create_url_invalid_scheme(client):
    rv = client.post("/urls", json={
        "user_id": TEST_USER_ID,
        "original_url": "ftp://not-http.com/file",
    })
    assert rv.status_code == 400


def test_create_url_javascript_scheme_rejected(client):
    """Open-redirect attack via javascript: scheme must be blocked."""
    rv = client.post("/urls", json={
        "user_id": TEST_USER_ID,
        "original_url": "javascript:alert(1)",
    })
    assert rv.status_code == 400


def test_create_url_user_not_found(client):
    rv = client.post("/urls", json={
        "user_id": 99999999,
        "original_url": "https://example.com",
    })
    assert rv.status_code == 404


def test_create_url_bad_user_id(client):
    rv = client.post("/urls", json={
        "user_id": "not-an-int",
        "original_url": "https://example.com",
    })
    assert rv.status_code == 400


# ── URLs — PUT ─────────────────────────────────────────────────────────────────


def test_update_url_title(client):
    rv = client.put(f"/urls/{TEST_URL_ID}", json={"title": "Updated Title"})
    assert rv.status_code == 200
    assert rv.get_json()["title"] == "Updated Title"
    # Reset
    client.put(f"/urls/{TEST_URL_ID}", json={"title": "Test URL"})


def test_deactivate_url(client):
    rv = client.put(f"/urls/{TEST_URL_ID}", json={"is_active": False})
    assert rv.status_code == 200
    assert rv.get_json()["is_active"] is False
    # Reactivate so other tests aren't affected
    client.put(f"/urls/{TEST_URL_ID}", json={"is_active": True})


def test_update_url_invalid_original_url(client):
    rv = client.put(f"/urls/{TEST_URL_ID}", json={"original_url": "not-a-url"})
    assert rv.status_code == 400


def test_update_url_not_found(client):
    rv = client.put("/urls/99999999", json={"title": "Ghost"})
    assert rv.status_code == 404


# ── URLs — DELETE ──────────────────────────────────────────────────────────────


def test_delete_url(client):
    """Create a URL, delete it, verify it's gone from the DB."""
    create_rv = client.post("/urls", json={
        "user_id": TEST_USER_ID,
        "original_url": "https://example.com/to-be-deleted",
        "title": "Delete Me",
    })
    assert create_rv.status_code == 201
    url_id = create_rv.get_json()["id"]

    delete_rv = client.delete(f"/urls/{url_id}")
    assert delete_rv.status_code == 200

    # Confirm it's gone
    get_rv = client.get(f"/urls/{url_id}")
    assert get_rv.status_code == 404


def test_delete_url_not_found(client):
    rv = client.delete("/urls/99999999")
    assert rv.status_code == 404


# ── Events — GET ───────────────────────────────────────────────────────────────


def test_list_events_returns_list(client):
    rv = client.get("/events")
    assert rv.status_code == 200
    assert isinstance(rv.get_json(), list)


def test_list_events_has_expected_fields(client):
    rv = client.get(f"/events?url_id={TEST_URL_ID}")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert len(rows) > 0
    row = rows[0]
    for field in ("id", "url_id", "user_id", "event_type", "timestamp", "details"):
        assert field in row, f"missing field: {field}"


def test_list_events_filter_by_url(client):
    rv = client.get(f"/events?url_id={TEST_URL_ID}")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert isinstance(rows, list)
    assert any(r["id"] == TEST_EVENT_ID for r in rows)
    assert all(r["url_id"] == TEST_URL_ID for r in rows)


def test_list_events_filter_by_user(client):
    rv = client.get(f"/events?user_id={TEST_USER_ID}")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert isinstance(rows, list)
    assert any(r["id"] == TEST_EVENT_ID for r in rows)
    assert all(r["user_id"] == TEST_USER_ID for r in rows)


def test_list_events_filter_by_event_type(client):
    rv = client.get("/events?event_type=click")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert isinstance(rows, list)
    assert any(r["id"] == TEST_EVENT_ID for r in rows)
    assert all(r["event_type"] == "click" for r in rows)


def test_list_events_filter_unknown_url(client):
    rv = client.get("/events?url_id=99999999")
    assert rv.status_code == 200
    assert rv.get_json() == []


def test_list_events_filter_unknown_user(client):
    rv = client.get("/events?user_id=99999999")
    assert rv.status_code == 200
    assert rv.get_json() == []


def test_list_events_filter_unknown_event_type(client):
    rv = client.get("/events?event_type=nonexistent_type")
    assert rv.status_code == 200
    assert rv.get_json() == []


def test_list_events_combined_filters(client):
    """url_id + event_type combined must AND the filters."""
    rv = client.get(f"/events?url_id={TEST_URL_ID}&event_type=click")
    assert rv.status_code == 200
    rows = rv.get_json()
    assert all(r["url_id"] == TEST_URL_ID and r["event_type"] == "click" for r in rows)


def test_list_events_limit(client):
    rv = client.get("/events?limit=1")
    assert rv.status_code == 200
    assert len(rv.get_json()) <= 1


# ── Events — POST ──────────────────────────────────────────────────────────────


def test_create_event_success(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "url_id": TEST_URL_ID,
        "user_id": TEST_USER_ID,
        "details": {"referrer": "https://google.com"},
    })
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["event_type"] == "click"
    assert data["url_id"] == TEST_URL_ID
    assert data["user_id"] == TEST_USER_ID
    assert data["details"] == {"referrer": "https://google.com"}
    assert "id" in data
    assert "timestamp" in data
    # cleanup
    from app.models import Event
    Event.delete().where(Event.id == data["id"]).execute()


def test_create_event_missing_event_type(client):
    rv = client.post("/events", json={
        "url_id": TEST_URL_ID,
        "user_id": TEST_USER_ID,
    })
    assert rv.status_code == 400


def test_create_event_missing_url_id(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "user_id": TEST_USER_ID,
    })
    assert rv.status_code == 400


def test_create_event_missing_user_id(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "url_id": TEST_URL_ID,
    })
    assert rv.status_code == 400


def test_create_event_url_not_found(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "url_id": 99999999,
        "user_id": TEST_USER_ID,
    })
    assert rv.status_code == 404


def test_create_event_user_not_found(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "url_id": TEST_URL_ID,
        "user_id": 99999999,
    })
    assert rv.status_code == 404


def test_create_event_bad_url_id(client):
    rv = client.post("/events", json={
        "event_type": "click",
        "url_id": "not-an-int",
        "user_id": TEST_USER_ID,
    })
    assert rv.status_code == 400


def test_create_event_details_as_string_rejected(client):
    """details must be a JSON object — a plain string is rejected (The Fractured Vessel)."""
    rv = client.post("/events", json={
        "event_type": "view",
        "url_id": TEST_URL_ID,
        "user_id": TEST_USER_ID,
        "details": '{"source": "email"}',
    })
    assert rv.status_code == 400


def test_create_event_details_as_array_rejected(client):
    """details must be a JSON object — an array is rejected."""
    rv = client.post("/events", json={
        "event_type": "view",
        "url_id": TEST_URL_ID,
        "user_id": TEST_USER_ID,
        "details": ["a", "b"],
    })
    assert rv.status_code == 400


def test_create_event_without_details(client):
    """details is optional — should default to empty object."""
    rv = client.post("/events", json={
        "event_type": "view",
        "url_id": TEST_URL_ID,
        "user_id": TEST_USER_ID,
    })
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["details"] is not None
    from app.models import Event
    Event.delete().where(Event.id == data["id"]).execute()


# ── Redirect ───────────────────────────────────────────────────────────────────


def test_redirect_follows_short_code(client):
    rv = client.get(f"/s/{TEST_SHORT_CODE}")
    # Flask test client doesn't follow redirects by default
    assert rv.status_code == 302
    assert "example.com" in rv.headers["Location"]


def test_redirect_urls_path_mlh(client):
    """MLH automated test: GET /urls/<short_code>/redirect (not only /s/<code>)."""
    rv = client.get(f"/urls/{TEST_SHORT_CODE}/redirect")
    assert rv.status_code == 302
    assert "example.com" in rv.headers["Location"]


def test_redirect_inactive_url_returns_410(client):
    """Deactivate a URL, confirm redirect returns 410 Gone."""
    client.put(f"/urls/{TEST_URL_ID}", json={"is_active": False})
    rv = client.get(f"/s/{TEST_SHORT_CODE}")
    assert rv.status_code == 410
    assert rv.get_json()["error"] == "gone"
    # Reactivate
    client.put(f"/urls/{TEST_URL_ID}", json={"is_active": True})


def test_redirect_unknown_code_returns_404(client):
    rv = client.get("/s/doesnotexist")
    assert rv.status_code == 404


def test_redirect_too_long_code_returns_404(client):
    """Short codes longer than 32 chars are rejected immediately (DoS guard)."""
    rv = client.get("/s/" + "x" * 33)
    assert rv.status_code == 404


def test_redirect_creates_event(client):
    """The Unseen Observer: every successful redirect auto-creates a 'redirect' event."""
    from app.models import Event

    before = Event.select().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).count()

    client.get(f"/s/{TEST_SHORT_CODE}")

    after = Event.select().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).count()
    assert after == before + 1

    # cleanup
    Event.delete().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).execute()


def test_redirect_via_urls_path_creates_event(client):
    """The Unseen Observer: /urls/<code>/redirect also auto-creates a redirect event."""
    from app.models import Event

    before = Event.select().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).count()

    client.get(f"/urls/{TEST_SHORT_CODE}/redirect")

    after = Event.select().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).count()
    assert after == before + 1

    Event.delete().where(
        Event.url_id == TEST_URL_ID,
        Event.event_type == "redirect",
    ).execute()


def test_redirect_inactive_creates_no_event(client):
    """The Slumbering Guide: inactive URL redirect (410) must NOT create an event."""
    from app.models import Event

    client.put(f"/urls/{TEST_URL_ID}", json={"is_active": False})
    before = Event.select().where(Event.url_id == TEST_URL_ID).count()

    rv = client.get(f"/s/{TEST_SHORT_CODE}")
    assert rv.status_code == 410

    after = Event.select().where(Event.url_id == TEST_URL_ID).count()
    assert after == before, "Inactive redirect must not create an event"

    client.put(f"/urls/{TEST_URL_ID}", json={"is_active": True})
