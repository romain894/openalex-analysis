# Set up the python environment for the Jupyter notebooks included in the documentation

## Installation

Create a python virtual environment:
```bash
python3 -m venv .venv
```

And load it:
```bash
source .venv/bin/activate
```

Install Jupyter Lab and other required modules:
```bash
pip install jupyterlab kaleido
```

Install `openalex-analysis` as a local module:
```bash
pip install -e ../..
```

## Usage

Load the venv and start Jupyter Lab:
```bash
source .venv/bin/activate
jupyter lab
```

