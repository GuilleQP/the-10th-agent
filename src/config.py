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


class Category(str, Enum):
    """Field/domain an experiment belongs to (mirrors a benchmark domain group)."""

    MATHEMATICS = "mathematics"
    PHYSICAL_SCIENCES = "physical-sciences"
    LIFE_SCIENCES = "life-sciences"
    LOGIC_REASONING = "logic-reasoning"
    HISTORY_SOCIETY = "history-society"


CATEGORY_LABELS: dict[Category, str] = {
    Category.MATHEMATICS: "Mathematics & Probability",
    Category.PHYSICAL_SCIENCES: "Physics & Astronomy",
    Category.LIFE_SCIENCES: "Biology, Medicine & Health",
    Category.LOGIC_REASONING: "Logic & Critical Reasoning",
    Category.HISTORY_SOCIETY: "History, Geography & Society",
}


class AgentsConfig(BaseModel):
    count: int = 10
    dissenter_index: int = 9


class KnowledgeConfig(BaseModel):
    common: str
    dissenter: str


class ScoringConfig(BaseModel):
    """Offline outcome scoring.

    A majority agent is counted as *converted to truth* when its final
    ``[POSITION: ...]`` tag contains any ``truth_keywords`` and no
    ``false_keywords``. This lets the aggregator score runs deterministically
    without a second LLM pass.
    """

    truth_keywords: list[str] = Field(default_factory=list)
    false_keywords: list[str] = Field(default_factory=list)


class CommunicationConfig(BaseModel):
    structure: CommunicationStructure = CommunicationStructure.ROUND_ROBIN
    max_epochs: int = 15
    # When true, after each epoch the whole discussion is summarized and the
    # next epoch's agents receive that summary + the current epoch's raw
    # messages (instead of the full, ever-growing transcript).
    summarize_epoch: bool = True


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
    category: Category
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    knowledge: KnowledgeConfig
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    communication: CommunicationConfig = Field(default_factory=CommunicationConfig)
    consensus: ConsensusConfig = Field(default_factory=ConsensusConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)


def load_config(path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment config from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ExperimentConfig(**raw["experiment"])
