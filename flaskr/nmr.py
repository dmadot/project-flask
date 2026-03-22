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
    settings = settings_load(path_settings(filename))
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
  
    # if show_threshold:
    #     ax.hlines(threshold, *uc.ppm_limits(), linestyle="--", color="b")

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


# Return a float or None (float() dont work on None)
def form_float(key):
    val = request.form.get(key)
    return float(val) if val else None

def form_zero(key):
    val = request.form.get(key)
    return float(val) if val else float(0)


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
        json.dump(settings, f, indent=4)



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


@bp.route("/uploads/<filename>/delete", methods=["POST"])
@session_required
def delete(filename):
    path = path_file(filename)
    shutil.rmtree(path)
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
    show_peaks = bool(request.form.get("show_peaks")) 
    show_threshold = bool(request.form.get("show_threshold"))

    path = path_settings(filename)
    settings = settings_load(path)

    p0 = settings["freq_phase"]["p0"]
    p1 = settings["freq_phase"]["p1"]

    data, ppm_scale, uc = load_freq_domain(path_dataset(filename), p0, p1)

    list_peaks = []

    if threshold:
        peaks = ng.peakpick.pick(data, pthres=threshold, algorithm="downward")
        for n, peak in enumerate(peaks, start=1):
            height = float(data[int(peak["X_AXIS"])])
            ppm = float(uc.ppm(peak["X_AXIS"]))
            list_peaks.append({"id": n, "ppm": ppm, "height": height})

    settings["freq_peaks"] = list_peaks
    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/peaks/delete", methods=["POST"])
@session_required
def freq_peak_delete(filename):
    peak_id = int(request.form.get("peak_id")) 
    path = path_settings(filename)
    settings = settings_load(path)

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


@bp.route("freq/<filename>/peaks/zoom", methods=["POST"])
@session_required
def freq_peak_zoom(filename):
    peak_id = int(request.form.get("peak_id"))
    path = path_settings(filename)
    settings = settings_load(path)

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
    i0 = form_float("i0")
    i1 = form_float("i1")
    path = path_settings(filename)
    settings = settings_load(path)

    temp_integrals = {"id": None, "i0": i0, "i1": i1, "area": None}
    settings["freq_integrals"].append(temp_integrals)

    for n, integral in enumerate(settings["freq_integrals"], start=1):
        integral["id"] = n

    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return redirect(url_for("nmr.freq", filename=filename))


@bp.route("freq/<filename>/integrals/reset", methods=["POST"])
@session_required
def integrals_reset():
    return True


@bp.route("/freq/<filename>/download")
@session_required
def freq_download():
    return True
