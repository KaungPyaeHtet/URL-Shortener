import csv
import io
import json
import logging
import secrets
import string
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, redirect, request
from peewee import fn

from app.csv_parse import parse_dt
from app.database import db
from app.models import Event, Url, User

log = logging.getLogger(__name__)

_ALPHABET = string.ascii_letters + string.digits
_MAX_COLLISION_RETRIES = 10


def _dt_iso(dt) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat(sep="T", timespec="seconds")


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "created_at": _dt_iso(u.created_at),
    }


def url_dict(row: Url) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "short_code": row.short_code,
        "original_url": row.original_url,
        "title": row.title,
        "is_active": row.is_active,
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def event_dict(e: Event) -> dict:
    raw = e.details
    try:
        details_obj = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        details_obj = {"raw": raw}
    return {
        "id": e.id,
        "url_id": e.url_id,
        "user_id": e.user_id,
        "event_type": e.event_type,
        "timestamp": _dt_iso(e.timestamp),
        "details": details_obj,
    }


def _next_user_id() -> int:
    max_id = User.select(fn.MAX(User.id)).scalar()
    return (max_id or 0) + 1


def _next_url_id() -> int:
    max_id = Url.select(fn.MAX(Url.id)).scalar()
    return (max_id or 0) + 1


def _generate_short_code(length: int = 7) -> str:
    for _ in range(_MAX_COLLISION_RETRIES):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not Url.select().where(Url.short_code == code).exists():
            return code
    raise RuntimeError("Could not generate a unique short code — try again")


def _safe_limit(value, default: int = 100, maximum: int = 500) -> int:
    try:
        return min(max(1, int(value)), maximum)
    except (TypeError, ValueError):
        return default


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _redirect_response_for_short_code(short_code: str, *, log_name: str):
    """302 to original_url; 404 missing/invalid; 410 inactive. Used by /s/<code> and /urls/<code>/redirect."""
    code = short_code.strip()
    if len(code) > 32:
        abort(404)
    try:
        row = Url.get(Url.short_code == code)
    except Url.DoesNotExist:
        abort(404)
    if not row.is_active:
        log.warning("redirect_inactive", extra={"short_code": code, "url_id": row.id, "via": log_name})
        return jsonify(error="gone", reason="inactive"), 410
    if not _is_valid_url(row.original_url):
        abort(404)
    log.info(
        "redirect",
        extra={"short_code": code, "url_id": row.id, "destination": row.original_url, "via": log_name},
    )
    # The Unseen Observer: record every successful redirect as an event.
    # Use the URL owner's user_id since there is no authenticated user in a redirect.
    try:
        next_id = (Event.select(fn.MAX(Event.id)).scalar() or 0) + 1
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        Event.create(
            id=next_id,
            url_id=row.id,
            user_id=row.user_id,
            event_type="redirect",
            timestamp=now,
            details=json.dumps({"short_code": code, "destination": row.original_url}),
        )
    except Exception:
        pass  # never let event logging break the redirect
    return redirect(row.original_url, code=302)


# MLH automated tests expect /users, /urls, /events (no /api prefix).
api_bp = Blueprint("api", __name__)


# ── Users ──────────────────────────────────────────────────────────────────────


@api_bp.route("/users", methods=["GET"])
def list_users():
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page is not None or per_page is not None:
        p = page if page is not None else 1
        pp = per_page if per_page is not None else 10
        p = max(1, p)
        pp = min(max(1, pp), 500)
        offset = (p - 1) * pp
        q = (
            User.select()
            .order_by(User.id)
            .limit(pp)
            .offset(offset)
        )
        return jsonify([user_dict(u) for u in q])

    if request.args.get("limit") is not None:
        limit = _safe_limit(request.args.get("limit"))
        q = User.select().order_by(User.id).limit(limit)
    else:
        q = User.select().order_by(User.id)
    return jsonify([user_dict(u) for u in q])


@api_bp.route("/users/bulk", methods=["POST"])
def bulk_import_users():
    f = request.files.get("file") or request.files.get("users")
    if not f or not f.filename:
        return jsonify(error="validation_error", message="missing CSV file field 'file'"), 400

    text = f.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return jsonify(count=0, imported=0), 200

    batch = []
    for r in rows:
        batch.append(
            {
                "id": int(r["id"]),
                "username": r["username"],
                "email": r["email"],
                "created_at": parse_dt(r["created_at"]),
            }
        )

    with db.atomic():
        for i in range(0, len(batch), 200):
            chunk = batch[i : i + 200]
            User.insert_many(chunk).execute()

    n = len(batch)
    return jsonify(count=n, imported=n), 201


@api_bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_body", message="JSON object required"), 400

    username = data.get("username")
    email = data.get("email")

    if not isinstance(username, str) or not isinstance(email, str):
        return (
            jsonify(
                error="validation_error",
                errors={"username": "must be a string", "email": "must be a string"},
            ),
            422,
        )

    username = username.strip()
    email = email.strip()
    if not username or not email:
        return jsonify(error="validation_error", message="username and email required"), 400

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    u = User.create(id=_next_user_id(), username=username, email=email, created_at=now)
    return jsonify(user_dict(u)), 201


@api_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    try:
        u = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)
    return jsonify(user_dict(u))


