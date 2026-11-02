# Learnova

**Concept-level adaptive bilingual tutoring for underserved students**, built with the
[Strands Agents SDK](https://strandsagents.com) and Amazon Bedrock.

Many students have no access to a tutor, and many learn best in a language other than the
one their exams are written in. Learnova finds exactly which concepts a student hasn't
understood, teaches those concepts in the student's language while keeping the English
academic terms, and adapts practice to how they actually perform. The student never has to
work out what to ask: the system keeps a concept-level mastery record and decides what comes next.

It works in 10 languages (Hindi, Spanish, Bengali, Arabic, Portuguese, Swahili, Vietnamese,
Chinese, Tagalog, English), lays Arabic out right-to-left, reads lessons and quizzes aloud with
Amazon Polly for students who are more comfortable listening than reading, and runs on any lesson
the student or teacher uploads, not only the built-in math and science samples.

AWS services: **Amazon Bedrock** (the three agents' models) and **Amazon Polly** (read-aloud).
Students never need an account or pay anything; whoever hosts the app pays for its AWS usage.

## How it works

```
Lesson (sample, .txt/.md, or PDF) + student's language
        │
        ▼
Content Agent ── extracts 3–5 concepts (with prerequisites) and writes Quiz A
                 then, in the background while the student takes Quiz A, a parallel Quiz B
                 (same concept × difficulty blueprint)
                 ├─ deterministic checks reject invalid or non-comparable quizzes and ask the agent to fix them
                 └─ answer options are shuffled in code, so the correct answer's position is random
        │
        ▼
Diagnostic Quiz A ── graded against structured answer keys (no LLM grading)
        │
        ▼
Assessment Agent ── tools: get_mastery_report, get_mistakes, get_tutoring_history, assign_tutoring
   │                chooses the next concept (prerequisites first, lowest mastery, lower difficulty on repeat)
   │
   └─ assign_tutoring ──► Tutor Agent ── bilingual explanation, worked example, glossary,
                                         3 targeted practice questions with hints
        │
        ▼
Practice ── graded, recorded in SQLite, feeds the next Assessment Agent decision (loop)
        │
        ▼
Follow-up Quiz B ── progress view: Quiz A vs Quiz B per concept, answer review, CSV report
```

| Agent | Role | Strands features used |
|---|---|---|
| Content Agent | Lesson → concepts + parallel quizzes | Structured output (Pydantic), validate-and-retry loop, runs Quiz B in the background |
| Assessment Agent | Decides what to study next | Tools over the SQLite mastery record; calls the Tutor Agent as a tool (agents as tools) |
| Tutor Agent | Bilingual teaching and practice | Structured output |

All three agents share a retry strategy (a `ModelRetryStrategy` subclass) that also retries Bedrock's
temporary errors such as `serviceUnavailableException`, and each agent can use its own Bedrock model.

Design choices:
- **Grading is deterministic.** Every question has a structured answer key; the LLM never decides whether an answer is right.
- **Quizzes are comparable by construction.** Quiz B must match Quiz A's (concept, difficulty) blueprint, with no reused questions. This is checked in code.
- **The session never stalls.** If the model skips the tool call, a deterministic version of the same policy picks the concept, and the UI shows which path made the decision.
- **Fair quizzes.** Options are shuffled after generation, because models tend to put the correct answer in the same position.
- **Short waits.** Only concepts + Quiz A are on the student's critical path; Quiz B is written while they answer.
- **One setting switches the model provider** (`MODEL_PROVIDER=bedrock|ollama`). No agent code changes.
- **Each agent can use its own model** (`CONTENT_MODEL_ID`, `ASSESSMENT_MODEL_ID`, `TUTOR_MODEL_ID`), e.g. a larger
  model for the Content Agent, whose answer keys all grading depends on.

## Run it

### In the AWS workshop sandbox (Bedrock)

```bash
git clone https://github.com/GireesheePendela/learnova.git
cd learnova
pip install -r requirements.txt
cp .env.example .env        # works as is; optionally choose models (see list_models.py)
python -m unittest discover tests
python scripts/list_models.py          # models this account offers (to pick a larger one)
python scripts/check_model.py          # ~10s: confirms Bedrock access and each agent's model id
python scripts/check_speech.py         # ~10s: confirms Amazon Polly read-aloud works
python scripts/smoke_content.py Hindi  # Content Agent only: concepts + parallel quizzes
python scripts/smoke_content.py Hindi photosynthesis   # same, on the science sample
python scripts/smoke_languages.py      # Content Agent in every supported language (a few minutes)
python scripts/smoke_flow.py Hindi     # whole session with a simulated student
python scripts/simulate_learners.py    # 4 simulated learners: how the agents adapt to each (~5-10 min)
streamlit run app.py --server.port 8501 --server.headless true
```

If the sandbox editor forwards ports, open port 8501 from its ports/preview panel. If the browser
UI can't be reached, the CLI runs the same three-agent workflow.

### Locally with Ollama

```bash
pip install -r requirements.txt "strands-agents[ollama]"
ollama pull qwen2.5:7b
MODEL_PROVIDER=ollama streamlit run app.py
```

Small local models are slower and less reliable at tool calling and non-English text than Bedrock models.

## Project layout

```
app.py                     Streamlit UI
assets/style.css           Look and feel: Marina palette, layout, right-to-left Arabic
.streamlit/config.toml     Streamlit theme colours
cli.py                     Terminal UI
learnova/config.py         Model provider switch
learnova/agents/           content.py, assessment.py, tutor.py, common.py
learnova/grading.py        Grading, mastery, quiz comparability checks (no LLM)
learnova/store.py          SQLite: lessons, attempts, tutoring decisions
learnova/session.py        Workflow shared by both UIs
learnova/speech.py         Read-aloud with Amazon Polly
data/                      Built-in sample lessons (fractions, photosynthesis)
tests/                     Unit tests for the deterministic parts
```

## What the app does for the student

- **Start:** pick a language and a sample lesson (fractions or photosynthesis) or upload a .txt/.md/.pdf lesson. Name is optional.
- **Diagnostic Quiz A**, then a **Learn** page per concept: why this concept was chosen, a short explanation in
  the student's language with English terms kept, a worked example, a glossary and practice with hints.
- **🔊 Listen** buttons read the lesson, quizzes and practice aloud with Amazon Polly (Hindi, Arabic, Spanish,
  Portuguese, Chinese, English; the button is hidden for languages without a Polly voice).
- **Follow-up Quiz B** and a **Progress** page: Quiz A vs Quiz B per concept, mastery bars, answer review with
  explanations, and a downloadable CSV report for a teacher or parent.
- The step bar lets the student move back to any step already reached.

## Checks run in the AWS sandbox (Bedrock)

These confirm the pipeline works; they are not learning results.

- Content Agent output passes all quiz checks (`problems: []`); spot-checked answer keys were correct.
- All 10 languages produce quizzes in the right script (`scripts/smoke_languages.py`).
- In a full simulated session the Assessment Agent made every decision itself (no fallback), chose prerequisites
  first, and on a repeat lowered the focus to the student's specific mistake.
- Quiz B was ready before the student needed it (0 s wait).

## Measuring impact honestly

Learnova reports each student's Quiz A and Quiz B scores per concept. These are immediate,
within-session changes on parallel quizzes. They are not a controlled study and do not show
long-term retention. Any results in the project write-up are labelled with how they were collected
(real students vs. simulated runs) and how many sessions they cover.

## Limitations and next steps

- Text-based PDFs only (scanned pages would need OCR, e.g. Amazon Textract).
- Progress lasts as long as the SQLite file. In the sandbox that is one session.
- Read-aloud covers 6 of the 10 languages; Polly has no Bengali, Swahili, Vietnamese or Tagalog voice.
- Planned: Bedrock Guardrails, persistent storage (DynamoDB), spaced review across days.
