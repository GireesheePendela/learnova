from typing import TypeVar

from pydantic import BaseModel
from strands import Agent

from ..config import get_model, provider

T = TypeVar("T", bound=BaseModel)

# Bedrock errors that mean "busy, try again", not "your request is wrong".
TRANSIENT_ERROR_CODES = {
    "throttlingexception", "serviceunavailableexception", "internalserverexception",
    "modelstreamerrorexception", "modelnotreadyexception",
}

try:
    from strands import ModelRetryStrategy

    class TransientErrorRetry(ModelRetryStrategy):
        """Strands retries throttling by default; also retry Bedrock's temporary outages."""

        def is_retryable(self, exception: Exception) -> bool:
            code = str(getattr(exception, "response", {}).get("Error", {}).get("Code", "")).lower()
            return super().is_retryable(exception) or code in TRANSIENT_ERROR_CODES

    def _retry_kwargs() -> dict:
        # Waits 2s, 4s, 8s, 16s between attempts.
        return {"retry_strategy": TransientErrorRetry(max_attempts=5, initial_delay=2, max_delay=30)}
except ImportError:  # older Strands versions: keep their built-in throttling retry
    def _retry_kwargs() -> dict:
        return {}


def make_agent(system_prompt: str, tools: list | None = None, output_model: type[BaseModel] | None = None,
               role: str | None = None) -> Agent:
    schema = output_model.model_json_schema() if output_model else None
    # callback_handler=None stops Strands from streaming tokens to stdout.
    return Agent(model=get_model(schema, role), system_prompt=system_prompt, tools=tools or [],
                 callback_handler=None, **_retry_kwargs())


def structured(agent: Agent, output_model: type[T], prompt: str) -> T:
    """Ask an agent for a validated Pydantic object.

    Newer Strands versions take structured_output_model on the call; older ones
    expose agent.structured_output(). Support both so the sandbox version works.
    """
    if provider() == "ollama":
        # Ollama already constrains the reply to the schema (see make_agent), so parse it
        # directly. Strands' structured-output path would send a second, slow request.
        return output_model.model_validate_json(str(agent(prompt)).strip())
    try:
        result = agent(prompt, structured_output_model=output_model)
        out = getattr(result, "structured_output", None)
        if isinstance(out, output_model):
            return out
    except TypeError:
        pass
    return agent.structured_output(output_model, prompt)
