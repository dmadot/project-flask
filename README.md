# NMR to TikZ

A Flask web application that processes NMR (Nuclear Magnetic Resonance) spectra and exports them as TikZ code for use in LaTeX documents.

## Features

- Upload FID (Free Induction Decay) files
- Process NMR spectra using nmrglue
- Export publication-ready TikZ/LaTeX code

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
