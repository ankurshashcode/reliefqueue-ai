#!/usr/bin/env python3
"""Build an Ollama-friendly local AI context packet for this repository.

The script is intentionally dependency-light: Python stdlib only. Optional tools
such as repomix, ctags, ripgrep, ast-grep, and ollama are detected at runtime.
Missing tools create clear notes rather than failing the whole packet.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import os
import pathlib
import re
import shutil
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".turbo",
    ".next",
    ".nuxt",
    ".cache",
    "dist",
    "build",
    "target",
    "coverage",
    "htmlcov",
    "__pycache__",
    "var/ai-context",
    "reports/latest",
}

EXCLUDED_FILE_GLOBS = [
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.o",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.tar",
    "*.tar.gz",
    "*.tgz",
    "*.zip",
    "*.7z",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.pdf",
    "*.mp4",
    "*.mov",
    "*.mp3",
    "*.wav",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
]

PROJECT_KNOWLEDGE_ROOT = "docs/project-knowledge"

IMPORTANT_DOCS = [
    "README.md",
    "README.rst",
    "README.txt",
    "AGENTS.md",
    "CLAUDE.md",
    "Codex_Input_Guidelines.md",
    "docs/Codex_Input_Guidelines.md",
    "00_GLOBAL_RULES.md",
    "docs/00_GLOBAL_RULES.md",
    "CONTRIBUTING.md",
    "Makefile",
    "pyproject.toml",
    "package.json",
    "vite.config.ts",
    "tsconfig.json",
    "docs/project-knowledge/index.md",
    "docs/project-knowledge/log.md",
    "docs/project-knowledge/runbooks/local-ai-review-on-oci.md",
    "docs/project-knowledge/architecture/ai-context-workflow.md",
]

SECRET_PATTERNS = [
    ("OpenAI-style key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{25,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key marker", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
]

@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


def now_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(cmd: Sequence[str], cwd: pathlib.Path, timeout: int = 120) -> CommandResult:
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CommandResult(" ".join(cmd), proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CommandResult(" ".join(cmd), 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(" ".join(cmd), 124, stdout, stderr + f"\nTIMEOUT after {timeout}s")


def write_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def append_command_report(path: pathlib.Path, title: str, result: CommandResult) -> None:
    body = [
        f"# {title}",
        "",
        f"Command: `{result.command}`",
        f"Exit: `{result.returncode}`",
        "",
        "## stdout",
        "```text",
        result.stdout.rstrip(),
        "```",
        "",
        "## stderr",
        "```text",
        result.stderr.rstrip(),
        "```",
        "",
    ]
    write_text(path, "\n".join(body))


def is_git_repo(repo: pathlib.Path) -> bool:
    return run(["git", "rev-parse", "--is-inside-work-tree"], repo, timeout=10).returncode == 0


def tool_path(names: Sequence[str]) -> str | None:
    for name in names:
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def safe_rel(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def should_exclude(rel: str, is_dir: bool) -> bool:
    rel = rel.strip("/")
    parts = rel.split("/") if rel else []
    for i in range(len(parts)):
        candidate = "/".join(parts[: i + 1])
        if candidate in EXCLUDED_DIRS or parts[i] in EXCLUDED_DIRS:
            return True
    if not is_dir:
        return any(fnmatch.fnmatch(parts[-1] if parts else rel, pat) or fnmatch.fnmatch(rel, pat) for pat in EXCLUDED_FILE_GLOBS)
    return False


def iter_repo_files(root: pathlib.Path, max_files: int = 20000) -> Iterable[pathlib.Path]:
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        base = pathlib.Path(dirpath)
        rel_dir = safe_rel(base, root)
        if rel_dir != "." and should_exclude(rel_dir, True):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in sorted(dirnames) if not should_exclude(safe_rel(base / d, root), True)]
        for filename in sorted(filenames):
            path = base / filename
            rel = safe_rel(path, root)
            if should_exclude(rel, False):
                continue
            count += 1
            if count > max_files:
                return
            yield path


def build_tree(root: pathlib.Path, max_entries: int = 1500) -> str:
    lines = ["."]
    entries: list[str] = []
    for path in iter_repo_files(root, max_files=max_entries):
        rel = safe_rel(path, root)
        entries.append(rel)
    for rel in sorted(entries):
        depth = rel.count("/")
        prefix = "  " * depth + "- "
        lines.append(prefix + rel.split("/")[-1] if depth else "- " + rel)
    if len(entries) >= max_entries:
        lines.append(f"... truncated after {max_entries} files")
    return "\n".join(lines) + "\n"


def read_small_file(path: pathlib.Path, max_chars: int = 12000) -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report only
        return f"[could not read: {exc}]\n"
    if len(value) > max_chars:
        return value[:max_chars] + f"\n\n[truncated at {max_chars} chars]\n"
    return value


def collect_docs(root: pathlib.Path, out: pathlib.Path) -> None:
    parts = ["# Important project docs", ""]
    seen: set[str] = set()
    for rel in IMPORTANT_DOCS:
        path = root / rel
        if path.exists() and path.is_file() and rel not in seen:
            seen.add(rel)
            parts.extend([f"## {rel}", "```text", read_small_file(path).rstrip(), "```", ""])
    write_text(out / "important-docs.md", "\n".join(parts))


def yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def okf_frontmatter(fields: dict[str, object]) -> str:
    lines = ["---"]
    # OKF v0.1 requires `type`; keep it first for readability.
    ordered = ["type", "title", "description", "resource", "tags", "timestamp"]
    keys = ordered + [key for key in sorted(fields) if key not in ordered]
    for key in keys:
        if key not in fields or fields[key] is None:
            continue
        value = fields[key]
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def okf_write_if_missing(path: pathlib.Path, fields: dict[str, object], body: str) -> bool:
    if path.exists():
        return False
    write_text(path, okf_frontmatter(fields) + body.rstrip() + "\n")
    return True


def okf_append(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_text(path, text.rstrip() + "\n")
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n" + text.rstrip() + "\n")


def project_knowledge_root(root: pathlib.Path) -> pathlib.Path:
    return root / os.environ.get("AI_CONTEXT_PROJECT_KNOWLEDGE_ROOT", PROJECT_KNOWLEDGE_ROOT)


def ensure_project_knowledge(root: pathlib.Path) -> list[str]:
    """Create a small OKF-compatible project knowledge base if it is missing.

    This is intentionally not a separate endpoint. Normal local-ai-context runs call
    it automatically so the repo gains durable memory even when the operator forgets
    the knowledge commands.
    """
    pk = project_knowledge_root(root)
    created: list[str] = []
    pk.mkdir(parents=True, exist_ok=True)
    now = now_stamp()
    docs = [
        (
            pk / "index.md",
            {
                "type": "index",
                "title": "Project knowledge index",
                "description": "Canonical human and agent-readable project memory for this repository.",
                "tags": ["project-knowledge", "okf", "local-ai"],
                "timestamp": now,
            },
            """
