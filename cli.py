"""Terminal version of Learnova, for when the browser UI is not reachable.

    python cli.py --language Hindi
    python cli.py --lesson my_lesson.pdf --language Spanish --rounds 2
"""

import argparse
import sys

from learnova import session
from learnova.config import db_path
from learnova.lesson import sample_lesson, text_from_path
from learnova.store import Store


def ask(questions) -> dict[int, int | None]:
    answers = {}
    for i, q in enumerate(questions):
        print(f"\n{i + 1}. {q.question}")
        for j, opt in enumerate(q.options):
            print(f"   {'abcd'[j]}) {opt}")
        while True:
            raw = input("Your answer (a-d, Enter to skip): ").strip().lower()
            if raw == "":
                answers[i] = None
                break
            if raw in ("a", "b", "c", "d"):
                answers[i] = "abcd".index(raw)
                break
    return answers


def fmt(p):
    return "  —" if p is None else f"{p:4.0%}"


def print_progress(store, lesson_id):
    p = session.progress(store, lesson_id)
    print(f"\n=== Progress: {p['topic']} ===")
    print(f"{'Concept':40} {'Quiz A':>7} {'Practice':>9} {'Quiz B':>7} {'Mastery':>8}")
    for r in p["concepts"]:
        label = f"{r['concept']} ({r['english_term']})"[:40]
        print(f"{label:40} {fmt(r['quiz_a']):>7} {fmt(r['practice']):>9} {fmt(r['quiz_b']):>7} {fmt(r['mastery']):>8}")
    print(f"\nQuiz A overall: {fmt(p['quiz_a'])}   Quiz B overall: {fmt(p['quiz_b'])}")


def main():
    parser = argparse.ArgumentParser(description="Learnova in the terminal")
    parser.add_argument("--lesson", help="Path to a .txt, .md or .pdf lesson (default: sample fractions lesson)")
    parser.add_argument("--language", default="Hindi")
    parser.add_argument("--name", default="Student")
    parser.add_argument("--rounds", type=int, default=2, help="Maximum tutoring rounds before Quiz B")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Hindi/Arabic text on Windows consoles

    store = Store(db_path())
    text = text_from_path(args.lesson) if args.lesson else sample_lesson()

    print("Content Agent is reading the lesson and writing two matching quizzes...")
    lesson_id = session.start_lesson(store, args.name, args.language, text)
    _, analysis = store.get_lesson(lesson_id)
    print(f"\nTopic: {analysis.topic}")
    for c in analysis.concepts:
        print(f" - {c.name} ({c.english_term})")

    print("\n##### Diagnostic Quiz A #####")
    score = session.submit_quiz(store, lesson_id, "quiz_a", ask(analysis.quiz_a))
    print(f"\nQuiz A score: {score:.0%}")

    for _ in range(args.rounds):
        print("\nAssessment Agent is choosing what to study next...")
        d = session.next_step(store, lesson_id)
        if d is None:
            print("Every concept is mastered.")
            break
        plan = d["plan"]
        print(f"\n##### Studying {d['concept_id']} [{d['source']}] #####")
        print(f"Why: {d['reason']}\n")
        print(plan.explanation)
        print(f"\nWorked example:\n{plan.worked_example}")
        if plan.glossary:
            print("\nKey terms:")
            for g in plan.glossary:
                print(f"  {g.english} = {g.translation}")
        answers = ask(plan.practice)
        results = session.submit_practice(store, lesson_id, d["concept_id"], plan.practice, answers, d["decision_id"])
        for q, ok in zip(plan.practice, results):
            print(f"\n{'✓' if ok else '✗'} {q.question}")
            if not ok:
                print(f"  Hint: {q.hint}\n  Solution: {q.solution}")
        if input("\nAnother tutoring round? (y/N): ").strip().lower() != "y":
            break

    print("\n##### Follow-up Quiz B #####")
    session.submit_quiz(store, lesson_id, "quiz_b", ask(analysis.quiz_b))
    print_progress(store, lesson_id)


if __name__ == "__main__":
    main()
