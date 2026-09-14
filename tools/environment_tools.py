"""Model-authored environment, executed through host-controlled Docker policy."""

from pydantic import Field

from tools.base import BaseTool, ToolArgs, ToolError, ToolResult
from tools.context import ToolContext


class BuildArgs(ToolArgs):
    dockerfile: str = Field(min_length=1, max_length=24000)


class BuildEnvironment(BaseTool):
    name = "build_environment"
    description = (
        "Write a Dockerfile and build dependencies. Single official Python slim stage; "
        "WORKDIR /workspace; COPY . /workspace/. Use ordinary RUN instructions. "
        "Public tests use python -m pytest. Dockerfile is saved outside the source patch."
    )
    args_schema = BuildArgs

    async def execute(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        assert isinstance(args, BuildArgs)
        if context.docker is None:
            raise ToolError("NO_DOCKER", "Docker environment is not configured")
        context.state.tested_revision = None
        context.state.test_status = None
        context.state.tested_patch_digest = None
        try:
            result = await context.docker.build(
                args.dockerfile, context.workspace.path, context.settings.max_build_timeout
            )
        except ValueError as exc:
            raise ToolError("INVALID_DOCKERFILE", str(exc)) from exc
        data = result.model_dump() | context.docker.last_build
        path = context.tracer.save_json(f"environment-{context.docker.build_number}.json", data)
        return ToolResult(
            success=result.exit_code == 0 and not result.timed_out,
            data=data | {"artifact": str(path)},
            truncated=result.truncated,
            error_code=None
            if result.exit_code == 0 and not result.timed_out
            else "ENVIRONMENT_BUILD_FAILED",
        )
