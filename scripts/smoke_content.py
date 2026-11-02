"""Smoke test: run the Content Agent on the sample lesson against the configured model.

    python scripts/smoke_content.py Hindi
"""

import faulthandler
import json
import os
import sys
import time
from pathlib import Path

# LEARNOVA_TRACE=60 prints every thread's stack every 60s, to find where a run hangs.
if os.getenv("LEARNOVA_TRACE"):
    faulthandler.dump_traceback_later(int(os.environ["LEARNOVA_TRACE"]), repeat=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova.agents.content import analyze_lesson  # noqa: E402
from learnova.grading import check_quizzes  # noqa: E402
from learnova.lesson import sample_lesson  # noqa: E402

language = sys.argv[1] if len(sys.argv) > 1 else "Hindi"
start = time.time()
try:
    analysis = analyze_lesson(sample_lesson(), language)
except Exception as e:
    print(f"FAILED after {time.time() - start:.0f}s: {type(e).__name__}: {e}")
    raise SystemExit(1)

print(f"OK in {time.time() - start:.0f}s | topic: {analysis.topic}")
for c in analysis.concepts:
    print(f"  {c.id} {c.name} ({c.english_term}) prerequisites={c.prerequisite_ids}")
print(f"quiz_a: {len(analysis.quiz_a)} questions, quiz_b: {len(analysis.quiz_b)} questions, "
      f"problems: {check_quizzes(analysis)}")
for q in analysis.quiz_a[:2]:
    print(json.dumps(q.model_dump(), ensure_ascii=False, indent=1))
