"""A tiny local MCP server for sharing project state."""

import json
import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


PROJECT_DIR = Path(__file__).resolve().parent
STATE_DIR = PROJECT_DIR / "data"
STATE_FILE = STATE_DIR / "state.json"
LEGACY_STATE_FILE = PROJECT_DIR / "state.json"
STATE_HISTORY_DIR = STATE_DIR / "history"
SHARED_FILES_DIR = PROJECT_DIR / "shared_files"
MAX_TEXT_FILE_BYTES = 500_000
MAX_SECTION_LINES = 200
MAX_SECTION_CHARS = 20_000
MAX_SEARCH_MATCHES = 50
IGNORED_DIRS = {".git", ".history", "__pycache__", ".venv", "node_modules"}

mcp = FastMCP(
    "MCP Shared Workspace",
    instructions=(
        "For every project continuation or coding request, call get_project_state and "
        "list_project_files first, then read WORKFLOW.md. Shared state is stored locally in data/state.json. Use search_project_file and "
        "read_project_section to inspect only relevant code. For a small targeted edit, "
        "use patch_project_file with the exact file_sha256 returned by a read/search call; "
        "it requires the expected match count and saves a backup. Use write_project_file "
        "for new files or intentional full rewrites. Do not ask for files already in the "
        "shared folder. Work on one account at a time. After meaningful changes, call "
        "update_project_state with a concise handoff. Do not print the full project or "
        "claim unrun tests."
    ),
)


def _read_state_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as state_file:
        data = json.load(state_file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _write_state_file(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
        state_file.flush()
        os.fsync(state_file.fileno())
    os.replace(temp_path, path)


def _archive_legacy_state() -> None:
    """Migrate the latest root-level state and backups into data/ on first use."""
    if not LEGACY_STATE_FILE.exists():
        return

    legacy_state = _read_state_file(LEGACY_STATE_FILE)
    if not STATE_FILE.exists() or LEGACY_STATE_FILE.stat().st_mtime_ns >= STATE_FILE.stat().st_mtime_ns:
        _write_state_file(STATE_FILE, legacy_state)

    STATE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = STATE_HISTORY_DIR / f"state.json.legacy-root.{stamp}.bak"
    LEGACY_STATE_FILE.replace(archive_path)

    for backup_path in PROJECT_DIR.glob("state.json.*.bak"):
        destination = STATE_HISTORY_DIR / backup_path.name
        if destination.exists():
            destination = STATE_HISTORY_DIR / f"{backup_path.stem}.{stamp}{backup_path.suffix}"
        backup_path.replace(destination)


def read_state() -> dict[str, Any]:
    """Read shared state from data/state.json, migrating the legacy root file once."""
    _archive_legacy_state()
    if not STATE_FILE.exists():
        return {
            "project_name": "My shared project",
            "current_status": "Not started yet",
            "completed_work": [],
            "next_step": "Describe the first task",
            "notes": "",
        }
    return _read_state_file(STATE_FILE)


def write_state(state: dict[str, Any]) -> None:
    """Save readable state in data/state.json, migrating the legacy file first."""
    _archive_legacy_state()
    _write_state_file(STATE_FILE, state)

@mcp.tool()
def get_project_state() -> dict[str, Any]:
    """Get the current shared project state."""
    return read_state()


@mcp.tool()
def update_project_state(
    project_name: str,
    current_status: str,
    completed_work: list[str],
    next_step: str,
    notes: str = "",
) -> dict[str, Any]:
    """Replace the shared state with the latest project progress."""
    state = {
        "project_name": project_name,
        "current_status": current_status,
        "completed_work": completed_work,
        "next_step": next_step,
        "notes": notes,
    }
    write_state(state)
    return {"saved": True, "state": state}


def resolve_project_file(relative_path: str) -> Path:
    """Resolve a file path without allowing it to escape the shared folder."""
    candidate = Path(relative_path)
    if not relative_path.strip() or candidate.is_absolute() or candidate.drive:
        raise ValueError("Use a non-empty path relative to the shared_files folder")
    if any(part in ("..", "") for part in candidate.parts):
        raise ValueError("Parent-directory paths are not allowed")

    root = SHARED_FILES_DIR.resolve()
    target = (root / candidate).resolve()
    if target != root and root not in target.parents:
        raise ValueError("That path is outside the shared files folder")
    return target


def _read_text_bytes(target: Path) -> tuple[bytes, str]:
    """Read a bounded UTF-8 file and return its bytes and SHA-256 digest."""
    if not target.is_file():
        raise FileNotFoundError(f"No file exists at {target}")
    raw = target.read_bytes()
    if len(raw) > MAX_TEXT_FILE_BYTES:
        raise ValueError("This file is over 500 KB; split it into smaller text files first")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("This tool reads UTF-8 text files only; binary assets are not supported") from exc
    return raw, hashlib.sha256(raw).hexdigest()


def _normalized_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _save_text_with_backup(target: Path, content: str) -> str | None:
    """Atomically save text and preserve the previous file under .history."""
    SHARED_FILES_DIR.mkdir(parents=True, exist_ok=True)
    backup_path: str | None = None
    if target.exists():
        if not target.is_file():
            raise ValueError("The target path exists and is not a file")
        relative = target.relative_to(SHARED_FILES_DIR.resolve())
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = SHARED_FILES_DIR / ".history" / relative.parent / f"{relative.name}.{timestamp}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(target.read_bytes())
        backup_path = backup.relative_to(SHARED_FILES_DIR).as_posix()

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=target.parent, delete=False) as temp_file:
        temp_file.write(content)
        temp_name = temp_file.name
    os.replace(temp_name, target)
    return backup_path


@mcp.tool()
def list_project_files() -> list[dict[str, Any]]:
    """List source and text files in the shared files folder."""
    SHARED_FILES_DIR.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for path in sorted(SHARED_FILES_DIR.rglob("*")):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.relative_to(SHARED_FILES_DIR).parts):
            continue
        files.append({
            "path": path.relative_to(SHARED_FILES_DIR).as_posix(),
            "size_bytes": path.stat().st_size,
        })
        if len(files) >= 500:
            break
    return files


