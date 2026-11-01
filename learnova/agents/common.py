from typing import TypeVar

from pydantic import BaseModel
from strands import Agent

from ..config import get_model

T = TypeVar("T", bound=BaseModel)


def make_agent(system_prompt: str, tools: list | None = None) -> Agent:
    # callback_handler=None stops Strands from streaming tokens to stdout.
    return Agent(model=get_model(), system_prompt=system_prompt, tools=tools or [], callback_handler=None)


def structured(agent: Agent, output_model: type[T], prompt: str) -> T:
    """Ask an agent for a validated Pydantic object.

    Newer Strands versions take structured_output_model on the call; older ones
    expose agent.structured_output(). Support both so the sandbox version works.
    """
    try:
        result = agent(prompt, structured_output_model=output_model)
        out = getattr(result, "structured_output", None)
        if isinstance(out, output_model):
            return out
    except TypeError:
        pass
    return agent.structured_output(output_model, prompt)
