"""Learnova Streamlit app. Run with:  streamlit run app.py"""

import html
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from learnova import session, speech
from learnova.config import db_path
from learnova.lesson import LANGUAGES, RTL_LANGUAGES, SAMPLES, sample_lesson, text_from_upload
from learnova.store import Store

st.set_page_config(page_title="Learnova", page_icon="📘", layout="wide")
st.html(f"<style>{(Path(__file__).parent / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>")

DEEP, BROWN = "#326080", "#805232"
STEPS = [("setup", "Lesson"), ("quiz_a", "Diagnostic"), ("learn", "Learn"),
         ("quiz_b", "Follow-up"), ("report", "Progress")]


@st.cache_resource
def get_store() -> Store:
    return Store(db_path())


store = get_store()
state = st.session_state
state.setdefault("stage", "setup")


# ---------- small helpers ----------

def fmt(p):
    return "—" if p is None else f"{p:.0%}"


def term(name: str, english: str) -> str:
    """'name (english)' with the English part isolated, so its brackets stay in place in Arabic text."""
    return f"{name} {chr(0x2066)}({english}){chr(0x2069)}"  # left-to-right isolate ... pop


def go(stage: str):
    state.stage = stage
    st.rerun()


def scroll_to_top():
    """Streamlit keeps the scroll position between pages; jump back up so loading messages are seen."""
    components.html("""<script>
      const doc = window.parent.document;
      for (const el of [doc.querySelector('[data-testid="stMain"]'),
                        doc.querySelector('[data-testid="stAppViewContainer"]'), doc.documentElement]) {
        if (el) el.scrollTo({top: 0, behavior: 'instant'});
      }
    </script>""", height=0)


def title(eyebrow: str, heading: str, sub: str = ""):
    st.html(f'<div class="lv-title"><small>{html.escape(eyebrow)}</small><h2>{html.escape(heading)}</h2>'
            f'{f"<p>{html.escape(sub)}</p>" if sub else ""}</div>')


def card(heading: str, body: str, number: int | None = None):
    num = f'<span class="lv-num">{number}</span>' if number else ""
    st.html(f'<div class="lv-card"><h4>{num}{html.escape(heading)}</h4><p>{html.escape(body)}</p></div>')


def loading(heading: str, body: str):
    """Full-width loading card at the top of the page while an agent works."""
    st.html(f'<div class="lv-loading"><div class="lv-spinner"></div><h3>{html.escape(heading)}</h3>'
            f'<p>{html.escape(body)}</p><div class="lv-bar"><span></span></div></div>')


def concept_bars(report: list[dict]) -> str:
    """One progress bar per concept, with Quiz A / practice / Quiz B chips."""
    rows = []
    for r in report:
        mastery = r["mastery"] or 0
        up = r["quiz_a"] is not None and r["quiz_b"] is not None and r["quiz_b"] > r["quiz_a"]
        chips = (f'<span class="lv-chip">A {fmt(r["quiz_a"])}</span>'
                 f'<span class="lv-chip">Practice {fmt(r["practice"])}</span>'
                 f'<span class="lv-chip{" up" if up else ""}">B {fmt(r["quiz_b"])}</span>')
        rows.append(
            f'<div class="lv-concept"><div class="lv-concept-head">'
            f'<span class="lv-concept-name">{html.escape(term(r["concept"], r["english_term"]))}</span>'
            f'<span>{"✓ " if r["mastered"] else ""}{fmt(r["mastery"])}</span></div>'
            f'<div class="lv-track"><div class="lv-fill{" mastered" if r["mastered"] else ""}" '
            f'style="width:{mastery * 100:.0f}%"></div></div><div class="lv-chips">{chips}</div></div>')
    return "".join(rows)


