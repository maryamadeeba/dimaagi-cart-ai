# PyInstaller spec for the Dimaagi Cart backend (one-folder build: starts faster than one-file).
# Build from the repo root:   .venv\Scripts\pyinstaller dimaagi-backend.spec --noconfirm
# Output: dist\dimaagi-backend\dimaagi-backend.exe (+ _internal\). Check it: python packaging\verify_backend.py
#
# Licensing: ONLY code, the churn models, the demo store's segments and customer scores (dunnhumby-derived, anonymised
# household keys, no review text), config and app assets ship. Nothing from data\ (Yelp reviews, trend PDFs or
# chunks, the vector store, caches), no .env, no eval\spotcheck.csv, no why_summaries/campaign_kits (they quote Yelp
# reviews). Knowledge bases are built on each user's machine.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH)

# The shipped defaults, copied into %APPDATA%\DimaagiCart on first run. One list for the app, the spec and the checks.
sys.path.insert(0, str(ROOT))
from src.api.config import SEED_FILES as SHIP  # noqa: E402

datas = [(str(ROOT / f), str(Path("defaults") / Path(f).parent)) for f in SHIP]
binaries, hiddenimports = [], []

# Packages with data files, native libraries or plugins loaded by name at runtime
def not_tests(name):        # test suites import pytest/hypothesis and aren't needed
    return not any(part in ("test", "tests", "testing") for part in name.split("."))


for pkg in ["chromadb", "fastembed", "onnxruntime", "tokenizers", "xgboost", "shap", "google.genai", "rank_bm25"]:
    d, b, h = collect_all(pkg, filter_submodules=not_tests)
    datas += d
    binaries += b
    hiddenimports += h

# Grammar and schema files read at import time by chromadb's dependencies (found by --self-check)
for pkg in ["rfc3987_syntax", "jsonschema_specifications"]:
    datas += collect_data_files(pkg)

hiddenimports += collect_submodules("uvicorn")                 # protocols and loops are picked by name
hiddenimports += collect_submodules("keyring.backends")        # Windows Credential Manager backend
hiddenimports += ["win32ctypes.core", "win32ctypes.pywin32", "multipart", "python_multipart",
                  "sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes", "openpyxl", "pypdf",
                  "src.rag.assistant", "src.rag.campaign", "src.rag.generate", "src.rag.ingest_reviews",
                  "src.rag.ingest_trends", "src.rag.build_index", "src.segments", "src.train", "src.api.selfcheck"]
datas += copy_metadata("keyring")                              # keyring finds its backends via entry points
for pkg in ["chromadb", "fastembed", "onnxruntime", "tokenizers", "opentelemetry-api", "opentelemetry-sdk"]:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# Never needed at runtime (checked: shap, chromadb and the app import fine without them)
excludes = ["IPython", "matplotlib", "jupyter", "jupyter_client", "jupyter_core", "jupyterlab", "notebook",
            "ipykernel", "ipywidgets", "nbformat", "nbconvert", "tkinter", "pytest", "PyInstaller"]

a = Analysis(
    [str(ROOT / "src" / "api" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dimaagi-backend",
    icon=str(ROOT / "desktop" / "build" / "icon.ico"),
    console=True,               # Electron starts it hidden (windowsHide) and reads its output
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="dimaagi-backend")
