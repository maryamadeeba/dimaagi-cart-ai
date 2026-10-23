"""Day 8: routing and citation eval for the assistant chat.

Run:  python -m eval.run_chat_eval
      python -m eval.run_chat_eval --repeats 3     # also report whether tool choice is stable across runs
Each question runs in a fresh conversation. Routing is correct if every expected tool was called
(for out-of-scope questions: if no tool was called).
"""
import argparse
import json
import os
import time
from pathlib import Path

from src.rag import assistant as A
from src.console import utf8_console

QUESTIONS = Path("eval/chat_questions.jsonl")
REPORT = Path("reports/chat_eval.md")               # metrics only, safe to commit
ANSWERS = Path("models/chat_eval_answers.md")       # full answers (may quote reviews), gitignored
RESULTS = Path("models/chat_eval_results.json")     # answers + source texts for eval.judge, gitignored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=1, help="run each question N times to check tool-choice stability")
    args = ap.parse_args()
    repeats = max(1, args.repeats)

    client = A.make_client()
    questions = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Chat eval | {len(questions)} questions x {repeats} | model: {A.CHAT_MODEL} | retrieval: {A.CHAT_RETRIEVAL}")

    rows, answers, results, stability = [], ["# Chat eval answers", ""], [], []
    for i, q in enumerate(questions, 1):
        tool_sets = []
        for rep in range(1, repeats + 1):
            A.SESSION.__init__()                       # fresh refs and tool log for each run
            r = A.ask(A.make_chat(client), q["question"])
            expected, called = set(q["expected_tools"]), set(r["tools"])
            tool_sets.append(called)
            routed = (not called) if not expected else expected <= called
            print(f"[{i}/{len(questions)}]{f' rep {rep}/{repeats}' if repeats > 1 else ''} {q['qid']} "
                  f"{'✅' if routed else '❌'} routing | called: {sorted(called) or 'none'} | "
                  f"citations: {len(r['cited'])} ({'valid ' + format(r['validity'], '.0%') if r['validity'] is not None else 'none'}) | {r['seconds']}s",
                  flush=True)
            if rep == 1:                               # the main metrics use repeat 1 only
                cites_ok = bool(r["cited"]) if expected else True
                rows.append({**q, **r, "routed": routed, "cites_ok": cites_ok, "extra_tools": sorted(called - expected)})
                answers += [f"## {q['qid']}: {q['question']}", "", r["answer"], "",
                            f"*Tools:* {', '.join(r['tools']) or 'none'} · *Sources:* "
                            + "; ".join(f"{c} = {A.SESSION.refs[c]['label']}" for c in r["cited"] if c in A.SESSION.refs), ""]
                results.append({"qid": q["qid"], "type": q["type"], "question": q["question"], "answer": r["answer"],
                                "tools": r["tools"], "tool_args": r["tool_args"], "cited": r["cited"],
                                "invalid": r["invalid"], "ungrounded_numbers": r["ungrounded_numbers"],
                                "sources": {ref: {"label": m["label"], "text": m.get("text", "")}
                                            for ref, m in A.SESSION.refs.items()}})
            time.sleep(7)
        stability.append({"qid": q["qid"], "same": all(t == tool_sets[0] for t in tool_sets),
                          "sets": [sorted(t) for t in tool_sets]})

    in_scope = [r for r in rows if r["expected_tools"]]
    all_cited = sum(len(r["cited"]) for r in rows)
    all_invalid = sum(len(r["invalid"]) for r in rows)
    summary = {
        "routing_accuracy": sum(r["routed"] for r in rows) / len(rows),
        "answers_with_citations": sum(r["cites_ok"] for r in in_scope) / len(in_scope) if in_scope else 0,
        "citation_validity": 1 - all_invalid / all_cited if all_cited else 0,
        "numbers_grounded": sum(not r["ungrounded_numbers"] for r in rows) / len(rows),
        "mean_seconds": sum(r["seconds"] for r in rows) / len(rows),
    }

    lines = ["# Assistant chat eval (Day 8)", "",
             f"Model `{A.CHAT_MODEL}`, retrieval `{A.CHAT_RETRIEVAL}`, {len(rows)} questions, each in a fresh conversation.", "",
             "| Metric | Result | Target |", "|---|---|---|",
             f"| Routing accuracy | {summary['routing_accuracy']:.0%} | ≥ 90% |",
             f"| In-scope answers with citations | {summary['answers_with_citations']:.0%} | 100% |",
             f"| Citation validity | {summary['citation_validity']:.0%} | 100% |",
             f"| Numbers grounded (answers with no ungrounded numbers) | {summary['numbers_grounded']:.0%} | 100% |",
             f"| Mean latency | {summary['mean_seconds']:.1f}s | |", "",
             "| ID | Type | Expected | Called | Routed | Citations | Model s | Tools s |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['qid']} | {r['type']} | {', '.join(r['expected_tools']) or 'none'} | "
                     f"{', '.join(sorted(set(r['tools']))) or 'none'} | {'✅' if r['routed'] else '❌'} | "
                     f"{len(r['cited'])} | {r['model_seconds']} | {r['tool_seconds']} |")
    if repeats > 1:
        stable = sum(s["same"] for s in stability) / len(stability)
        lines += ["", f"## Stability ({repeats} runs per question)", "",
                  f"Questions with the same set of tools in every run: **{stable:.0%}**", "",
                  "| ID | Same tools every run | Tool sets per run |", "|---|---|---|"]
        for s in stability:
            sets = " / ".join("{" + ", ".join(t) + "}" if t else "{none}" for t in s["sets"])
            lines.append(f"| {s['qid']} | {'✅' if s['same'] else '❌'} | {sets} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ANSWERS.write_text("\n".join(answers), encoding="utf-8")
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "\n".join(lines[:11]))
    if repeats > 1:
        print(f"Tool-choice stability: {stable:.0%} of questions identical across {repeats} runs")
    print(f"\n✅ Saved {REPORT}, {ANSWERS} and {RESULTS}")


if __name__ == "__main__":
    utf8_console()
    main()