def listen(key: str, text: str, language: str):
    """A Listen button that reads text aloud with Amazon Polly in the student's language."""
    if not speech.available(language):
        return
    audio_key = f"audio_{key}"
    clicked = st.button("🔊 Listen", key=f"listen_{key}", help="Read this aloud")
    if clicked:
        try:
            state[audio_key] = speech.synthesize(text, language)
        except Exception as e:  # read-aloud is a nice-to-have; never break the lesson over it
            st.caption(f"Read-aloud isn't available right now ({type(e).__name__}).")
    if audio_key in state:
        st.audio(state[audio_key], format="audio/mpeg", autoplay=clicked)


def quiz_text(questions) -> str:
    """Questions and their options as one passage for read-aloud."""
    return " ".join(f"{i + 1}. {q.question} " + " ; ".join(q.options) + "." for i, q in enumerate(questions))


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


def review(questions, attempts):
    """Each question with the student's answer, the correct answer and the worked solution."""
    for i, (q, a) in enumerate(zip(questions, attempts[-len(questions):])):
        ok = bool(a["correct"])
        tag = '<span class="lv-tag right">Correct</span>' if ok else '<span class="lv-tag wrong">Not yet</span>'
        yours = html.escape(a["chosen"] or "(skipped)")
        st.html(f'<div class="lv-card lv-review {"right" if ok else "wrong"}">'
                f'<h4>{i + 1}. {html.escape(q.question)}{tag}</h4>'
                f'<p>Your answer: <b>{yours}</b></p>'
                f'{"" if ok else f"<p>Correct answer: <b>{html.escape(q.options[q.answer_index])}</b></p>"}'
                f'<p>{html.escape(q.explanation)}</p></div>')


# ---------- navigation ----------

lesson_id = state.get("lesson_id")
done_a = bool(lesson_id and store.attempts(lesson_id, "quiz_a"))
done_b = bool(lesson_id and store.attempts(lesson_id, "quiz_b"))
unlocked = {"setup": True, "quiz_a": lesson_id is not None, "learn": done_a, "quiz_b": done_a, "report": done_b}
current = {"decide": "learn", "preparing": "setup"}.get(state.stage, state.stage)

with st.container(key="nav"):
    cols = st.columns([2.2] + [1.25] * len(STEPS))
    cols[0].html('<div class="lv-brand"><span class="lv-mark">L</span>Learnova</div>')
    for col, (key, label) in zip(cols[1:], STEPS):
        if col.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary",
                      disabled=not unlocked[key] or state.stage in ("preparing", "decide"), width="stretch"):
            # "Learn" opens the latest tutoring round, or asks the Assessment Agent for one.
            go("decide" if key == "learn" and not state.get("decision") else key)

# Jump to the top whenever the page changes, so loading messages are always in view.
if state.get("shown_stage") != state.stage:
    scroll_to_top()
    state.shown_stage = state.stage

if lesson_id is not None:
    row, analysis = store.get_lesson(lesson_id)
    if row["language"] in RTL_LANGUAGES:
        st.html('<span class="lv-rtl"></span>')  # switches lesson content to right-to-left (see style.css)
    with st.sidebar:
        st.markdown(f"### {analysis.topic}")
        st.caption(f"{row['student']} · {row['language']} + English")
        st.markdown("**Your progress**")
        st.html(concept_bars(session.progress(store, lesson_id)["concepts"]))
        if st.button("Start a new lesson", width="stretch"):
            for k in list(state.keys()):
                del state[k]
            st.rerun()

