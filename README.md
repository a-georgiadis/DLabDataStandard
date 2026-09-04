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
#    Use `python -m pip`, never a bare `pip` -- see the warning below.
#    --no-deps stops pip from pulling its own numpy/Pillow wheels over the
#    conda-forge builds installed in step 2.
python -m pip install --no-deps -e ./wdf_python   # vendored Renishaw `wdf` reader, not published anywhere
python -m pip install --no-deps renishawWiRE      # PyPI only

# 4. Optional: tests, linting, and the notebook
mamba install -c conda-forge --file requirements-dev.txt
```

> **Always write `python -m pip`, not `pip`, in step 3.** On a Mac with a python.org
> Python.framework install, `/Library/Frameworks/Python.framework/Versions/<x.y>/bin/pip` can sit
> ahead of the conda environment on your `PATH`. A bare `pip install` then silently installs into
> that system Python *even with `dlab-raman` activated* — the packages land somewhere the environment
> cannot see, and your system Python gets modified instead. `python -m pip` always targets the
> interpreter that is actually active. Confirm with `python -m pip --version`; the path it prints
> should be inside `envs/dlab-raman`.

If you do not have mamba, `conda` accepts the same `install -c conda-forge --file ...` commands (just
more slowly), and `python -m pip install -r requirements.txt` works as a last resort — but note that
`requirements.txt` covers only the conda-forge half, so step 3 is required either way.

### Verify the install

```bash
python -m pip --version   # path should be inside envs/dlab-raman
python -c "import numpy, h5py, pandas, matplotlib, PIL, natsort, wdf; from renishawWiRE.wdfReader import WDFReader; print('ok')"
python -m pip check       # should report no broken requirements
```

### Running the scripts

Both exporters take the input folder as the first argument and the output folder as an optional
second, defaulting to `<inputFolder>/Extracted`:

```bash
python DataStandard/wdfProcessing.py     <inputFolder> [outputFolder]   # Renishaw (WiRE) .wdf
python DataStandard/labspecProcessing.py <inputFolder> [outputFolder]   # Horiba XploRA (LabSpec 6) .txt
```

Note there is no `--help`; both parse `sys.argv` directly, so an unrecognized flag is taken as the
input folder name. **Run them with an explicit input folder** — invoked with no arguments at all they
fall back to a hardcoded path from the original author's machine.

Invoke them by script path as shown above, from any working directory. `wdfProcessing.py` does
`from wdfTimestamps import ...` ([wdfProcessing.py:41](DataStandard/wdfProcessing.py#L41)), a
sibling-module import, and running a file by path puts that file's own directory on `sys.path`, so it
resolves fine. What does *not* work is `python -m DataStandard.wdfProcessing`, or importing
`wdfProcessing` from another directory — both put the caller's location on `sys.path` instead of
`DataStandard/` and fail with `No module named 'wdfTimestamps'`. To import it as a module, add
`DataStandard/` to `sys.path` or run from within that folder. The `wdf` package itself is importable
from anywhere once step 3 above has run.

The `wdfbrowser` GUI shipped in `wdf_python` additionally needs Tk; the conda-forge `python` build
already includes it, so nothing extra is required.

### Why mamba, and why those two pip lines

Mamba resolves the compiled scientific stack (`numpy`, `h5py`, `matplotlib`, `pillow`) as a consistent
set of binaries, which avoids the HDF5-versus-numpy ABI mismatches that pip-only environments hit.
The two exceptions are genuinely unavailable there: `wdf` is vendored in this repo and published
nowhere, and `renishawWiRE` exists only on PyPI. Please keep them out of `requirements.txt` — a
pip-only line in that file makes `mamba install --file` fail for everyone.
