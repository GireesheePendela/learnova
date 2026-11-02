"""List the Bedrock models this AWS account and region offer, to choose a larger model.

    python scripts/list_models.py            # Anthropic models
    python scripts/list_models.py all        # every provider

Being listed does not prove access: put an id in .env and run scripts/check_model.py.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3  # noqa: E402

import learnova.config  # noqa: E402,F401  (loads .env)

show_all = len(sys.argv) > 1 and sys.argv[1] == "all"
region = os.getenv("AWS_REGION") or boto3.session.Session().region_name or "us-west-2"
bedrock = boto3.client("bedrock", region_name=region)

# Newer models are called through inference profiles (ids like 'global.anthropic...' or 'us.anthropic...').
profiles = []
for page in bedrock.get_paginator("list_inference_profiles").paginate(typeEquals="SYSTEM_DEFINED"):
    profiles += page["inferenceProfileSummaries"]
print(f"Inference profiles in {region} (use these ids for BEDROCK_MODEL_ID / CONTENT_MODEL_ID):")
for p in sorted(profiles, key=lambda p: p["inferenceProfileId"]):
    if show_all or "anthropic" in p["inferenceProfileId"]:
        print(f"  {p['inferenceProfileId']:60} {p['status']}")

models = bedrock.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
print(f"\nOn-demand foundation models in {region}:")
for m in sorted(models, key=lambda m: m["modelId"]):
    if "ON_DEMAND" in m.get("inferenceTypesSupported", []) and (show_all or m["providerName"] == "Anthropic"):
        print(f"  {m['modelId']:60} {m['modelName']}")
