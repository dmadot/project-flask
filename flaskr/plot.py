from flask import Blueprint, render_template


bp = Blueprint("plot", __name__, url_prefix="/plot")

@bp.route("/")
def index():
    return render_template("plot/index.html")