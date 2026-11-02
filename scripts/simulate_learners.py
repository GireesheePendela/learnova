"""Run Learnova for four SIMULATED learners and report what the agents decided for each.

    python scripts/simulate_learners.py

Each learner has a language, a lesson and a fixed set of concepts they already know. They answer
Quiz A from that knowledge, get 1 of 3 practice questions right in their first round and all 3 in
later rounds. The point is to show how the agents adapt (which concept, why, in which language,
when they move on); the scores are produced by these rules, so they are NOT learning results.
Quiz B is not taken for the same reason. Takes about 5-10 minutes: each step is printed as it
happens, then a summary per learner and a Markdown table at the end.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova import session  # noqa: E402
from learnova.lesson import sample_lesson  # noqa: E402
from learnova.store import Store  # noqa: E402

ROUNDS = 3

# knows: which concepts (by position in the lesson, 0 = first) the learner already understands.
LEARNERS = [
    {"name": "Learner 1", "language": "Hindi", "lesson": "Fractions (math)", "knows": lambda n: {0},
     "profile": "knows only the first concept"},
    {"name": "Learner 2", "language": "Arabic", "lesson": "Fractions (math)", "knows": lambda n: {0, 1},
     "profile": "knows the first two concepts"},
    {"name": "Learner 3", "language": "Spanish", "lesson": "Photosynthesis (science)", "knows": lambda n: set(),
     "profile": "knows none of the concepts"},
    {"name": "Learner 4", "language": "Swahili", "lesson": "Photosynthesis (science)",
     "knows": lambda n: set(range(n - 1)), "profile": "knows all but the last concept"},
]


def log(learner: dict, message: str):
    print(f"[{learner['name']} · {learner['language']}] {message}", flush=True)


def run(learner: dict) -> dict:
    log(learner, f"started: {learner['lesson']}, {learner['profile']}. Content Agent is writing Quiz A…")
    store = Store(":memory:")
    out = {**learner, "rounds": [], "error": None}
    start = time.time()
    try:
        lesson_id = session.start_lesson(store, learner["name"], learner["language"], sample_lesson(learner["lesson"]))
        out["quiz_a_seconds"] = time.time() - start
        log(learner, f"Quiz A ready in {out['quiz_a_seconds']:.0f}s")
        quiz_b = session.start_quiz_b(store, lesson_id)
        _, analysis = store.get_lesson(lesson_id)
        ids = [c.id for c in analysis.concepts]
        known = {ids[i] for i in learner["knows"](len(ids))}
        out["concepts"] = [f"{c.id} {c.english_term}" for c in analysis.concepts]
        out["prereqs"] = {c.id: c.prerequisite_ids for c in analysis.concepts}
        answers = {i: q.answer_index if q.concept_id in known else (q.answer_index + 1) % 4
                   for i, q in enumerate(analysis.quiz_a)}
        out["quiz_a"] = session.submit_quiz(store, lesson_id, "quiz_a", answers)
        log(learner, f"answered Quiz A: {out['quiz_a']:.0%}. Assessment Agent is choosing round 1…")

        practised: set[str] = set()
        for _ in range(ROUNDS):
            t = time.time()
            d = session.next_step(store, lesson_id)
            if d is None:
                out["rounds"].append({"concept": "all ready → Quiz B"})
                log(learner, "Assessment Agent: every concept is ready, moving on to Quiz B")
                break
            first_time = d["concept_id"] not in practised
            practised.add(d["concept_id"])
            right = 1 if first_time else 3
            plan = d["plan"]
            practice = {i: q.answer_index if i < right else (q.answer_index + 1) % 4 for i, q in enumerate(plan.practice)}
            session.submit_practice(store, lesson_id, d["concept_id"], plan.practice, practice, d["decision_id"])
            out["rounds"].append({"concept": d["concept_id"], "source": d["source"], "difficulty": d["difficulty"],
                                  "reason": d["reason"], "practice": f"{right}/3", "seconds": time.time() - t})
            log(learner, f"round {len(out['rounds'])}: chose {d['concept_id']} via {d['source']} in "
                         f"{time.time() - t:.0f}s, practice {right}/3")
        t = time.time()
        session.finish_quiz_b(store, lesson_id, quiz_b)
        out["quiz_b_wait"] = time.time() - t
        log(learner, "done")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
        log(learner, f"FAILED: {out['error']}")
    return out


def report(r: dict):
    print(f"\n=== {r['name']} · {r['language']} · {r['lesson']} · {r['profile']} ===")
    if r["error"]:
        print(f"FAILED: {r['error']}")
        return
    print(f"concepts: {r['concepts']}")
    print(f"prerequisites: {r['prereqs']}")
    print(f"Quiz A ready in {r['quiz_a_seconds']:.0f}s · score {r['quiz_a']:.0%} (from the profile)")
    for i, rd in enumerate(r["rounds"], 1):
        if "source" not in rd:
            print(f"  round {i}: {rd['concept']}")
            continue
        print(f"  round {i}: {rd['concept']} via {rd['source']} · difficulty {rd['difficulty']} · "
              f"practice {rd['practice']} · {rd['seconds']:.0f}s")
        print(f"           reason: {rd['reason'][:160]}")
    print(f"Quiz B extra wait: {r['quiz_b_wait']:.0f}s")


print("Running 4 simulated learners, 2 at a time. Each step is printed as it happens.", flush=True)
print(flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(run, LEARNERS))
print()
print("#" * 30 + " Summary " + "#" * 30)
for r in results:
    report(r)

print("\nMarkdown table (SIMULATED learners: shows agent decisions, not learning results):\n")
print("| Learner | Language · lesson | Profile | Agent's choices, round by round | Decided by agent | Quiz A ready |")
print("|---|---|---|---|---|---|")
for r in results:
    if r["error"]:
        print(f"| {r['name']} | {r['language']} · {r['lesson']} | {r['profile']} | failed | | |")
        continue
    choices = " → ".join(f"{rd['concept']} (d{rd['difficulty']}, {rd['practice']})" if "source" in rd else rd["concept"]
                         for rd in r["rounds"])
    by_agent = sum(rd.get("source") == "assessment_agent" for rd in r["rounds"])
    total = sum("source" in rd for rd in r["rounds"])
    print(f"| {r['name']} | {r['language']} · {r['lesson']} | {r['profile']} | {choices} | "
          f"{by_agent}/{total} | {r['quiz_a_seconds']:.0f}s |")
