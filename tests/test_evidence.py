import hashlib
import json

from pydantic import SecretStr

from config import Settings
from tracing.evidence import capture_start, finalize_evidence
from tracing.tracer import Tracer
from workspace.repository import git


def test_dirty_snapshot_and_redaction(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "code.py").write_text("value = 1\n")
    (root / ".gitignore").write_text(".env\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    (root / "code.py").write_text('value = "sensitive-value"\n')
    (root / ".env").write_text("do-not-archive-env")
    (root / "new.py").write_text("value = 2\n")
    tracer = Tracer(tmp_path / "run", secrets=("sensitive-value",))
    settings = Settings(
        _env_file=None,
        model_api_key=SecretStr("sensitive-value"),
        model_extra_body={"password": "private", "temperature": 0.1},
    )
    capture_start(tracer, settings, root)
    finalize_evidence(tracer)
    metadata = json.loads((tracer.directory / "metadata.json").read_text())
    assert metadata["agent"]["dirty"] is True
    assert "new.py" in metadata["agent"]["untracked_sha256"]
    assert ".env" not in metadata["agent"]["untracked_sha256"]
    assert metadata["config"]["resolved_model"]["extra_body"]["password"] == "[REDACTED]"
    assert metadata["agent"]["tracked_diff_sha256"] != metadata["agent"]["redacted_diff_sha256"]
    for path in tracer.directory.glob("*.json"):
        assert "sensitive-value" not in path.read_text()
        assert "do-not-archive-env" not in path.read_text()
    manifest = json.loads((tracer.directory / "manifest.json").read_text())
    for name, artifact in manifest["artifacts"].items():
        assert (
            artifact["sha256"] == hashlib.sha256((tracer.directory / name).read_bytes()).hexdigest()
        )
