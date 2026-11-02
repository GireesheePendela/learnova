"""Check that Amazon Polly read-aloud works for each language that has a voice.

    python scripts/check_speech.py
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from learnova import speech  # noqa: E402

SAMPLES = {
    "Hindi": "हर (denominator) बताता है कि पूरे को कितने बराबर भागों में बाँटा गया है।",
    "Arabic": "المقام (denominator) يخبرنا بعدد الأجزاء المتساوية.",
    "Spanish": "El denominador (denominator) dice en cuántas partes iguales se divide el entero.",
    "Portuguese": "O denominador (denominator) diz em quantas partes iguais o todo é dividido.",
    "Chinese (Simplified)": "分母 (denominator) 表示整体被分成几个相等的部分。",
    "English": "The denominator tells us how many equal parts the whole is divided into.",
}

print(f"READ_ALOUD enabled: {speech.enabled()}  AWS_REGION={os.getenv('AWS_REGION', '(default)')}\n")
failed = False
for language, text in SAMPLES.items():
    start = time.time()
    try:
        audio = speech.synthesize(text, language)
    except Exception as e:
        print(f"FAILED {language:22} {type(e).__name__}: {e}"[:160])
        failed = True
        continue
    print(f"OK     {language:22} {len(audio) / 1024:5.0f} KB of audio in {time.time() - start:.1f}s")

print("\nNo Polly voice (no Listen button): Bengali, Swahili, Vietnamese, Tagalog")
if failed:
    print("AccessDenied -> the account may not allow Polly; the app then just hides read-aloud errors.")
    raise SystemExit(1)