@mcp.tool()
def read_project_file(path: str) -> dict[str, Any]:
    """Read one UTF-8 text file from shared_files; use this for relevant files only."""
    target = resolve_project_file(path)
    if any(part in IGNORED_DIRS for part in target.relative_to(SHARED_FILES_DIR.resolve()).parts):
        raise ValueError("That folder is reserved for internal or dependency files")
    raw, file_sha256 = _read_text_bytes(target)
    return {
        "path": target.relative_to(SHARED_FILES_DIR.resolve()).as_posix(),
        "content": raw.decode("utf-8"),
        "file_sha256": file_sha256,
        "size_bytes": len(raw),
    }


@mcp.tool()
def read_project_section(path: str, start_line: int, line_count: int = 80) -> dict[str, Any]:
    """Read a bounded range of lines from a UTF-8 project file without returning the whole file."""
    target = resolve_project_file(path)
    if any(part in IGNORED_DIRS for part in target.relative_to(SHARED_FILES_DIR.resolve()).parts):
        raise ValueError("That folder is reserved for internal or dependency files")
    if start_line < 1:
        raise ValueError("start_line must be 1 or greater")
    if line_count < 1 or line_count > MAX_SECTION_LINES:
        raise ValueError(f"line_count must be between 1 and {MAX_SECTION_LINES}")

    raw, file_sha256 = _read_text_bytes(target)
    lines = _normalized_newlines(raw.decode("utf-8")).splitlines()
    start = start_line - 1
    selected = lines[start:start + line_count]
    content = "\n".join(selected)
    truncated = len(content) > MAX_SECTION_CHARS
    if truncated:
        content = content[:MAX_SECTION_CHARS]
    return {
        "path": target.relative_to(SHARED_FILES_DIR.resolve()).as_posix(),
        "start_line": start_line,
        "end_line": start + len(selected),
        "total_lines": len(lines),
        "content": content,
        "content_truncated": truncated,
        "file_sha256": file_sha256,
    }


