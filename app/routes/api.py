from flask import Blueprint, abort, jsonify, redirect, request
from playhouse.shortcuts import model_to_dict

from app.models import Event, Url, User

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/users")
def list_users():
    limit = min(int(request.args.get("limit", 100)), 500)
    q = User.select().order_by(User.id).limit(limit)
    return jsonify([model_to_dict(u, recurse=False) for u in q])


@api_bp.route("/users/<int:user_id>")
def get_user(user_id: int):
    try:
        u = User.get_by_id(user_id)
    except User.DoesNotExist:
        abort(404)
    return jsonify(model_to_dict(u, recurse=False))


@api_bp.route("/urls")
def list_urls():
    limit = min(int(request.args.get("limit", 100)), 500)
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
    limit = min(int(request.args.get("limit", 100)), 500)
    q = Event.select().order_by(Event.id).limit(limit)
    url_id = request.args.get("url_id", type=int)
    if url_id is not None:
        q = (
            Event.select()
            .where(Event.url_id == url_id)
            .order_by(Event.id)
            .limit(limit)
        )
    return jsonify([model_to_dict(row, recurse=False) for row in q])


short_bp = Blueprint("short", __name__)


@short_bp.route("/s/<short_code>")
def redirect_short(short_code: str):
    try:
        row = Url.get(Url.short_code == short_code.strip())
    except Url.DoesNotExist:
        abort(404)
    if not row.is_active:
        return jsonify(error="gone", reason="inactive"), 410
    return redirect(row.original_url, code=302)