# Project knowledge index

This directory is the canonical durable knowledge layer for this repository. It follows the lightweight OKF shape: Markdown files with YAML frontmatter, readable by humans and local AI tools.

## Daily entry points

- [Local AI review on OCI](runbooks/local-ai-review-on-oci.md)
- [Validation commands](runbooks/validation-commands.md)
- [AI context workflow](architecture/ai-context-workflow.md)
- [Project activity log](log.md)

## Operating rule

Temporary packets live in `var/ai-context/` and are ignored by git. Durable lessons, validation commands, architecture decisions, and repeated failure fixes belong here.
""",
        ),
        (
            pk / "log.md",
            {
                "type": "log",
                "title": "Project knowledge log",
                "description": "Append-only ledger of local AI context packets, validations, and durable observations.",
                "tags": ["project-knowledge", "log", "local-ai"],
                "timestamp": now,
            },
            """
# Project knowledge log

Newest entries are appended below. This file is intentionally short and factual.
""",
        ),
        (
            pk / "runbooks" / "local-ai-review-on-oci.md",
            {
                "type": "runbook",
                "title": "Local AI review on OCI",
                "description": "Atomic local Ollama review workflow for this repository.",
                "tags": ["ollama", "oci", "review", "operator-workflow"],
                "timestamp": now,
            },
            """
# Local AI review on OCI

Use the atomic flow. Generate a packet, inspect it, then run the smallest review profile first.

```bash
make local-ai-context TASK=general-review
make local-ai-inspect
OLLAMA_MODEL=qwen2.5-coder:7b make local-ai-run-latest-small
```

From a parent directory, use copy-paste-safe `make -C` commands:

```bash
make -C /absolute/path/to/repo local-ai-context TASK=general-review
make -C /absolute/path/to/repo local-ai-inspect
OLLAMA_MODEL=qwen2.5-coder:7b make -C /absolute/path/to/repo local-ai-run-latest-small
```

Do not start with the full profile on CPU-only OCI. Move from `small` to `medium` only after the small output is useful.
""",
        ),
        (
            pk / "runbooks" / "validation-commands.md",
            {
                "type": "runbook",
                "title": "Validation commands",
                "description": "Repository-specific validation commands that should be captured in local AI context packets.",
                "tags": ["validation", "operator-workflow", "local-ai"],
                "timestamp": now,
            },
            """
# Validation commands

Prefer a real repository-specific validation command. Do not assume every repo has `make test`.

## Discovery

```bash
grep -nE '^[a-zA-Z0-9_.-]+:' Makefile
```

## Usage

```bash
AI_CONTEXT_VALIDATE_COMMAND='<repo-specific-command>' make local-ai-context TASK=general-review
```

## Known-good commands

Add commands here when they are confirmed for this repository.
""",
        ),
        (
            pk / "architecture" / "ai-context-workflow.md",
            {
                "type": "architecture",
                "title": "AI context workflow",
                "description": "How temporary AI packets and durable project knowledge work together.",
                "tags": ["architecture", "local-ai", "okf", "context"],
                "timestamp": now,
            },
            """
# AI context workflow

This repository uses two layers:

1. `var/ai-context/` — temporary, ignored packets for one review or run.
2. `docs/project-knowledge/` — durable, git-tracked project memory.

The `local-ai-context` command automatically includes project knowledge in each review packet and appends a factual log entry. This keeps the workflow useful even if the operator forgets about the knowledge layer.

## Rule

If a fact will matter tomorrow, keep it in `docs/project-knowledge/`. If it is only a one-run artifact, keep it in `var/ai-context/`.
""",
        ),
    ]
    for path, fields, body in docs:
        if okf_write_if_missing(path, fields, textwrap.dedent(body).strip()):
            created.append(safe_rel(path, root))
    return created


def append_project_knowledge_log(root: pathlib.Path, task: str, packet: pathlib.Path, validation_command: str | None, validation_exit: str | None) -> None:
    ensure_project_knowledge(root)
    pk = project_knowledge_root(root)
    stamp = now_stamp()
    rel_packet = safe_rel(packet, root)
    status = f"validation_exit={validation_exit}" if validation_exit is not None else "validation=not-run"
    command = validation_command or "not-run"
    text = f"""
## {stamp} — {task}

