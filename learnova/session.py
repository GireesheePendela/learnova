"""The learning-session workflow shared by the Streamlit app and the CLI.

Agent modules are imported lazily so grading and storage work (and can be tested)
without the Strands SDK installed.
"""

from concurrent.futures import Future, ThreadPoolExecutor

from .grading import is_correct, mastery_report, overall
from .schemas import PracticeQuestion, QuizQuestion
from .schemas import LessonAnalysis
from .store import Store

# Writes Quiz B while the student takes Quiz A. The worker only calls the model;
# the database is read and written on the caller's thread.
_background = ThreadPoolExecutor(max_workers=4)


def start_lesson(store: Store, student: str, language: str, lesson_text: str) -> int:
    """Content Agent step 1: concepts and Quiz A. Follow with start_quiz_b."""
    from .agents.content import draft_diagnostic

    analysis = draft_diagnostic(lesson_text, language)
    return store.create_lesson(student, language, lesson_text, analysis)


def start_quiz_b(store: Store, lesson_id: int) -> Future:
    """Content Agent step 2, in the background: a Quiz B parallel to Quiz A."""
    from .agents.content import write_follow_up

    row, analysis = store.get_lesson(lesson_id)
    return _background.submit(write_follow_up, analysis, row["lesson_text"], row["language"])


def finish_quiz_b(store: Store, lesson_id: int, future: Future) -> LessonAnalysis:
    """Wait for start_quiz_b's result and save it. Re-raises the Content Agent's error, if any."""
    analysis = future.result()
    store.update_analysis(lesson_id, analysis)
    return analysis


def submit_quiz(store: Store, lesson_id: int, phase: str, answers: dict[int, int | None]) -> float:
    """Grade quiz_a or quiz_b against the answer key. answers maps question index -> chosen option index."""
    _, analysis = store.get_lesson(lesson_id)
    quiz: list[QuizQuestion] = analysis.quiz_a if phase == "quiz_a" else analysis.quiz_b
    for i, q in enumerate(quiz):
        chosen = answers.get(i)
        store.record_attempt(lesson_id, phase, q.concept_id, q.question,
                             q.options[chosen] if chosen is not None else None,
                             is_correct(q.answer_index, chosen))
    return overall(store.attempts(lesson_id), phase)


def submit_practice(store: Store, lesson_id: int, concept_id: str, practice: list[PracticeQuestion],
                    answers: dict[int, int | None], round_no: int) -> list[bool]:
    results = []
    for i, q in enumerate(practice):
        chosen = answers.get(i)
        ok = is_correct(q.answer_index, chosen)
        store.record_attempt(lesson_id, "practice", concept_id, q.question,
                             q.options[chosen] if chosen is not None else None, ok, round_no)
        results.append(ok)
    return results


def next_step(store: Store, lesson_id: int) -> dict | None:
    from .agents.assessment import recommend_next

    return recommend_next(store, lesson_id)


def progress(store: Store, lesson_id: int) -> dict:
    _, analysis = store.get_lesson(lesson_id)
    attempts = store.attempts(lesson_id)
    return {
        "topic": analysis.topic,
        "quiz_a": overall(attempts, "quiz_a"),
        "quiz_b": overall(attempts, "quiz_b"),
        "concepts": mastery_report(analysis, attempts),
        "tutoring_rounds": len(store.decisions(lesson_id)),
    }
