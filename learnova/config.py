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


def provider() -> str:
    return os.getenv("MODEL_PROVIDER", "bedrock").lower()


def get_model(output_schema: dict | None = None):
    """output_schema: JSON schema the reply must follow. Bedrock models handle Strands'
    structured-output tool well, so it is only used to constrain Ollama models."""
    name = provider()

    if name == "bedrock":
        from strands.models import BedrockModel

        kwargs = {"temperature": float(os.getenv("TEMPERATURE", "0.3"))}
        # Leave model_id unset to use the Strands default; set it to whatever
        # model the sandbox account has access to.
        if os.getenv("BEDROCK_MODEL_ID"):
            kwargs["model_id"] = os.environ["BEDROCK_MODEL_ID"]
        if os.getenv("AWS_REGION"):
            kwargs["region_name"] = os.environ["AWS_REGION"]
        # Strands fills max_tokens for models it knows; for others Bedrock's per-model default
        # can be too small for a full bilingual quiz, so allow setting it explicitly.
        if os.getenv("MAX_TOKENS"):
            kwargs["max_tokens"] = int(os.environ["MAX_TOKENS"])
        return BedrockModel(**kwargs)

    if name == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model_id=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            temperature=float(os.getenv("TEMPERATURE", "0.3")),
            # Ollama's default 4096-token context is too small for a full quiz.
            options={"num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192"))},
            # Small local models rarely call the structured-output tool, so make
            # Ollama itself constrain the reply to the schema instead.
            additional_args={"format": output_schema} if output_schema else None,
        )

    raise ValueError(f"Unknown MODEL_PROVIDER '{name}'. Use 'bedrock' or 'ollama'.")


def db_path() -> str:
    return os.getenv("LEARNOVA_DB", "learnova.db")
