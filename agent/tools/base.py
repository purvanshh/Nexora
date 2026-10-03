"""Abstract tool contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agent.models import Observation


class Tool(ABC):
    name: str
    description: str
    args_schema: type[BaseModel]

    @abstractmethod
    async def run(self, args: BaseModel) -> Observation:
        raise NotImplementedError

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.args_schema.model_json_schema(by_alias=True)
        # OpenAI tools expect a JSON schema without pydantic extras that confuse some models
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }
