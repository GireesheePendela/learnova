"""Deterministic grading, mastery scores and quiz checks. No LLM is involved here."""

from collections import Counter, defaultdict

from .schemas import LessonAnalysis

MASTERY_THRESHOLD = 0.8


def is_correct(answer_index: int, chosen_index: int | None) -> bool:
    return chosen_index is not None and chosen_index == answer_index


def concept_scores(attempts, phases: tuple[str, ...]) -> dict[str, tuple[int, int]]:
    """(correct, total) per concept over the given phases."""
    scores: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in attempts:
        if a["phase"] in phases:
            scores[a["concept_id"]][0] += a["correct"]
            scores[a["concept_id"]][1] += 1
    return {cid: (c, t) for cid, (c, t) in scores.items()}


def pct(correct: int, total: int) -> float | None:
    return None if total == 0 else correct / total


def mastery_report(analysis: LessonAnalysis, attempts) -> list[dict]:
    """One row per concept: diagnostic, practice, follow-up and current mastery."""
    pre = concept_scores(attempts, ("quiz_a",))
    practice = concept_scores(attempts, ("practice",))
    post = concept_scores(attempts, ("quiz_b",))
    # Current mastery uses everything seen so far, so practice moves it too.
    current = concept_scores(attempts, ("quiz_a", "practice", "quiz_b"))
    rows = []
    for c in analysis.concepts:
        cur = pct(*current.get(c.id, (0, 0)))
        rows.append({
            "concept_id": c.id,
            "concept": c.name,
            "english_term": c.english_term,
            "prerequisites": c.prerequisite_ids,
            "quiz_a": pct(*pre.get(c.id, (0, 0))),
            "practice": pct(*practice.get(c.id, (0, 0))),
            "quiz_b": pct(*post.get(c.id, (0, 0))),
            "mastery": cur,
            "mastered": cur is not None and cur >= MASTERY_THRESHOLD,
        })
    return rows


def overall(attempts, phase: str) -> float | None:
    rows = [a for a in attempts if a["phase"] == phase]
    return pct(sum(a["correct"] for a in rows), len(rows))


def weakest_concept(report: list[dict]) -> dict | None:
    """Deterministic fallback: lowest current mastery, unmastered prerequisites first."""
    unmastered = [r for r in report if r["mastery"] is not None and not r["mastered"]]
    if not unmastered:
        return None
    ids = {r["concept_id"] for r in unmastered}
    roots = [r for r in unmastered if not ids.intersection(r["prerequisites"])] or unmastered
    return min(roots, key=lambda r: r["mastery"])


def _check_questions(name: str, quiz, ids: set[str]) -> list[str]:
    problems = []
    for i, q in enumerate(quiz):
        if q.concept_id not in ids:
            problems.append(f"{name}[{i}] uses unknown concept_id '{q.concept_id}'.")
        if len({o.strip().lower() for o in q.options}) != len(q.options):
            problems.append(f"{name}[{i}] has duplicate options.")
    return problems


def check_diagnostic(analysis: LessonAnalysis) -> list[str]:
    """Problems with the concepts or Quiz A alone. Empty list means OK."""
    problems = []
    ids = {c.id for c in analysis.concepts}
    if len(ids) != len(analysis.concepts):
        problems.append("Concept ids are not unique.")
    if not analysis.quiz_a:
        problems.append("quiz_a must contain questions.")
    problems += _check_questions("quiz_a", analysis.quiz_a, ids)
    missing = ids - {q.concept_id for q in analysis.quiz_a}
    if missing:
        problems.append(f"Concepts with no diagnostic question: {sorted(missing)}.")
    return problems


def check_quizzes(analysis: LessonAnalysis) -> list[str]:
    """Problems that make Quiz A and Quiz B not comparable. Empty list means OK."""
    problems = check_diagnostic(analysis)
    ids = {c.id for c in analysis.concepts}
    if not analysis.quiz_b:
        problems.append("quiz_b must contain questions.")
    problems += _check_questions("quiz_b", analysis.quiz_b, ids)

    blueprint_a = Counter((q.concept_id, q.difficulty) for q in analysis.quiz_a)
    blueprint_b = Counter((q.concept_id, q.difficulty) for q in analysis.quiz_b)
    if blueprint_a != blueprint_b:
        problems.append(
            "quiz_a and quiz_b must cover the same (concept_id, difficulty) pairs the same number of times. "
            f"quiz_a: {dict(blueprint_a)}; quiz_b: {dict(blueprint_b)}."
        )

    reused = {q.question.strip().lower() for q in analysis.quiz_a} & {q.question.strip().lower() for q in analysis.quiz_b}
    if reused:
        problems.append(f"{len(reused)} question(s) appear in both quizzes; quiz_b must use new questions.")
    return problems
