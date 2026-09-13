import asyncio
import sys
import time

import pytest

from sandbox.local import LocalSandbox


async def test_output_bound_and_launch_failure(tmp_path):
    sandbox = LocalSandbox(trusted=True, max_output_bytes=100)
    result = await sandbox.run((sys.executable, "-c", "print('x'*10000)"), tmp_path, 5)
    assert result.exit_code == 0 and result.truncated
    assert len(result.stdout.encode()) == 100
    missing = await sandbox.run(("/nonexistent/command",), tmp_path, 5)
    assert missing.launch_error == "FileNotFoundError"
    with pytest.raises(ValueError):
        LocalSandbox(trusted=False, max_output_bytes=100)


async def test_timeout_kills_descendant_and_preserves_output(tmp_path):
    marker = tmp_path / "escaped"
    child = f"import time; time.sleep(1); open({str(marker)!r}, 'w').write('alive')"
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "print('started',flush=True); time.sleep(10)"
    )
    sandbox = LocalSandbox(trusted=True, max_output_bytes=1000)
    start = time.monotonic()
    result = await sandbox.run((sys.executable, "-c", parent), tmp_path, 0.25)
    assert result.timed_out and "started" in result.stdout
    assert time.monotonic() - start < 3
    await asyncio.sleep(1.1)
    assert not marker.exists()


async def test_env_secret_not_forwarded(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "secret-value")
    result = await LocalSandbox(trusted=True, max_output_bytes=1000).run(
        (sys.executable, "-c", "import os; print(os.getenv('MODEL_API_KEY'))"),
        tmp_path,
        5,
    )
    assert result.stdout.strip() == "None"


async def test_test_results_and_invalidation(registry, context):
    result = await registry.call("run_tests", {})
    assert result.success and result.data["status"] == "passed"
    assert context.state.current_tests_passed
    read = await registry.call("read_file", {"path": "test_sample.py"})
    edit = await registry.call(
        "edit_file",
        {
            "path": "test_sample.py",
            "old_text": "assert True",
            "new_text": "assert False",
            "version": read.data["version"],
        },
    )
    assert edit.success and not context.state.current_tests_passed
    fail = await registry.call("run_tests", {})
    assert fail.success and fail.data["status"] == "failed"
    assert fail.data["exit_code"] == 1
    (context.workspace.path / "test_sample.py").unlink()
    empty = await registry.call("run_tests", {})
    assert empty.success and empty.data["status"] == "no_tests"
    assert not context.state.current_tests_passed
    context.trusted_local = False
    assert (await registry.call("run_tests", {})).error_code == "UNTRUSTED_EXECUTION"


async def test_unknown_target_and_tool_timeout(registry, context):
    assert (await registry.call("run_tests", {"target": "missing"})).error_code == "UNKNOWN_TARGET"
    context.test_targets["slow"] = (sys.executable, "-c", "import time; time.sleep(10)")
    context.settings.max_test_timeout = 0.1
    result = await registry.call("run_tests", {"target": "slow", "timeout": 20})
    assert not result.success and result.error_code == "TIMEOUT"
    assert result.data["duration"] < 3


async def test_test_side_effects_invalidate_success(registry, context):
    (context.workspace.path / "test_sample.py").write_text(
        "from pathlib import Path\n"
        "def test_mutate():\n"
        "    Path('sample.py').write_text('changed = True\\n')\n"
    )
    result = await registry.call("run_tests", {})
    assert result.data["exit_code"] == 0
    assert result.data["status"] == "workspace_changed"
    assert not context.state.current_tests_passed


async def test_external_edit_before_export_invalidates_tests(registry, context):
    await registry.call("run_tests", {})
    assert context.state.current_tests_passed
    (context.workspace.path / "sample.py").write_text("modified = True\n")
    assert (await registry.call("git_diff", {})).success
    assert not context.state.current_tests_passed


async def test_same_size_same_timestamp_bytecode_is_not_reused(tmp_path):
    import os
    import py_compile

    source = tmp_path / "module.py"
    source.write_text("value = 1\n")
    timestamp = source.stat().st_mtime
    py_compile.compile(str(source), doraise=True)
    source.write_text("value = 2\n")
    os.utime(source, (timestamp, timestamp))
    result = await LocalSandbox(trusted=True, max_output_bytes=1000).run(
        (sys.executable, "-c", "import module; print(module.value)"),
        tmp_path,
        10,
    )
    assert result.stdout.strip() == "2"
