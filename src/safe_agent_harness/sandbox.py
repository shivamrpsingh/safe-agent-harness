"""P6 sandboxed code execution."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from .core import TransientError


def run_in_sandbox(code: str, *, timeout: int = 10, use_docker: bool = True,
                   image: str = "python:3.12-slim", memory: str = "256m",
                   cpus: str = "0.5", max_output: int = 2000) -> str:
    """Run Python code in an isolated container and return stdout.

    use_docker=False runs a local isolated subprocess. That is for development
    only and is NOT a security boundary.
    """
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "main.py")
        with open(script, "w") as f:
            f.write(code)
        if use_docker:
            cmd = ["docker", "run", "--rm", "--network=none", "--read-only",
                   f"--memory={memory}", f"--cpus={cpus}", "--pids-limit=64",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges",
                   "-v", f"{tmp}:/work:ro", image, "python", "/work/main.py"]
        else:
            cmd = [sys.executable, "-I", script]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired as e:
            raise TransientError(f"sandbox timed out after {timeout}s") from e
        if out.returncode != 0:
            return f"ERROR: {out.stderr.strip()[-500:]}"
        return out.stdout.strip()[-max_output:]