- Packet: `{rel_packet}`
- Validation command: `{command}`
- Status: `{status}`
"""
    okf_append(pk / "log.md", textwrap.dedent(text))


def update_project_knowledge_topic(root: pathlib.Path, topic: str, packet: pathlib.Path | None = None, validation_command: str | None = None, validation_exit: str | None = None) -> pathlib.Path:
    ensure_project_knowledge(root)
    pk = project_knowledge_root(root)
    stamp = now_stamp()
    slug = slugify(topic)
    path = pk / "topics" / f"{slug}.md"
    if not path.exists():
        okf_write_if_missing(
            path,
            {
                "type": "topic",
                "title": topic,
                "description": f"Durable project knowledge for {topic}.",
                "tags": ["topic", "local-ai", slug],
                "timestamp": stamp,
            },
            f"# {topic}\n\nThis topic note is updated by local AI context runs when `{topic}` is used as the task/topic.\n",
        )
    rel_packet = safe_rel(packet, root) if packet else "not-linked"
    text = f"""
## Observation {stamp}

- Packet: `{rel_packet}`
- Validation command: `{validation_command or 'not-run'}`
- Validation exit: `{validation_exit if validation_exit is not None else 'not-run'}`

Add durable findings here after reviewing the packet. Keep only facts that will help future work.
"""
    okf_append(path, textwrap.dedent(text))
    return path


def collect_project_knowledge(root: pathlib.Path, out: pathlib.Path, max_files: int = 40, max_chars_per_file: int = 12000) -> None:
    pk = project_knowledge_root(root)
    if not pk.exists():
        write_text(out / "project-knowledge.md", "# Project knowledge\n\nNo project knowledge directory exists yet.\n")
        return
    parts = ["# Project knowledge", "", f"Root: `{safe_rel(pk, root)}`", ""]
    files = sorted(path for path in pk.rglob("*.md") if path.is_file())[:max_files]
    for path in files:
        rel = safe_rel(path, root)
        parts.extend([f"## {rel}", "```markdown", read_small_file(path, max_chars=max_chars_per_file).rstrip(), "```", ""])
    if len(files) >= max_files:
        parts.append(f"[truncated after {max_files} project knowledge files]")
    write_text(out / "project-knowledge.md", "\n".join(parts).rstrip() + "\n")


def latest_validation_exit(packet: pathlib.Path) -> str | None:
    validation = packet / "validation-output.txt"
    if not validation.exists():
        return None
    text = validation.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[:5]:
        if line.startswith("Exit:"):
            return line.split(":", 1)[1].strip()
    return None


def inspect_project_knowledge(root: pathlib.Path) -> int:
    pk = project_knowledge_root(root)
    print("Project knowledge")
    print("=================")
    print(f"[INFO] repo: {root}")
    print(f"[INFO] root: {pk}")
    if not pk.exists():
        print("[WARN] project knowledge is not initialized")
        print(f"Run: make -C {shlex.quote(str(root))} local-ai-knowledge-init")
        return 1
    docs = sorted(path for path in pk.rglob("*.md") if path.is_file())
    print(f"[OK] markdown docs: {len(docs)}")
    for path in docs[:30]:
        print(f"  - {safe_rel(path, root)} ({human_size(path.stat().st_size)})")
    if len(docs) > 30:
        print(f"  ... {len(docs) - 30} more")
    log = pk / "log.md"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-24:]
        print("\nRecent log tail:")
        for line in lines:
            print(f"  {line[:180]}")
    print("\nDaily commands:")
    print(f"  make -C {shlex.quote(str(root))} local-ai-context TASK=general-review")
    print(f"  make -C {shlex.quote(str(root))} local-ai-inspect")
    print(f"  make -C {shlex.quote(str(root))} local-ai-knowledge-inspect")
    return 0


def collect_git(root: pathlib.Path, out: pathlib.Path) -> dict[str, str | bool]:
    info: dict[str, str | bool] = {"is_git_repo": False}
    if not is_git_repo(root):
        write_text(out / "git-status.txt", "Not a git repository.\n")
        return info

    info["is_git_repo"] = True
    commands = {
        "git-status.txt": ["git", "status", "--short", "--branch"],
        "recent-commits.txt": ["git", "log", "--oneline", "--decorate", "-n", "20"],
        "changed-files.txt": ["git", "diff", "--name-only", "HEAD"],
        "current-diff.patch": ["git", "diff", "--binary"],
        "staged-diff.patch": ["git", "diff", "--cached", "--binary"],
    }
    for filename, cmd in commands.items():
        result = run(cmd, root, timeout=120)
        write_text(out / filename, result.stdout if result.stdout else result.stderr)

    branch = run(["git", "branch", "--show-current"], root, timeout=10).stdout.strip()
    head = run(["git", "rev-parse", "--short", "HEAD"], root, timeout=10).stdout.strip()
    remote = run(["git", "remote", "-v"], root, timeout=10).stdout.strip()
    info.update({"branch": branch, "head": head, "remote": remote})
    return info


def collect_tool_versions(root: pathlib.Path, out: pathlib.Path) -> dict[str, str | None]:
    tools = {
        "git": ["git", "--version"],
        "python": [sys.executable, "--version"],
        "repomix": ["repomix", "--version"],
        "npx": ["npx", "--version"],
        "ctags": ["ctags", "--version"],
        "rg": ["rg", "--version"],
        "ast-grep": ["ast-grep", "--version"],
        "sg": ["sg", "--version"],
        "ollama": ["ollama", "--version"],
    }
    detected: dict[str, str | None] = {}
    lines = ["# Tool detection", ""]
    for name, cmd in tools.items():
        exe = tool_path([cmd[0]])
        detected[name] = exe
        if not exe:
            lines.append(f"- {name}: not found")
            continue
        result = run(cmd, root, timeout=20)
        first = (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr).splitlines() else "found"
        lines.append(f"- {name}: `{exe}` — {first}")
    lines.extend([
        "",
        "## Install hints",
        "",
        "Debian/Ubuntu examples:",
        "",
        "```bash",
        "sudo apt-get update",
        "sudo apt-get install -y ripgrep universal-ctags npm",
        "# Optional: npm install -g repomix @ast-grep/cli",
        "```",
        "",
        "This packet does not require every tool. Missing optional tools create notes instead of failing.",
    ])
    write_text(out / "tool-detection.md", "\n".join(lines) + "\n")
    return detected


def collect_secrets_scan(root: pathlib.Path, out: pathlib.Path) -> None:
    findings: list[str] = []
    for path in iter_repo_files(root, max_files=8000):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:200000]
        except Exception:
            continue
        rel = safe_rel(path, root)
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"- {label}: `{rel}`")
    if findings:
        body = "# Lightweight secret scan\n\nPotential secrets were found. Review before sharing context outside your machine.\n\n" + "\n".join(findings) + "\n"
    else:
        body = "# Lightweight secret scan\n\nNo obvious high-signal secret patterns found by the lightweight local scan.\n"
    write_text(out / "secret-scan.md", body)


def collect_ripgrep(root: pathlib.Path, out: pathlib.Path, detected: dict[str, str | None]) -> None:
    rg = detected.get("rg")
    if not rg:
        write_text(out / "ripgrep-findings.md", "# Ripgrep findings\n\n`rg` not found. Install ripgrep to enable deterministic text findings.\n")
        return
    patterns = [
        ("TODO/FIXME/HACK", r"TODO|FIXME|HACK|XXX"),
        ("Safety/temporary markers", r"temporary|workaround|bypass|skip|xfail|noqa|type:\s*ignore"),
        ("Operator command markers", r"make |Codex|Ollama|tmux|Daytona|operator"),
    ]
    parts = ["# Ripgrep findings", ""]
    for title, pattern in patterns:
        result = run([rg, "--line-number", "--hidden", "--glob", "!.git", pattern], root, timeout=60)
        content = (result.stdout or result.stderr).strip()
        if len(content) > 30000:
            content = content[:30000] + "\n[truncated]\n"
        parts.extend([f"## {title}", "```text", content or "No findings.", "```", ""])
    write_text(out / "ripgrep-findings.md", "\n".join(parts))


def collect_ctags(root: pathlib.Path, out: pathlib.Path, detected: dict[str, str | None]) -> None:
    ctags = detected.get("ctags")
    if not ctags:
        write_text(out / "repo-map.md", "# Repository symbol map\n\n`ctags` not found. Install universal-ctags to enable symbol maps.\n")
        return
    json_path = out / "ctags-symbols.jsonl"
    tags_path = out / "ctags-symbols.tags"
    exclude_args: list[str] = []
    for item in sorted(EXCLUDED_DIRS):
        exclude_args.append(f"--exclude={item}")
    result = run([ctags, "-R", "--output-format=json", "-f", str(json_path), *exclude_args, "."], root, timeout=180)
    if result.returncode != 0 or not json_path.exists() or json_path.stat().st_size == 0:
        fallback = run([ctags, "-R", "-f", str(tags_path), *exclude_args, "."], root, timeout=180)
        if fallback.returncode != 0:
            write_text(out / "repo-map.md", "# Repository symbol map\n\nctags failed.\n\n```text\n" + result.stderr + "\n" + fallback.stderr + "\n```\n")
            return
        build_repo_map_from_tags(tags_path, out / "repo-map.md")
        return
    build_repo_map_from_jsonl(json_path, out / "repo-map.md")


def build_repo_map_from_jsonl(json_path: pathlib.Path, out_path: pathlib.Path) -> None:
    by_file: dict[str, list[dict[str, str]]] = {}
    for line in json_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        path = item.get("path") or "unknown"
        name = item.get("name") or "?"
        kind = item.get("kind") or item.get("kindName") or "symbol"
        line_no = str(item.get("line") or "")
        signature = item.get("signature") or item.get("typeref") or ""
        by_file.setdefault(path, []).append({"name": name, "kind": kind, "line": line_no, "signature": signature})
    write_repo_map(by_file, out_path)


def build_repo_map_from_tags(tags_path: pathlib.Path, out_path: pathlib.Path) -> None:
    by_file: dict[str, list[dict[str, str]]] = {}
    for line in tags_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("!"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, path = parts[0], parts[1]
        extra = "\t".join(parts[3:])
        kind = extra.split("\t", 1)[0] if extra else "symbol"
        by_file.setdefault(path, []).append({"name": name, "kind": kind, "line": "", "signature": ""})
    write_repo_map(by_file, out_path)


def write_repo_map(by_file: dict[str, list[dict[str, str]]], out_path: pathlib.Path) -> None:
    parts = ["# Repository symbol map", "", "Generated from ctags. Use this before sending whole files to a local model.", ""]
    total = 0
    for path in sorted(by_file)[:500]:
        symbols = by_file[path][:80]
        if not symbols:
            continue
        parts.append(f"## {path}")
        for symbol in symbols:
            total += 1
            loc = f":{symbol['line']}" if symbol.get("line") else ""
            sig = f" — {symbol['signature']}" if symbol.get("signature") else ""
            parts.append(f"- `{symbol['kind']}` `{symbol['name']}`{loc}{sig}")
        parts.append("")
    if len(by_file) > 500:
        parts.append(f"[truncated after 500 files; total files with symbols: {len(by_file)}]")
    parts.append(f"\nTotal listed symbols: {total}\n")
    write_text(out_path, "\n".join(parts))


def collect_ast_grep(root: pathlib.Path, out: pathlib.Path, detected: dict[str, str | None]) -> None:
    sg = detected.get("ast-grep") or detected.get("sg")
    if not sg:
        write_text(out / "ast-grep-findings.md", "# ast-grep findings\n\n`ast-grep`/`sg` not found. Install `@ast-grep/cli` to enable structural search.\n")
        return
    config = root / "sgconfig.yml"
    if config.exists():
        result = run([sg, "scan"], root, timeout=120)
        content = (result.stdout or result.stderr).strip()
        write_text(out / "ast-grep-findings.md", f"# ast-grep findings\n\nCommand: `{sg} scan`\n\n```text\n{content or 'No findings.'}\n```\n")
    else:
        write_text(out / "ast-grep-findings.md", "# ast-grep findings\n\nast-grep is installed, but no `sgconfig.yml` exists. Add project-specific structural rules when needed.\n")


def collect_repomix(root: pathlib.Path, out: pathlib.Path, detected: dict[str, str | None], use_npx: bool) -> None:
    output = out / "repomix-compressed.xml"
    notes = out / "repomix-notes.md"
    repomix = detected.get("repomix")
    cmd: list[str] | None = None
    if repomix:
        cmd = [repomix, "--output", str(output), "--style", "xml", "--compress"]
    elif use_npx and detected.get("npx"):
        cmd = [detected["npx"] or "npx", "--yes", "repomix@latest", "--output", str(output), "--style", "xml", "--compress"]
    if not cmd:
        write_text(notes, "# Repomix\n\nRepomix was not found. Install it or run with `AI_CONTEXT_USE_NPX=1` to allow `npx --yes repomix@latest`.\n")
        return
    result = run(cmd, root, timeout=300)
    if result.returncode != 0:
        write_text(notes, "# Repomix\n\nRepomix failed. The rest of the packet is still usable.\n\n```text\n" + result.stdout + "\n" + result.stderr + "\n```\n")
        return
    size = output.stat().st_size if output.exists() else 0
    write_text(notes, f"# Repomix\n\nGenerated `{output.name}` ({size} bytes).\n\n```text\n{result.stdout.strip()}\n{result.stderr.strip()}\n```\n")


def collect_validation(root: pathlib.Path, out: pathlib.Path, command: str | None) -> None:
    if not command:
        write_text(out / "validation-output.txt", "No validation command was run. Set AI_CONTEXT_VALIDATE_COMMAND, for example:\n\nAI_CONTEXT_VALIDATE_COMMAND='make test' make local-ai-context\n")
        return
    result = subprocess.run(command, cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, timeout=1800, check=False)
    write_text(out / "validation-output.txt", f"Command: {command}\nExit: {result.returncode}\n\n{result.stdout}")


def build_prompt(root: pathlib.Path, out: pathlib.Path, task: str, model_hint: str) -> None:
    rel_out = safe_rel(out, root)
    prompt = f"""
