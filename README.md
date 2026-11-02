# Learnova

**Concept-level adaptive bilingual tutoring for underserved students**, built with the
[Strands Agents SDK](https://strandsagents.com) and Amazon Bedrock.

Many students have no access to a tutor, and many learn best in a language other than the
one their exams are written in. Learnova finds exactly which concepts a student hasn't
understood, teaches those concepts in the student's language while keeping the English
academic terms, and adapts practice to how they actually perform. The student never has to
work out what to ask: the system keeps a concept-level mastery record and decides what comes next.

## How it works

```
Lesson (sample, .txt/.md, or PDF) + student's language
        │
        ▼
Content Agent ── extracts 3–5 concepts (with prerequisites)
                 writes parallel Quiz A and Quiz B (same concept × difficulty blueprint)
                 └─ deterministic check rejects non-comparable quizzes and asks the agent to fix them
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
Follow-up Quiz B ── progress view: Quiz A vs Quiz B per concept
```

| Agent | Role | Strands features used |
|---|---|---|
| Content Agent | Lesson → concepts + parallel quizzes | Structured output (Pydantic), validate-and-retry loop |
| Assessment Agent | Decides what to study next | Tools over the SQLite mastery record; calls the Tutor Agent as a tool |
| Tutor Agent | Bilingual teaching and practice | Structured output |

Design choices:
- **Grading is deterministic.** Every question has a structured answer key; the LLM never decides whether an answer is right.
- **Quizzes are comparable by construction.** Quiz B must match Quiz A's (concept, difficulty) blueprint, with no reused questions. This is checked in code.
- **The session never stalls.** If the model skips the tool call, a deterministic version of the same policy picks the concept, and the UI shows which path made the decision.
- **One setting switches the model provider** (`MODEL_PROVIDER=bedrock|ollama`). No agent code changes.

## Run it

### In the AWS workshop sandbox (Bedrock)

```bash
git clone https://github.com/GireesheePendela/learnova.git
cd learnova
pip install -r requirements.txt
cp .env.example .env        # set BEDROCK_MODEL_ID to a model the sandbox can use
python -m unittest discover tests
python scripts/check_model.py          # ~10s: confirms Bedrock access and the model id
python scripts/smoke_content.py Hindi  # Content Agent only: concepts + parallel quizzes
python scripts/smoke_flow.py Hindi     # whole session with a simulated student
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
cli.py                     Terminal UI
learnova/config.py         Model provider switch
learnova/agents/           content.py, assessment.py, tutor.py, common.py
learnova/grading.py        Grading, mastery, quiz comparability checks (no LLM)
learnova/store.py          SQLite: lessons, attempts, tutoring decisions
learnova/session.py        Workflow shared by both UIs
data/sample_fractions.md   Built-in sample lesson
tests/                     Unit tests for the deterministic parts
```

## Measuring impact honestly

Learnova reports each student's Quiz A and Quiz B scores per concept. These are immediate,
within-session changes on parallel quizzes. They are not a controlled study and do not show
long-term retention. Any results in the project write-up are labelled with how they were collected
(real students vs. simulated runs) and how many sessions they cover.

## Limitations and next steps

- Text-based PDFs only (scanned pages would need OCR, e.g. Amazon Textract).
- Progress lasts as long as the SQLite file. In the sandbox that is one session.
- Planned: read-aloud with Amazon Polly, Bedrock Guardrails, persistent storage (DynamoDB), spaced review across days.
