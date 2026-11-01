"""Structured outputs exchanged between agents, the database and the UI."""

from pydantic import BaseModel, Field


class Concept(BaseModel):
    id: str = Field(description="Short stable id such as 'c1', 'c2'")
    name: str = Field(description="Concept name in the student's language")
    english_term: str = Field(description="The English academic term, e.g. 'denominator'")
    summary: str = Field(description="One or two sentences on what the concept means")
    prerequisite_ids: list[str] = Field(
        default_factory=list,
        description="Ids of concepts the student should understand first",
    )


class QuizQuestion(BaseModel):
    concept_id: str
    difficulty: int = Field(ge=1, le=3, description="1 = basic, 2 = standard, 3 = challenging")
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3, description="Index of the correct option")
    explanation: str = Field(description="Short worked solution")


class LessonAnalysis(BaseModel):
    """Content Agent output: the lesson's concepts plus two parallel quizzes."""

    topic: str
    concepts: list[Concept]
    quiz_a: list[QuizQuestion] = Field(description="Diagnostic quiz")
    quiz_b: list[QuizQuestion] = Field(
        description="Follow-up quiz: same concepts and difficulties as quiz_a, different questions"
    )


class GlossaryTerm(BaseModel):
    english: str
    translation: str


class PracticeQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    hint: str = Field(description="A nudge shown after a wrong answer; must not reveal the answer")
    solution: str = Field(description="Step-by-step solution")


class TutoringPlan(BaseModel):
    """Tutor Agent output for one concept."""

    concept_id: str
    explanation: str = Field(description="Explanation in the student's language, English terms kept")
    worked_example: str
    glossary: list[GlossaryTerm]
    practice: list[PracticeQuestion]
