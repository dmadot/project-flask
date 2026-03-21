import functools
import os
import shutil
import uuid

from flask import Blueprint, current_app, g, redirect, render_template, request, session, url_for
from urllib.parse import urlparse


bp = Blueprint("auth", __name__, url_prefix="/auth")

# checks if a user have a session
def session_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return render_template("auth/index.html")
        
        return view(**kwargs)
    
    return wrapped_view


# open a session to get access to the working space
# using uuid to create a unique session id (sid)
@bp.route("/open", methods=["POST"])
def open_session():
    if "id" not in session:
        session["id"] = str(uuid.uuid4())
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], session["id"])
        os.makedirs(path, exist_ok=True)
    
    # next should only redirect to internal paths
    next_page = request.args.get("next")
    if not next_page or urlparse(next_page).netloc != "":
        next_page = url_for("main.index")

    return redirect(next_page)


# storing sid in g.user
# store data during an application context
@bp.before_app_request
def load_session():
    sid = session.get("id")

    if sid is None:
        g.user = None
    else:
        g.user = sid


# close the session
# delete the workspace
@bp.route("/close", methods=["POST"])
def close_session():
    sid = session.get("id")
    if sid:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)
        if os.path.isdir(path):
            shutil.rmtree(path)
    session.clear()

    # next should only redirect to internal paths
    next_page = request.args.get("next")
    if not next_page or urlparse(next_page).netloc != "":
        next_page = url_for("main.index")
        
    return redirect(next_page)