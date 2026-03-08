import os
import nmrglue as ng
import matplotlib.pyplot as plt
import io
import base64
import zipfile
import shutil

from flask import abort, Blueprint, current_app, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename


bp = Blueprint("nmr", __name__, url_prefix="/nmr")

@bp.route("/")
def index():
    sid = session.get("id")
    items = []
    
    if sid:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)
        if os.path.isdir(path):
            items = os.listdir(path)

    return render_template("nmr/index.html", id=sid, items=items)


def allowed_file(filename):
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


@bp.route("/uploads", methods=["POST"])
def uploads():
    sid = session.get("id")
    if not sid:
        return abort(403)

    file = request.files.get("file")

    if not file or file.filename == "":
        return "No file", 400

    elif not allowed_file(file.filename):
        return "File type not allowed", 400

    else:
        filename = secure_filename(file.filename)
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)

        if zipfile.is_zipfile(file):
            with zipfile.ZipFile(file) as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(path, member))
                    if not member_path.startswith(os.path.realpath(path) + os.sep):
                        return "Invalid zip contents", 400
                zf.extractall(path)

        return redirect(url_for("nmr.index"))


@bp.route("/action", methods=["POST"])
def action():
    sid = session.get("id")
    if not sid:
        return abort(403)

    items = []
    
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)

    if os.path.isdir(path):
        items = os.listdir(path)

    filename = request.form.get("filename")
    if filename:
        filename = secure_filename(filename)
    else:
        return "Missing filename", 400

    action_type = request.form.get("action")

    file_path = os.path.join(path, filename)

    if not os.path.isdir(file_path):
        return "Data not found", 404

    elif action_type == "download":
        return send_from_directory(path, filename)
    
    elif action_type == "delete":
        shutil.rmtree(file_path)
    
    elif action_type == "rename":
        new_name = request.form.get("new_name")
        if not new_name:
            return "Missing new filename", 400
        
        new_name = secure_filename(new_name)
        new_path = os.path.join(path, new_name)
        os.rename(file_path, new_path)
        return redirect(url_for("nmr.index"))
    
    elif action_type == "plot":
        dic, data = ng.bruker.read(file_path)                                                                                                                                                                                                    
        data = ng.bruker.remove_digital_filter(dic, data)

        udic = ng.bruker.guess_udic(dic, data)
        uc = ng.fileiobase.uc_from_udic(udic)


        fig, ax = plt.subplots()
        ms_scale = uc.ms_scale()

        ax.plot(ms_scale, data, "k-")
        ax.set_xlim(0, ms_scale[-1])
        ax.set_yticklabels([])
        ax.set_title(filename)
        ax.set_xlabel("Time (ms)")

        buffer = io.BytesIO()
        fig.savefig(buffer, format="svg")
        buffer.seek(0)
        svg_b64 = base64.b64encode(buffer.read()).decode("utf-8")

        plt.close(fig)

        return render_template("nmr/index.html", id=sid, items=items, fid=svg_b64, fid_name=filename)
    
    return redirect(url_for("nmr.index"))


@bp.route("/fid", methods=["POST"])
def fid():
    sid = session.get("id")
    if not sid:
        return abort(403)

    items = []
    
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], sid)
    if os.path.isdir(path):
        items = os.listdir(path)
    
    filename = request.form.get("filename")
    if filename:
        filename = secure_filename(filename)
    else:
        return "Missing filename", 400

    p0 = float(request.form.get("p0", 0.0))
    p1 = float(request.form.get("p1", 0.0))

    def form_float(key):
        val = request.form.get(key)
        return float(val) if val else None

    xmin = form_float("xmin")
    xmax = form_float("xmax")
    ymin = form_float("ymin")
    ymax = form_float("ymax")

    file_path = os.path.join(path, filename)

    dic, data = ng.bruker.read(file_path)                                                                                                                                                                                                    
    data = ng.bruker.remove_digital_filter(dic, data)

    udic = ng.bruker.guess_udic(dic, data)
    uc = ng.fileiobase.uc_from_udic(udic)

    data = ng.proc_base.fft(data)
    data = ng.proc_base.ps(data, p0=p0, p1=p1)
    data = ng.proc_base.di(data)
    data = ng.proc_base.rev(data)
    data = ng.proc_bl.baseline_corrector(data, wd=20)
    data = data / data.max()

    ppm_scale = uc.ppm_scale()

    fig, ax = plt.subplots()
    ax.plot(ppm_scale, data, "k-")

    threshold = form_float("threshold")
    show_peaks = bool(request.form.get("show_peaks")) 
    show_threshold = bool(request.form.get("show_threshold"))

    if threshold:
        if show_peaks:
            peaks = ng.peakpick.pick(data, pthres = threshold, algorithm="downward")
            for peak in peaks:
                height = data[int(peak["X_AXIS"])]
                ppm = uc.ppm(peak["X_AXIS"])
                ax.scatter(ppm, height + 0.1, marker="|", color="k")
                ax.text(ppm, height + 0.3, round(ppm, 2), ha="center", va="center", rotation=90)
        
            if show_threshold:
                ax.hlines(threshold, *uc.ppm_limits(), linestyle="--", color="b")

    if request.form.get("reset_integrals") == "reset_integrals":
        session.pop("integrals", None)

    if "integrals" not in session:
        session["integrals"] = []

    iname = request.form.get("iname")
    i0 = form_float("i0")
    i1 = form_float("i1")
    
    new_dict_item = {
        "peak": request.form.get("iname"),
        "start": form_float("i0"),
        "end": form_float("i1")
    }

    temp_list = session["integrals"]
    temp_list.append(new_dict_item)
    session["integrals"] = temp_list


    show_integrals = bool(request.form.get("show_integrals"))
    start, end = None, None

    if show_integrals:
        for item in session["integrals"]:
            start = item["start"]
            end = item["end"]

            if start is not None and end is not None:
                i0 = uc(start, unit="ppm")
                i1 = uc(end, unit="ppm")
                if i0 > i1:
                    i0, i1 = i1, i0

                i_data  = data[i0:i1 + 1]
                i_scale = ppm_scale[i0:i1 + 1]

                i_cumsum = i_data.cumsum()

                ax.plot(i_scale, i_cumsum / 20 + i_data.max() + 0.5, "g-")
                ax.plot(i_scale, [0] * len(i_scale), "r")
                ax.text(i_scale[0], i_cumsum[-1] / 20 + i_data.max() + 0.55, round(i_data.sum(), 2))
                ax.text(i_scale[0], i_cumsum[-1] / 20 + i_data.max() + 0.65, item["peak"])


    ax.set_ylim(ymin, ymax)
    ax.set_xlim(xmin, xmax)
    ax.invert_xaxis()
    ax.set_title(filename)
    ax.set_xlabel("1H ppm")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    buffer.seek(0)
    svg_b64 = base64.b64encode(buffer.read()).decode("utf-8")

    plt.close(fig)

    return render_template("nmr/index.html", 
    id=sid, items=items, 
    p0=p0, p1=p1, 
    plot=svg_b64, plt_name=filename, 
    xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, 
    i0=start, i1=end, integrals=session["integrals"], 
    threshold=threshold,
    show_peaks=show_peaks, show_threshold=show_threshold, show_integrals=show_integrals)

    