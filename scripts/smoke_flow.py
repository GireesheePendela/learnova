"""Runs the whole learning session with a SIMULATED student, no clicking needed:
Content Agent -> Quiz A (Quiz B written in the background) -> Assessment Agent -> Tutor Agent -> practice -> Quiz B.

    python scripts/smoke_flow.py Hindi

The simulated student knows only the first concept on Quiz A, gets half the practice right,
and answers Quiz B correctly. The scores show the pipeline works; they are not learning results.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova import session  # noqa: E402
from learnova.lesson import sample_lesson  # noqa: E402
from learnova.store import Store  # noqa: E402


def timed(label, fn, *args):
    start = time.time()
    result = fn(*args)
    print(f"[{time.time() - start:5.1f}s] {label}")
    return result


language = sys.argv[1] if len(sys.argv) > 1 else "Hindi"
store = Store(":memory:")

lesson_id = timed("Content Agent: concepts + Quiz A", session.start_lesson, store, "Sim", language, sample_lesson())
quiz_b_future = session.start_quiz_b(store, lesson_id)  # runs during the tutoring rounds below
_, analysis = store.get_lesson(lesson_id)
for c in analysis.concepts:
    print(f"    {c.id} {c.name} ({c.english_term}) prerequisites={c.prerequisite_ids}")

known = analysis.concepts[0].id
answers = {i: q.answer_index if q.concept_id == known else (q.answer_index + 1) % 4
           for i, q in enumerate(analysis.quiz_a)}
print(f"    Quiz A score: {session.submit_quiz(store, lesson_id, 'quiz_a', answers):.0%}")

for round_no in (1, 2):
    decision = timed(f"Assessment Agent + Tutor Agent (round {round_no})", session.next_step, store, lesson_id)
    if decision is None:
        print("    Assessment Agent: everything mastered")
        break
    plan = decision["plan"]
    print(f"    chose {decision['concept_id']} via {decision['source']} at difficulty {decision['difficulty']}")
    print(f"    reason: {decision['reason']}")
    print(f"    explanation: {plan.explanation[:200]}...")
    print(f"    glossary: {[(g.english, g.translation) for g in plan.glossary]}")
    practice_answers = {i: q.answer_index if i % 2 == 0 else (q.answer_index + 1) % 4
                        for i, q in enumerate(plan.practice)}
    results = session.submit_practice(store, lesson_id, decision["concept_id"], plan.practice,
                                      practice_answers, decision["decision_id"])
    print(f"    practice: {sum(results)}/{len(results)} correct")

analysis = timed("Waiting for Quiz B (written in the background)", session.finish_quiz_b,
                 store, lesson_id, quiz_b_future)
session.submit_quiz(store, lesson_id, "quiz_b", {i: q.answer_index for i, q in enumerate(analysis.quiz_b)})
report = session.progress(store, lesson_id)
print("\nSIMULATED student, not real results:")
for r in report["concepts"]:
    fmt = lambda p: "  —" if p is None else f"{p:4.0%}"  # noqa: E731
    print(f"    {r['concept_id']}: Quiz A {fmt(r['quiz_a'])}  practice {fmt(r['practice'])}  Quiz B {fmt(r['quiz_b'])}")
print(f"    overall: Quiz A {report['quiz_a']:.0%} -> Quiz B {report['quiz_b']:.0%}")
print("FLOW OK")
