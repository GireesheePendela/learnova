"""Tutor Agent: bilingual explanation, worked example and targeted practice for one concept."""

from ..schemas import Concept, TutoringPlan
from .common import make_agent, structured

SYSTEM_PROMPT = """You are the Tutor Agent of Learnova. You teach one concept at a time to a
student who learns best in their own language but is tested at school in English.

Bilingual rule: explain in the student's language, but keep every key English academic term
next to its translation, e.g. "हर (denominator)", so the student learns the vocabulary their
exams use. List those terms in the glossary.

Teaching rules:
- Start from the specific mistakes the student made and name the misconception kindly.
- Use short sentences, everyday examples from the student's likely context, and one worked example.
- Write 3 practice questions at the requested difficulty, aimed at those mistakes. Each has
  exactly 4 options, one correct answer_index (solve it yourself first), a hint that nudges
  without giving the answer away, and a step-by-step solution.
- If the student's language is English, still keep the glossary of key terms.
"""


def build_plan(concept: Concept, lesson_excerpt: str, language: str, difficulty: int,
               mistakes: list[dict], focus: str) -> TutoringPlan:
    mistake_lines = "\n".join(
        f"- Q: {m['question']} | student chose: {m['chosen']}" for m in mistakes
    ) or "- (no recorded mistakes; reinforce the concept)"
    prompt = (
        f"Student's language: {language}\n"
        f"Concept id: {concept.id}\nConcept: {concept.name} ({concept.english_term})\n"
        f"Summary: {concept.summary}\n"
        f"Practice difficulty: {difficulty} (1 = basic, 3 = challenging)\n"
        f"What to focus on (from the Assessment Agent): {focus}\n"
        f"Student's mistakes:\n{mistake_lines}\n\n"
        f"Lesson for reference:\n<lesson>\n{lesson_excerpt}\n</lesson>"
    )
    plan = structured(make_agent(SYSTEM_PROMPT, output_model=TutoringPlan), TutoringPlan, prompt)
    plan.concept_id = concept.id
    return plan
