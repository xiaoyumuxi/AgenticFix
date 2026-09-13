from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: str
    run_id: str
    base_commit: str
    workspace_path: str
    issue: str = ""
    plan: list[str] = Field(default_factory=list)
    workspace_revision: int = 0
    tested_revision: int | None = None
    test_status: str | None = None
    tested_patch_digest: str | None = None
    total_tool_calls: int = 0
    modified_files: list[str] = Field(default_factory=list)
    status: Literal["running", "completed", "failed"] = "running"
    stop_reason: str | None = None
    final_patch_path: str | None = None

    def record_edit(self, path: str) -> None:
        self.workspace_revision += 1
        self.tested_revision = None
        self.test_status = None
        self.tested_patch_digest = None
        if path not in self.modified_files:
            self.modified_files.append(path)

    @property
    def current_tests_passed(self) -> bool:
        return self.test_status == "passed" and self.tested_revision == self.workspace_revision