@mcp.tool()
def search_project_file(
    path: str,
    query: str,
    context_lines: int = 2,
    max_matches: int = 20,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """Search one UTF-8 project file and return matching lines with small surrounding context."""
    target = resolve_project_file(path)
    if any(part in IGNORED_DIRS for part in target.relative_to(SHARED_FILES_DIR.resolve()).parts):
        raise ValueError("That folder is reserved for internal or dependency files")
    if not query:
        raise ValueError("query must not be empty")
    if len(query) > 500:
        raise ValueError("query must be 500 characters or fewer")
    if context_lines < 0 or context_lines > 10:
        raise ValueError("context_lines must be between 0 and 10")
    if max_matches < 1 or max_matches > MAX_SEARCH_MATCHES:
        raise ValueError(f"max_matches must be between 1 and {MAX_SEARCH_MATCHES}")

    raw, file_sha256 = _read_text_bytes(target)
    lines = _normalized_newlines(raw.decode("utf-8")).splitlines()
    needle = query if case_sensitive else query.casefold()
    found = [i for i, line in enumerate(lines) if needle in (line if case_sensitive else line.casefold())]
    matches = []
    for i in found[:max_matches]:
        lo = max(0, i - context_lines)
        hi = min(len(lines), i + context_lines + 1)
        matches.append({
            "line": i + 1,
            "snippet_start_line": lo + 1,
            "snippet": "\n".join(f"{j + 1}: {lines[j]}" for j in range(lo, hi)),
        })
    return {
        "path": target.relative_to(SHARED_FILES_DIR.resolve()).as_posix(),
        "query": query,
        "total_matches": len(found),
        "matches_truncated": len(found) > max_matches,
        "matches": matches,
        "file_sha256": file_sha256,
    }


@mcp.tool()
def patch_project_file(
    path: str,
    find_text: str,
    replace_text: str,
    expected_sha256: str,
    expected_matches: int = 1,
) -> dict[str, Any]:
    """Replace exact text only if the file hash and expected match count still match; back up before saving."""
    target = resolve_project_file(path)
    if any(part in IGNORED_DIRS for part in target.relative_to(SHARED_FILES_DIR.resolve()).parts):
        raise ValueError("That folder is reserved for internal or dependency files")
    if not find_text:
        raise ValueError("find_text must not be empty")
    if not expected_sha256 or len(expected_sha256) != 64:
        raise ValueError("expected_sha256 must be the 64-character hash returned by a read/search tool")
    if expected_matches < 1 or expected_matches > 100:
        raise ValueError("expected_matches must be between 1 and 100")

    raw, current_sha256 = _read_text_bytes(target)
    if current_sha256 != expected_sha256:
        raise ValueError("The file changed since it was read. Re-read/search the file and prepare the patch again.")

    original = raw.decode("utf-8")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    normalized = _normalized_newlines(original)
    find_normalized = _normalized_newlines(find_text)
    replace_normalized = _normalized_newlines(replace_text)
    matches = normalized.count(find_normalized)
    if matches != expected_matches:
        raise ValueError(f"Expected {expected_matches} exact match(es), found {matches}; file was not changed")

    patched = normalized.replace(find_normalized, replace_normalized, expected_matches)
    saved_content = patched.replace("\n", newline)
    if len(saved_content.encode("utf-8")) > MAX_TEXT_FILE_BYTES:
        raise ValueError("This tool writes text files up to 500 KB")
    backup_path = _save_text_with_backup(target, saved_content)
    saved_raw = target.read_bytes()
    return {
        "saved": True,
        "path": target.relative_to(SHARED_FILES_DIR.resolve()).as_posix(),
        "replacements": matches,
        "backup_path": backup_path,
        "size_bytes": len(saved_raw),
        "file_sha256": hashlib.sha256(saved_raw).hexdigest(),
    }


@mcp.tool()
def write_project_file(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Create or update a UTF-8 text file in shared_files, preserving a backup when replacing a file."""
    target = resolve_project_file(path)
    if any(part in IGNORED_DIRS for part in target.relative_to(SHARED_FILES_DIR.resolve()).parts):
        raise ValueError("That folder is reserved for internal or dependency files")
    if len(content.encode("utf-8")) > MAX_TEXT_FILE_BYTES:
        raise ValueError("This tool writes text files up to 500 KB")
    SHARED_FILES_DIR.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError("That file already exists. Set overwrite=true only after reading it and preparing the intended complete replacement.")
    backup_path = _save_text_with_backup(target, content)
    return {
        "saved": True,
        "path": target.relative_to(SHARED_FILES_DIR.resolve()).as_posix(),
        "backup_path": backup_path,
        "size_bytes": target.stat().st_size,
        "file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        # stdio is used by desktop clients that launch a local MCP server.
        mcp.run(transport="stdio")
    elif transport == "streamable-http":
        # For the temporary HTTPS tunnel setup, the long random URL path
        # acts as a shared secret. Keep the generated secret private.
        secret = os.environ.get("MCP_SHARED_PATH_SECRET", "").strip()
        if len(secret) < 32:
            raise SystemExit("MCP_SHARED_PATH_SECRET must be at least 32 characters")

        from mcp.server.transport_security import TransportSecuritySettings

        # FastMCP v1 keeps HTTP transport options on its settings object.
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))
        mcp.settings.streamable_http_path = f"/mcp/{secret}"
        # The HTTPS tunnel provides the public boundary. The random
        # path is the access secret for this simple, single-user prototype.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.run(transport="streamable-http")
    else:
        raise SystemExit("MCP_TRANSPORT must be 'stdio' or 'streamable-http'")
