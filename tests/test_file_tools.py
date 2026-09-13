import pytest


@pytest.mark.parametrize(
    "name", ["../source/sample.py", "/etc/passwd", ".git", ".env", ".env.production"]
)
async def test_reject_paths(name, registry):
    result = await registry.call("read_file", {"path": name})
    assert not result.success
    assert result.error_code in {"PATH_ESCAPE", "PROTECTED_PATH"}


async def test_symlink_escape_and_metadata(registry, context, tmp_path):
    root = context.workspace.path
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    (root / "metadata").symlink_to(root / ".git")
    for name in ("escape/secret", "metadata"):
        assert (await registry.call("read_file", {"path": name})).error_code == "PATH_ESCAPE"
    assert (
        await registry.call(
            "edit_file",
            {
                "path": "metadata",
                "old_text": "a",
                "new_text": "b",
                "version": "0" * 64,
            },
        )
    ).error_code == "PATH_ESCAPE"


async def test_read_bounds_types(registry, context):
    root = context.workspace.path
    context.settings.max_read_lines = 1
    result = await registry.call("read_file", {"path": "sample.py"})
    assert result.success and result.truncated
    assert result.data["content"] == "1: value = 1"
    assert (
        await registry.call(
            "read_file",
            {
                "path": "sample.py",
                "start_line": 3,
                "end_line": 1,
            },
        )
    ).error_code == "INVALID_RANGE"
    (root / "binary").write_bytes(b"a\x00b")
    (root / "encoding").write_bytes(b"\xff")
    (root / "big").write_bytes(b"a" * 100)
    assert (await registry.call("read_file", {"path": "binary"})).error_code == "UNSUPPORTED_FILE"
    assert (
        await registry.call("read_file", {"path": "encoding"})
    ).error_code == "UNSUPPORTED_ENCODING"
    context.settings.max_file_bytes = 50
    assert (await registry.call("read_file", {"path": "big"})).error_code == "FILE_TOO_LARGE"
    assert (await registry.call("read_file", {"path": "."})).error_code == "NOT_FILE"


async def test_listing_search_limits_and_ignored(registry, context):
    root = context.workspace.path
    (root / "nested").mkdir()
    (root / "nested" / "deep.py").write_text("value = 10\nvalue = 11\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "secret.py").write_text("value = 12")
    listing = await registry.call("list_files", {"max_depth": 0})
    assert "sample.py" in listing.data["files"]
    assert all("/" not in p for p in listing.data["files"])
    matches = await registry.call("search_code", {"query": "value", "max_results": 1})
    assert matches.success and matches.truncated
    assert len(matches.data["matches"]) == 1
    full = await registry.call("search_code", {"query": "value", "file_pattern": "*.py"})
    assert all("node_modules" not in m["file"] for m in full.data["matches"])
    context.settings.max_entries = 1
    assert (await registry.call("list_files", {})).truncated
    context.settings.max_scan_entries = 1
    assert (await registry.call("list_files", {})).truncated


async def test_edit_requires_read_unique_match_and_fresh_version(registry, context):
    args = {
        "path": "sample.py",
        "old_text": "value = 1",
        "new_text": "value = 2",
        "version": "0" * 64,
    }
    assert (await registry.call("edit_file", args)).error_code == "NOT_INSPECTED"
    read = await registry.call("read_file", {"path": "sample.py"})
    args["version"] = read.data["version"]
    assert (
        await registry.call("edit_file", args | {"old_text": "absent"})
    ).error_code == "MATCH_COUNT"
    assert (
        await registry.call("edit_file", args | {"old_text": " = "})
    ).error_code == "MATCH_COUNT"
    assert (await registry.call("edit_file", args)).success
    assert context.state.workspace_revision == 1
    assert "value = 2" in (context.workspace.path / "sample.py").read_text()
    read = await registry.call("read_file", {"path": "sample.py"})
    (context.workspace.path / "sample.py").write_text("external = 3\n")
    assert (
        await registry.call("edit_file", args | {"version": read.data["version"]})
    ).error_code == "STALE_READ"


async def test_edit_preserves_mode_and_line_endings(registry, context):
    path = context.workspace.path / "script.py"
    path.write_bytes(b"a = 1\r\nb = 2\r\n")
    path.chmod(0o755)
    read = await registry.call("read_file", {"path": "script.py"})
    result = await registry.call(
        "edit_file",
        {
            "path": "script.py",
            "old_text": "a = 1",
            "new_text": "a = 3",
            "version": read.data["version"],
        },
    )
    assert result.success
    assert path.read_bytes() == b"a = 3\r\nb = 2\r\n"
    assert path.stat().st_mode & 0o777 == 0o755


async def test_hardlink_and_replaced_workspace_root(registry, context, tmp_path):
    import os

    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    os.link(outside, context.workspace.path / "hardlink")
    assert (await registry.call("read_file", {"path": "hardlink"})).error_code == "UNSUPPORTED_FILE"
    root = context.workspace.path
    moved = root.with_name("moved")
    root.rename(moved)
    root.symlink_to(moved, target_is_directory=True)
    result = await registry.call("read_file", {"path": "sample.py"})
    assert result.fatal and result.error_code == "ISOLATION_FAILURE"
    assert (await registry.call("list_files", {})).error_code == "RUN_STOPPED"
