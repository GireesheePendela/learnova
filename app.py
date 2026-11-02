"""Learnova Streamlit app. Run with:  streamlit run app.py"""

import pandas as pd
import streamlit as st

from learnova import session
from learnova.config import db_path
from learnova.lesson import LANGUAGES, sample_lesson, text_from_upload
from learnova.store import Store

st.set_page_config(page_title="Learnova", page_icon="📘", layout="wide")


@st.cache_resource
def get_store() -> Store:
    return Store(db_path())


store = get_store()
state = st.session_state
state.setdefault("stage", "setup")


def fmt(p):
    return "—" if p is None else f"{p:.0%}"


def go(stage: str):
    state.stage = stage
    st.rerun()


def quiz_form(questions, key: str):
    """Render multiple-choice questions; returns {index: chosen option index} on submit, else None."""
    with st.form(key):
        answers = {}
        for i, q in enumerate(questions):
            answers[i] = st.radio(f"**{i + 1}.** {q.question}", options=range(len(q.options)),
                                  format_func=lambda j, q=q: q.options[j], index=None, key=f"{key}_{i}")
        if st.form_submit_button("Submit answers", type="primary"):
            return answers
    return None


def show_progress(lesson_id: int):
    p = session.progress(store, lesson_id)
    c1, c2, c3 = st.columns(3)
    c1.metric("Diagnostic Quiz A", fmt(p["quiz_a"]))
    delta = None
    if p["quiz_a"] is not None and p["quiz_b"] is not None:
        delta = f"{(p['quiz_b'] - p['quiz_a']) * 100:+.0f} points"
    c2.metric("Follow-up Quiz B", fmt(p["quiz_b"]), delta)
    c3.metric("Tutoring rounds", p["tutoring_rounds"])
    df = pd.DataFrame([{
        "Concept": f"{r['concept']} ({r['english_term']})",
        "Quiz A": fmt(r["quiz_a"]), "Practice": fmt(r["practice"]),
        "Quiz B": fmt(r["quiz_b"]), "Mastery": fmt(r["mastery"]),
        "Status": "✅ mastered" if r["mastered"] else ("—" if r["mastery"] is None else "📈 learning"),
    } for r in p["concepts"]])
    st.dataframe(df, hide_index=True, width="stretch")
    if p["quiz_b"] is not None:
        chart = pd.DataFrame({
            "Quiz A": [r["quiz_a"] or 0 for r in p["concepts"]],
            "Quiz B": [r["quiz_b"] or 0 for r in p["concepts"]],
        }, index=[r["english_term"] for r in p["concepts"]])
        st.bar_chart(chart, stack=False)
    st.caption("Scores are this student's immediate performance in this session, not a controlled study.")


st.title("📘 Learnova")
st.caption("Concept-level adaptive bilingual tutoring, powered by three Strands agents.")

# 1. Setup
if state.stage == "setup":
    name = st.text_input("Your first name", value="Student")
    language = st.selectbox("Language you learn best in", LANGUAGES)
    source = st.radio("Lesson", ["Use the sample fractions lesson", "Upload my own lesson (.txt, .md, .pdf)"])
    lesson_text = None
    if source.startswith("Use"):
        lesson_text = sample_lesson()
        with st.expander("Preview sample lesson"):
            st.markdown(lesson_text)
    else:
        upload = st.file_uploader("Lesson file", type=["txt", "md", "pdf"])
        if upload:
            try:
                lesson_text = text_from_upload(upload.name, upload.getvalue())
            except ValueError as e:
                st.error(str(e))
    if st.button("Start diagnostic quiz", type="primary", disabled=not lesson_text):
        with st.spinner("Content Agent is reading the lesson and writing your diagnostic quiz…"):
            try:
                state.lesson_id = session.start_lesson(store, name, language, lesson_text)
            except Exception as e:  # surface model/credential errors in the UI during the demo
                st.error(f"Could not prepare the lesson: {e}")
                st.stop()
        # Quiz B is written in the background while the student takes Quiz A.
        state.quiz_b_future = session.start_quiz_b(store, state.lesson_id)
        go("quiz_a")