# Ollama review prompt

You are reviewing this repository using a deterministic context packet. Do not guess from memory.

Task: {task}

Context packet path: `{rel_out}`

Important: plain `ollama run` cannot open files from disk. Use the generated self-contained file `ollama-review-input.md` for direct CLI review. This prompt file is kept as a small readable instruction template.

When reviewing, use packet facts in this order:

1. Git status and changed files
2. Current/staged diffs
3. Validation output
4. Important docs and repo map
5. Ripgrep/ast-grep findings
6. Repomix summary/content when present

Response format:

- Verdict: PASS / NEEDS_WORK / BLOCKED
- What changed or what should change
- Highest-risk files/functions
- Exact validation command to run next
- Any missing context you need

Rules:

- Prefer simple operator workflows over clever hidden behavior.
- Do not invent files or APIs that are not visible in the packet.
- If validation failed, explain the first meaningful failure, not every downstream symptom.
- If the packet lacks enough context, name the exact files or commands needed.

Suggested direct command:

```bash
cat {shlex.quote(str(out / 'ollama-review-input.md'))} | ollama run {shlex.quote(model_hint)}
```
""".strip() + "\n"
    write_text(out / "ollama-review-prompt.md", prompt)


def read_for_review(path: pathlib.Path, max_chars: int, prefer_tail: bool = False) -> str:
    if not path.exists():
        return "[missing]\n"
    try:
        value = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report only
        return f"[could not read: {exc}]\n"
    if len(value) <= max_chars:
        return value.rstrip() + "\n"
    marker = f"\n[truncated: original {len(value)} chars, included {max_chars} chars]\n"
    if prefer_tail:
        return marker + value[-max_chars:].rstrip() + "\n"
    if max_chars >= 2000:
        head = max_chars // 2
        tail = max_chars - head
        return value[:head].rstrip() + marker + value[-tail:].rstrip() + "\n"
    return value[:max_chars].rstrip() + marker


def append_review_section(parts: list[str], out: pathlib.Path, filename: str, title: str, max_chars: int, prefer_tail: bool = False) -> None:
    parts.extend([f"## {title}", "", f"File: `{filename}`", "", "```text", read_for_review(out / filename, max_chars=max_chars, prefer_tail=prefer_tail).rstrip(), "```", ""])



def review_profiles() -> dict[str, dict[str, int]]:
    """Character budgets for self-contained Ollama review input.

    Small is intentionally conservative for CPU-only Ollama. Full keeps the v2
    behavior for cases where the operator explicitly wants a large prompt.
    """
    return {
        "small": {
            "manifest.json": 6000,
            "git-status.txt": 12000,
            "recent-commits.txt": 8000,
            "changed-files.txt": 10000,
            "current-diff.patch": 25000,
            "staged-diff.patch": 25000,
            "validation-output.txt": 30000,
            "project-knowledge.md": 22000,
            "important-docs.md": 22000,
            "repo-map.md": 18000,
            "ripgrep-findings.md": 12000,
            "ast-grep-findings.md": 8000,
            "repomix-notes.md": 6000,
            "repomix-compressed.xml": int(os.environ.get("AI_CONTEXT_REPOMIX_REVIEW_CHARS", "0")),
            "secret-scan.md": 6000,
        },
        "medium": {
            "manifest.json": 10000,
            "git-status.txt": 16000,
            "recent-commits.txt": 12000,
            "changed-files.txt": 14000,
            "current-diff.patch": 45000,
            "staged-diff.patch": 45000,
            "validation-output.txt": 50000,
            "project-knowledge.md": 35000,
            "important-docs.md": 40000,
            "repo-map.md": 40000,
            "ripgrep-findings.md": 25000,
            "ast-grep-findings.md": 15000,
            "repomix-notes.md": 10000,
            "repomix-compressed.xml": int(os.environ.get("AI_CONTEXT_REPOMIX_REVIEW_CHARS", "25000")),
            "secret-scan.md": 10000,
        },
        "full": {
            "manifest.json": 12000,
            "git-status.txt": 20000,
            "recent-commits.txt": 16000,
            "changed-files.txt": 16000,
            "current-diff.patch": 70000,
            "staged-diff.patch": 70000,
            "validation-output.txt": 70000,
            "project-knowledge.md": 50000,
            "important-docs.md": 55000,
            "repo-map.md": 55000,
            "ripgrep-findings.md": 45000,
            "ast-grep-findings.md": 25000,
            "repomix-notes.md": 12000,
            "repomix-compressed.xml": int(os.environ.get("AI_CONTEXT_REPOMIX_REVIEW_CHARS", "90000")),
            "secret-scan.md": 12000,
        },
    }


def normalize_review_profile(value: str | None) -> str:
    profile = (value or os.environ.get("AI_CONTEXT_REVIEW_PROFILE") or "small").strip().lower()
    if profile not in review_profiles():
        valid = ", ".join(sorted(review_profiles()))
        raise ValueError(f"unknown review profile: {profile!r}; expected one of: {valid}")
    return profile


def build_review_input(root: pathlib.Path, out: pathlib.Path, task: str, model_hint: str, profile: str = "small") -> pathlib.Path:
    profile = normalize_review_profile(profile)
    budgets = review_profiles()[profile]
    parts: list[str] = [
        "# Self-contained Ollama review input",
        "",
        "You are reviewing a repository using a deterministic context packet that has been pasted below.",
        "Plain Ollama CLI cannot open files from disk, so useful packet content is included in this one file with size guards.",
        "",
        f"Task: {task}",
        f"Repository: {root}",
        f"Packet: {out}",
        f"Review profile: {profile}",
        f"Model hint: {model_hint}",
        "",
        "## Review instructions",
        "",
        "Return:",
        "",
        "- Verdict: PASS / NEEDS_WORK / BLOCKED",
        "- What changed or what should change",
        "- Highest-risk files/functions",
        "- Exact validation command to run next",
        "- Any missing context needed",
        "",
        "Rules:",
        "",
        "- Do not invent files or APIs that are not present in this input.",
        "- Prefer simple operator workflows over clever hidden behavior.",
        "- If validation failed, explain the first meaningful failure, not every downstream symptom.",
        "- If this input is insufficient, name the exact file or command needed next.",
        "- Treat `docs/project-knowledge/` content as durable project memory, but still verify against current git state.",
        "",
        "# Packet content",
        "",
    ]
    section_order = [
        ("manifest.json", "Manifest", False),
        ("git-status.txt", "Git status", False),
        ("recent-commits.txt", "Recent commits", False),
        ("changed-files.txt", "Changed files", False),
        ("current-diff.patch", "Current unstaged diff", False),
        ("staged-diff.patch", "Current staged diff", False),
        ("validation-output.txt", "Validation output", True),
        ("project-knowledge.md", "Durable project knowledge", False),
        ("important-docs.md", "Important docs", False),
        ("repo-map.md", "Repository symbol map", False),
        ("ripgrep-findings.md", "Ripgrep findings", False),
        ("ast-grep-findings.md", "ast-grep findings", False),
        ("repomix-notes.md", "Repomix notes", False),
        ("repomix-compressed.xml", "Repomix compressed context", False),
        ("secret-scan.md", "Lightweight secret scan", False),
    ]
    for filename, title, prefer_tail in section_order:
        max_chars = budgets.get(filename, 0)
        if max_chars <= 0:
            parts.extend([f"## {title}", "", f"File: `{filename}`", "", "```text", "[omitted by review profile]", "```", ""])
            continue
        append_review_section(parts, out, filename, title, max_chars, prefer_tail)

    review_input = out / f"ollama-review-input.{profile}.md"
    write_text(review_input, "\n".join(parts).rstrip() + "\n")
    # Backwards-compatible default path points at the selected profile.
    write_text(out / "ollama-review-input.md", review_input.read_text(encoding="utf-8"))
    return review_input


def latest_packet_dir(root: pathlib.Path, output_root: str) -> pathlib.Path | None:
    out_root = (root / output_root).resolve()
    latest = out_root / "latest"
    if latest.exists():
        return latest.resolve()
    pointer = out_root / "LATEST.txt"
    if pointer.exists():
        pointed = pathlib.Path(pointer.read_text(encoding="utf-8").strip())
        return pointed if pointed.exists() else None
    return None


def human_size(num: int) -> str:
    value = float(num)
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num} B"


def inspect_latest(root: pathlib.Path, output_root: str, profile: str, model_hint: str) -> int:
    packet = latest_packet_dir(root, output_root)
    print("Local AI latest packet")
    print("======================")
    print(f"[INFO] repo: {root}")
    if not packet:
        print(f"[ERROR] no latest packet found under {(root / output_root).resolve()}", file=sys.stderr)
        return 2
    print(f"[INFO] packet: {packet}")
    profile = normalize_review_profile(profile)
    candidates = [
        packet / f"ollama-review-input.{profile}.md",
        packet / "ollama-review-input.md",
    ]
    input_file = next((p for p in candidates if p.exists()), candidates[0])
    files = [
        "git-status.txt",
        "changed-files.txt",
        "current-diff.patch",
        "staged-diff.patch",
        "validation-output.txt",
        "project-knowledge.md",
        "important-docs.md",
        "repo-map.md",
        "repomix-compressed.xml",
        "ollama-review-input.small.md",
        "ollama-review-input.medium.md",
        "ollama-review-input.full.md",
        "ollama-review-input.md",
    ]
    print("\nFiles:")
    for name in files:
        path = packet / name
        if path.exists():
            print(f"  {name}: {human_size(path.stat().st_size)}")
    validation = packet / "validation-output.txt"
    if validation.exists():
        text = validation.read_text(encoding="utf-8", errors="replace")
        first_lines = text.splitlines()[:6]
        print("\nValidation head:")
        for line in first_lines:
            print(f"  {line[:180]}")
        tail_lines = text.splitlines()[-12:]
        print("\nValidation tail:")
        for line in tail_lines:
            print(f"  {line[:180]}")
    print("\nRun latest review:")
    print(f"  cat {shlex.quote(str(input_file))} | ollama run {shlex.quote(model_hint)}")
    print("\nSafer atomic flow:")
    print(f"  make -C {shlex.quote(str(root))} local-ai-context TASK=<task>")
    print(f"  make -C {shlex.quote(str(root))} local-ai-inspect")
    print(f"  make -C {shlex.quote(str(root))} local-ai-run-latest-small")
    return 0

def build_packet_readme(root: pathlib.Path, out: pathlib.Path, task: str) -> None:
    rel_out = safe_rel(out, root)
    text = f"""
