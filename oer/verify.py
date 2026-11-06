"""Hidden-test verification and quality scoring.

Verification runs on a *copy* of the agent's workdir in which tests/ is replaced
by the task's hidden tests, so an agent can neither see nor weaken them.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from oer.tasks import Task

IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", "node_modules"}


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_DIRS, "*.pyc"), dirs_exist_ok=True)


def snapshot(root: Path) -> dict[str, str]:
    """Map of relative posix path -> sha256 for every non-ignored file."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            p = Path(dirpath) / name
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def run_extra_checks(workdir: Path, checks: list[dict]) -> list[str]:
    """Return a list of failure messages (empty means all checks passed)."""
    failures = []
    for chk in checks:
        kind = chk["type"]
        flags = re.I if "i" in chk.get("flags", "") else 0
        if kind == "exists" and not (workdir / chk["path"]).exists():
            failures.append(f"missing {chk['path']}")
        elif kind == "file_absent" and (workdir / chk["path"]).exists():
            failures.append(f"{chk['path']} should not exist")
        elif kind in ("contains", "not_contains"):
            if "path" in chk:
                files = [workdir / chk["path"]] if (workdir / chk["path"]).exists() else []
            else:
                files = [p for p in workdir.glob(chk["glob"]) if p.is_file()]
            hit = any(re.search(chk["pattern"], p.read_text(errors="replace"), flags) for p in files)
            if kind == "contains" and not hit:
                failures.append(f"no match for /{chk['pattern']}/ in {chk.get('path') or chk.get('glob')}")
            if kind == "not_contains" and hit:
                failures.append(f"unexpected /{chk['pattern']}/ in {chk.get('glob') or chk.get('path')}")
    return failures


def run_hidden_tests(workdir: Path, task: Task, timeout_s: int = 300) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="oer-verify-") as tmp:
        vdir = Path(tmp) / "repo"
        copy_tree(workdir, vdir)
        shutil.rmtree(vdir / "tests", ignore_errors=True)
        copy_tree(task.hidden_tests_dir, vdir / "tests")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(vdir)}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                cwd=vdir, env=env, capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return False, "hidden tests timed out"
        tail = (proc.stdout + proc.stderr)[-1500:]
        return proc.returncode == 0, tail


def compiles(workdir: Path) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "."],
        cwd=workdir, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return proc.returncode == 0


def quality_score(workdir: Path, task: Task, changed: list[str]) -> float:
    """0.5 * code compiles + 0.5 * scope discipline (share of changes inside task scope)."""
    compile_ok = 1.0 if compiles(workdir) else 0.0
    if changed:
        out_of_scope = [c for c in changed if not _matches(c, task.scope)]
        scope = 1.0 - len(out_of_scope) / len(changed)
    else:
        scope = 0.0
    return round(0.5 * compile_ok + 0.5 * scope, 4)


def verify(workdir: Path, task: Task, baseline: dict[str, str]) -> dict:
    changed = changed_files(baseline, snapshot(workdir))
    tests_ok, tail = run_hidden_tests(workdir, task)
    failures = run_extra_checks(workdir, task.extra_checks)
    passed = tests_ok and not failures
    return {
        "passed": passed,
        "tests_passed": tests_ok,
        "check_failures": failures,
        "changed_files": changed,
        "quality": quality_score(workdir, task, changed) if passed else 0.0,
        "log_tail": tail,
    }
