"""最小自检:python3 src/test_analyzer.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyzer import keyword_stage, parse_deadline
from scraper import clean_title

for text, want in [
    ("Deadline: October 15, 2026", "2026-10-15"),
    ("apply by 15 October 2026", "2026-10-15"),
    ("2026-10-15", "2026-10-15"),
    ("Oct 15, 2026", "2026-10-15"),
    ("2026/10/15", "2026-10-15"),
    ("27th September 2026", "2026-09-27"),
    ("no date anywhere", None),
]:
    got = parse_deadline(text)
    assert got == want, f"parse_deadline({text!r}) = {got}, 期望 {want}"

MINI_KW = {
    "trigger_words": ["residenc"],
    "block_words": ["tuition"],
    "funding_words": {"allowance": 2, "budget": 1},
    "media_words": {},
}
MEDIALAB = ("Medialab Matadero: Situated Research Residencies 2027. "
            "Each selected project will receive a financial allowance of 10,000 EUR. "
            "Medialab will arrange and cover the cost of one return trip.")
assert keyword_stage(MEDIALAB, MINI_KW) == 2, "allowance 变体应命中 funding 词"
assert keyword_stage("tuition fee required for residency", MINI_KW) is None, "block 词应拦截"
assert keyword_stage("exhibition opening next week", MINI_KW) is None, "无 trigger 应拦截"

assert clean_title('[News] <a href="https://x">Ses12naus: Residency</a>') == '[News] Ses12naus: Residency'

print("ALL SELF-CHECKS PASSED")