# Local AI context packet

Task: {task}
Generated: {now_stamp()}
Repository: `{root}`

This packet is designed for local/Ollama-assisted code review and planning. It keeps deterministic facts separate from model reasoning.

## Main files

- `manifest.json` — repo, branch, tool, and packet metadata.
- `git-status.txt` — short status and branch.
- `current-diff.patch` — unstaged diff.
- `staged-diff.patch` — staged diff.
- `changed-files.txt` — changed files relative to HEAD.
- `project-knowledge.md` — durable OKF-style project knowledge included in the review packet.
- `important-docs.md` — key docs/config files copied into one small file.
- `tree.txt` — lightweight repo file tree.
- `repo-map.md` — ctags-based symbol map if ctags is installed.
- `repomix-compressed.xml` — compressed repo packet if Repomix is installed.
- `ripgrep-findings.md` — deterministic text findings if ripgrep is installed.
- `ast-grep-findings.md` — structural findings if ast-grep is installed/configured.
- `validation-output.txt` — validation command output when `AI_CONTEXT_VALIDATE_COMMAND` is set.
- `ollama-review-prompt.md` — small readable instruction template.
- `ollama-review-input.md` — self-contained prompt plus packet content for direct `ollama run`.

## Durable project knowledge

Canonical reusable knowledge lives under `docs/project-knowledge/`. The `local-ai-context` command initializes it automatically and appends a factual run log so repeated work becomes easier over time.

