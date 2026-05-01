#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Minimal unattended agent runner for CallProfiler.

It intentionally stays dependency-free:
- reads agent_backlog.json;
- picks the next todo task;
- renders a bounded prompt with project rules and relevant files;
- runs an external agent command, for example an opencode wrapper;
- applies a unified diff response or accepts direct edits;
- runs tests/lint;
- updates task status and writes per-task logs.

The runner does not know any vendor-specific API. Configure the command with
placeholders:

  python tools/agent_runner.py ^
    --agent-cmd "opencode run --prompt-file {prompt_file}" ^
    --apply-mode direct ^
    --max-hours 4 ^
    --max-tasks 10

For tools that print a diff instead of editing files directly:

  python tools/agent_runner.py ^
    --agent-cmd "your-agent --prompt {prompt_file}" ^
    --apply-mode patch

Placeholders available in --agent-cmd:
  {repo} {task_id} {prompt_file} {response_file} {run_dir}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any


STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

DEFAULT_BACKLOG = "agent_backlog.json"
DEFAULT_RUNS_DIR = ".agent_runs"


class RunnerError(RuntimeError):
    """Expected runner failure for a single task or preflight."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        fh.write("\n")


def run_cmd(
    command: str,
    cwd: Path,
    timeout_sec: int | None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_sec,
        env=env,
    )


def ensure_git_clean(repo: Path) -> None:
    result = run_cmd("git status --porcelain", repo, timeout_sec=60)
    if result.returncode != 0:
        raise RunnerError(f"git status failed: {result.stderr or result.stdout}")
    if result.stdout.strip():
        raise RunnerError(
            "Git worktree is dirty. Commit/stash current changes or pass --allow-dirty."
        )


def git_changed_files(repo: Path) -> list[str]:
    result = run_cmd("git diff --name-only", repo, timeout_sec=60)
    if result.returncode != 0:
        raise RunnerError(f"git diff --name-only failed: {result.stderr or result.stdout}")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def git_current_branch(repo: Path) -> str:
    result = run_cmd("git branch --show-current", repo, timeout_sec=60)
    if result.returncode != 0:
        raise RunnerError(f"git branch failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def git_checkout_new_branch(repo: Path, branch: str) -> None:
    current = git_current_branch(repo)
    if current == branch:
        return
    result = run_cmd(f'git checkout -B "{branch}"', repo, timeout_sec=120)
    if result.returncode != 0:
        raise RunnerError(f"git checkout branch failed: {result.stderr or result.stdout}")


def git_commit_all(repo: Path, message: str) -> str | None:
    status = run_cmd("git status --porcelain", repo, timeout_sec=60)
    if status.returncode != 0:
        raise RunnerError(f"git status failed before commit: {status.stderr or status.stdout}")
    if not status.stdout.strip():
        return None

    add = run_cmd("git add -A", repo, timeout_sec=120)
    if add.returncode != 0:
        raise RunnerError(f"git add failed: {add.stderr or add.stdout}")
    commit = run_cmd(f'git commit -m "{message}"', repo, timeout_sec=180)
    if commit.returncode != 0:
        raise RunnerError(f"git commit failed: {commit.stderr or commit.stdout}")
    rev = run_cmd("git rev-parse --short HEAD", repo, timeout_sec=60)
    if rev.returncode != 0:
        return None
    return rev.stdout.strip()


def maybe_git_push(repo: Path, branch: str) -> None:
    result = run_cmd(f'git push -u origin "{branch}"', repo, timeout_sec=300)
    if result.returncode != 0:
        raise RunnerError(f"git push failed: {result.stderr or result.stdout}")


def read_text_limited(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return f"[missing file: {path.as_posix()}]"
    except OSError as exc:
        return f"[could not read {path.as_posix()}: {exc}]"

    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace")

    head = data[: max_bytes // 2].decode("utf-8", errors="replace")
    tail = data[-max_bytes // 2 :].decode("utf-8", errors="replace")
    return f"{head}\n\n[... truncated by agent_runner ...]\n\n{tail}"


def task_sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
    index, task = item
    return int(task.get("priority", 999)), index


def find_next_task(backlog: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
    candidates = [
        (idx, task)
        for idx, task in enumerate(backlog.get("backlog", []))
        if task.get("status") == STATUS_TODO
    ]
    if not candidates:
        return None
    return sorted(candidates, key=task_sort_key)[0]


def collect_context_files(task: dict[str, Any]) -> list[str]:
    artifacts = task.get("artifacts") or {}
    result: list[str] = []
    for key in ("read", "touch"):
        for value in artifacts.get(key, []) or []:
            if isinstance(value, str) and value not in result:
                result.append(value)
    for required in ("AGENTS.md", "CONTINUITY.md", "CONSTITUTION.md"):
        if required not in result:
            result.insert(0, required)
    return result


def render_prompt(
    backlog: dict[str, Any],
    task: dict[str, Any],
    repo: Path,
    max_context_bytes_per_file: int,
) -> str:
    project = backlog.get("project", {})
    guardrails = "\n".join(f"- {g}" for g in project.get("global_guardrails", []))
    runtime = "\n".join(f"- {g}" for g in project.get("runtime_constraints", []))
    notes = "\n".join(f"- {g}" for g in task.get("implementation_notes", []))
    acceptance = "\n".join(f"- {g}" for g in task.get("acceptance", []))
    verification = "\n".join(f"- {g}" for g in task.get("verification", []))

    context_parts: list[str] = []
    for rel in collect_context_files(task):
        abs_path = repo / rel
        if abs_path.is_dir():
            context_parts.append(f"## {rel}\n[context path is a directory; inspect selectively]")
            continue
        content = read_text_limited(abs_path, max_context_bytes_per_file)
        context_parts.append(f"## {rel}\n```text\n{content}\n```")

    artifacts = json.dumps(task.get("artifacts", {}), ensure_ascii=False, indent=2)
    context_text = "\n\n".join(context_parts)

    return textwrap.dedent(
        f"""
        You are a senior Python/software architecture agent working on CallProfiler.

        Project:
        - Name: {project.get("name", "CallProfiler")}
        - Root: {repo.as_posix()}
        - Mission: {project.get("mission", "")}

        Runtime constraints:
        {runtime}

        Mandatory guardrails:
        {guardrails}

        Current task:
        - id: {task.get("id")}
        - title: {task.get("title")}
        - type: {task.get("type")}
        - priority: {task.get("priority")}

        Description:
        {task.get("description", "")}

        Rationale:
        {task.get("rationale", "")}

        Artifacts:
        ```json
        {artifacts}
        ```

        Implementation notes:
        {notes}

        Acceptance criteria:
        {acceptance}

        Verification expected:
        {verification}

        Work rules:
        - Make the smallest vertical change that satisfies this task only.
        - Do not implement later backlog tasks.
        - Do not change files outside artifacts.touch unless unavoidable; explain why.
        - Add/update focused tests when the task touches runtime behavior.
        - Keep changes compatible with local-only Windows + SQLite + llama.cpp architecture.
        - Preserve CHANGELOG.md and CONTINUITY.md discipline when task artifacts include them.

        Response format:
        1. Brief plan.
        2. Unified diff patch in one fenced ```diff block, OR state that you edited files directly if the runner is in direct mode.
        3. Verification commands to run.

        Relevant context follows.

        {context_text}
        """
    ).strip() + "\n"


def extract_patch(response: str) -> str:
    blocks = re.findall(r"```(?:diff|patch)?\s*\n(.*?)```", response, flags=re.DOTALL)
    for block in blocks:
        candidate = block.strip() + "\n"
        if looks_like_patch(candidate):
            return candidate
    stripped = response.strip() + "\n"
    if looks_like_patch(stripped):
        return stripped
    raise RunnerError("Agent response did not contain a unified diff patch.")


def looks_like_patch(text: str) -> bool:
    return (
        "diff --git " in text
        or re.search(r"^---\s+\S+", text, flags=re.MULTILINE) is not None
        and re.search(r"^\+\+\+\s+\S+", text, flags=re.MULTILINE) is not None
    )


def normalize_patch_path(raw: str) -> str | None:
    raw = raw.strip()
    if raw == "/dev/null":
        return None
    if raw.startswith("a/") or raw.startswith("b/"):
        raw = raw[2:]
    return raw.replace("\\", "/")


def patch_changed_files(patch_text: str) -> set[str]:
    files: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = normalize_patch_path(parts[3])
                if path:
                    files.add(path)
        elif line.startswith("+++ "):
            path = normalize_patch_path(line[4:].split("\t", 1)[0])
            if path:
                files.add(path)
    return files


def allowed_paths_for_task(task: dict[str, Any]) -> set[str]:
    artifacts = task.get("artifacts") or {}
    allowed = set()
    for value in artifacts.get("touch", []) or []:
        if isinstance(value, str):
            allowed.add(value.replace("\\", "/").rstrip("/"))
    return allowed


def path_allowed(path: str, allowed: set[str]) -> bool:
    if not allowed:
        return True
    normalized = path.replace("\\", "/").rstrip("/")
    for item in allowed:
        if normalized == item or normalized.startswith(item.rstrip("/") + "/"):
            return True
    return False


def enforce_file_guard(changed: set[str], task: dict[str, Any]) -> None:
    allowed = allowed_paths_for_task(task)
    illegal = sorted(path for path in changed if not path_allowed(path, allowed))
    if illegal:
        raise RunnerError(
            "Patch/direct edits touched files outside task artifacts.touch: "
            + ", ".join(illegal)
        )


def apply_patch_file(repo: Path, patch_file: Path) -> None:
    check = run_cmd(f'git apply --check "{patch_file}"', repo, timeout_sec=120)
    if check.returncode != 0:
        raise RunnerError(f"git apply --check failed:\n{check.stderr or check.stdout}")
    apply = run_cmd(f'git apply "{patch_file}"', repo, timeout_sec=120)
    if apply.returncode != 0:
        raise RunnerError(f"git apply failed:\n{apply.stderr or apply.stdout}")


def revert_worktree(repo: Path) -> None:
    restore = run_cmd("git restore .", repo, timeout_sec=120)
    if restore.returncode != 0:
        raise RunnerError(f"git restore failed: {restore.stderr or restore.stdout}")
    clean = run_cmd("git clean -fd", repo, timeout_sec=120)
    if clean.returncode != 0:
        raise RunnerError(f"git clean failed: {clean.stderr or clean.stdout}")


def format_agent_command(template: str, repo: Path, task_id: str, run_dir: Path) -> str:
    prompt_file = run_dir / "prompt.md"
    response_file = run_dir / "response.md"
    return template.format(
        repo=str(repo),
        task_id=task_id,
        prompt_file=str(prompt_file),
        response_file=str(response_file),
        run_dir=str(run_dir),
    )


def mark_task(task: dict[str, Any], status: str, **fields: Any) -> None:
    task["status"] = status
    task.setdefault("history", []).append({"ts": utc_now(), "status": status, **fields})
    task.update(fields)


def run_verification(
    repo: Path,
    task: dict[str, Any],
    run_dir: Path,
    default_test_command: str,
    lint_command: str,
    timeout_sec: int,
) -> tuple[bool, dict[str, Any]]:
    commands: list[str] = []
    explicit = task.get("verification_commands")
    if isinstance(explicit, list):
        commands.extend(str(cmd) for cmd in explicit if str(cmd).strip())
    elif default_test_command:
        commands.append(default_test_command)
    if lint_command:
        commands.append(lint_command)

    results = []
    ok = True
    for idx, command in enumerate(commands, 1):
        result = run_cmd(command, repo, timeout_sec=timeout_sec)
        log_file = run_dir / f"verify_{idx}.log"
        log_file.write_text(
            f"$ {command}\n\n[stdout]\n{result.stdout}\n\n[stderr]\n{result.stderr}\n",
            encoding="utf-8",
        )
        item = {
            "command": command,
            "returncode": result.returncode,
            "log": str(log_file),
        }
        results.append(item)
        if result.returncode != 0:
            ok = False
            break
    return ok, {"commands": results}


def run_one_task(
    args: argparse.Namespace,
    backlog: dict[str, Any],
    task_index: int,
    task: dict[str, Any],
    run_root: Path,
) -> bool:
    repo = Path(args.repo).resolve()
    task_id = str(task["id"])
    run_dir = run_root / f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    mark_task(task, STATUS_IN_PROGRESS, started_at=utc_now(), run_dir=str(run_dir))
    save_json_atomic(Path(args.backlog), backlog)

    prompt = render_prompt(
        backlog=backlog,
        task=task,
        repo=repo,
        max_context_bytes_per_file=args.max_context_bytes_per_file,
    )
    prompt_file = run_dir / "prompt.md"
    response_file = run_dir / "response.md"
    prompt_file.write_text(prompt, encoding="utf-8", newline="\n")

    append_jsonl(
        run_root / "run.log.jsonl",
        {"ts": utc_now(), "event": "task_started", "task_id": task_id, "run_dir": str(run_dir)},
    )

    if args.dry_run:
        mark_task(task, STATUS_TODO, last_prompt=str(prompt_file), note="dry-run prompt generated")
        save_json_atomic(Path(args.backlog), backlog)
        return False

    if not args.agent_cmd:
        raise RunnerError("--agent-cmd is required unless --dry-run is used.")

    before_files = set(git_changed_files(repo))
    command = format_agent_command(args.agent_cmd, repo, task_id, run_dir)
    agent = run_cmd(command, repo, timeout_sec=args.agent_timeout_sec)
    response_text = agent.stdout
    if agent.stderr:
        response_text += "\n\n[stderr]\n" + agent.stderr
    response_file.write_text(response_text, encoding="utf-8", newline="\n")

    (run_dir / "agent_command.txt").write_text(command, encoding="utf-8")
    if agent.returncode != 0:
        raise RunnerError(f"Agent command failed with exit code {agent.returncode}.")

    if args.apply_mode == "patch":
        patch_text = extract_patch(response_text)
        changed = patch_changed_files(patch_text)
        if not args.no_file_guard:
            enforce_file_guard(changed, task)
        patch_file = run_dir / "change.patch"
        patch_file.write_text(patch_text, encoding="utf-8", newline="\n")
        apply_patch_file(repo, patch_file)
    elif args.apply_mode == "direct":
        after_files = set(git_changed_files(repo))
        changed = after_files - before_files
        if not changed:
            raise RunnerError("Agent command completed, but no repository files changed.")
        if not args.no_file_guard:
            enforce_file_guard(changed, task)
        diff = run_cmd("git diff -- .", repo, timeout_sec=120)
        (run_dir / "direct_changes.diff").write_text(diff.stdout, encoding="utf-8", newline="\n")
    elif args.apply_mode == "none":
        pass
    else:
        raise RunnerError(f"Unknown apply mode: {args.apply_mode}")

    changed_files = git_changed_files(repo)
    (run_dir / "changed_files.txt").write_text(
        "\n".join(changed_files) + ("\n" if changed_files else ""),
        encoding="utf-8",
    )

    verified, verify_result = run_verification(
        repo=repo,
        task=task,
        run_dir=run_dir,
        default_test_command=args.test_command,
        lint_command=args.lint_command,
        timeout_sec=args.verify_timeout_sec,
    )
    if not verified:
        raise RunnerError(f"Verification failed. Logs: {verify_result}")

    mark_task(
        task,
        STATUS_DONE,
        completed_at=utc_now(),
        changed_files=changed_files,
        verification=verify_result,
        response_file=str(response_file),
    )
    save_json_atomic(Path(args.backlog), backlog)
    append_jsonl(
        run_root / "run.log.jsonl",
        {"ts": utc_now(), "event": "task_done", "task_id": task_id, "changed_files": changed_files},
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run atomic CallProfiler backlog tasks with an external agent.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--backlog", default=DEFAULT_BACKLOG, help="Path to agent_backlog.json.")
    parser.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR, help="Directory for prompts/responses/logs.")
    parser.add_argument("--agent-cmd", default="", help="External agent command template.")
    parser.add_argument(
        "--apply-mode",
        choices=["patch", "direct", "none"],
        default="patch",
        help="patch: parse/apply diff from response; direct: command edits files; none: prompt/log only.",
    )
    parser.add_argument("--max-hours", type=float, default=2.0, help="Wall-clock limit.")
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means no explicit task count limit.")
    parser.add_argument("--max-failures", type=int, default=3, help="Stop after this many failed tasks.")
    parser.add_argument("--agent-timeout-sec", type=int, default=3600)
    parser.add_argument("--verify-timeout-sec", type=int, default=1800)
    parser.add_argument("--test-command", default=None, help="Default verification command.")
    parser.add_argument("--lint-command", default=None, help="Optional lint command.")
    parser.add_argument("--max-context-bytes-per-file", type=int, default=None)
    parser.add_argument("--allow-dirty", action="store_true", help="Allow starting with dirty git worktree.")
    parser.add_argument("--revert-on-fail", action="store_true", help="Restore worktree after failed task.")
    parser.add_argument("--no-file-guard", action="store_true", help="Disable artifacts.touch file guard.")
    parser.add_argument("--dry-run", action="store_true", help="Only generate prompt for the next task.")
    parser.add_argument("--branch", default="", help="Optional branch to checkout/create before running.")
    parser.add_argument("--commit-every", type=int, default=None, help="Commit after every N done tasks. 0 disables.")
    parser.add_argument("--push", action="store_true", help="Push after checkpoint commits.")
    return parser


def apply_defaults(args: argparse.Namespace, backlog: dict[str, Any]) -> None:
    defaults = backlog.get("runner_defaults", {})
    if args.test_command is None:
        args.test_command = defaults.get("test_command", "python -m pytest -q")
    if args.lint_command is None:
        args.lint_command = defaults.get("lint_command", "")
    if args.max_context_bytes_per_file is None:
        args.max_context_bytes_per_file = int(defaults.get("max_context_bytes_per_file", 24000))
    if args.commit_every is None:
        args.commit_every = int(defaults.get("commit_every", 0))
    if not args.revert_on_fail:
        args.revert_on_fail = bool(defaults.get("revert_on_fail", False))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    backlog_path = Path(args.backlog)
    if not backlog_path.is_absolute():
        backlog_path = repo / backlog_path
    args.backlog = str(backlog_path)

    backlog = load_json(backlog_path)
    apply_defaults(args, backlog)

    run_root = repo / args.runs_dir
    run_root.mkdir(parents=True, exist_ok=True)

    if args.branch:
        git_checkout_new_branch(repo, args.branch)

    if not args.allow_dirty and not args.dry_run:
        ensure_git_clean(repo)

    deadline = time.monotonic() + max(args.max_hours, 0.01) * 3600
    done_count = 0
    failure_count = 0
    attempted = 0

    append_jsonl(
        run_root / "run.log.jsonl",
        {
            "ts": utc_now(),
            "event": "run_started",
            "repo": str(repo),
            "backlog": str(backlog_path),
            "apply_mode": args.apply_mode,
            "max_hours": args.max_hours,
            "max_tasks": args.max_tasks,
        },
    )

    while time.monotonic() < deadline:
        if args.max_tasks and attempted >= args.max_tasks:
            break
        if failure_count >= args.max_failures:
            break

        next_task = find_next_task(backlog)
        if next_task is None:
            break

        task_index, task = next_task
        attempted += 1
        try:
            completed = run_one_task(args, backlog, task_index, task, run_root)
            if not completed and args.dry_run:
                break
            done_count += 1
        except Exception as exc:
            failure_count += 1
            task["status"] = STATUS_FAILED
            task.setdefault("history", []).append(
                {"ts": utc_now(), "status": STATUS_FAILED, "error": str(exc)}
            )
            task["failed_at"] = utc_now()
            task["last_error"] = str(exc)
            save_json_atomic(backlog_path, backlog)
            append_jsonl(
                run_root / "run.log.jsonl",
                {"ts": utc_now(), "event": "task_failed", "task_id": task.get("id"), "error": str(exc)},
            )
            if args.revert_on_fail and not args.allow_dirty:
                revert_worktree(repo)
            continue

        if args.commit_every and done_count > 0 and done_count % args.commit_every == 0:
            branch = args.branch or git_current_branch(repo)
            rev = git_commit_all(repo, f"agent: batch checkpoint {done_count}")
            append_jsonl(
                run_root / "run.log.jsonl",
                {"ts": utc_now(), "event": "checkpoint_commit", "rev": rev, "branch": branch},
            )
            if args.push and branch:
                maybe_git_push(repo, branch)

    append_jsonl(
        run_root / "run.log.jsonl",
        {
            "ts": utc_now(),
            "event": "run_finished",
            "attempted": attempted,
            "done": done_count,
            "failed": failure_count,
        },
    )
    print(f"agent_runner finished: attempted={attempted}, done={done_count}, failed={failure_count}")
    return 0 if failure_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
