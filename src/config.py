"""Pydantic models for experiment configuration."""

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CommunicationStructure(str, Enum):
    ROUND_ROBIN = "round-robin"
    RANDOM = "random"
    FREE_FOR_ALL = "free-for-all"


class ConsensusMethod(str, Enum):
    LLM_JUDGE = "llm-judge"
    KEYWORD = "keyword"
    UNANIMOUS = "unanimous"


class AgentsConfig(BaseModel):
    count: int = 10
    dissenter_index: int = 9


class KnowledgeConfig(BaseModel):
    common: str
    dissenter: str


class CommunicationConfig(BaseModel):
    structure: CommunicationStructure = CommunicationStructure.ROUND_ROBIN
    max_epochs: int = 15


class ConsensusConfig(BaseModel):
    method: ConsensusMethod = ConsensusMethod.LLM_JUDGE
    threshold: float = 0.8
    check_every: int = 1


class ModelConfig(BaseModel):
    name: str = "openai:gpt-4o-mini"
    temperature: float = 0.7


class ExperimentConfig(BaseModel):
    name: str
    description: str
    topic: str
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    knowledge: KnowledgeConfig
    communication: CommunicationConfig = Field(default_factory=CommunicationConfig)
    consensus: ConsensusConfig = Field(default_factory=ConsensusConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)


def load_config(path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment config from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ExperimentConfig(**raw["experiment"])
