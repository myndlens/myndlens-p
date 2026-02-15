"""
Tests for MyndLens Optimization Scheduler and Agent Workspace File I/O APIs.

Optimization Scheduler:
- POST /api/optimization/run - manual optimization cycle
- POST /api/optimization/scheduler/start - start background scheduler
- POST /api/optimization/scheduler/stop - stop scheduler
- GET /api/optimization/scheduler/status - get scheduler status
- GET /api/optimization/runs - list recent runs

Workspace File I/O:
- POST /api/workspace/create - create workspace with soil files
- GET /api/workspace/{agent_id}/files - list files
- GET /api/workspace/{agent_id}/file/{filename} - read file content
- PUT /api/workspace/{agent_id}/file/{filename} - write/overwrite file
- DELETE /api/workspace/{agent_id}/file/{filename} - delete file
- GET /api/workspace/{agent_id}/stats - get workspace stats
- POST /api/workspace/{agent_id}/archive - archive workspace
- DELETE /api/workspace/{agent_id} - permanently delete workspace
- GET /api/workspace/archives - list archived workspaces
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# =====================================================
#  Optimization Scheduler Tests
# =====================================================

class TestOptimizationManualRun:
    """Tests for manual optimization cycle endpoint."""
    
    def test_manual_optimization_run(self, api_client):
        """POST /api/optimization/run triggers a manual optimization cycle and returns run report."""
        response = api_client.post(f"{BASE_URL}/api/optimization/run?days=7")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify run report structure
        assert "run_id" in data, "run_id missing from report"
        assert "started_at" in data, "started_at missing from report"
        assert "completed_at" in data, "completed_at missing from report"
        assert "duration_ms" in data, "duration_ms missing from report"
        assert "success" in data, "success flag missing from report"
        assert "steps" in data, "steps missing from report"
        assert "errors" in data, "errors missing from report"
        
        print(f"Manual run completed: run_id={data['run_id']}, duration={data['duration_ms']}ms")
    
    def test_optimization_run_has_all_steps(self, api_client):
        """Optimization run report includes all 5 required steps."""
        response = api_client.post(f"{BASE_URL}/api/optimization/run?days=7")
        
        assert response.status_code == 200
        data = response.json()
        steps = data.get("steps", {})
        
        # All 5 steps should be present
        required_steps = ["insights", "section_scores", "recommendations", "user_learning", "experiments"]
        for step in required_steps:
            assert step in steps, f"Step '{step}' missing from run report"
            print(f"Step '{step}' present: {steps[step]}")
    
    def test_optimization_run_persisted(self, api_client):
        """Optimization run is persisted to MongoDB optimization_runs collection."""
        # First, trigger a run
        run_response = api_client.post(f"{BASE_URL}/api/optimization/run?days=7")
        assert run_response.status_code == 200
        run_data = run_response.json()
        run_id = run_data["run_id"]
        
        # Then list runs to verify persistence
        list_response = api_client.get(f"{BASE_URL}/api/optimization/runs?limit=5")
        assert list_response.status_code == 200
        runs = list_response.json()
        
        # Find our run
        found = any(r.get("run_id") == run_id for r in runs)
        assert found, f"Run {run_id} not found in recent runs list"
        print(f"Verified run_id={run_id} persisted to optimization_runs collection")


class TestOptimizationScheduler:
    """Tests for optimization scheduler start/stop/status endpoints."""
    
    def test_scheduler_start(self, api_client):
        """POST /api/optimization/scheduler/start starts background scheduler."""
        # First ensure stopped
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/stop")
        
        response = api_client.post(f"{BASE_URL}/api/optimization/scheduler/start?interval_seconds=3600")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "STARTED", f"Expected STARTED, got {data.get('status')}"
        print(f"Scheduler started: {data}")
    
    def test_scheduler_start_idempotent(self, api_client):
        """Starting already running scheduler returns ALREADY_RUNNING."""
        # Ensure started
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/start?interval_seconds=3600")
        
        # Try to start again
        response = api_client.post(f"{BASE_URL}/api/optimization/scheduler/start?interval_seconds=3600")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "ALREADY_RUNNING", f"Expected ALREADY_RUNNING, got {data.get('status')}"
        print(f"Idempotent start: {data}")
    
    def test_scheduler_status_when_running(self, api_client):
        """GET /api/optimization/scheduler/status returns running=true when started."""
        # Ensure started
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/start?interval_seconds=3600")
        
        response = api_client.get(f"{BASE_URL}/api/optimization/scheduler/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("running") is True, f"Expected running=true, got {data.get('running')}"
        assert "last_run" in data
        assert "last_success" in data
        assert "last_duration_ms" in data
        print(f"Scheduler status (running): {data}")
    
    def test_scheduler_stop(self, api_client):
        """POST /api/optimization/scheduler/stop stops scheduler."""
        # Ensure started first
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/start?interval_seconds=3600")
        
        response = api_client.post(f"{BASE_URL}/api/optimization/scheduler/stop")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "STOPPED", f"Expected STOPPED, got {data.get('status')}"
        print(f"Scheduler stopped: {data}")
    
    def test_scheduler_stop_idempotent(self, api_client):
        """Stopping already stopped scheduler returns NOT_RUNNING."""
        # Ensure stopped
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/stop")
        
        # Try to stop again
        response = api_client.post(f"{BASE_URL}/api/optimization/scheduler/stop")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "NOT_RUNNING", f"Expected NOT_RUNNING, got {data.get('status')}"
        print(f"Idempotent stop: {data}")
    
    def test_scheduler_status_when_stopped(self, api_client):
        """GET /api/optimization/scheduler/status returns running=false when stopped."""
        # Ensure stopped
        api_client.post(f"{BASE_URL}/api/optimization/scheduler/stop")
        
        response = api_client.get(f"{BASE_URL}/api/optimization/scheduler/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("running") is False, f"Expected running=false, got {data.get('running')}"
        print(f"Scheduler status (stopped): {data}")


class TestOptimizationRunsList:
    """Tests for listing optimization runs."""
    
    def test_list_runs_newest_first(self, api_client):
        """GET /api/optimization/runs lists recent runs newest first."""
        response = api_client.get(f"{BASE_URL}/api/optimization/runs?limit=10")
        assert response.status_code == 200
        runs = response.json()
        
        assert isinstance(runs, list), "Expected list of runs"
        
        if len(runs) > 1:
            # Verify ordering (newest first = descending by run_id which is ISO timestamp)
            for i in range(len(runs) - 1):
                run_id_current = runs[i].get("run_id", "")
                run_id_next = runs[i + 1].get("run_id", "")
                assert run_id_current >= run_id_next, f"Runs not sorted newest first: {run_id_current} < {run_id_next}"
        
        print(f"Listed {len(runs)} optimization runs (newest first)")


# =====================================================
#  Workspace File I/O Tests
# =====================================================

class TestWorkspaceCreate:
    """Tests for workspace creation."""
    
    def test_create_workspace_with_soil_files(self, api_client):
        """POST /api/workspace/create creates workspace directory with soil files."""
        agent_id = f"TEST_ws_{uuid.uuid4().hex[:8]}"
        soil = {
            "SOUL.md": "# Soul\nThis agent's purpose.",
            "TOOLS.md": "# Tools\nAvailable tools.",
            "AGENTS.md": "# Agents\nAgent config.",
            "IDENTITY.md": "# Identity\nAgent identity."
        }
        
        response = api_client.post(f"{BASE_URL}/api/workspace/create", json={
            "agent_id": agent_id,
            "soil": soil
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "workspace" in data
        assert "files_written" in data
        assert data.get("agent_id") == agent_id
        assert len(data.get("files_written", [])) == 4
        
        print(f"Workspace created: {data['workspace']}, files: {len(data['files_written'])}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/workspace/{agent_id}")


class TestWorkspaceFileOperations:
    """Tests for workspace file CRUD operations."""
    
    @pytest.fixture(autouse=True)
    def setup_workspace(self, api_client):
        """Create a test workspace for file operations."""
        self.agent_id = f"TEST_fileops_{uuid.uuid4().hex[:8]}"
        soil = {"README.md": "# Test Workspace\nInitial content."}
        api_client.post(f"{BASE_URL}/api/workspace/create", json={
            "agent_id": self.agent_id,
            "soil": soil
        })
        yield
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/workspace/{self.agent_id}")
    
    def test_list_files(self, api_client):
        """GET /api/workspace/{agent_id}/files lists all files with name, size, modified_at."""
        response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/files")
        
        assert response.status_code == 200
        files = response.json()
        
        assert isinstance(files, list)
        assert len(files) >= 1
        
        for f in files:
            assert "name" in f
            assert "size_bytes" in f
            assert "modified_at" in f
        
        print(f"Listed {len(files)} files: {[f['name'] for f in files]}")
    
    def test_read_file_content(self, api_client):
        """GET /api/workspace/{agent_id}/file/{filename} reads file content."""
        response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/file/README.md")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("agent_id") == self.agent_id
        assert data.get("filename") == "README.md"
        assert "content" in data
        assert "Initial content" in data.get("content", "")
        
        print(f"Read file: {data['filename']}, content length: {len(data.get('content', ''))}")
    
    def test_read_file_404_for_missing(self, api_client):
        """GET /api/workspace/{agent_id}/file/{filename} returns 404 for non-existent file."""
        response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/file/nonexistent.md")
        
        assert response.status_code == 404
        print("Correctly returned 404 for non-existent file")
    
    def test_write_new_file(self, api_client):
        """PUT /api/workspace/{agent_id}/file/{filename} creates new file."""
        filename = "NEW_FILE.txt"
        content = "This is brand new content."
        
        response = api_client.put(
            f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}",
            json={"content": content}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("operation") == "create"
        assert data.get("size_bytes") == len(content.encode("utf-8"))
        
        # Verify file was created
        read_response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}")
        assert read_response.status_code == 200
        assert read_response.json().get("content") == content
        
        print(f"Created new file: {filename}, size: {data.get('size_bytes')} bytes")
    
    def test_overwrite_existing_file(self, api_client):
        """PUT /api/workspace/{agent_id}/file/{filename} overwrites existing file."""
        filename = "README.md"
        new_content = "# Updated Content\nThis has been overwritten."
        
        response = api_client.put(
            f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}",
            json={"content": new_content}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("operation") == "overwrite"
        
        # Verify content was updated
        read_response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}")
        assert read_response.status_code == 200
        assert "Updated Content" in read_response.json().get("content", "")
        
        print(f"Overwrote file: {filename}")
    
    def test_delete_file(self, api_client):
        """DELETE /api/workspace/{agent_id}/file/{filename} deletes file."""
        # First create a file to delete
        filename = "TO_DELETE.txt"
        api_client.put(
            f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}",
            json={"content": "delete me"}
        )
        
        # Delete it
        response = api_client.delete(f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "deleted"
        
        # Verify it's gone
        read_response = api_client.get(f"{BASE_URL}/api/workspace/{self.agent_id}/file/{filename}")
        assert read_response.status_code == 404
        
        print(f"Deleted file: {filename}")
    
    def test_delete_file_404_for_missing(self, api_client):
        """DELETE /api/workspace/{agent_id}/file/{filename} returns 404 for missing file."""
        response = api_client.delete(f"{BASE_URL}/api/workspace/{self.agent_id}/file/nonexistent.txt")
        
        assert response.status_code == 404
        print("Correctly returned 404 for deleting non-existent file")


class TestWorkspaceStats:
    """Tests for workspace statistics."""
    
    def test_workspace_stats(self, api_client):
        """GET /api/workspace/{agent_id}/stats returns exists, file_count, total_size."""
        agent_id = f"TEST_stats_{uuid.uuid4().hex[:8]}"
        soil = {
            "FILE1.md": "Content one",
            "FILE2.md": "Content two is longer"
        }
        api_client.post(f"{BASE_URL}/api/workspace/create", json={
            "agent_id": agent_id,
            "soil": soil
        })
        
        response = api_client.get(f"{BASE_URL}/api/workspace/{agent_id}/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("exists") is True
        assert data.get("agent_id") == agent_id
        assert data.get("file_count") == 2
        assert data.get("total_size_bytes") > 0
        assert "path" in data
        
        print(f"Workspace stats: files={data.get('file_count')}, size={data.get('total_size_bytes')} bytes")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/workspace/{agent_id}")
    
    def test_workspace_stats_nonexistent(self, api_client):
        """GET /api/workspace/{agent_id}/stats returns exists=false for non-existent workspace."""
        response = api_client.get(f"{BASE_URL}/api/workspace/nonexistent_agent_xyz/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("exists") is False
        print("Correctly returned exists=false for non-existent workspace")


class TestWorkspaceArchive:
    """Tests for workspace archive operations."""
    
    def test_archive_workspace(self, api_client):
        """POST /api/workspace/{agent_id}/archive moves workspace to archive."""
        agent_id = f"TEST_archive_{uuid.uuid4().hex[:8]}"
        api_client.post(f"{BASE_URL}/api/workspace/create", json={
            "agent_id": agent_id,
            "soil": {"FILE.md": "Archive test content"}
        })
        
        response = api_client.post(f"{BASE_URL}/api/workspace/{agent_id}/archive")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "archived"
        assert data.get("agent_id") == agent_id
        assert "archive_path" in data
        
        # Verify original workspace is gone
        stats_response = api_client.get(f"{BASE_URL}/api/workspace/{agent_id}/stats")
        assert stats_response.json().get("exists") is False
        
        print(f"Archived workspace to: {data.get('archive_path')}")
    
    def test_archive_workspace_404_for_missing(self, api_client):
        """POST /api/workspace/{agent_id}/archive returns 404 for non-existent workspace."""
        response = api_client.post(f"{BASE_URL}/api/workspace/nonexistent_agent_xyz/archive")
        
        assert response.status_code == 404
        print("Correctly returned 404 for archiving non-existent workspace")
    
    def test_list_archives(self, api_client):
        """GET /api/workspace/archives lists archived workspaces."""
        response = api_client.get(f"{BASE_URL}/api/workspace/archives")
        
        assert response.status_code == 200
        archives = response.json()
        
        assert isinstance(archives, list)
        
        if len(archives) > 0:
            for archive in archives:
                assert "name" in archive
                assert "path" in archive
                assert "archived_at" in archive
        
        print(f"Listed {len(archives)} archived workspaces")


class TestWorkspaceDelete:
    """Tests for permanent workspace deletion."""
    
    def test_delete_workspace(self, api_client):
        """DELETE /api/workspace/{agent_id} permanently deletes workspace."""
        agent_id = f"TEST_delete_{uuid.uuid4().hex[:8]}"
        api_client.post(f"{BASE_URL}/api/workspace/create", json={
            "agent_id": agent_id,
            "soil": {"FILE.md": "Delete test content"}
        })
        
        response = api_client.delete(f"{BASE_URL}/api/workspace/{agent_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "deleted"
        assert data.get("agent_id") == agent_id
        
        # Verify it's gone
        stats_response = api_client.get(f"{BASE_URL}/api/workspace/{agent_id}/stats")
        assert stats_response.json().get("exists") is False
        
        print(f"Permanently deleted workspace: {agent_id}")
    
    def test_delete_workspace_404_for_missing(self, api_client):
        """DELETE /api/workspace/{agent_id} returns 404 for non-existent workspace."""
        response = api_client.delete(f"{BASE_URL}/api/workspace/nonexistent_agent_xyz")
        
        assert response.status_code == 404
        print("Correctly returned 404 for deleting non-existent workspace")


class TestWorkspace404Scenarios:
    """Tests for 404 scenarios with non-existent workspaces."""
    
    def test_list_files_for_nonexistent_workspace(self, api_client):
        """GET /api/workspace/{agent_id}/files returns empty list for non-existent workspace."""
        response = api_client.get(f"{BASE_URL}/api/workspace/nonexistent_agent_xyz/files")
        
        # The implementation returns empty list (not 404) for non-existent workspace
        assert response.status_code == 200
        files = response.json()
        assert files == []
        
        print("Non-existent workspace returns empty file list")
    
    def test_read_file_nonexistent_workspace(self, api_client):
        """GET /api/workspace/{agent_id}/file/{filename} returns 404 for non-existent workspace's file."""
        response = api_client.get(f"{BASE_URL}/api/workspace/nonexistent_agent_xyz/file/test.md")
        
        assert response.status_code == 404
        print("Correctly returned 404 for file in non-existent workspace")