lesson_id = state.get("lesson_id")
if lesson_id is not None:
    row, analysis = store.get_lesson(lesson_id)
    with st.sidebar:
        st.subheader(analysis.topic)
        st.write(f"{row['student']} · {row['language']} + English")
        st.markdown("**Concepts**")
        for c in analysis.concepts:
            st.write(f"- {c.name} *({c.english_term})*")
        if st.button("Start over"):
            for k in list(state.keys()):
                del state[k]
            st.rerun()

# 2. Diagnostic
if state.stage == "quiz_a":
    st.header("Diagnostic Quiz A")
    st.write("No pressure: this only shows the tutor where to start.")
    answers = quiz_form(analysis.quiz_a, "quiz_a")
    if answers is not None:
        session.submit_quiz(store, lesson_id, "quiz_a", answers)
        go("decide")

# 3. Assessment Agent decides what to study
if state.stage == "decide":
    with st.spinner("Assessment Agent is checking your answers and choosing what to study next…"):
        state.decision = session.next_step(store, lesson_id)
    go("learn" if state.decision else "quiz_b")

# 4. Tutoring round
if state.stage == "learn":
    d = state.decision
    plan = d["plan"]
    concept = next(c for c in analysis.concepts if c.id == d["concept_id"])
    st.header(f"Let's work on: {concept.name} ({concept.english_term})")
    st.info(f"**Why this concept:** {d['reason']}")
    with st.expander("How the agents decided"):
        st.write(f"Decided by: `{d['source']}`")
        st.write(f"Focus given to the Tutor Agent: {d['focus']}")
        st.write(f"Practice difficulty: {d['difficulty']} / 3")
        if d.get("agent_note"):
            st.write(f"Assessment Agent: {d['agent_note']}")

    st.markdown(plan.explanation)
    st.subheader("Worked example")
    st.markdown(plan.worked_example)
    if plan.glossary:
        st.subheader("Key terms")
        st.table(pd.DataFrame([{"English": g.english, row["language"]: g.translation} for g in plan.glossary]))

    st.subheader("Practice")
    results_key = f"results_{d['decision_id']}"
    if results_key not in state:
        answers = quiz_form(plan.practice, f"practice_{d['decision_id']}")
        if answers is not None:
            state[results_key] = (answers, session.submit_practice(
                store, lesson_id, d["concept_id"], plan.practice, answers, d["decision_id"]))
            st.rerun()
    else:
        answers, results = state[results_key]
        for i, (q, ok) in enumerate(zip(plan.practice, results)):
            st.markdown(f"**{i + 1}.** {q.question}")
            if ok:
                st.success(f"Correct: {q.options[q.answer_index]}")
            else:
                st.warning(f"Hint: {q.hint}")
                with st.expander("Show solution"):
                    st.markdown(q.solution)
        c1, c2 = st.columns(2)
        if c1.button("Get my next recommendation", type="primary"):
            go("decide")
        if c2.button("I'm ready for follow-up Quiz B"):
            go("quiz_b")

# 5. Follow-up
if state.stage == "quiz_b":
    if not analysis.quiz_b:
        if "quiz_b_future" not in state:
            state.quiz_b_future = session.start_quiz_b(store, lesson_id)
        with st.spinner("Content Agent is finishing your follow-up quiz…"):
            try:
                analysis = session.finish_quiz_b(store, lesson_id, state.quiz_b_future)
            except Exception as e:
                del state["quiz_b_future"]
                st.error(f"Could not write Quiz B: {e}")
                st.button("Try again")
                st.stop()
    st.header("Follow-up Quiz B")
    if state.get("decision") is None:
        st.success("The Assessment Agent found every concept mastered. Let's confirm with Quiz B.")
    st.write("Same concepts and difficulty as Quiz A, new questions.")
    answers = quiz_form(analysis.quiz_b, "quiz_b")
    if answers is not None:
        session.submit_quiz(store, lesson_id, "quiz_b", answers)
        go("report")

# 6. Progress
if state.stage == "report":
    st.header("Your learning progress")
    show_progress(lesson_id)
    if st.button("Keep practising weak concepts"):
        go("decide")
elif lesson_id is not None and state.stage in ("learn", "quiz_b"):
    with st.expander("Progress so far"):
        show_progress(lesson_id)
