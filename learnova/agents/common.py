from typing import TypeVar

from pydantic import BaseModel
from strands import Agent

from ..config import get_model, provider

T = TypeVar("T", bound=BaseModel)


def make_agent(system_prompt: str, tools: list | None = None, output_model: type[BaseModel] | None = None) -> Agent:
    schema = output_model.model_json_schema() if output_model else None
    # callback_handler=None stops Strands from streaming tokens to stdout.
    return Agent(model=get_model(schema), system_prompt=system_prompt, tools=tools or [], callback_handler=None)


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
