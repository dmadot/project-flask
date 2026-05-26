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

    # Set default axis
    axis = settings["freq_axis"]
    if axis["xmin"] == None:
        axis["xmin"] = ppm_scale.min()
    if axis["xmax"] == None:
        axis["xmax"] = ppm_scale.max()
    if axis["ymin"] == None:
        axis["ymin"] = -0.1
    if axis["ymax"] == None:
        axis["ymax"] = 3

    # Plot settings
    ax.set_title(filename)
    ax.set_xlabel("1H / ppm")
    ax.set_xlim(settings["freq_axis"]["xmin"], settings["freq_axis"]["xmax"])
    ax.set_ylim(settings["freq_axis"]["ymin"], settings["freq_axis"]["ymax"])
    ax.invert_xaxis()
  
    if settings["freq_threshold"]["bool"]:
        ax.hlines(settings["freq_threshold"]["value"], *uc.ppm_limits(), linestyle="--", color="k", lw=1)

    # Update settings
    settings["freq_axis"] = axis
    with open(path, "w") as p:
        json.dump(settings, p, indent=4)

    return fig

def build_fig_time(filename):
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


# Return a float or None or 0 (float() dont work on None).
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

    data = ng.proc_base.fft(data)                       # fourier transform
    data = ng.proc_base.ps(data, p0=p0, p1=p1)          # phase correction
    data = ng.proc_base.di(data)                        # discard the imaginaries
    data = ng.proc_base.rev(data)                       # reverse the data
    data = ng.proc_bl.baseline_corrector(data, wd=20)   # calculate a baseline using a distribution based classification method
    data = data / data.max()                            # harmonize data
    ppm_scale = uc.ppm_scale()                          # converting to ppm

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
    # AI-assisted: using io.BytesIO() as an in-memory buffer to capture the SVG output
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
        if ".timestamp.json" in items:
            items.remove(".timestamp.json")

    # Load default setting
    default_settings_path = os.path.join(current_app.root_path, "static", "default_settings.json")
    settings = settings_load(default_settings_path)
    if not settings:
        abort(400, "Default settings could not be loaded")
    
    return render_template("nmr/index.html", items=items, settings=settings)


@bp.route("/uploads", methods=["POST"])
@session_required
def uploads():
    file = request.files.get("file")
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))

    if not file or file.filename == "":
        return abort(400, "No file")

    if not allowed_file(file.filename):
        return abort(400, "File type not allowed")

    # Upload count limit 
    items = os.listdir(path)
    if ".timestamp.json" in items:
        if len(items) >= 20:
            return abort(400, "Too many uploads")
    else:
        if len(items) >= 19:
            return abort(400, "Too many uploads")
    
    # Check for valid filename
    filename = Path(secure_filename(file.filename)).stem
    if not filename:
        abort(400, "Invalid filename")

    # Create the file folder
    file_path = os.path.join(path, filename)
    if os.path.exists(file_path):
        abort(400, "A file with this name already exists")
    os.makedirs(file_path)

    # AI-assisted: hardening the ZIP upload to prevent path traversal attacks
    if zipfile.is_zipfile(file):
        with zipfile.ZipFile(file) as zf:
            for member in zf.namelist():
                member_path = os.path.realpath(os.path.join(file_path, member))
                if not member_path.startswith(os.path.realpath(file_path) + os.sep):
                    shutil.rmtree(file_path)
                    return abort(400, "Invalid zip contents")

            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > 50 * 1024 * 1024:
                shutil.rmtree(file_path)
                return abort(400, "Zip contents too large")

            zf.extractall(os.path.join(file_path + "/.dataset"))
    
    # Create the default settings for this dataset.
    default_settings_path = os.path.join(current_app.root_path, "static", "default_settings.json")
    with open(file_path + f"/.settings.json", "w") as f:
        json.dump(settings_load(default_settings_path), f)

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

    # AI-assisted: base64 encoding and embedding of the SVG figure via data URL
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

    # AI-assisted: serving the in-memory SVG buffer as a file download via send_file()
    return send_file(svg_buffer, mimetype="image/svg+xml", as_attachment=True, download_name=f"{filename}_time.svg")


