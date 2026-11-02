"""Learnova Streamlit app. Run with:  streamlit run app.py"""

import html
from pathlib import Path

import pandas as pd
import streamlit as st

from learnova import session
from learnova.config import db_path
from learnova.lesson import LANGUAGES, RTL_LANGUAGES, sample_lesson, text_from_upload
from learnova.store import Store

st.set_page_config(page_title="Learnova", page_icon="📘", layout="wide")
st.html(f"<style>{(Path(__file__).parent / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>")

VIOLET, AQUA = "#7C5CFF", "#22D3EE"
STEPS = [("setup", "Choose lesson"), ("quiz_a", "Diagnostic"), ("learn", "Learn"),
         ("quiz_b", "Follow-up"), ("report", "Progress")]


@st.cache_resource
def get_store() -> Store:
    return Store(db_path())


store = get_store()
state = st.session_state
state.setdefault("stage", "setup")


def fmt(p):
    return "—" if p is None else f"{p:.0%}"


def term(name: str, english: str) -> str:
    """'name (english)' with the English part isolated, so its brackets stay in place in Arabic text."""
    return f"{name} \u2066({english})\u2069"


def go(stage: str):
    state.stage = stage
    st.rerun()


def nav():
    """Brand plus a step indicator showing where the student is in the session."""
    current = "learn" if state.stage == "decide" else state.stage
    order = [key for key, _ in STEPS]
    pills = "".join(
        f'<span class="lv-step {"now" if key == current else "done" if order.index(key) < order.index(current) else ""}">'
        f"{label}</span>"
        for key, label in STEPS
    )
    st.html(f'<div class="lv-nav"><div class="lv-brand"><span class="lv-mark">L</span>Learnova</div>'
            f'<div class="lv-steps">{pills}</div></div>')


def title(eyebrow: str, heading: str, sub: str = ""):
    st.html(f'<div class="lv-title"><small>{html.escape(eyebrow)}</small><h2>{html.escape(heading)}</h2>'
            f'{f"<p>{html.escape(sub)}</p>" if sub else ""}</div>')


def card(heading: str, body: str, number: int | None = None, extra_class: str = ""):
    num = f'<span class="lv-num">{number}</span>' if number else ""
    st.html(f'<div class="lv-card {extra_class}"><h4>{num}{html.escape(heading)}</h4>'
            f"<p>{html.escape(body)}</p></div>")


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
        "Concept": term(r["concept"], r["english_term"]),
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
        st.bar_chart(chart, stack=False, horizontal=True, color=[VIOLET, AQUA])
    st.caption("Scores are this student's immediate performance in this session, not a controlled study.")


nav()

# 1. Setup
if state.stage == "setup":
    st.html('<div class="lv-hero"><span class="lv-eyebrow">Adaptive bilingual tutoring</span>'
            '<h1>Learn in <span class="lv-grad">your language</span>.<br>Ace it in English.</h1>'
            "<p>Learnova finds exactly which concepts you haven't understood yet, teaches them in your "
            "language with the English terms your exams use, and adapts practice to how you do.</p></div>")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(key="card_start"):
            st.markdown("#### Start a session")
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
            start = st.button("Start diagnostic quiz", type="primary", disabled=not lesson_text, width="stretch")
    with right:
        st.markdown("#### How it works")
        card("Content Agent", "Reads the lesson, finds its key concepts and writes two matching quizzes.", 1)
        card("Assessment Agent", "Checks every answer and decides which concept you should study next.", 2)
        card("Tutor Agent", "Explains that concept in your language, with a worked example and practice.", 3)
    if start:
        with st.spinner("The Content Agent is reading the lesson and writing your diagnostic quiz. "
                        "This takes about a minute…"):
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
    if row["language"] in RTL_LANGUAGES:
        st.html('<span class="lv-rtl"></span>')  # switches lesson content to right-to-left (see style.css)
    with st.sidebar:
        st.markdown(f"### {analysis.topic}")
        st.caption(f"{row['student']} · {row['language']} + English")
        st.markdown("**Concepts**")
        for c in analysis.concepts:
            st.markdown(f"- {term(c.name, c.english_term)}")
        if st.button("Start over", width="stretch"):
            for k in list(state.keys()):
                del state[k]
            st.rerun()

# 2. Diagnostic
if state.stage == "quiz_a":
    title("Step 1 · Diagnostic", "Quiz A", "No pressure: this only shows the tutor where to start.")
    answers = quiz_form(analysis.quiz_a, "quiz_a")
    if answers is not None:
        session.submit_quiz(store, lesson_id, "quiz_a", answers)
        go("decide")

# 3. Assessment Agent decides what to study
if state.stage == "decide":
    with st.spinner("The Assessment Agent is checking your answers and the Tutor Agent is preparing your lesson…"):
        state.decision = session.next_step(store, lesson_id)
    go("learn" if state.decision else "quiz_b")

# 4. Tutoring round
if state.stage == "learn":
    d = state.decision
    plan = d["plan"]
    concept = next(c for c in analysis.concepts if c.id == d["concept_id"])
    title("Step 2 · Learn", term(concept.name, concept.english_term))
    st.markdown(f"**Why this concept:** {d['reason']}")
    with st.expander("How the agents decided"):
        st.write(f"Decided by: `{d['source']}`")
        st.write(f"Focus given to the Tutor Agent: {d['focus']}")
        st.write(f"Practice difficulty: {d['difficulty']} / 3")
        if d.get("agent_note"):
            st.write(f"Assessment Agent: {d['agent_note']}")

    lesson_col, terms_col = st.columns([3, 2], gap="large")
    with lesson_col:
        with st.container(key="card_explanation"):
            st.markdown(plan.explanation)
        st.markdown("#### Worked example")
        with st.container(key="card_example"):
            st.markdown(plan.worked_example)
    with terms_col:
        if plan.glossary:
            st.markdown("#### Key terms")
            st.table(pd.DataFrame([{"English": g.english, row["language"]: g.translation} for g in plan.glossary]))

    st.markdown("#### Practice")
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
        if c1.button("Get my next recommendation", type="primary", width="stretch"):
            go("decide")
        if c2.button("I'm ready for follow-up Quiz B", width="stretch"):
            go("quiz_b")

# 5. Follow-up
if state.stage == "quiz_b":
    if not analysis.quiz_b:
        if "quiz_b_future" not in state:
            state.quiz_b_future = session.start_quiz_b(store, lesson_id)
        with st.spinner("The Content Agent is finishing your follow-up quiz…"):
            try:
                analysis = session.finish_quiz_b(store, lesson_id, state.quiz_b_future)
            except Exception as e:
                del state["quiz_b_future"]
                st.error(f"Could not write Quiz B: {e}")
                st.button("Try again")
                st.stop()
    title("Step 3 · Follow-up", "Quiz B", "Same concepts and difficulty as Quiz A, new questions.")
    if state.get("decision") is None:
        st.success("The Assessment Agent found every concept mastered. Let's confirm with Quiz B.")
    answers = quiz_form(analysis.quiz_b, "quiz_b")
    if answers is not None:
        session.submit_quiz(store, lesson_id, "quiz_b", answers)
        go("report")

# 6. Progress
if state.stage == "report":
    title("Step 4 · Progress", "Your learning progress", "Quiz A before tutoring, Quiz B after, concept by concept.")
    show_progress(lesson_id)
    if st.button("Keep practising weak concepts", type="primary"):
        go("decide")
elif lesson_id is not None and state.stage in ("learn", "quiz_b"):
    with st.expander("Progress so far"):
        show_progress(lesson_id)
