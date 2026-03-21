import os
import nmrglue as ng
import matplotlib.pyplot as plt
import io
import base64
import zipfile
import shutil
import json

from flask import abort, Blueprint, current_app, redirect, render_template, request, send_file, send_from_directory, session, url_for
from flaskr.auth import session_required
from werkzeug.utils import secure_filename
from pathlib import Path



bp = Blueprint("nmr", __name__, url_prefix="/nmr")


# Allow just Zipfiles.
def allowed_file(filename):
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# Build the plot and return to the figure.
def build_fig_time(filename):
    # Load the .settings.json for the current file.
    settings = settings_load(path_settings(filename))

    # Run the function to get the time domain from the nmr data set.
    data, ms_scale = load_time_domain(path_dataset(filename))

    # Open a figure to create the plot.
    fig, ax = plt.subplots()
    ax.plot(ms_scale, data, "k", lw=1)
    ax.set_title(filename)
    ax.set_xlabel("Time / ms")
    ax.set_xlim(settings["time"]["xmin"], settings["time"]["xmax"])
    ax.set_ylim(settings["time"]["ymin"], settings["time"]["ymax"])
    return fig

def build_fig_freq(filename):
    # Load the .settings.json for the current file.
    settings = settings_load(path_settings(filename))

    p0 = settings
    p1 = settings

    # Run the function to get the freq domain from the nmr data set.
    data, ppm_scale = load_freq_domain(file_path(), p0, p1)

    # Open a figure to create the plot.
    fig, ax = plt.subplots()
    ax.plot(ppm_scale, data, "k", lw=1)
    ax.invert_xaxis()
    ax.set_title(filename)
    ax.set_xlabel("1H / ppm")
    ax.set_xlim(settings["freq"]["xmin"], settings["freq"]["xmax"])
    ax.set_ylim(settings["freq"]["ymin"], settings["freq"]["ymax"])
    return True


# Return a float or None (float() dont work on None)
def form_float(key):
    val = request.form.get(key)
    return float(val) if val else None


# Proces the dataset and return the values for the plot.
def load_freq_domain(path, p0, p1):
    dic, data = ng.bruker.read(path)                                                                                                                                                                                                    
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
    return data, ppm_scale

def load_time_domain(path):
    dic, data = ng.bruker.read(path)                                                                                                                                                                                                    
    data = ng.bruker.remove_digital_filter(dic, data)

    udic = ng.bruker.guess_udic(dic, data)
    uc = ng.fileiobase.uc_from_udic(udic)

    data = data / data.max()

    ms_scale = uc.ms_scale()
    return data, ms_scale


