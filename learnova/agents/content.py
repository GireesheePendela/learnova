"""Content Agent: lesson text -> concepts + Quiz A, then a parallel Quiz B.

The work is split in two calls so the student can start Quiz A while Quiz B is still
being written (see session.start_quiz_b)."""

from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from ..grading import check_diagnostic, check_quizzes, shuffle_options
from ..schemas import DiagnosticDraft, FollowUpQuiz, LessonAnalysis
from .common import make_agent, structured

try:
    from strands.types.exceptions import StructuredOutputException
except ImportError:  # older Strands versions raise ValidationError directly
    StructuredOutputException = ValidationError

T = TypeVar("T", bound=BaseModel)

ROLE = """You are the Content Agent of Learnova, a tutor for students who have little
access to tutoring and who learn best in a language other than English."""

QUESTION_RULES = """Rules for every question:
- Exactly 4 options, exactly one correct, answer_index pointing to it. Vary which position
  holds the correct option.
- Wrong options should reflect real misconceptions (for fractions, e.g. adding denominators).
- Solve each question yourself before writing answer_index, and put a short solution (one or two
  sentences) in explanation.
  Never refer to options by letter or position ("option b"); options are shuffled afterwards.
- Only test what the lesson teaches.
- Write questions, options, explanations and concept names in the student's language and its
  usual script (Devanagari for Hindi, Bengali script for Bengali, Arabic script for Arabic,
  simplified characters for Chinese), keeping the English academic term in parentheses the first
  time it appears, e.g. "हर (denominator)". If the student's language is English, just write English.
- Address the student informally and consistently (e.g. तुम in Hindi, tú in Spanish).
"""

DIAGNOSTIC_PROMPT = f"""{ROLE}

From the lesson you are given:
1. Identify 3 to 5 core concepts the lesson teaches, in teaching order. Give each a short id
   ('c1', 'c2', ...), its English academic term, and prerequisite_ids for concepts that must be
   understood first.
2. Write a diagnostic quiz (quiz_a) with exactly 2 multiple-choice questions per concept:
   one difficulty 1 and one difficulty 2.

{QUESTION_RULES}"""

FOLLOW_UP_PROMPT = f"""{ROLE}

You are given a lesson, its concepts and a diagnostic quiz (quiz_a). Write a follow-up quiz
(quiz_b) that is a parallel form of quiz_a: for every quiz_a question, in the same order, one
quiz_b question on the same concept_id at the same difficulty, testing the same skill with
different numbers or context. Never reuse a quiz_a question.

{QUESTION_RULES}"""


def _generate(system_prompt: str, output_model: type[T], prompt: str,
              check: Callable[[T], list[str]], max_attempts: int) -> T:
    """Ask for output_model, re-asking with the problems listed until check() passes."""
    problems: list[str] = []
    for _ in range(max_attempts):
        request = prompt
        if problems:
            request += "\n\nYour previous answer had these problems; fix all of them:\n- " + "\n- ".join(problems)
        try:
            result = structured(make_agent(system_prompt, output_model=output_model, role="content"),
                                output_model, request)
        except ValidationError as e:
            problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]]
            continue
        except StructuredOutputException as e:
            problems = [str(e)[:1000]]
            continue
        problems = check(result)
        if not problems:
            return result
    raise ValueError("Content Agent could not produce valid quizzes: " + "; ".join(problems))


def draft_diagnostic(lesson_text: str, language: str, max_attempts: int = 2) -> LessonAnalysis:
    """Concepts and Quiz A. The returned analysis has an empty quiz_b."""
    prompt = f"Student's language: {language}\n\nLesson:\n<lesson>\n{lesson_text}\n</lesson>"

    def as_analysis(draft: DiagnosticDraft) -> LessonAnalysis:
        return LessonAnalysis(topic=draft.topic, concepts=draft.concepts, quiz_a=draft.quiz_a, quiz_b=[])

    draft = _generate(DIAGNOSTIC_PROMPT, DiagnosticDraft, prompt,
                      lambda d: check_diagnostic(as_analysis(d)), max_attempts)
    analysis = as_analysis(draft)
    return analysis.model_copy(update={"quiz_a": shuffle_options(analysis.quiz_a)})


def write_follow_up(analysis: LessonAnalysis, lesson_text: str, language: str,
                    max_attempts: int = 2) -> LessonAnalysis:
    """Quiz B for a drafted analysis. Returns the analysis with quiz_b filled in."""
    prompt = (
        f"Student's language: {language}\n\n"
        f"Concepts:\n{[c.model_dump() for c in analysis.concepts]}\n\n"
        f"quiz_a:\n{[q.model_dump() for q in analysis.quiz_a]}\n\n"
        f"Lesson:\n<lesson>\n{lesson_text}\n</lesson>"
    )

    def with_quiz_b(follow_up: FollowUpQuiz) -> LessonAnalysis:
        return analysis.model_copy(update={"quiz_b": follow_up.quiz_b})

    follow_up = _generate(FOLLOW_UP_PROMPT, FollowUpQuiz, prompt,
                          lambda f: check_quizzes(with_quiz_b(f)), max_attempts)
    return analysis.model_copy(update={"quiz_b": shuffle_options(follow_up.quiz_b)})
