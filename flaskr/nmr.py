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
def build_fig_freq(filename):
    # Load the .settings.json for the current file.
    path = path_settings(filename)
    settings = settings_load(path)
    p0 = settings["freq_phase"]["p0"]
    p1 = settings["freq_phase"]["p1"]

    # Run the function to get the freq domain from the nmr data set.
    data, ppm_scale, uc = load_freq_domain(path_dataset(filename), p0, p1)

    # Open a figure to create the plot.
    fig, ax = plt.subplots()
    ax.plot(ppm_scale, data, "k", lw=1)
    ax.set_title(filename)
    ax.set_xlabel("1H / ppm")
    ax.set_xlim(settings["freq_axis"]["xmin"], settings["freq_axis"]["xmax"])
    ax.set_ylim(settings["freq_axis"]["ymin"], settings["freq_axis"]["ymax"])
    ax.invert_xaxis()

    # Plot the peaks.
    for peak in settings["freq_peaks"]:
        ppm = peak["ppm"]
        height = peak["height"]
        ax.scatter(ppm, height + 0.1, marker="|", color="k")
        ax.text(ppm, height + 0.3, round(ppm, 2), ha="center", va="center", rotation=90)

    # Plot the integrals.
    for integral in settings["freq_integrals"]:
        start = integral["start"]
        end = integral["end"]
        area = round(integral["area"], 2)

        i0 = uc(start, "ppm")
        i1 = uc(end, "ppm")

        if i0 > i1:
            i0, i1 = i1, i0
    
        i_data  = data[i0:i1 + 1]
        i_scale = ppm_scale[i0:i1 + 1]

        i_cumsum = i_data.cumsum()

        ax.plot(i_scale, i_cumsum / 20 + i_data.max() + 0.5, "k", lw=1)
        ax.text(i_scale[0], i_cumsum[-1] / 20 + i_data.max() + 0.55, area)
  
    if settings["freq_threshold"]["bool"]:
        ax.hlines(settings["freq_threshold"]["value"], *uc.ppm_limits(), linestyle="--", color="k", lw=1)

    return fig

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
    ax.set_xlim(settings["time_axis"]["xmin"], settings["time_axis"]["xmax"])
    ax.set_ylim(settings["time_axis"]["ymin"], settings["time_axis"]["ymax"])
    return fig


# Return a float or None/0 (float() dont work on None)
def form_float(key):
    val = request.form.get(key)
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        abort(400, "Invalid number")

def form_zero(key):
    val = request.form.get(key)
    if not val:
        return int(0)
    try:
        return float(val)
    except ValueError:
        abort(400, "Invalid number")


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
    return data, ppm_scale, uc

def load_time_domain(path):
    dic, data = ng.bruker.read(path)                                                                                                                                                                                                    
    data = ng.bruker.remove_digital_filter(dic, data)

    udic = ng.bruker.guess_udic(dic, data)
    uc = ng.fileiobase.uc_from_udic(udic)

    data = data / data.max()

    ms_scale = uc.ms_scale()
    return data, ms_scale


