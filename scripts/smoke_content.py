"""Smoke test: run the Content Agent on the sample lesson against the configured model.

    python scripts/smoke_content.py Hindi
"""

import faulthandler
import json
from collections import Counter
import os
import sys
import time
from pathlib import Path

# LEARNOVA_TRACE=60 prints every thread's stack every 60s, to find where a run hangs.
if os.getenv("LEARNOVA_TRACE"):
    faulthandler.dump_traceback_later(int(os.environ["LEARNOVA_TRACE"]), repeat=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova.agents.content import draft_diagnostic, write_follow_up  # noqa: E402
from learnova.grading import check_quizzes  # noqa: E402
from learnova.lesson import sample_lesson  # noqa: E402

language = sys.argv[1] if len(sys.argv) > 1 else "Hindi"
start = time.time()
try:
    analysis = draft_diagnostic(sample_lesson(), language)
    print(f"concepts + Quiz A in {time.time() - start:.0f}s (what the student waits for)")
    mid = time.time()
    analysis = write_follow_up(analysis, sample_lesson(), language)
    print(f"Quiz B in {time.time() - mid:.0f}s (written in the background in the app)")
except Exception as e:
    print(f"FAILED after {time.time() - start:.0f}s: {type(e).__name__}: {e}")
    raise SystemExit(1)

print(f"OK in {time.time() - start:.0f}s | topic: {analysis.topic}")
for c in analysis.concepts:
    print(f"  {c.id} {c.name} ({c.english_term}) prerequisites={c.prerequisite_ids}")
print(f"quiz_a: {len(analysis.quiz_a)} questions, quiz_b: {len(analysis.quiz_b)} questions, "
      f"problems: {check_quizzes(analysis)}")
positions = Counter("abcd"[q.answer_index] for q in analysis.quiz_a + analysis.quiz_b)
print(f"correct-answer positions (should be spread out): {dict(sorted(positions.items()))}")
for q in analysis.quiz_a[:2]:
    print(json.dumps(q.model_dump(), ensure_ascii=False, indent=1))
