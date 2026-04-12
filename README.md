# PlotPie

A Flask web application for processing 1H-NMR (Nuclear Magnetic Resonance) data.

## Introduction

PlotPie is a free tool for processing and visualizing scientific spectral data directly in the browser. The current version focuses on NMR spectra, where users can upload a Bruker dataset, process it, and export the plot as SVG.

PlotPie is built with Python, using nmrglue for spectral data processing and matplotlib for visualization. The web interface is implemented with Flask and plain HTML forms.

NMR analysis tools are often expensive, bloated, and heavy. PlotPie was born out of a lack of good, free, web-based alternatives and a desire to build one from scratch.

PlotPie is experimental and under active development — features may change and additional spectroscopic methods may be added over time.

## Video Demo

Click [here]().

## Features

- Upload and visualize the raw FID (Free Induction Decay)
- Process NMR spectra (FFT, phase correction, baseline correction, normalization)
- Detect and manage peaks
- Define and list integration regions
- Export the spectrum as SVG

## Requirements

- Python 3.x
- Dependencies listed in `requirements.txt`

## Installation

```bash
git clone https://github.com/dmadot/project-flask.git
cd project-flask
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
flask --app flaskr run
```

Then open your browser at `http://127.0.0.1:5000`.

## Explanation

This section mirrors the learn page from PlotPie and may be more detailed than the in-app version.

### Sessions

Before uploading data, a session must be started. The session creates a temporary workspace where uploaded files are processed and stored during use. Sessions are temporary and must be closed after use — all data is discarded when the session ends.

> [!NOTE]
> Research data is often sensitive. PlotPie strictly avoids data storage and does not collect any user data.

> [!NOTE]
> When uploading a file, PlotPie creates a `.settings.json` file for each dataset to store any changes made during the session. This file is also discarded when the session is closed.

> [!NOTE]
> Sessions are cookie-based. Closing the session removes the cookie.

### Upload

- Only Bruker datasets are supported
- Only 1H-NMR datasets are supported
- The dataset must be uploaded as a ZIP archive
- The ZIP file should contain the original Bruker folder structure

> [!NOTE]
> The uploaded archive is automatically extracted by the application.

#### File Naming

Please use simple file names without spaces or special characters, as these may cause issues during processing. Recommended format:
- `butyl_phenyl_ether.zip`
- `sample_1.zip`

Avoid names such as:
- `butyl phenyl ether.zip`
- `butyl-phenyl-ether (final).zip`
- `sample#1.zip`

### Processing

Raw Bruker data from modern spectrometers contains a group delay artifact that must be removed during processing. nmrglue provides an algorithm for this based on the protocol from *"DMX Digital Filters and Non-Bruker Offline Processing III"* by W. M. Westler and F. Abildgaard, available via [`fileio.bruker.remove_digital_filter()`](https://nmrglue.readthedocs.io/en/latest/examples/proc_bruker_1d.html).

For more information please check the official website of [nmrglue](https://nmrglue.readthedocs.io/en/latest/index.html).

#### Free Induction Decay (FID)

Select your file by clicking the **plot** icon to view the raw FID. You can zoom in by adjusting the axis fields and download the figure as SVG.

> [!NOTE]
> `ms_scale()` converts the X-axis from data points to milliseconds, representing the signal acquisition time.

#### Process the Spectrum

Click the **plot** icon again to view the frequency-domain spectrum. Processing follows the official nmrglue documentation, with the exceptions noted below.

```python
data = ng.proc_base.fft(data)                       # Fourier transform
data = ng.proc_base.ps(data, p0=p0, p1=p1)          # phase correction
data = ng.proc_base.di(data)                        # discard imaginaries
data = ng.proc_base.rev(data)                       # reverse the data
data = ng.proc_bl.baseline_corrector(data, wd=20)   # baseline correction
data = data / data.max()                            # normalize
ppm_scale = uc.ppm_scale()                          # convert to ppm
```

> [!NOTE]
> `ppm_scale()` converts the X-axis to ppm, the standard unit for NMR spectral analysis.

> [!NOTE]
> `data / data.max()` normalizes the data so the tallest peak always equals 1. This makes spectra comparable and replaces very large raw values with a familiar 0–1 range.

> [!NOTE]
> Baseline correction is applied automatically. Algorithm described in: Wang et al. *Anal. Chem.* 2013, 85, 1231–1239.

#### Plotting

Matplotlib is used to visualize the spectrum as a figure. For more information please check the official website of [matplotlib](https://matplotlib.org/).

> [!NOTE]
> The created figure is rendered to SVG, encoded as a Base64 string via `base64.b64encode()`, and embedded directly in the HTML response via a data URL — or served as a download via `send_file()`. No static files needed.

### Downloading

To download the FID or the final spectrum, click the **download** icon.

### Apply Changes

To submit the form (e.g. when changing the axis range), press **Enter**.

### Phase Correction

After the FFT, the spectrum may appear distorted. Use the phase correction controls to fix this:
- **P0** — zero-order phase correction: applies a constant phase shift across the whole spectrum
- **P1** — first-order phase correction: applies a phase shift that varies linearly across the spectrum

Adjust P0 and P1 until the peaks appear symmetric and upright (pure absorption mode).

### Axis

Use the **X-Min** / **X-Max** and **Y-Min** / **Y-Max** fields to zoom into a region of interest.

### Peak Detection

PlotPie detects peaks using `ng.peakpick.pick()` with the `downward` algorithm. Use the controls to filter out noise and focus on real peaks.
- **Threshold** — sets the minimum intensity required for peak detection
- **Eye** — toggles the threshold line on the plot

### Peak List

Shows all peaks detected by the algorithm.
- Zoom in by clicking the **zoom** icon
- Remove a peak by clicking the **trashcan** icon
- Reset the entire list by clicking the **circle** icon

> [!NOTE]
> The plot is a static SVG and is not interactive. The zoom button is provided to make navigating the spectrum more convenient.

### Integration

- **Start** — the left boundary of the integration region
- **End** — the right boundary of the integration region

### Integral List

Shows all selected integration regions.
- Remove an integral by clicking the **trashcan** icon
- Reset the entire list by clicking the **circle** icon

## Use of AI

AI was used mainly for debugging and text generation. Any code copied verbatim is explicitly marked as such within the source code.
