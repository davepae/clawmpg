"""Task manifest loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from oer import config
from oer.scoring import ocm_for_minutes


@dataclass
class Task:
    id: str
    cycle: str
    title: str
    prompt: str
    human_minutes: float
    timeout_s: int
    scope: list = field(default_factory=list)
    extra_checks: list = field(default_factory=list)
    solution_deletes: list = field(default_factory=list)
    dir: Path = Path(".")

    @property
    def ocm(self) -> float:
        return ocm_for_minutes(self.human_minutes)

    @property
    def hidden_tests_dir(self) -> Path:
        return self.dir / "hidden_tests"

    @property
    def solution_dir(self) -> Path:
        return self.dir / "solution"


def load_tasks(root: Path, cycles: Optional[list[str]] = None, ids: Optional[list[str]] = None) -> list[Task]:
    tasks = []
    for manifest in sorted(Path(root).glob("*/*/task.json")):
        data = json.loads(manifest.read_text())
        task = Task(dir=manifest.parent, **data)
        if task.cycle not in config.CYCLES:
            raise ValueError(f"{task.id}: unknown cycle {task.cycle}")
        if cycles and task.cycle not in cycles:
            continue
        if ids and task.id not in ids:
            continue
        tasks.append(task)
    order = {c: i for i, c in enumerate(config.CYCLES)}
    tasks.sort(key=lambda t: (order[t.cycle], t.id))
    return tasks
