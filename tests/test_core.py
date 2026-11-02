"""Tests for the deterministic parts: quiz checks, grading, mastery and storage.
Run with:  python -m unittest discover tests
"""

import unittest
from unittest import mock

from learnova import session, speech
import random

from learnova.grading import check_diagnostic, check_quizzes, mastery_report, shuffle_options, weakest_concept
from learnova.schemas import Concept, LessonAnalysis, PracticeQuestion, QuizQuestion, TutoringPlan
from learnova.store import Store


def q(cid, diff, text, answer=0):
    return QuizQuestion(concept_id=cid, difficulty=diff, question=text,
                        options=["A", "B", "C", "D"], answer_index=answer, explanation="...")


def analysis():
    return LessonAnalysis(
        topic="Fractions",
        concepts=[
            Concept(id="c1", name="Equivalent fractions", english_term="equivalent fractions", summary="..."),
            Concept(id="c2", name="Adding unlike fractions", english_term="common denominator",
                    summary="...", prerequisite_ids=["c1"]),
        ],
        quiz_a=[q("c1", 1, "a1"), q("c1", 2, "a2"), q("c2", 1, "a3"), q("c2", 2, "a4")],
        quiz_b=[q("c1", 1, "b1"), q("c1", 2, "b2"), q("c2", 1, "b3"), q("c2", 2, "b4")],
    )


class CheckQuizzesTest(unittest.TestCase):
    def test_parallel_quizzes_pass(self):
        self.assertEqual(check_quizzes(analysis()), [])

    def test_mismatched_difficulty_fails(self):
        a = analysis()
        a.quiz_b[3] = q("c2", 3, "b4")
        self.assertTrue(any("same (concept_id, difficulty)" in p for p in check_quizzes(a)))

    def test_reused_question_fails(self):
        a = analysis()
        a.quiz_b[0] = q("c1", 1, "a1")
        self.assertTrue(any("both quizzes" in p for p in check_quizzes(a)))

    def test_unknown_concept_fails(self):
        a = analysis()
        a.quiz_a[0] = q("c9", 1, "a1")
        self.assertTrue(any("unknown concept_id" in p for p in check_quizzes(a)))

    def test_shuffle_keeps_correct_answer_and_spreads_positions(self):
        questions = [QuizQuestion(concept_id="c1", difficulty=1, question=f"q{i}", options=["right", "w1", "w2", "w3"],
                                  answer_index=0, explanation="...") for i in range(40)]
        shuffled = shuffle_options(questions, random.Random(1))
        self.assertTrue(all(s.options[s.answer_index] == "right" for s in shuffled))
        self.assertTrue(all(sorted(s.options) == sorted(q.options) for s, q in zip(shuffled, questions)))
        self.assertEqual(len({s.answer_index for s in shuffled}), 4)

    def test_diagnostic_checked_without_quiz_b(self):
        a = analysis().model_copy(update={"quiz_b": []})
        self.assertEqual(check_diagnostic(a), [])
        self.assertTrue(any("quiz_b must contain" in p for p in check_quizzes(a)))

    def test_concept_without_diagnostic_question_fails(self):
        a = analysis()
        a.quiz_a = a.quiz_a[:2]
        self.assertTrue(any("no diagnostic question" in p for p in check_diagnostic(a)))