@bp.route("/freq/<filename>")
@session_required
def freq(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], session.get("id"))
    if not os.path.isdir(path):
        abort(400, "Path not found")
    else:
        items = os.listdir(path)
        if ".timestamp.json" in items:
            items.remove(".timestamp.json")

    fig = build_fig_freq(filename)
    svg_buffer = render_svg(fig)
    svg_b64 = base64.b64encode(svg_buffer.read()).decode("utf-8")
    plt.close(fig)

    settings = settings_load(path_settings(filename))

    return render_template("nmr/index.html", figure=svg_b64, filename=filename, items=items, settings=settings)


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

    # Distribute new peak_id's
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


@bp.route("freq/<filename>/peak/action", methods=["POST"])
@session_required
def freq_peaks_action(filename):
    # Load the settings
    path = path_settings(filename)
    settings = settings_load(path)

    # Valid actions for validation of users input
    valid_actions = ["remove", "reset", "zoom"]

    # Users input
    action = request.form.get("action")
    selectet_peaks = request.form.getlist("peaks")

    # Convert the peak list into integer & check for valid input
    for n, peak in enumerate(selectet_peaks):
        try:
            selectet_peaks[n] = int(peak)
        except(ValueError, TypeError):
            abort(400, "Invalid ID")

    # Check for valid action input
    if action not in valid_actions:
        abort(400, "Action not allowed")

    # Check if the peaks are in the peaklist
    for peak in selectet_peaks:
        if peak not in [peak["id"] for peak in settings["freq_peaks"]]:
            abort(400, "Invalid id")

    # Reset peaks
    if action == "reset":
        settings["freq_peaks"] = []
        with open(path, "w") as f:
            json.dump(settings, f, indent=4)

    # Delete peaks
    elif action == "remove":

        # Copy the settings for editing
        temp_peaks = settings["freq_peaks"].copy() 

        # Remove all peaks the user are selectet
        for peak in settings["freq_peaks"]:
            if peak["id"] in selectet_peaks:
                temp_peaks.remove(peak)

        # Distribute new peak_id's
        for n, peak in enumerate(temp_peaks, start=1):
            peak["id"] = n

        # Update the settings
        settings["freq_peaks"] = temp_peaks
        with open(path, "w") as f:
            json.dump(settings, f, indent=4)

    # Zoom
    else:
        if len(selectet_peaks) > 1:
            abort(400, "Just one peak are allowed")
        else:
            for peak in settings["freq_peaks"]:
                if peak["id"] in selectet_peaks:
                    settings["freq_axis"]["xmin"] = peak["ppm"] - 0.1
                    settings["freq_axis"]["xmax"] = peak["ppm"] + 0.1
                    break

            # Update the settings
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

    if start > end:
        start, end = end, start

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