@api_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id: int):
    try:
        u = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="invalid_body"), 400

    if "username" in data:
        v = data["username"]
        if not isinstance(v, str):
            return jsonify(error="validation_error", errors={"username": "must be a string"}), 422
        u.username = v.strip()
    if "email" in data:
        v = data["email"]
        if not isinstance(v, str):
            return jsonify(error="validation_error", errors={"email": "must be a string"}), 422
        u.email = v.strip()

    u.save()
    return jsonify(user_dict(u))


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id: int):
    try:
        u = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)
    u.delete_instance(recursive=True)
    return "", 204


# ── URLs ───────────────────────────────────────────────────────────────────────


@api_bp.route("/urls", methods=["GET"])
def list_urls():
    limit = _safe_limit(request.args.get("limit"))
    uid = request.args.get("user_id", type=int)
    is_active_param = request.args.get("is_active")

    q = Url.select().order_by(Url.id)

    if uid is not None:
        q = q.where(Url.user_id == uid)

    if is_active_param is not None:
        active = is_active_param.lower() in ("true", "1", "yes")
        q = q.where(Url.is_active == active)

    return jsonify([url_dict(row) for row in q.limit(limit)])


@api_bp.route("/urls", methods=["POST"])
def create_url():
    data = request.get_json(silent=True) or {}
    original_url = data.get("original_url", "").strip()

    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify(error="user_id must be an integer"), 400

    if not original_url:
        return jsonify(error="original_url is required"), 400
    if not _is_valid_url(original_url):
        return jsonify(error="original_url must be a valid http or https URL"), 400

    try:
        User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify(error="user not found"), 404

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row = Url.create(
            id=_next_url_id(),
            user_id=user_id,
            short_code=_generate_short_code(),
            original_url=original_url,
            title=(data.get("title") or "").strip(),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    except RuntimeError as e:
        log.error("short_code_generation_failed", extra={"error": str(e)})
        return jsonify(error=str(e)), 503

    log.info("url_created", extra={"url_id": row.id, "user_id": user_id, "short_code": row.short_code})
    return jsonify(url_dict(row)), 201


@api_bp.route("/urls/<string:short_code>/redirect", methods=["GET"])
def redirect_by_short_code(short_code: str):
    """MLH: GET /urls/<short_code>/redirect → 302 Location: original_url (allow_redirects: false)."""
    return _redirect_response_for_short_code(short_code, log_name="urls_redirect")


@api_bp.route("/urls/<int:url_id>", methods=["GET"])
def get_url(url_id: int):
    try:
        row = Url.get_by_id(url_id)
    except Url.DoesNotExist:
        abort(404)
    return jsonify(url_dict(row))


@api_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id: int):
    try:
        row = Url.get_by_id(url_id)
    except Url.DoesNotExist:
        abort(404)

    data = request.get_json(silent=True) or {}
    changed = False

    if "title" in data:
        row.title = str(data["title"])
        changed = True

    if "is_active" in data:
        row.is_active = bool(data["is_active"])
        changed = True

    if "original_url" in data:
        new_url = str(data["original_url"]).strip()
        if not _is_valid_url(new_url):
            return jsonify(error="original_url must be a valid http or https URL"), 400
        row.original_url = new_url
        changed = True

    if changed:
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row.save()

    return jsonify(url_dict(row))


@api_bp.route("/urls/<int:url_id>", methods=["DELETE"])
def delete_url(url_id: int):
    try:
        row = Url.get_by_id(url_id)
    except Url.DoesNotExist:
        abort(404)
    row.delete_instance()
    log.info("url_deleted", extra={"url_id": url_id})
    return jsonify(deleted=True, id=url_id)


# ── Events ─────────────────────────────────────────────────────────────────────


@api_bp.route("/events", methods=["GET"])
def list_events():
    limit = _safe_limit(request.args.get("limit"))
    url_id = request.args.get("url_id", type=int)
    user_id = request.args.get("user_id", type=int)
    event_type = request.args.get("event_type")

    q = Event.select()
    if url_id is not None:
        q = q.where(Event.url_id == url_id)
    if user_id is not None:
        q = q.where(Event.user_id == user_id)
    if event_type is not None:
        q = q.where(Event.event_type == event_type)
    q = q.order_by(Event.id).limit(limit)
    return jsonify([event_dict(row) for row in q])


@api_bp.route("/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type", "").strip()
    if not event_type:
        return jsonify(error="event_type is required"), 400

    try:
        url_id = int(data.get("url_id"))
    except (TypeError, ValueError):
        return jsonify(error="url_id must be an integer"), 400

    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify(error="user_id must be an integer"), 400

    try:
        Url.get_by_id(url_id)
    except Url.DoesNotExist:
        return jsonify(error="url not found"), 404

    try:
        User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify(error="user not found"), 404

    # The Fractured Vessel: details must be a JSON object, not a plain string or other type.
    details = data.get("details", {})
    if details is not None and not isinstance(details, dict):
        return jsonify(error="details must be a JSON object"), 400
    details = json.dumps(details or {})

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    next_id = (Event.select(fn.MAX(Event.id)).scalar() or 0) + 1
    row = Event.create(
        id=next_id,
        url_id=url_id,
        user_id=user_id,
        event_type=event_type,
        timestamp=now,
        details=details,
    )
    return jsonify(event_dict(row)), 201


# ── Redirect ───────────────────────────────────────────────────────────────────


short_bp = Blueprint("short", __name__)


@short_bp.route("/s/<short_code>")
def redirect_short(short_code: str):
    return _redirect_response_for_short_code(short_code, log_name="s_prefix")
