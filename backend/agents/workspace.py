"""Agent Workspace Manager — file I/O for agent workspaces.

Manages the physical workspace directory and soil files (SOUL.md, TOOLS.md,
AGENTS.md, IDENTITY.md) for each agent. Supports create, read, update,
list, archive, and delete operations.

Workspaces live under a configurable base directory (default: /tmp/openclaw-workspaces).
"""
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WORKSPACE_BASE = os.environ.get("OPENCLAW_WORKSPACE_BASE", "/tmp/openclaw-workspaces")
ARCHIVE_BASE = os.path.join(WORKSPACE_BASE, ".archived")


def _ws_path(agent_id: str) -> Path:
    return Path(WORKSPACE_BASE) / f"workspace-{agent_id}"


def _archive_path(agent_id: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path(ARCHIVE_BASE) / f"workspace-{agent_id}-{ts}"


def create_workspace(agent_id: str, soil: Dict[str, str]) -> Dict[str, Any]:
    """Create a workspace directory and write soil files."""
    ws = _ws_path(agent_id)
    ws.mkdir(parents=True, exist_ok=True)

    written = []
    for filename, content in soil.items():
        fpath = ws / filename
        fpath.write_text(content, encoding="utf-8")
        written.append(str(fpath))

    logger.info("Workspace created: %s files=%d", ws, len(written))
    return {
        "workspace": str(ws),
        "files_written": written,
        "agent_id": agent_id,
    }


def read_file(agent_id: str, filename: str) -> Optional[str]:
    """Read a single file from an agent's workspace."""
    fpath = _ws_path(agent_id) / filename
    if not fpath.exists():
        return None
    return fpath.read_text(encoding="utf-8")


def write_file(agent_id: str, filename: str, content: str) -> Dict[str, Any]:
    """Write or overwrite a file in an agent's workspace."""
    ws = _ws_path(agent_id)
    ws.mkdir(parents=True, exist_ok=True)
    fpath = ws / filename
    existed = fpath.exists()
    fpath.write_text(content, encoding="utf-8")
    return {
        "file": str(fpath),
        "operation": "overwrite" if existed else "create",
        "size_bytes": len(content.encode("utf-8")),
    }


def list_files(agent_id: str) -> List[Dict[str, Any]]:
    """List all files in an agent's workspace."""
    ws = _ws_path(agent_id)
    if not ws.exists():
        return []
    files = []
    for f in sorted(ws.iterdir()):
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    return files


def delete_file(agent_id: str, filename: str) -> bool:
    """Delete a single file from an agent's workspace."""
    fpath = _ws_path(agent_id) / filename
    if not fpath.exists():
        return False
    fpath.unlink()
    logger.info("File deleted: %s/%s", agent_id, filename)
    return True


def archive_workspace(agent_id: str) -> Optional[str]:
    """Move workspace to archive directory. Returns archive path or None."""
    ws = _ws_path(agent_id)
    if not ws.exists():
        return None
    dest = _archive_path(agent_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ws), str(dest))
    logger.info("Workspace archived: %s -> %s", ws, dest)
    return str(dest)


def delete_workspace(agent_id: str) -> bool:
    """Permanently delete a workspace directory."""
    ws = _ws_path(agent_id)
    if not ws.exists():
        return False
    shutil.rmtree(ws)
    logger.info("Workspace deleted: %s", ws)
    return True


def workspace_exists(agent_id: str) -> bool:
    return _ws_path(agent_id).exists()


def get_workspace_stats(agent_id: str) -> Dict[str, Any]:
    """Get workspace statistics."""
    ws = _ws_path(agent_id)
    if not ws.exists():
        return {"exists": False, "agent_id": agent_id}

    files = list(ws.iterdir())
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    return {
        "exists": True,
        "agent_id": agent_id,
        "path": str(ws),
        "file_count": len([f for f in files if f.is_file()]),
        "total_size_bytes": total_size,
    }


def list_archived_workspaces() -> List[Dict[str, Any]]:
    """List all archived workspaces."""
    archive = Path(ARCHIVE_BASE)
    if not archive.exists():
        return []
    return [
        {
            "name": d.name,
            "path": str(d),
            "archived_at": datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for d in sorted(archive.iterdir())
        if d.is_dir()
    ]