class SpeechTest(unittest.TestCase):
    def test_speakable_strips_markdown_and_direction_marks(self):
        lri, pdi, nl = chr(0x2066), chr(0x2069), chr(10)
        text = f"**नियम:** अंश {lri}(numerator){pdi}{nl}- पहला कदम{nl}# Title"
        self.assertEqual(speech.speakable(text), "नियम: अंश (numerator) पहला कदम Title")

    def test_only_languages_with_a_voice_get_read_aloud(self):
        with mock.patch.dict("os.environ", {"READ_ALOUD": "on"}):
            self.assertTrue(speech.available("Hindi"))
            self.assertFalse(speech.available("Swahili"))
        with mock.patch.dict("os.environ", {"READ_ALOUD": "off"}):
            self.assertFalse(speech.available("Hindi"))

    def test_falls_back_to_standard_voice(self):
        from botocore.exceptions import ClientError

        calls = []

        def synthesize_speech(**kwargs):
            calls.append(kwargs["Engine"])
            if kwargs["Engine"] == "neural":
                raise ClientError({"Error": {"Code": "ValidationException", "Message": "engine"}}, "SynthesizeSpeech")
            return {"AudioStream": mock.Mock(read=lambda: b"mp3")}

        speech.synthesize.cache_clear()
        with mock.patch("boto3.client", return_value=mock.Mock(synthesize_speech=synthesize_speech)):
            self.assertEqual(speech.synthesize("hello", "English"), b"mp3")
        self.assertEqual(calls, ["neural", "standard"])


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.lesson_id = self.store.create_lesson("Asha", "Hindi", "lesson text", analysis())

    def test_quiz_grading_and_improvement(self):
        # Quiz A: c1 both right, c2 both wrong -> 50%
        score_a = session.submit_quiz(self.store, self.lesson_id, "quiz_a", {0: 0, 1: 0, 2: 1, 3: None})
        self.assertEqual(score_a, 0.5)
        score_b = session.submit_quiz(self.store, self.lesson_id, "quiz_b", {0: 0, 1: 0, 2: 0, 3: 1})
        self.assertEqual(score_b, 0.75)
        p = session.progress(self.store, self.lesson_id)
        c2 = next(r for r in p["concepts"] if r["concept_id"] == "c2")
        self.assertEqual((c2["quiz_a"], c2["quiz_b"]), (0.0, 0.5))

    def test_weakest_concept_respects_prerequisites(self):
        # Both concepts weak; c2 is weaker but depends on c1, so c1 comes first.
        session.submit_quiz(self.store, self.lesson_id, "quiz_a", {0: 0, 1: 1, 2: 1, 3: 1})
        _, a = self.store.get_lesson(self.lesson_id)
        report = mastery_report(a, self.store.attempts(self.lesson_id))
        self.assertEqual(weakest_concept(report)["concept_id"], "c1")

    def test_everything_mastered_returns_none(self):
        session.submit_quiz(self.store, self.lesson_id, "quiz_a", {0: 0, 1: 0, 2: 0, 3: 0})
        _, a = self.store.get_lesson(self.lesson_id)
        self.assertIsNone(weakest_concept(mastery_report(a, self.store.attempts(self.lesson_id))))

    def test_quiz_b_written_in_background_is_saved(self):
        full = analysis()
        lesson_id = self.store.create_lesson("Asha", "Hindi", "lesson text", full.model_copy(update={"quiz_b": []}))
        with mock.patch("learnova.agents.content.write_follow_up", return_value=full) as write:
            future = session.start_quiz_b(self.store, lesson_id)
            session.finish_quiz_b(self.store, lesson_id, future)
        self.assertEqual(write.call_args.args[1:], ("lesson text", "Hindi"))
        _, saved = self.store.get_lesson(lesson_id)
        self.assertEqual([x.question for x in saved.quiz_b], ["b1", "b2", "b3", "b4"])

    def test_perfect_latest_practice_means_move_on(self):
        practice = [PracticeQuestion(question=f"p{i}", options=["1", "2", "3", "4"], answer_index=0,
                                     hint="h", solution="s") for i in range(3)]
        # c1 known, c2 missed on Quiz A
        session.submit_quiz(self.store, self.lesson_id, "quiz_a", {0: 0, 1: 0, 2: 1, 3: 1})
        session.submit_practice(self.store, self.lesson_id, "c2", practice, {0: 0, 1: 1, 2: 1}, round_no=1)
        _, a = self.store.get_lesson(self.lesson_id)
        report = mastery_report(a, self.store.attempts(self.lesson_id))
        self.assertEqual(weakest_concept(report)["concept_id"], "c2")  # 1/3: still needs work

        session.submit_practice(self.store, self.lesson_id, "c2", practice, {0: 0, 1: 0, 2: 0}, round_no=2)
        report = mastery_report(a, self.store.attempts(self.lesson_id))
        c2 = next(r for r in report if r["concept_id"] == "c2")
        self.assertEqual(c2["last_practice"], 1.0)
        self.assertFalse(c2["mastered"])  # 4/8 overall
        self.assertTrue(c2["ready"])      # but 3/3 in the latest round
        self.assertIsNone(weakest_concept(report))

    def test_practice_moves_mastery_and_plan_round_trips(self):
        session.submit_quiz(self.store, self.lesson_id, "quiz_a", {0: 0, 1: 0, 2: 1, 3: 1})
        plan = TutoringPlan(
            concept_id="c2", explanation="हर (denominator) ...", worked_example="1/4 + 1/6 = 5/12",
            glossary=[], practice=[PracticeQuestion(question=f"p{i}", options=["1", "2", "3", "4"],
                                                    answer_index=2, hint="h", solution="s") for i in range(3)],
        )
        decision_id = self.store.record_decision(self.lesson_id, "c2", 1, "reason", plan)
        _, loaded = self.store.latest_plan(self.lesson_id)
        self.assertEqual(loaded.explanation, plan.explanation)
        results = session.submit_practice(self.store, self.lesson_id, "c2", loaded.practice,
                                          {0: 2, 1: 2, 2: 2}, decision_id)
        self.assertEqual(results, [True, True, True])
        c2 = next(r for r in session.progress(self.store, self.lesson_id)["concepts"] if r["concept_id"] == "c2")
        self.assertEqual(c2["practice"], 1.0)
        self.assertAlmostEqual(c2["mastery"], 3 / 5)


if __name__ == "__main__":
    unittest.main()
