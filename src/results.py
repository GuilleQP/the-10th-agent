"""Result logging and serialization."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.consensus import ConsensusResult


@dataclass
class ChatMessage:
    epoch: int
    agent_id: int
    content: str
    is_dissenter: bool


@dataclass
class ExperimentResult:
    experiment_name: str
    total_epochs: int
    consensus: ConsensusResult | None
    dissenter_positions: list[str]
    transcript: list[ChatMessage]
    config_snapshot: dict = field(default_factory=dict)

    def save(self, experiment_dir: str | Path) -> Path:
        """Save results to the experiment's runs/ directory.

        Filenames embed a model slug so a matrix run (one experiment across
        many models) doesn't collide and the aggregator can group by model.
        """
        runs_dir = Path(experiment_dir) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_name = self.config_snapshot.get("model", {}).get("name", "unknown")
        model_slug = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")
        stem = f"{timestamp}_{model_slug}"

        # Save full transcript as JSON
        chat_path = runs_dir / f"{stem}_chat.json"
        chat_data = {
            "experiment_name": self.experiment_name,
            "total_epochs": self.total_epochs,
            "consensus": _consensus_to_dict(self.consensus) if self.consensus else None,
            "dissenter_positions": self.dissenter_positions,
            "transcript": [asdict(m) for m in self.transcript],
            "config": self.config_snapshot,
        }
        chat_path.write_text(json.dumps(chat_data, indent=2))

        # Save summary markdown
        summary_path = runs_dir / f"{stem}_summary.md"
        summary_path.write_text(self._generate_summary())

        return chat_path

    def _generate_summary(self) -> str:
        lines = [
            f"# Run Summary: {self.experiment_name}",
            "",
            f"**Epochs completed:** {self.total_epochs}",
            f"**Total messages:** {len(self.transcript)}",
            "",
        ]

        if self.consensus:
            lines.extend([
                "## Consensus",
                f"- **Reached:** {self.consensus.reached}",
                f"- **Majority position:** {self.consensus.majority_position}",
                f"- **Agreement ratio:** {self.consensus.agreement_ratio:.0%}",
                f"- **Dissenter silenced:** {self.consensus.dissenter_silenced}",
                "",
            ])

        if self.dissenter_positions:
            lines.extend([
                "## Dissenter Position History",
                "",
            ])
            for i, pos in enumerate(self.dissenter_positions):
                lines.append(f"- Epoch {i + 1}: {pos}")
            lines.append("")

        return "\n".join(lines)


def _consensus_to_dict(c: ConsensusResult) -> dict:
    return {
        "reached": c.reached,
        "majority_position": c.majority_position,
        "dissenter_silenced": c.dissenter_silenced,
        "positions": {str(k): v for k, v in c.positions.items()},
        "agreement_ratio": c.agreement_ratio,
    }
