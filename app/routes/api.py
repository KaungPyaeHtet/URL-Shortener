import secrets
import string
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, redirect, request
from playhouse.shortcuts import model_to_dict

from app.models import Event, Url, User

_ALPHABET = string.ascii_letters + string.digits
_MAX_COLLISION_RETRIES = 10


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


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/users")
def list_users():
    limit = _safe_limit(request.args.get("limit"))
    q = User.select().order_by(User.id).limit(limit)
    return jsonify([model_to_dict(u, recurse=False) for u in q])


@api_bp.route("/users/<int:user_id>")
def get_user(user_id: int):
    try:
        u = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)
    return jsonify(model_to_dict(u, recurse=False))


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
        now = datetime.now(timezone.utc)
        row = Url.create(
            user_id=user_id,
            short_code=_generate_short_code(),
            original_url=original_url,
            title=data.get("title", ""),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    except RuntimeError as e:
        return jsonify(error=str(e)), 503

    return jsonify(model_to_dict(row, recurse=False)), 201


@api_bp.route("/urls")
def list_urls():
    limit = _safe_limit(request.args.get("limit"))
    uid = request.args.get("user_id", type=int)
    if uid is not None:
        q = Url.select().where(Url.user_id == uid).order_by(Url.id).limit(limit)
    else:
        q = Url.select().order_by(Url.id).limit(limit)
    return jsonify([model_to_dict(row, recurse=False) for row in q])


@api_bp.route("/urls/<int:url_id>")
def get_url(url_id: int):
    try:
        row = Url.get_by_id(url_id)
    except Url.DoesNotExist:
        abort(404)
    return jsonify(model_to_dict(row, recurse=False))


@api_bp.route("/events")
def list_events():
    limit = _safe_limit(request.args.get("limit"))
    url_id = request.args.get("url_id", type=int)
    if url_id is not None:
        q = Event.select().where(Event.url_id == url_id).order_by(Event.id).limit(limit)
    else:
        q = Event.select().order_by(Event.id).limit(limit)
    return jsonify([model_to_dict(row, recurse=False) for row in q])


short_bp = Blueprint("short", __name__)


@short_bp.route("/s/<short_code>")
def redirect_short(short_code: str):
    # Guard against absurdly long codes (DoS via DB query)
    if len(short_code) > 32:
        abort(404)
    try:
        row = Url.get(Url.short_code == short_code.strip())
    except Url.DoesNotExist:
        abort(404)
    if not row.is_active:
        return jsonify(error="gone", reason="inactive"), 410
    # Safety: only redirect to http/https (defense-in-depth against bad seed data)
    if not _is_valid_url(row.original_url):
        abort(404)
    return redirect(row.original_url, code=302)
