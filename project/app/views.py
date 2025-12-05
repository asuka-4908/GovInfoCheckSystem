from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from .db import query_all

bp = Blueprint("main", __name__)

@bp.get("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

@bp.get("/health")
def health():
    return jsonify({"status": "ok"})

@bp.get('/favicon.ico')
def favicon():
    try:
        return current_app.send_static_file('images/logo.png')
    except Exception:
        return jsonify({"status":"no-favicon"}), 204

@bp.get("/api/users")
@login_required
def api_users():
    data = query_all("select id, username, role_id, created_at from users order by id")
    return jsonify(data)
