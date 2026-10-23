"""Make printing safe on any console. The CLIs print emoji (✅ ⚠ ❌); a Windows console or a redirected stream
often uses cp1252, which can't encode them and would crash the run after the work (and the Gemini calls) are done."""
import io
import sys


def utf8_console():
    """Switch stdout and stderr to UTF-8, replacing anything unencodable. Safe when a stream is missing
    (a windowed app has no console) or can't be reconfigured (a test capture, a custom writer)."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, io.UnsupportedOperation):
                pass
