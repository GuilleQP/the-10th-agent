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
    # Per-epoch recaps (when summarize_epoch is on): {"after_epoch", "summary"}.
    epoch_summaries: list[dict] = field(default_factory=list)
    # Why the run ended: "consensus" | "max_epochs" | "contaminated".
    finish_reason: str = "max_epochs"
    # LLM verdict per agent per epoch:
    # {"epoch", "agent_id", "is_dissenter", "position", "holds_truth"}.
    verdicts_by_epoch: list[dict] = field(default_factory=list)
    # Majority agents that argued the truth in epoch 1 before the dissenter
    # spoke (prior-knowledge leak). Under the EXCLUDE policy these are dropped
    # from the conversion denominator; empty otherwise.
    precommitted_agents: list[int] = field(default_factory=list)

    def save(self, experiment_dir: str | Path, name_suffix: str = "") -> Path:
        """Save results to the experiment's runs/ directory.

        Filenames embed a model slug so a matrix run (one experiment across
        many models) doesn't collide and the aggregator can group by model.
        ``name_suffix`` appends an extra tag to the stem (e.g. ``n16_r1`` for a
        group-size sweep) so those runs don't collide either.
        """
        runs_dir = Path(experiment_dir) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_name = self.config_snapshot.get("model", {}).get("name", "unknown")
        model_slug = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")
        structure = self.config_snapshot.get("communication", {}).get(
            "structure", "round-robin"
        )
        struct_slug = re.sub(r"[^a-z0-9]+", "-", structure.lower()).strip("-")
        stem = f"{timestamp}_{model_slug}_{struct_slug}"
        if name_suffix:
            stem = f"{stem}_{name_suffix}"

        # Save full transcript as JSON
        chat_path = runs_dir / f"{stem}_chat.json"
        chat_data = {
            "experiment_name": self.experiment_name,
            "total_epochs": self.total_epochs,
            "finish_reason": self.finish_reason,
            "consensus": _consensus_to_dict(self.consensus) if self.consensus else None,
            "dissenter_positions": self.dissenter_positions,
            "verdicts_by_epoch": self.verdicts_by_epoch,
            "precommitted_agents": self.precommitted_agents,
            "epoch_summaries": self.epoch_summaries,
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
            f"**Finish reason:** {self.finish_reason}",
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

        if self.verdicts_by_epoch:
            epochs = sorted({v["epoch"] for v in self.verdicts_by_epoch})
            lines.extend([
                "## Conversion by Epoch (LLM-judged)",
                "",
                "Majority agents holding the truth at the end of each epoch:",
                "",
            ])
            for ep in epochs:
                maj = [
                    v for v in self.verdicts_by_epoch
                    if v["epoch"] == ep and not v.get("is_dissenter")
                ]
                won = sum(1 for v in maj if v.get("holds_truth"))
                lines.append(f"- Epoch {ep}: {won}/{len(maj)}")
            lines.append("")

        if self.epoch_summaries:
            lines.extend(["## Epoch Summaries", ""])
            for entry in self.epoch_summaries:
                lines.append(f"### After epoch {entry['after_epoch']}")
                lines.append("")
                lines.append(entry["summary"])
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
