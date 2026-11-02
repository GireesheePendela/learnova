"""Assessment Agent: reads the mastery record through tools, decides what the student studies
next, and hands that concept to the Tutor Agent (agents-as-tools)."""

import json

from strands import tool

from ..grading import mastery_report, weakest_concept
from ..store import Store
from . import tutor
from .common import make_agent

SYSTEM_PROMPT = """You are the Assessment Agent of Learnova. You decide what one student
should study next, based on evidence, so the student never has to diagnose their own gaps.

Always:
1. Call get_mastery_report and get_tutoring_history.
2. Call get_mistakes for the concepts you are considering.
3. Choose ONE concept using this policy:
   - A concept is "ready" when it is mastered (mastery 0.8 or above) OR its last_practice (the
     latest practice round) is 0.8 or above: the student just showed they can do it, even if
     older mistakes keep the average low. Never choose a ready concept; move on.
   - If a concept that is not ready has a prerequisite that is not ready, choose the prerequisite first.
   - Otherwise choose the lowest mastery among concepts that are not ready.
   - If the student was already tutored on a concept and its last practice is still low, choose it
     again with a LOWER difficulty (or the same if already 1) and a different focus.
4. Call assign_tutoring exactly once with a focus that names the specific misconception you saw
   in the mistakes, and a one-sentence reason a student can read. Base it on the most recent
   mistakes (get_mistakes marks them); do not say the student still makes a mistake they have
   since stopped making. Write the reason in the
   student's language and its usual script, keeping English academic terms in parentheses, and
   address the student informally (e.g. तुम in Hindi, tú in Spanish).

If every assessed concept is ready, do not call assign_tutoring; reply ALL_MASTERED.
After acting, reply with one short sentence in English explaining your decision (for the teacher).
"""


def recommend_next(store: Store, lesson_id: int) -> dict | None:
    """Run the Assessment Agent once. Returns the decision, or None if everything is mastered."""
    row, analysis = store.get_lesson(lesson_id)
    concepts = {c.id: c for c in analysis.concepts}
    assigned: dict = {}

    @tool
    def get_mastery_report() -> str:
        """Per-concept scores for this student as JSON: quiz_a (diagnostic), practice (all rounds),
        last_practice (latest round only), quiz_b (follow-up), mastery (all evidence so far),
        mastered, ready and prerequisite ids. Scores are fractions from 0 to 1, or null if not
        assessed yet."""
        return json.dumps(mastery_report(analysis, store.attempts(lesson_id)), ensure_ascii=False)

    @tool
    def get_mistakes(concept_id: str) -> str:
        """Questions the student answered wrongly for one concept, oldest first, with the option
        they chose and when: "quiz_a", "practice round N" or "quiz_b". "latest": true marks
        mistakes from the most recent practice round on this concept.

        Args:
            concept_id: Concept id such as 'c2'.
        """
        attempts = [a for a in store.attempts(lesson_id) if a["concept_id"] == concept_id]
        rounds = sorted({a["round"] for a in attempts if a["phase"] == "practice"})
        wrong = [
            {"when": f"practice round {rounds.index(a['round']) + 1}" if a["phase"] == "practice" else a["phase"],
             "latest": a["phase"] == "practice" and a["round"] == rounds[-1],
             "question": a["question"], "chosen": a["chosen"]}
            for a in attempts if not a["correct"]
        ]
        return json.dumps(wrong, ensure_ascii=False)

    @tool
    def get_tutoring_history() -> str:
        """Concepts already tutored in this session, oldest first, with difficulty and reason."""
        return json.dumps(
            [{"concept_id": d["concept_id"], "difficulty": d["difficulty"], "reason": d["reason"]}
             for d in store.decisions(lesson_id)],
            ensure_ascii=False,
        )

    @tool
    def assign_tutoring(concept_id: str, difficulty: int, focus: str, reason: str) -> str:
        """Hand one concept to the Tutor Agent, which writes a bilingual explanation and practice
        questions for it. Call exactly once.

        Args:
            concept_id: The concept the student should study next.
            difficulty: Practice difficulty, 1 (basic) to 3 (challenging).
            focus: The specific misconception or skill the Tutor Agent should target.
            reason: One sentence, written for the student, on why this concept is next.
        """
        if assigned:
            return "Tutoring was already assigned this round."
        if concept_id not in concepts:
            return f"Unknown concept_id '{concept_id}'. Valid ids: {sorted(concepts)}."
        assigned.update(_assign(store, lesson_id, row, analysis, concept_id, difficulty, focus, reason))
        return f"Tutor Agent prepared practice for {concept_id}."

    agent = make_agent(SYSTEM_PROMPT, tools=[get_mastery_report, get_mistakes, get_tutoring_history, assign_tutoring],
                       role="assessment")
    result = agent(f"Student's language: {row['language']}\nDecide what this student should study next.")
    if assigned:
        assigned["source"] = "assessment_agent"
        assigned["agent_note"] = str(result).strip()
        return assigned

    # The agent may decline because everything is mastered, or a small model may skip the tool
    # call. Fall back to the same policy deterministically so the session never stalls.
    weakest = weakest_concept(mastery_report(analysis, store.attempts(lesson_id)))
    if weakest is None:
        return None
    decision = _assign(store, lesson_id, row, analysis, weakest["concept_id"], 1,
                       f"Rebuild understanding of {weakest['english_term']} from the basics.",
                       f"{weakest['concept']} is your lowest-scoring concept so far.")
    decision["source"] = "fallback_policy"
    return decision


def _assign(store, lesson_id, row, analysis, concept_id, difficulty, focus, reason) -> dict:
    concept = next(c for c in analysis.concepts if c.id == concept_id)
    difficulty = max(1, min(3, int(difficulty)))
    mistakes = [
        {"question": a["question"], "chosen": a["chosen"]}
        for a in store.attempts(lesson_id)
        if a["concept_id"] == concept_id and not a["correct"]
    ]
    plan = tutor.build_plan(concept, row["lesson_text"], row["language"], difficulty, mistakes, focus)
    decision_id = store.record_decision(lesson_id, concept_id, difficulty, reason, plan)
    return {"decision_id": decision_id, "concept_id": concept_id, "difficulty": difficulty,
            "focus": focus, "reason": reason, "plan": plan}