# ---------- 1. Setup ----------
if state.stage == "setup":
    st.html('<div class="lv-hero"><span class="lv-eyebrow">Adaptive bilingual tutoring</span>'
            '<h1>Learn in <span class="lv-grad">your language</span>.<br>Ace it in English.</h1>'
            "<p>Learnova finds exactly which concepts you haven't understood yet, teaches them in your "
            "language with the English terms your exams use, and adapts practice to how you do.</p>"
            '<div class="lv-badges"><span class="lv-badge">10 languages</span>'
            '<span class="lv-badge">Concept-level diagnosis</span><span class="lv-badge">Quiz A → Quiz B progress</span>'
            "</div></div>")
    if lesson_id is not None:
        st.info("You already have a lesson in progress. Use the steps above to go back to it, "
                "or start a new one below (this replaces the current session).")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(key="card_start"):
            st.markdown("#### Start a session")
            name = st.text_input("Your name (optional)", placeholder="e.g. Asha",
                                 help="Only shown on your progress page and report. You can leave it empty.")
            language = st.selectbox("Language you learn best in", LANGUAGES)
            upload_label = "Upload my own lesson (.txt, .md, .pdf)"
            source = st.radio("Lesson", [f"Sample: {s}" for s in SAMPLES] + [upload_label])
            lesson_text = None
            if source != upload_label:
                lesson_text = sample_lesson(source.removeprefix("Sample: "))
                with st.expander("Preview this lesson"):
                    st.markdown(lesson_text)
            else:
                upload = st.file_uploader("Lesson file", type=["txt", "md", "pdf"])
                if upload:
                    try:
                        lesson_text = text_from_upload(upload.name, upload.getvalue())
                    except ValueError as e:
                        st.error(str(e))
            if st.button("Start diagnostic quiz", type="primary", disabled=not lesson_text, width="stretch"):
                for k in [k for k in state.keys() if k != "stage"]:
                    del state[k]
                state.pending = {"name": name.strip() or "Student", "language": language, "lesson_text": lesson_text}
                go("preparing")
    with right:
        st.markdown("#### How it works")
        card("Content Agent", "Reads the lesson, finds its key concepts and writes two matching quizzes.", 1)
        card("Assessment Agent", "Checks every answer and decides which concept you should study next.", 2)
        card("Tutor Agent", "Explains that concept in your language, with a worked example and practice.", 3)

# ---------- Preparing the lesson (Content Agent) ----------
if state.stage == "preparing":
    loading("Preparing your diagnostic quiz",
            "The Content Agent is reading the lesson, finding its key concepts and writing questions "
            "in your language. This takes about a minute.")
    p = state.pending
    try:
        state.lesson_id = session.start_lesson(store, p["name"], p["language"], p["lesson_text"])
    except Exception as e:  # surface model/credential errors in the UI during the demo
        st.error(f"Could not prepare the lesson: {e}")
        if st.button("Back to start"):
            go("setup")
        st.stop()
    # Quiz B is written in the background while the student takes Quiz A.
    state.quiz_b_future = session.start_quiz_b(store, state.lesson_id)
    go("quiz_a")

# ---------- 2. Diagnostic ----------
if state.stage == "quiz_a":
    if not done_a:
        title("Step 1 · Diagnostic", "Quiz A", "No pressure: this only shows the tutor where to start.")
        listen(f"quiz_a_{lesson_id}", quiz_text(analysis.quiz_a), row["language"])
        answers = quiz_form(analysis.quiz_a, "quiz_a")
        if answers is not None:
            session.submit_quiz(store, lesson_id, "quiz_a", answers)
            go("decide")
    else:
        score = session.progress(store, lesson_id)["quiz_a"]
        title("Step 1 · Diagnostic", f"Quiz A review · {fmt(score)}", "Your answers, the correct ones and why.")
        review(analysis.quiz_a, store.attempts(lesson_id, "quiz_a"))
        if st.button("Continue learning", type="primary"):
            go("decide" if not state.get("decision") else "learn")

# ---------- 3. Assessment Agent decides what to study ----------
if state.stage == "decide":
    loading("Choosing what you should study next",
            "The Assessment Agent is checking your answers, and the Tutor Agent is preparing a short "
            "lesson and practice questions for you.")
    state.decision = session.next_step(store, lesson_id)
    go("learn" if state.decision else "quiz_b")

# ---------- 4. Tutoring round ----------
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
        listen(f"lesson_{d['decision_id']}", f"{plan.explanation} {plan.worked_example}", row["language"])
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
        listen(f"practice_{d['decision_id']}", quiz_text(plan.practice), row["language"])
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

