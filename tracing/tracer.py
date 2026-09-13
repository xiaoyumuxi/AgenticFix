import json
import os
import re
from pathlib import Path
from typing import Any

from filelock import FileLock

from tracing.models import TraceEvent


class Tracer:
    """Append-only events. Redacts known secrets; this is not a general DLP scanner."""

    def __init__(self, directory: Path, secrets: tuple[str, ...] = ()) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "events.jsonl"
        self.secrets = tuple(s for s in secrets if s)
        self.lock = FileLock(str(self.directory / ".trace.lock"), timeout=10)

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: "[REDACTED]"
                if re.search(r"api[_-]?key|password|secret|authorization|access[_-]?token", k, re.I)
                else self.redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
        return value

    def append(self, event: TraceEvent) -> None:
        data = json.dumps(self.redact(event.model_dump()), ensure_ascii=False)
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(data + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def save_json(self, name: str, data: dict[str, Any]) -> Path:
        if Path(name).name != name:
            raise ValueError("Artifact name must be a basename")
        target = self.directory / name
        temporary = target.with_suffix(target.suffix + ".tmp")
        with self.lock:
            temporary.write_text(json.dumps(self.redact(data), ensure_ascii=False, indent=2) + "\n")
            temporary.replace(target)
        return target
