from flask import Blueprint, render_template
from flaskr.auth import session_required


bp = Blueprint("plot", __name__, url_prefix="/plot")

@bp.route("/")
@session_required
def index():
    return render_template("plot/index.html")