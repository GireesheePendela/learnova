"""Check that the Content Agent writes Quiz A in each supported language and script.

    python scripts/smoke_languages.py                  # every language in the app
    python scripts/smoke_languages.py Arabic Swahili   # just these

Runs up to 3 languages at a time (~30-60s each). Script/word checks are a rough signal:
read the sample question for each language too.
"""

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova.agents.content import draft_diagnostic  # noqa: E402
from learnova.lesson import LANGUAGES, sample_lesson  # noqa: E402

# A pattern the student's language should match in the quiz text.
SIGNS = {
    "Hindi": r"[ऀ-ॿ]",
    "Bengali": r"[ঀ-৿]",
    "Arabic": r"[؀-ۿ]",
    "Chinese (Simplified)": r"[一-鿿]",
    "Vietnamese": r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
    "Spanish": r"[áéíóúñ¿]|\b(el|la|los|las|de|una?)\b",
    "Portuguese": r"[ãõçâêô]|\b(o|os|as|de|um|uma|não)\b",
    "Swahili": r"\b(ni|ya|na|kwa|wa|sehemu)\b",
    "Tagalog": r"\b(ang|ng|mga|sa|ay|ito)\b",
    "English": r"\b(the|of|is|what)\b",
}


def run(language: str) -> tuple[str, str, float, str]:
    start = time.time()
    try:
        analysis = draft_diagnostic(sample_lesson(), language)
    except Exception as e:
        return language, "FAIL", time.time() - start, f"{type(e).__name__}: {e}"[:300]
    text = " ".join(q.question + " " + " ".join(q.options) for q in analysis.quiz_a)
    hits = len(re.findall(SIGNS[language], text, flags=re.IGNORECASE))
    status = "PASS" if hits >= 5 else "CHECK"
    return language, status, time.time() - start, f"{analysis.concepts[0].name} | {analysis.quiz_a[0].question}"


languages = sys.argv[1:] or LANGUAGES
unknown = [lang for lang in languages if lang not in SIGNS]
if unknown:
    raise SystemExit(f"Unknown language(s) {unknown}. Choose from: {list(SIGNS)}")

with ThreadPoolExecutor(max_workers=3) as pool:
    for language, status, seconds, detail in pool.map(run, languages):
        print(f"{status:5} {language:22} {seconds:4.0f}s  {detail}")
