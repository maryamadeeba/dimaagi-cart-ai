"""Regression tests for two src/rag/generate.py bugs found in the Phase 3 review. Offline, no Gemini calls."""
import json

from src.rag.generate import merge_results, theme


def test_theme_reads_reason_mix_not_the_name():
    # High-value is 59% "visiting less" but used to get "basket changed" queries: the name says nothing about it
    hv = {"segment": "High-value · at risk", "reason_mix": {"Visiting less": 0.59, "Basket changed": 0.41}}
    assert theme(hv) == "visiting less"
    assert theme({"segment": "High-value · at risk", "reason_mix": {"Basket changed": 0.7, "Visiting less": 0.3}}) == "basket changed"
    assert theme({"segment": "Core · Visiting less"}) == "visiting less"       # no reason_mix: name fallback


def test_segment_rerun_keeps_other_segments(tmp_path):
    # `generate --segment high` used to overwrite the file with that one segment
    path = tmp_path / "why.json"
    path.write_text(json.dumps([{"segment": "A", "v": 1}, {"segment": "B", "v": 1}, {"segment": "C", "v": 1}]))
    merged = merge_results(path, [{"segment": "B", "v": 2}])
    assert merged == [{"segment": "A", "v": 1}, {"segment": "B", "v": 2}, {"segment": "C", "v": 1}]