# ---------- 5. Follow-up ----------
if state.stage == "quiz_b":
    if not analysis.quiz_b:
        if "quiz_b_future" not in state:
            state.quiz_b_future = session.start_quiz_b(store, lesson_id)
        placeholder = st.empty()
        with placeholder.container():
            loading("Finishing your follow-up quiz", "The Content Agent is writing Quiz B: same concepts, new questions.")
        try:
            analysis = session.finish_quiz_b(store, lesson_id, state.quiz_b_future)
        except Exception as e:
            del state["quiz_b_future"]
            st.error(f"Could not write Quiz B: {e}")
            st.button("Try again")
            st.stop()
        placeholder.empty()
    if not done_b:
        title("Step 3 · Follow-up", "Quiz B", "Same concepts and difficulty as Quiz A, new questions.")
        if state.get("decision") is None:
            st.success("The Assessment Agent found every concept mastered. Let's confirm with Quiz B.")
        listen(f"quiz_b_{lesson_id}", quiz_text(analysis.quiz_b), row["language"])
        answers = quiz_form(analysis.quiz_b, "quiz_b")
        if answers is not None:
            session.submit_quiz(store, lesson_id, "quiz_b", answers)
            go("report")
    else:
        score = session.progress(store, lesson_id)["quiz_b"]
        title("Step 3 · Follow-up", f"Quiz B review · {fmt(score)}", "Your answers, the correct ones and why.")
        review(analysis.quiz_b, store.attempts(lesson_id, "quiz_b"))
        if st.button("See my progress", type="primary"):
            go("report")

# ---------- 6. Progress ----------
if state.stage == "report":
    p = session.progress(store, lesson_id)
    title("Step 4 · Progress", "Your learning progress", "Quiz A before tutoring, Quiz B after, concept by concept.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Diagnostic Quiz A", fmt(p["quiz_a"]))
    delta = None
    if p["quiz_a"] is not None and p["quiz_b"] is not None:
        delta = f"{(p['quiz_b'] - p['quiz_a']) * 100:+.0f} points"
    c2.metric("Follow-up Quiz B", fmt(p["quiz_b"]), delta)
    c3.metric("Tutoring rounds", p["tutoring_rounds"])

    bars_col, chart_col = st.columns([1, 1], gap="large")
    with bars_col:
        st.markdown("#### Mastery by concept")
        st.html(f'<div class="lv-card">{concept_bars(p["concepts"])}</div>')
    with chart_col:
        st.markdown("#### Quiz A vs Quiz B")
        chart = pd.DataFrame({
            "Quiz A": [r["quiz_a"] or 0 for r in p["concepts"]],
            "Quiz B": [r["quiz_b"] or 0 for r in p["concepts"]],
        }, index=[r["english_term"] for r in p["concepts"]])
        st.bar_chart(chart, stack=False, horizontal=True, color=[DEEP, BROWN])

    table = pd.DataFrame([{
        "Concept": f"{r['concept']} ({r['english_term']})",
        "Quiz A": fmt(r["quiz_a"]), "Practice": fmt(r["practice"]),
        "Quiz B": fmt(r["quiz_b"]), "Mastery": fmt(r["mastery"]),
        "Status": "mastered" if r["mastered"] else ("—" if r["mastery"] is None else "learning"),
    } for r in p["concepts"]])
    b1, b2, b3 = st.columns(3)
    if b1.button("Keep practising weak concepts", type="primary", width="stretch"):
        go("decide")
    if b2.button("Review Quiz B answers", width="stretch"):
        go("quiz_b")
    b3.download_button("Download report (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"learnova_{row['student']}_report.csv", mime="text/csv", width="stretch")
    st.caption("Scores are this student's immediate performance in this session, not a controlled study.")

st.html('<div class="lv-footer"><span><b>Learnova</b> · Concept-level adaptive bilingual tutoring</span>'
        "<span>Built with Strands Agents on Amazon Bedrock</span></div>")
