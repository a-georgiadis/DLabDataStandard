# DLabDataStandard
This repository is for aligning data standards across different Raman instruments

See [`DataStandard/README.md`](DataStandard/README.md) for the unified `.h5` schema and the
per-instrument export scripts.

## Installation

Dependencies come from **conda-forge via [mamba](https://mamba.readthedocs.io/)**. Only two packages
are installed with `pip`, because conda-forge does not carry them.

```bash
git clone https://github.com/a-georgiadis/DLabDataStandard.git
cd DLabDataStandard

# 1. Create and activate the environment
mamba create -n dlab-raman python=3.12
mamba activate dlab-raman

# 2. Runtime dependencies, all from conda-forge
mamba install -c conda-forge --file requirements.txt

# 3. The only two packages conda-forge does not carry.
#    --no-deps stops pip from pulling its own numpy/Pillow wheels over the
#    conda-forge builds installed in step 2.
pip install --no-deps -e ./wdf_python     # vendored Renishaw `wdf` reader, not published anywhere
pip install --no-deps renishawWiRE        # PyPI only

# 4. Optional: tests, linting, and the notebook
mamba install -c conda-forge --file requirements-dev.txt
```

If you do not have mamba, `conda` accepts the same `install -c conda-forge --file ...` commands (just
more slowly), and `pip install -r requirements.txt` works as a last resort — but note that
`requirements.txt` covers only the conda-forge half, so step 3 is required either way.

### Verify the install

```bash
python -c "import numpy, h5py, pandas, matplotlib, PIL, natsort, wdf; from renishawWiRE.wdfReader import WDFReader; print('ok')"
pip check   # should report no broken requirements
```

### Running the scripts

Both exporters are runnable directly or importable as modules:

```bash
cd DataStandard
python wdfProcessing.py     [inputFolder] [outputFolder]   # Renishaw (WiRE) .wdf
python labspecProcessing.py [inputFolder] [outputFolder]   # Horiba XploRA Plus (LabSpec 6) .txt
```

**Run `wdfProcessing.py` from inside `DataStandard/`.** It does `from wdfTimestamps import ...`
([wdfProcessing.py:41](DataStandard/wdfProcessing.py#L41)) — a sibling-module import that only
resolves when that directory is on `sys.path`, which is the case when it is the script's own folder.
`labspecProcessing.py` has no such constraint (it needs only numpy + h5py). The `wdf` package itself
is importable from anywhere once step 3 above has run.

The `wdfbrowser` GUI shipped in `wdf_python` additionally needs Tk; the conda-forge `python` build
already includes it, so nothing extra is required.

### Why mamba, and why those two pip lines

Mamba resolves the compiled scientific stack (`numpy`, `h5py`, `matplotlib`, `pillow`) as a consistent
set of binaries, which avoids the HDF5-versus-numpy ABI mismatches that pip-only environments hit.
The two exceptions are genuinely unavailable there: `wdf` is vendored in this repo and published
nowhere, and `renishawWiRE` exists only on PyPI. Please keep them out of `requirements.txt` — a
pip-only line in that file makes `mamba install --file` fail for everyone.