# Path functions.
def path(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    if not os.path.isdir(path):
        abort(400, "Path not found")
    if filename not in os.listdir(path):
        abort(400, "Path not found")
    return os.path.join(path, filename)

def path_dataset(filename):
    return os.path.join(path(filename), ".dataset")

def path_settings(filename):
    return os.path.join(path(filename), ".settings.json")


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
        json.dump(settings, f, indent=4)



@bp.route("/")
@session_required
def index():
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    if not os.path.isdir(path):
        abort(400, "Path not found")
    else:
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
        
        if not filename:
            abort(400, "Invalid filename")

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


@bp.route("/uploads/<filename>/delete", methods=["POST"])
@session_required
def delete(filename):
    shutil.rmtree(path(filename))
    return redirect(url_for("nmr.index"))


@bp.route("/time/<filename>")
@session_required
def time(filename):
    fig = build_fig_time(filename)
    svg_buffer = render_svg(fig)
    svg_b64 = base64.b64encode(svg_buffer.read()).decode("utf-8")
    plt.close(fig)

    settings = settings_load(path_settings(filename))
    return render_template("nmr/time.html", figure=svg_b64, filename=filename, settings=settings)


@bp.route("/time/<filename>/axis", methods=["POST"])
@session_required
def time_axis(filename):
    path = path_settings(filename)
    settings = settings_load(path)

    for key in settings["time_axis"].keys():
        settings_save(path, settings, "time_axis", key, form_float(key))

    return redirect(url_for("nmr.time", filename=filename))


@bp.route("/time/<filename>/download")
@session_required
def time_download(filename):
    fig = build_fig_time(filename)
    svg_buffer = render_svg(fig)
    plt.close(fig)

    return send_file(svg_buffer, mimetype="image/svg+xml", as_attachment=True, download_name=f"{filename}_time.svg")


@bp.route("/freq/<filename>")
@session_required
def freq(filename):
    fig = build_fig_freq(filename)
    svg_buffer = render_svg(fig)
    svg_b64 = base64.b64encode(svg_buffer.read()).decode("utf-8")
    plt.close(fig)

    settings = settings_load(path_settings(filename))
    return render_template("nmr/freq.html", figure=svg_b64, filename=filename, settings=settings)


@bp.route("/freq/<filename>/axis", methods=["POST"])
@session_required
def freq_axis(filename):
    path = path_settings(filename)
    settings = settings_load(path)

    for key in settings["freq_axis"].keys():
        settings_save(path, settings, "freq_axis", key, form_float(key))

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("/freq/<filename>/peaks", methods=["POST"])
@session_required
def freq_peaks(filename):
    threshold = form_float("threshold")
    path = path_settings(filename)
    settings = settings_load(path)

    settings["freq_threshold"]["value"] = threshold

    p0 = settings["freq_phase"]["p0"]
    p1 = settings["freq_phase"]["p1"]

    data, ppm_scale, uc = load_freq_domain(path_dataset(filename), p0, p1)

    list_peaks = []

    if threshold:
        peaks = ng.peakpick.pick(data, pthres=threshold, algorithm="downward")
        for peak in peaks:
            height = float(data[int(peak["X_AXIS"])])
            ppm = float(uc.ppm(peak["X_AXIS"]))
            list_peaks.append({"id": None, "ppm": ppm, "height": height})

    sorted_peaks = sorted(list_peaks, key=lambda x: x["ppm"], reverse=True)

    for n, peak in enumerate(sorted_peaks, start=1):
        peak["id"] = n

    settings["freq_peaks"] = sorted_peaks
    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/peaks/delete", methods=["POST"])
@session_required
def freq_peak_delete(filename):
    try:
        peak_id = int(request.form.get("peak_id"))
    except (ValueError, TypeError):
        abort(400, "Invalid id")
    
    path = path_settings(filename)
    settings = settings_load(path)

    if peak_id not in [peak["id"] for peak in settings["freq_peaks"]]:
        abort(400, "Invalid id")

    temp_peaks = settings["freq_peaks"]

    # Find the peak and delete it.
    for peak in temp_peaks:
        if peak["id"] == peak_id:
            temp_peaks.remove(peak)
            break 

    # Distribute new peak_is's
    for n, peak in enumerate(temp_peaks, start=1):
        peak["id"] = n

    settings["freq_peaks"] = temp_peaks

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/threshold", methods=["POST"])
@session_required
def freq_threshold(filename):
    path = path_settings(filename)
    settings = settings_load(path)

    if settings["freq_threshold"]["bool"]:
        settings["freq_threshold"]["bool"] = False
    else:
        settings["freq_threshold"]["bool"] = True

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/peaks/reset", methods=["POST"])
@session_required
def freq_peaks_reset(filename):
    path = path_settings(filename)
    settings = settings_load(path)
    
    settings["freq_peaks"] = []

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/peaks/zoom", methods=["POST"])
@session_required
def freq_peak_zoom(filename):
    try:
        peak_id = int(request.form.get("peak_id"))
    except (ValueError, TypeError):
        abort(400, "Invalid id")
    
    path = path_settings(filename)
    settings = settings_load(path)

    if peak_id not in [peak["id"] for peak in settings["freq_peaks"]]:
        abort(400, "Invalid id")

    for peak in settings["freq_peaks"]:
        if peak["id"] == peak_id:
            settings["freq_axis"]["xmin"] = peak["ppm"] - 0.1
            settings["freq_axis"]["xmax"] = peak["ppm"] + 0.1
            break

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/phase", methods=["POST"])
@session_required
def freq_phase(filename):
    path = path_settings(filename)
    settings = settings_load(path)

    for key in settings["freq_phase"].keys():
        settings_save(path, settings, "freq_phase", key, form_zero(key))

    return redirect(url_for("nmr.freq", filename=filename)) 


@bp.route("/freq/<filename>/integrals", methods=["POST"])
@session_required
def freq_integrals(filename):
    start = form_float("start")
    end = form_float("end")

    if start is None or end is None:
        abort(400, "Start and end are required")

    path = path_settings(filename)
    settings = settings_load(path)

    p0 = settings["freq_phase"]["p0"]
    p1 = settings["freq_phase"]["p1"]

    data, ppm_scale, uc = load_freq_domain(path_dataset(filename), p0, p1)

    i0 = uc(start, "ppm")
    i1 = uc(end, "ppm")

    if i0 > i1:
        i0, i1 = i1, i0

    i_data  = data[i0:i1 + 1]
    area = i_data.sum()

    new_integrals = {"id": None, "start": start, "end": end, "area": area}
    settings["freq_integrals"].append(new_integrals)

    sorted_integrals = sorted(settings["freq_integrals"], key=lambda x: x["start"], reverse=True)

    for n, integral in enumerate(sorted_integrals, start=1):
        integral["id"] = n

    settings["freq_integrals"] = sorted_integrals

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/integrals/delete", methods=["POST"])
@session_required
def freq_integrals_delete(filename):
    try:
        integral_id = int(request.form.get("integral_id"))
    except (ValueError, TypeError):
        abort (400, "Invalid id")

    path = path_settings(filename)
    settings = settings_load(path)

    if integral_id not in [integral["id"] for integral in settings["freq_integrals"]]:
        abort(400, "Invalid id")

    temp_integrals = settings["freq_integrals"]

    for integral in temp_integrals:
        if integral["id"] == integral_id:
            temp_integrals.remove(integral)
            break
    
    settings["freq_integrals"] = temp_integrals

    sorted_integrals = sorted(settings["freq_integrals"], key=lambda x: x["start"], reverse=True)

    for n, integral in enumerate(sorted_integrals, start=1):
        integral["id"] = n

    settings["freq_integrals"] = sorted_integrals

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/integral/reset", methods=["POST"])
@session_required
def freq_integrals_reset(filename):
    path = path_settings(filename)
    settings = settings_load(path)
    
    settings["freq_integrals"] = []

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("/freq/<filename>/download")
@session_required
def freq_download(filename):
    fig = build_fig_freq(filename)
    svg_buffer = render_svg(fig)
    plt.close(fig)

    return send_file(svg_buffer, mimetype="image/svg+xml", as_attachment=True, download_name=f"{filename}_time.svg")

