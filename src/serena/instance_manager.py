"""
Instance Manager for running multiple Serena MCP servers simultaneously.

This module provides functionality to launch, track, and manage multiple
Serena instances, each serving a different project.
"""

import json
import os
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import psutil
from sensai.util import logging

from serena.config.serena_config import SerenaPaths

log = logging.getLogger(__name__)


@dataclass
class SerenaInstance:
    """Represents a running Serena MCP server instance."""

    pid: int
    project_path: str
    project_name: str
    mcp_port: int
    dashboard_port: Optional[int]
    transport: str
    context: str
    modes: list[str]
    start_time: float

    def is_running(self) -> bool:
        """Check if this instance is still running."""
        try:
            process = psutil.Process(self.pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def to_dict(self) -> dict:
        """Convert instance to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SerenaInstance":
        """Create instance from dictionary."""
        return cls(**data)


class SerenaInstanceManager:
    """Manages multiple Serena MCP server instances."""

    def __init__(self) -> None:
        self.instances_file = Path(SerenaPaths().user_config_dir) / "instances.json"
        self.instances: list[SerenaInstance] = []
        self._load_instances()

    def _load_instances(self) -> None:
        """Load instances from the instances file."""
        if self.instances_file.exists():
            try:
                with open(self.instances_file) as f:
                    data = json.load(f)
                    self.instances = [SerenaInstance.from_dict(inst) for inst in data]
                    # Clean up dead instances
                    self.instances = [inst for inst in self.instances if inst.is_running()]
                    self._save_instances()
            except Exception as e:
                log.warning(f"Failed to load instances file: {e}")
                self.instances = []

    def _save_instances(self) -> None:
        """Save instances to the instances file."""
        try:
            self.instances_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.instances_file, "w") as f:
                json.dump([inst.to_dict() for inst in self.instances], f, indent=2)
        except Exception as e:
            log.error(f"Failed to save instances file: {e}")

    def _find_free_port(self, start_port: int, exclude_ports: set[int]) -> int:
        """Find a free port starting from the given port."""
        port = start_port
        while port <= 65535:
            if port in exclude_ports:
                port += 1
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("0.0.0.0", port))
                    return port
            except OSError:
                port += 1
        raise RuntimeError(f"No free ports found starting from {start_port}")

    def get_running_instances(self) -> list[SerenaInstance]:
        """Get list of currently running instances."""
        self._load_instances()
        return [inst for inst in self.instances if inst.is_running()]

    def find_instance_by_project(self, project_path_or_name: str) -> Optional[SerenaInstance]:
        """Find a running instance for the given project."""
        project_path = Path(project_path_or_name).resolve()
        for inst in self.get_running_instances():
            if Path(inst.project_path).resolve() == project_path or inst.project_name == project_path_or_name:
                return inst
        return None

    def launch_instance(
        self,
        project: str,
        transport: str = "stdio",
        context: str = "desktop-app",
        modes: tuple[str, ...] = ("planning", "editing"),
        mcp_port: Optional[int] = None,
        enable_web_dashboard: bool = True,
        log_level: Optional[str] = None,
        force: bool = False,
    ) -> SerenaInstance:
        """
        Launch a new Serena instance for the given project.

        Args:
            project: Project path or name
            transport: Transport protocol (stdio or sse)
            context: Context name or path
            modes: Mode names or paths
            mcp_port: MCP server port (auto-assigned if None)
            enable_web_dashboard: Whether to enable the web dashboard
            log_level: Log level override
            force: If True, kill existing instance for the same project

        Returns:
            The launched SerenaInstance

        Raises:
            RuntimeError: If instance already exists for project and force=False

        """
        # Check if instance already exists for this project
        existing = self.find_instance_by_project(project)
        if existing:
            if force:
                self.kill_instance(existing.pid)
            else:
                raise RuntimeError(
                    f"Instance already running for project '{project}' on port {existing.mcp_port}. "
                    f"Use --force to kill the existing instance."
                )

        # Determine ports
        used_ports = {inst.mcp_port for inst in self.get_running_instances()}
        for inst in self.get_running_instances():
            if inst.dashboard_port:
                used_ports.add(inst.dashboard_port)

        if transport == "sse":
            if mcp_port is None:
                mcp_port = self._find_free_port(8000, used_ports)
            elif mcp_port in used_ports:
                raise RuntimeError(f"Port {mcp_port} is already in use")

        # Build command - use uv run to ensure correct environment
        cmd = [
            "uv",
            "run",
            "serena",
            "start-mcp-server",
            "--project",
            project,
            "--transport",
            transport,
            "--context",
            context,
        ]

        for mode in modes:
            cmd.extend(["--mode", mode])

        if transport == "sse" and mcp_port:
            cmd.extend(["--port", str(mcp_port)])

        if enable_web_dashboard is not None:
            cmd.append(f"--enable-web-dashboard={'true' if enable_web_dashboard else 'false'}")

        if log_level:
            cmd.extend(["--log-level", log_level])

        # Launch the process
        env = os.environ.copy()
        log.info(f"Launching Serena with command: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if transport == "stdio" else None,
            stdin=subprocess.PIPE if transport == "stdio" else None,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Wait a moment for the process to start
        time.sleep(2)

        # Check if process started successfully
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            stdout = process.stdout.read().decode() if process.stdout else ""
            raise RuntimeError(f"Failed to start Serena instance:\nCommand: {' '.join(cmd)}\nSTDERR: {stderr}\nSTDOUT: {stdout}")

        # Extract project name from path if needed
        project_path = str(Path(project).resolve())
        project_name = Path(project).name

        # Estimate dashboard port (it auto-finds from 0x5EDA)
        dashboard_port = None
        if enable_web_dashboard:
            # The dashboard will find its own port, we can't know it exactly
            # but we can estimate based on other running instances
            dashboard_ports = {inst.dashboard_port for inst in self.get_running_instances() if inst.dashboard_port}
            dashboard_port = 0x5EDA  # 24282
            while dashboard_port in dashboard_ports:
                dashboard_port += 1

        # Create and save instance
        instance = SerenaInstance(
            pid=process.pid,
            project_path=project_path,
            project_name=project_name,
            mcp_port=mcp_port if transport == "sse" and mcp_port is not None else 0,
            dashboard_port=dashboard_port,
            transport=transport,
            context=context,
            modes=list(modes),
            start_time=time.time(),
        )

        self.instances.append(instance)
        self._save_instances()

        return instance

    def kill_instance(self, pid: int) -> bool:
        """
        Kill a Serena instance by PID.

        Args:
            pid: Process ID of the instance to kill

        Returns:
            True if instance was killed, False if not found

        """
        try:
            process = psutil.Process(pid)
            process.terminate()
            # Give it time to terminate gracefully
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                # Force kill if it doesn't terminate
                process.kill()

            # Remove from instances list
            self.instances = [inst for inst in self.instances if inst.pid != pid]
            self._save_instances()
            return True
        except psutil.NoSuchProcess:
            # Clean up from list anyway
            self.instances = [inst for inst in self.instances if inst.pid != pid]
            self._save_instances()
            return False

    def kill_all_instances(self) -> int:
        """
        Kill all running Serena instances.

        Returns:
            Number of instances killed

        """
        killed = 0
        for instance in self.get_running_instances():
            if self.kill_instance(instance.pid):
                killed += 1
        return killed
