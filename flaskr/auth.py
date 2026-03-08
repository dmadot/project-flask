import os
import uuid
import shutil
from flask import Blueprint, current_app, request, redirect, session, url_for


bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.route("/open", methods=["POST"])
def open_session():
    if "id" not in session:
        session["id"] = str(uuid.uuid4())
        sid = session.get("id")
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)
        os.makedirs(path, exist_ok=True)
        return redirect(url_for("nmr.index"))


@bp.route("/close", methods=["POST"])
def close_session():
    sid = session.get("id")
    if sid:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)
        if os.path.isdir(path):
            shutil.rmtree(path)
    session.clear()
    return redirect(url_for("nmr.index"))