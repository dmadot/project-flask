import functools
import json
import os
import shutil
import uuid

import datetime as dt
from flask import abort, Blueprint, current_app, g, redirect, render_template, request, session, url_for
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
        # Check for expired sessions
        # TODO: Delete session during use?
        # TODO: Can you delete the timestamp.json?
        items = os.listdir(os.path.join(current_app.config["UPLOAD_FOLDER"]))
        for item in items:
            path_item = os.path.join(current_app.config["UPLOAD_FOLDER"], item)

            # Is the item a folder? If not listdir can crash
            if not os.path.isdir(path_item):
                continue

            # Check for valid timestamp file
            if ".timestamp.json" not in os.listdir(path_item):
                shutil.rmtree(path_item)
            else:
                # Get the timestamp
                with open(path_item + f"/.timestamp.json") as f:
                    time_then = json.load(f)
                    time_delta = dt.datetime.now(dt.timezone.utc).timestamp() - time_then["time"]

                # Delete the working space when the session is older then 12 h
                if time_delta > 43200:
                    shutil.rmtree(path_item)

        # Create the new working space
        # TODO: Check if the working space are created
        session["id"] = str(uuid.uuid4())
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], session["id"])
        os.makedirs(path, exist_ok=True)

        # Create a timestamp to close the session automatically
        # TODO: Check if the timestamp are created
        timestamp = {
            "time": dt.datetime.now(dt.timezone.utc).timestamp()
        }
        with open(path + f"/.timestamp.json", "w") as f:
            json.dump(timestamp, f)
    
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

    return redirect(url_for("main.index"))