## Good next commands

From repo root:

```bash
cat {rel_out}/ollama-review-input.md | ollama run qwen2.5-coder:14b
```

From any parent directory:

```bash
cat {shlex.quote(str(out / 'ollama-review-input.md'))} | ollama run qwen2.5-coder:14b
```

Or regenerate and review in one step:

```bash
make -C {shlex.quote(str(root))} local-ai-review TASK='{task}'
```

For a validation-aware packet:

```bash
AI_CONTEXT_VALIDATE_COMMAND='make test' make local-ai-context TASK='{task}'
```

For one-off Repomix through npx when it is not globally installed:

```bash
AI_CONTEXT_USE_NPX=1 make local-ai-context TASK='{task}'
```
""".strip() + "\n"
    write_text(out / "PACKET_README.md", text)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an Ollama-friendly local AI context packet.")
    parser.add_argument("--task", default=os.environ.get("TASK", "general-review"), help="Task/slice/refactor name for this packet.")
    parser.add_argument("--output-root", default=os.environ.get("AI_CONTEXT_OUTPUT_ROOT", "var/ai-context"), help="Output root under repo.")
    parser.add_argument("--repo-root", default=os.environ.get("REPO_ROOT", "."), help="Repository root. Defaults to current directory.")
    parser.add_argument("--validate-command", default=os.environ.get("AI_CONTEXT_VALIDATE_COMMAND"), help="Optional validation command to run and capture.")
    parser.add_argument("--use-npx", action="store_true", default=os.environ.get("AI_CONTEXT_USE_NPX") == "1", help="Allow npx --yes repomix@latest when repomix is not installed.")
    parser.add_argument("--model-hint", default=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b"), help="Model name shown in generated prompt examples.")
    parser.add_argument("--review-profile", default=os.environ.get("AI_CONTEXT_REVIEW_PROFILE", "small"), choices=sorted(review_profiles()), help="Size profile for self-contained Ollama input. Default: small.")
    parser.add_argument("--inspect-latest", action="store_true", help="Inspect latest packet and print exact atomic review commands without generating a new packet.")
    parser.add_argument("--okf-init", action="store_true", help="Initialize durable OKF-style project knowledge and exit.")
    parser.add_argument("--okf-inspect", action="store_true", help="Inspect durable project knowledge and exit.")
    parser.add_argument("--okf-update", action="store_true", help="Append a factual topic observation from the latest packet and exit.")
    parser.add_argument("--topic", default=os.environ.get("TOPIC"), help="Topic name for --okf-update. Defaults to --task.")
    parser.add_argument("--skip-okf", action="store_true", default=os.environ.get("AI_CONTEXT_SKIP_OKF") == "1", help="Do not initialize/update project knowledge during packet generation.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    root = pathlib.Path(args.repo_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] repo root not found: {root}", file=sys.stderr)
        return 2

    if args.okf_init:
        created = ensure_project_knowledge(root)
        print("Project knowledge init")
        print("======================")
        print(f"[INFO] repo: {root}")
        print(f"[INFO] root: {project_knowledge_root(root)}")
        if created:
            for rel in created:
                print(f"[CREATE] {rel}")
        else:
            print("[OK] already initialized")
        return 0

    if args.okf_inspect:
        return inspect_project_knowledge(root)

    if args.okf_update:
        packet = latest_packet_dir(root, args.output_root)
        topic = args.topic or args.task
        path = update_project_knowledge_topic(
            root,
            topic,
            packet,
            args.validate_command,
            latest_validation_exit(packet) if packet else None,
        )
        print("Project knowledge update")
        print("========================")
        print(f"[INFO] topic: {topic}")
        print(f"[OK] updated: {path}")
        return 0

    if args.inspect_latest:
        return inspect_latest(root, args.output_root, args.review_profile, args.model_hint)

    stamp = now_stamp()
    out_root = (root / args.output_root).resolve()
    out = out_root / f"{stamp}-{slugify(args.task)}"
    out.mkdir(parents=True, exist_ok=False)

    print("Local AI context packet")
    print("=======================")
    print(f"[INFO] repo: {root}")
    print(f"[INFO] task: {args.task}")
    print(f"[INFO] output: {out}")
    print(f"[INFO] review profile: {args.review_profile}")

    if not args.skip_okf:
        print("[STEP] ensuring durable project knowledge")
        created = ensure_project_knowledge(root)
        for rel in created:
            print(f"[CREATE] {rel}")
    else:
        print("[STEP] skipping durable project knowledge")

    print("[STEP] detecting tools")
    detected = collect_tool_versions(root, out)
    print("[STEP] collecting git state")
    git_info = collect_git(root, out)
    print("[STEP] collecting important docs")
    collect_docs(root, out)
    print("[STEP] collecting durable project knowledge")
    collect_project_knowledge(root, out)
    print("[STEP] building lightweight file tree")
    write_text(out / "tree.txt", build_tree(root))
    print("[STEP] scanning for obvious secrets")
    collect_secrets_scan(root, out)
    print("[STEP] collecting ripgrep findings")
    collect_ripgrep(root, out, detected)
    print("[STEP] collecting ctags repo map")
    collect_ctags(root, out, detected)
    print("[STEP] collecting ast-grep findings")
    collect_ast_grep(root, out, detected)
    print("[STEP] collecting repomix context if available")
    collect_repomix(root, out, detected, bool(args.use_npx))
    print("[STEP] running validation command" if args.validate_command else "[STEP] skipping validation command")
    collect_validation(root, out, args.validate_command)
    print("[STEP] writing packet docs and prompts")
    build_packet_readme(root, out, args.task)
    build_prompt(root, out, args.task, args.model_hint)

    manifest = {
        "schema": "local-ai-context.v1",
        "generated_utc": stamp,
        "task": args.task,
        "repo_root": str(root),
        "output_dir": str(out),
        "git": git_info,
        "tools": detected,
        "validation_command": args.validate_command,
        "project_knowledge_root": str(project_knowledge_root(root)),
        "project_knowledge_enabled": not bool(args.skip_okf),
        "repomix_via_npx_allowed": bool(args.use_npx),
    }
    write_text(out / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if not args.skip_okf:
        validation_exit = latest_validation_exit(out)
        append_project_knowledge_log(root, args.task, out, args.validate_command, validation_exit)
        update_project_knowledge_topic(root, args.task, out, args.validate_command, validation_exit)
        collect_project_knowledge(root, out)
    for profile_name in sorted(review_profiles()):
        if profile_name != args.review_profile:
            build_review_input(root, out, args.task, args.model_hint, profile_name)
    review_input = build_review_input(root, out, args.task, args.model_hint, args.review_profile)

    latest = out_root / "latest"
    try:
        if latest.exists() or latest.is_symlink():
            if latest.is_symlink() or latest.is_file():
                latest.unlink()
            elif latest.is_dir():
                shutil.rmtree(latest)
        latest.symlink_to(out.name, target_is_directory=True)
    except OSError:
        # Symlinks may be unavailable; copy a pointer file instead.
        write_text(out_root / "LATEST.txt", str(out) + "\n")

    print("[OK] packet created")
    print(f"[OK] latest: {out_root / 'latest'}")
    print(f"[OK] review input: {review_input} ({human_size(review_input.stat().st_size)})")
    if not args.skip_okf:
        print(f"[OK] project knowledge: {project_knowledge_root(root)}")
    print("\nInspect before review:")
    print(f"  make -C {shlex.quote(str(root))} local-ai-inspect")
    print("\nNext from any directory:")
    print(f"  cat {shlex.quote(str(review_input))} | ollama run {shlex.quote(args.model_hint)}")
    print("\nOr regenerate and review in one step, small profile by default:")
    print(f"  make -C {shlex.quote(str(root))} local-ai-review TASK={shlex.quote(args.task)}")
    return 0


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip("-._")
    return value or "context"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
