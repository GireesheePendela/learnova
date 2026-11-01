"""Model provider switch. Agents call get_model() and never name a provider themselves.

MODEL_PROVIDER=bedrock (default) uses Amazon Bedrock with the ambient AWS credentials,
which is what the workshop sandbox provides. MODEL_PROVIDER=ollama uses a local model.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def get_model():
    provider = os.getenv("MODEL_PROVIDER", "bedrock").lower()

    if provider == "bedrock":
        from strands.models import BedrockModel

        kwargs = {"temperature": float(os.getenv("TEMPERATURE", "0.3"))}
        # Leave model_id unset to use the Strands default; set it to whatever
        # model the sandbox account has access to.
        if os.getenv("BEDROCK_MODEL_ID"):
            kwargs["model_id"] = os.environ["BEDROCK_MODEL_ID"]
        if os.getenv("AWS_REGION"):
            kwargs["region_name"] = os.environ["AWS_REGION"]
        return BedrockModel(**kwargs)

    if provider == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model_id=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            temperature=float(os.getenv("TEMPERATURE", "0.3")),
        )

    raise ValueError(f"Unknown MODEL_PROVIDER '{provider}'. Use 'bedrock' or 'ollama'.")


def db_path() -> str:
    return os.getenv("LEARNOVA_DB", "learnova.db")
