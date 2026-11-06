"""Adapters for agents that can be driven from a command line, plus a manual adapter
for IDE-only tools (Cursor IDE, Windsurf, Copilot in an editor)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from oer.adapters.base import Adapter, AdapterRequest, AdapterResult

PRESETS_FILE = Path(__file__).with_name("presets.json")


def load_presets() -> dict:
    return json.loads(PRESETS_FILE.read_text())


def _find_json(text: str) -> Optional[dict]:
    """Best-effort: parse the whole text, else the last line that parses as a JSON object."""
    for candidate in [text] + list(reversed(text.strip().splitlines())):
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_claude_json(stdout: str) -> dict:
    obj = _find_json(stdout) or {}
    usage = obj.get("usage") or {}
    models = list((obj.get("modelUsage") or {}).keys())
    return {
        "cost_usd": obj.get("total_cost_usd", obj.get("cost_usd")),
        "tokens_in": usage.get("input_tokens"),
        "tokens_out": usage.get("output_tokens"),
        "observed_model": "+".join(models) if models else None,
        "is_error": bool(obj.get("is_error")),
    }


PARSERS = {"claude_json": parse_claude_json, "none": lambda s: {}}


def copilot_settings_effort() -> Optional[str]:
    """Effort level currently set in the Copilot CLI config file, if any."""
    home = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot"))
    try:
        return json.loads((home / "settings.json").read_text()).get("effortLevel")
    except (OSError, ValueError):
        return None


class CliAdapter(Adapter):
    """Runs ``command`` (list of args with {prompt} {workdir} {model} {effort} placeholders)
    in the workdir.

    effort_mode "flag": the effort is passed on the command line (Claude Code).
    effort_mode "settings": the tool reads effort from its config file (Copilot CLI); the
    adapter refuses to run if the config does not already match, so the pin cannot silently drift.
    """

    def __init__(self, name: str, command: list[str], model_id: Optional[str] = None,
                 effort: Optional[str] = None, effort_mode: str = "flag", plan: Optional[str] = None,
                 parser: str = "none", cost_per_run_usd: Optional[float] = None,
                 exhaustion_pattern: Optional[str] = None, env: Optional[dict] = None,
                 env_unset: Optional[list] = None, verified=False):
        self.name = name
        self.command = command
        self.model_id = model_id
        self.effort = effort
        self.plan = plan
        self.parser = parser
        self.cost_per_run_usd = cost_per_run_usd
        self.exhaustion = re.compile(exhaustion_pattern, re.I) if exhaustion_pattern else None
        self.env = env or {}
        self.env_unset = env_unset or []
        self.verified = verified
        if effort and effort_mode == "settings":
            current = copilot_settings_effort()
            if current != effort:
                raise ValueError(
                    f"{name}: reasoning effort is read from the tool's settings file. Set "
                    f'"effortLevel": "{effort}" in ~/.copilot/settings.json (currently {current!r}) and retry.')

    def tool_version(self) -> Optional[str]:
        """First line of ``<tool> --version``, or None if it cannot be read."""
        try:
            proc = subprocess.run([self.command[0], "--version"], capture_output=True, text=True,
                                  timeout=15, env=self._env())
        except (OSError, subprocess.SubprocessError):
            return None
        lines = (proc.stdout or proc.stderr).strip().splitlines()
        return lines[0].strip() if proc.returncode == 0 and lines else None

    def describe(self) -> dict:
        return {"system": self.name, "model": self.model_id, "model_id": self.model_id,
                "effort": self.effort, "plan": self.plan, "version": self.tool_version()}

    def _env(self) -> dict:
        env = {**os.environ, **self.env}
        for key in self.env_unset:
            env.pop(key, None)
        return env

    def run(self, req: AdapterRequest) -> AdapterResult:
        argv = [a.format(prompt=req.prompt, workdir=str(req.workdir), model=self.model_id or "",
                         effort=self.effort or "") for a in self.command]
        start = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=req.workdir, capture_output=True, text=True,
                                  timeout=req.timeout_s, env=self._env())
            exit_code, out, timed_out = proc.returncode, proc.stdout, False
            err = proc.stderr
        except subprocess.TimeoutExpired as e:
            exit_code, timed_out = 124, True
            out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = ""
        except FileNotFoundError:
            return AdapterResult(exit_code=127, notes=f"command not found: {argv[0]}")
        duration = time.monotonic() - start

        parsed = PARSERS[self.parser](out)
        cost = parsed.get("cost_usd")
        basis = "metered" if cost is not None else "unknown"
        if cost is None and self.cost_per_run_usd is not None:
            cost, basis = self.cost_per_run_usd, "quota_fraction"
        text = out + err
        raw_dir = os.environ.get("OER_RAW_LOG_DIR")
        if raw_dir:  # full agent output for debugging parsers; may contain secrets, keep it out of git
            d = Path(raw_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{req.task_id}.stdout.txt").write_text(out)
            (d / f"{req.task_id}.stderr.txt").write_text(err)
        failed = exit_code != 0 or parsed.get("is_error", False)
        exhausted = bool(self.exhaustion and failed and self.exhaustion.search(text))
        return AdapterResult(
            exit_code=exit_code, duration_s=duration, cost_usd=cost, cost_basis=basis,
            tokens_in=parsed.get("tokens_in"), tokens_out=parsed.get("tokens_out"),
            timed_out=timed_out, log_tail=text[-1500:], observed_model=parsed.get("observed_model"),
            quota_exhausted=exhausted,
        )


class ManualAdapter(Adapter):
    """Human-in-the-loop adapter for IDE/cloud agents with no CLI.

    Prints the prompt and workdir, waits while you run the tool by hand, then asks
    for the cost read from the tool's usage page. Any manual code edit you make
    beyond prompting the agent must be reported as an intervention.
    """

    name = "manual"

    def __init__(self, system: str = "manual", model_id: Optional[str] = None,
                 effort: Optional[str] = None, plan: Optional[str] = None):
        self.system = system
        self.model_id = model_id
        self.effort = effort
        self.plan = plan

    def describe(self) -> dict:
        return {"system": self.system, "model": self.model_id, "model_id": self.model_id,
                "effort": self.effort, "plan": self.plan, "version": None}

    def run(self, req: AdapterRequest) -> AdapterResult:
        print(f"\n=== {req.task_id} ({req.cycle}) ===\nWorkdir: {req.workdir}\nPrompt:\n{req.prompt}\n")
        start = time.monotonic()
        input("Run the agent on that directory, then press Enter when it has finished... ")
        duration = time.monotonic() - start
        cost_s = input("Cost in USD (API-equivalent or credits used; blank if unknown): ").strip()
        iv_s = input("Manual interventions (edits, restarts, fixes; clarification answers do not count) [0]: ").strip()
        exhausted = input("Did the plan's usage limit stop the agent? [y/N]: ").strip().lower() == "y"
        return AdapterResult(
            duration_s=duration,
            cost_usd=float(cost_s) if cost_s else None,
            cost_basis="manual" if cost_s else "unknown",
            interventions=int(iv_s) if iv_s else 0,
            quota_exhausted=exhausted,
        )