# Path functions.
def path_dataset(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    file_path = os.path.join(path, filename)
    return os.path.join(file_path + "/.dataset")

def path_file(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    return os.path.join(path, filename)

def path_settings(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    file_path = os.path.join(path, filename)
    return os.path.join(file_path + "/.settings.json")


# Renders figure to buffer.
def render_svg(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    buffer.seek(0)
    return buffer


# Settings.
def settings_load(path):
    with open(path) as f:
        return json.load(f)

def settings_save(path, settings, route, key, value):
    settings[route][key] = value
    with open(path, "w") as f:
        json.dump(settings, f)


@bp.route("/")
@session_required
def index():
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    if os.path.isdir(path):
        items = os.listdir(path)

    return render_template("nmr/index.html", items=items)


@bp.route("/uploads", methods=["POST"])
@session_required
def uploads():
    file = request.files.get("file")

    if not file or file.filename == "":
        return "No file", 400

    elif not allowed_file(file.filename):
        return "File type not allowed", 400

    else:
        filename = Path(secure_filename(file.filename)).stem
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
        file_path = os.path.join(path, filename)
        os.makedirs(file_path)

        default_settings_path = os.path.join(current_app.root_path, "static", "default_settings.json")

        # Create the default settings for this dataset.
        with open(file_path + f"/.settings.json", "w") as f:
            json.dump(settings_load(default_settings_path), f)

        if zipfile.is_zipfile(file):
            with zipfile.ZipFile(file) as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(file_path, member))
                    if not member_path.startswith(os.path.realpath(file_path) + os.sep):
                        return "Invalid zip contents", 400
                zf.extractall(os.path.join(file_path + "/.dataset"))

        return redirect(url_for("nmr.index"))


@bp.route("/uploads/<filename>/delete")
@session_required
def delete(filename):
    path = path_file(filename)
    shutil.rmtree(path)
    return redirect(url_for("nmr.index"))


@bp.route("/time/<filename>", methods=["GET", "POST"])
@session_required
def time(filename):
    # Create the plot.
    fig = build_fig_time(filename)

    # Save the figure to a temporary buffer in RAM.
    svg_buffer = render_svg(fig)

    # Encode binary SVG data to a Base64 string for direct embedding in HTML.
    svg_b64 = base64.b64encode(svg_buffer.read()).decode("utf-8")

    # Close the figure to evoid memory leak.
    plt.close(fig)

    return render_template("nmr/time.html", figure=svg_b64, filename=filename)


@bp.route("/time/<filename>/axis", methods=["POST"])
@session_required
def time_axis(filename):
    path = path_settings(filename)
    settings = settings_load(path)

    for key in settings["time"].keys():
        settings_save(path, settings, "time", key, form_float(key))

    return redirect(url_for("nmr.time", filename=filename))


@bp.route("/time/<filename>/download")
@session_required
def time_download(filename):
    # Create the plot.
    fig = build_fig_time(filename)

    # Save the figure to a temporary buffer in RAM.
    svg_buffer = render_svg(fig)

    # Close the figure to avoid memory leak.
    plt.close(fig)

    return send_file(svg_buffer, mimetype="image/svg+xml", as_attachment=True, download_name=f"{filename}_time.svg")


@bp.route("/freq/<filename>", methods=["GET", "POST"])
@session_required
def freq(filename):
    # Create the plot.
    fig = build_fig_freq(filename)

    # Save the figure to a temporary buffer in RAM.
    svg_buffer = render_template(fig)

    # Encode binary SVG data to a Base64 string for direct embedding in HTML.
    svg_b64 = base64.b64encode(svg_buffer.read()).decode("utf-8")

    # Close the figure to evoid memory leak.
    plt.close(fig)

    return render_template("nmr/freq.html", plot=svg_b64, filename=filename)


@bp.route("/freq/<filename>/peaks")
@session_required
def peaks():
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

    return True


@bp.route("/freq/integrals", methods=["POST", "GET"])
@session_required
def integrals():
    if "integrals" not in session:
        session["integrals"] = []

    integral_name = request.form.get("integral_name")
    i0 = form_float("i0")
    i1 = form_float("i1")

    new_dict_item = {
        "number": "1",
        "integral_name": request.form.get("integral_name"),
        "start": form_float("i0"),
        "end": form_float("i1")
    }

    temp_list = session["integrals"]
    temp_list.append(new_dict_item)
    session["integrals"] = temp_list


    if request.form.get("reset_integrals") == "reset_integrals":
        session.pop("integrals", None)
    

    show_integrals = bool(request.form.get("show_integrals"))
    start, end = None, None

    if show_integrals:
        for integral in session["integrals"]:
            start = integral["i0"]
            end = integral["i1"]

            if start is not None and end is not None:
                i0 = uc(start, unit="ppm")
                i1 = uc(end, unit="ppm")
                if i0 > i1:
                    i0, i1 = i1, i0

                i_data  = data[i0:i1 + 1]
                i_scale = ppm_scale[i0:i1 + 1]

                i_cumsum = i_data.cumsum()

                ax.plot(i_scale, i_cumsum / 20 + i_data.max() + 0.5, "k")
                ax.text(i_scale[0], i_cumsum[-1] / 20 + i_data.max() + 0.55, round(i_data.sum(), 2))
                ax.text(i_scale[0], i_cumsum[-1] / 20 + i_data.max() + 0.65, integral["peak"])

    return redirect(url_for("nmr.freq"))


@bp.route("freq/integrals/reset")
@session_required
def integrals_reset():
    return True


@bp.route("/freq/download")
@session_required
def freq_download():
    return True
