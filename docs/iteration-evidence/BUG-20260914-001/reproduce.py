"""Compare historical LocalSandbox implementations against a fixed stale-bytecode fixture.

Run from repository root: uv run python docs/iteration-evidence/BUG-20260914-001/reproduce.py
Prints JSON; does not modify checked-out source or call any model service.
"""
import asyncio
import importlib.util
import json
import os
import platform
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
VERSIONS = {
    "before": "ba96c26cb61efff5ba05105e07218b9aaa240940",
    "after": "30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6",
}


async def main():
    report = {"kind": "historical_sandbox_component_reproduction",
              "python": platform.python_version(), "platform": platform.platform(), "cases": {}}
    for label, commit in VERSIONS.items():
        with tempfile.TemporaryDirectory(prefix="bytecode-repro-") as directory:
            root = Path(directory)
            implementation = root / "historical_sandbox.py"
            implementation.write_bytes(subprocess.check_output(
                ["git", "show", f"{commit}:sandbox/local.py"], cwd=ROOT))
            spec = importlib.util.spec_from_file_location(f"sandbox_{label}", implementation)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            fixture = root / "fixture"
            fixture.mkdir()
            source = fixture / "example.py"
            source.write_text("value = 1\n")
            stamp = source.stat().st_mtime
            py_compile.compile(str(source), doraise=True)
            source.write_text("value = 2\n")
            os.utime(source, (stamp, stamp))
            result = await module.LocalSandbox(trusted=True, max_output_bytes=1000).run(
                (sys.executable, "-c", "import example; print(example.value)"), fixture, 10)
            report["cases"][label] = {"agent_commit": commit, "expected_stdout": "2",
                                     "actual_stdout": result.stdout.strip(),
                                     "exit_code": result.exit_code,
                                     "correct": result.stdout.strip() == "2"}
    assert report["cases"]["before"]["actual_stdout"] == "1"
    assert report["cases"]["after"]["correct"]
    print(json.dumps(report, ensure_ascii=False, indent=2))


asyncio.run(main())