@bp.route("freq/<filename>/integrals/action", methods=["POST"])
@session_required
def freq_integrals_action(filename):
    path = path_settings(filename)
    settings = settings_load(path)
    
    # Get the users action input & validation
    valid_actions = ["remove", "reset", "zoom"]
    action = request.form.get("action")
    if action not in valid_actions:
        abort(400, "Invalid action")

    # Get and validate the integral id
    selectet_integrals = request.form.getlist("integrals")
    if len(selectet_integrals) > 0:
        check_id = []
        for n, i in enumerate(selectet_integrals):
            selectet_integrals[n] = int(i)
        for i in settings["freq_integrals"]:
            check_id.append(i["id"])
        for i in selectet_integrals:
            if i not in check_id:
                abort(400, "Invalid id")

    # Remove integrals
    if action == "remove":
        temp_list = settings["freq_integrals"].copy()
        for i in settings["freq_integrals"]:
            if i["id"] in selectet_integrals:
                temp_list.remove(i)
        
        # Resort the list & re-enumerate the list
        sorted_integrals = sorted(temp_list, key=lambda x: x["start"], reverse=True)
        for n, i in enumerate(sorted_integrals, start=1):
            i["id"] = n

        # Update the settings
        settings["freq_integrals"] = sorted_integrals
    
    # Reset integrals
    elif action == "reset":
        settings["freq_integrals"] = []

    # Zoom in
    # TODO Check system to set min, max korrekt (12 <- 0 ppm)
    else:
        if len(selectet_integrals) != 1:
            abort(400, "Select one integral to zoom in")
        else:
            for i in settings["freq_integrals"]:
                if i["id"] in selectet_integrals:
                    settings["freq_axis"]["xmin"] = i["start"] - 0.1
                    settings["freq_axis"]["xmax"] = i["end"] + 0.1
                    
    # Save the settings
    with open(path, "w") as p:
        json.dump(settings, p, indent=4)

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

    return send_file(svg_buffer, mimetype="image/svg+xml", as_attachment=True, download_name=f"{filename}_freq.svg")


@bp.route("freq/<filename>/integral/navigate", methods=["POST"])
@session_required
def navigate(filename):

    # Set the allowed movements the user can select
    allowed_navigation = [
        "x_out",
        "up",
        "x_in",
        "left",
        "center",
        "right",
        "y_out",
        "down",
        "y_in"
    ]

    # Zoom & movement settings

    # Get & validate the user Input
    path = path_settings(filename)
    settings = settings_load(path)
    move = request.form.get("navigate")
    if move not in allowed_navigation:
        abort(400, "Input not allowed")

    try:
        move_index = float(request.form.get("move_index"))
        zoom_index = float(request.form.get("zoom_index"))
    except(ValueError, TypeError):
        abort(400, "Invalid Index")

    # Get the old axis
    axis = settings["freq_axis"]
    x_range = axis["xmax"] - axis["xmin"]
    y_range = axis["ymax"] - axis["ymin"]

    # Get the new axis
    # TODO: Bug left & right get oposit and y zoom baseline fix
    if move == "x_out":
        axis["xmin"] -= x_range * zoom_index
        axis["xmax"] += x_range * zoom_index
    elif move == "up":
        axis["ymin"] -= y_range * move_index
        axis["ymax"] -= y_range * move_index
    elif move == "x_in":
        axis["xmin"] += x_range * zoom_index
        axis["xmax"] -= x_range * zoom_index
    elif move == "left":
        axis["xmin"] -= x_range * move_index
        axis["xmax"] -= x_range * move_index
    elif move == "center":
        axis["xmin"], axis["xmax"], axis["ymin"], axis["ymax"] = None, None, None, None
    elif move == "right":
        axis["xmin"] += x_range * move_index
        axis["xmax"] += x_range * move_index
    elif move == "y_out":
        ymax = axis["ymax"]
        axis["ymin"] = 0 - ((ymax * (1 - zoom_index)) * 0.05)
        axis["ymax"] = ymax * (1 - zoom_index)
    elif move == "down":
        axis["ymin"] += y_range * move_index
        axis["ymax"] += y_range * move_index
    elif move == "y_in":
        ymax = axis["ymax"]
        axis["ymin"] = 0 - ((ymax * (1 + zoom_index)) * 0.05)
        axis["ymax"] = ymax * (1 + zoom_index)

    # Update the settings
    settings["freq_axis"] = axis
    settings["freq_navigation"]["move_index"] = move_index
    settings["freq_navigation"]["zoom_index"] = zoom_index
    with open(path, "w") as p:
        json.dump(settings, p, indent=4)

    # Redirect to main
    return redirect(url_for("nmr.freq", filename=filename))