"""Content Agent: lesson text -> concepts + parallel Quiz A / Quiz B."""

from ..grading import check_quizzes
from ..schemas import LessonAnalysis
from .common import make_agent, structured

SYSTEM_PROMPT = """You are the Content Agent of Learnova, a tutor for students who have little
access to tutoring and who learn best in a language other than English.

From the lesson you are given:
1. Identify 3 to 5 core concepts the lesson teaches, in teaching order. Give each a short id
   ('c1', 'c2', ...), its English academic term, and prerequisite_ids for concepts that must be
   understood first.
2. Write a diagnostic quiz (quiz_a) with exactly 2 multiple-choice questions per concept:
   one difficulty 1 and one difficulty 2.
3. Write a follow-up quiz (quiz_b) that is a parallel form of quiz_a: for every quiz_a question,
   one quiz_b question on the same concept at the same difficulty, testing the same skill with
   different numbers or context. Never reuse a quiz_a question.

Rules for every question:
- Exactly 4 options, exactly one correct, answer_index pointing to it.
- Wrong options should reflect real misconceptions (for fractions, e.g. adding denominators).
- Solve each question yourself before writing answer_index, and put the solution in explanation.
- Only test what the lesson teaches.
- Write questions, options and concept names in the student's language, keeping the English
  academic term in parentheses the first time it appears, e.g. "हर (denominator)".
"""


def analyze_lesson(lesson_text: str, language: str, max_attempts: int = 2) -> LessonAnalysis:
    prompt = f"Student's language: {language}\n\nLesson:\n<lesson>\n{lesson_text}\n</lesson>"
    problems: list[str] = []
    for _ in range(max_attempts):
        request = prompt
        if problems:
            request += "\n\nYour previous answer had these problems; fix all of them:\n- " + "\n- ".join(problems)
        analysis = structured(make_agent(SYSTEM_PROMPT), LessonAnalysis, request)
        problems = check_quizzes(analysis)
        if not problems:
            return analysis
    raise ValueError("Content Agent could not produce comparable quizzes: " + "; ".join(problems))
