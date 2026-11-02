"""Quick check that the configured model answers, before running anything long.

    python scripts/check_model.py
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from strands import Agent  # noqa: E402

from learnova.config import get_model, provider  # noqa: E402

print(f"MODEL_PROVIDER={provider()}  BEDROCK_MODEL_ID={os.getenv('BEDROCK_MODEL_ID', '(Strands default)')}  "
      f"AWS_REGION={os.getenv('AWS_REGION', '(default)')}")
start = time.time()
try:
    reply = Agent(model=get_model(), callback_handler=None)(
        "Translate the math word 'denominator' into Hindi. Reply with the Hindi word only.")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    print("Hints: AccessDenied -> set BEDROCK_MODEL_ID to a model the account can use; "
          "region errors -> set AWS_REGION; credentials errors -> run inside the workshop environment.")
    raise SystemExit(1)
print(f"OK in {time.time() - start:.1f}s: {str(reply).strip()}")
