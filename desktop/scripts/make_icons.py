"""Render the design's logo mark to build/icon.png (512px) and build/icon.ico (16-256px).
Uses headless Microsoft Edge to rasterise the SVG and Pillow to pack the .ico.
Run from desktop/:  ../.venv/Scripts/python scripts/make_icons.py"""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 34 34">'
       '<rect width="34" height="34" rx="10" fill="#E0582B"/>'
       '<path d="M10 19c0-5 4-9 9-9h3m0 0-3-3m3 3-3 3M24 15c0 5-4 9-9 9h-3m0 0 3 3m-3-3 3-3" fill="none" '
       'stroke="#FBF7EF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
OUT = Path(__file__).resolve().parents[1] / "build"

with tempfile.TemporaryDirectory() as tmp:
    page = Path(tmp) / "icon.html"
    page.write_text(f"<html><body style='margin:0;background:transparent'>{SVG}</body></html>", encoding="utf-8")
    shot = Path(tmp) / "icon.png"
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(tmp) / 'prof'}",
                    "--default-background-color=00000000", "--window-size=512,512", f"--screenshot={shot}",
                    page.as_uri()], check=True, capture_output=True, timeout=60)
    img = Image.open(shot).convert("RGBA").crop((0, 0, 512, 512))
OUT.mkdir(exist_ok=True)
img.save(OUT / "icon.png")
img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
print(f"Saved {OUT / 'icon.png'} and {OUT / 'icon.ico'}")
