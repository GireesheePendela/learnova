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

from learnova.config import AGENT_ROLES, get_model, provider  # noqa: E402

print(f"MODEL_PROVIDER={provider()}  BEDROCK_MODEL_ID={os.getenv('BEDROCK_MODEL_ID', '(Strands default)')}  "
      f"AWS_REGION={os.getenv('AWS_REGION', '(default)')}")

# Check each distinct model once; agents without an override share the default.
models: dict[str, list[str]] = {}
for role in AGENT_ROLES:
    models.setdefault(str(get_model(role=role).get_config().get("model_id")), []).append(role)

failed = False
for model_id, roles in models.items():
    model = get_model(role=roles[0])
    print(f"\n{', '.join(roles)} agent: model_id={model_id}  "
          f"max_tokens={model.get_config().get('max_tokens', '(provider default)')}")
    start = time.time()
    try:
        reply = Agent(model=model, callback_handler=None)(
            "Translate the math word 'denominator' into Hindi. Reply with the Hindi word only.")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        failed = True
        continue
    print(f"  OK in {time.time() - start:.1f}s: {str(reply).strip()}")

if failed:
    print("\nHints: AccessDenied or model not found -> pick an id from scripts/list_models.py; "
          "region errors -> set AWS_REGION; credentials errors -> run inside the workshop environment.")
    raise SystemExit(1)
