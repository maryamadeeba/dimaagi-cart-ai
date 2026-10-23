"""Citation refs shared by the generators, the assistant and the checks. Pure functions, no heavy imports."""
import re

REF_PATTERN = re.compile(r"\b([RT]\d+|[SKW]_[a-z]+)\b")     # R3, T2, S_highvalue, K_corebasket, W_highvalue
PLACEHOLDERS = {"STORE NAME", "LINK", "CONFIRM"}             # kit placeholders in brackets, not citations


def refs_in(citation):
    """Pull every ref out of one citation string: 'R1, R2' -> ['R1','R2'], 'R1, 7' -> ['R1','R7']."""
    s = str(citation)
    return [f"R{n}" for n in re.findall(r"\d+", s)] if "R" in s.upper() else []


def parse_refs(items):
    """R and T refs from a list of citation strings: ['T1', 'R 3, t4'] -> ['T1', 'R3', 'T4']."""
    return [p + n for c in items for p, n in re.findall(r"\b([RT])\s*(\d+)", str(c).upper())]


def parse_citations(answer, refs):
    """Return (cited, invalid). Bracketed text that isn't a ref (e.g. a tool name) counts as a fake citation,
    except store placeholders like [STORE NAME]."""
    bracketed = [x.strip() for group in re.findall(r"\[([^\]]+)\]", answer) for x in group.split(",")]
    cited = sorted(set(REF_PATTERN.findall(answer)))
    fake = sorted({x for x in bracketed if not REF_PATTERN.fullmatch(x) and x.upper() not in PLACEHOLDERS})
    invalid = [c for c in cited if c not in refs] + fake
    return cited + fake, invalid
