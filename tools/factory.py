from tools.context import ToolContext
from tools.file_tools import EditFile, ListFiles, ReadFile
from tools.git_tools import GitDiff
from tools.registry import ToolRegistry
from tools.search_tools import SearchCode
from tools.test_tools import RunTests


def build_registry(context: ToolContext) -> ToolRegistry:
    registry = ToolRegistry(context)
    for tool in (ListFiles(), ReadFile(), SearchCode(), EditFile(), RunTests(), GitDiff()):
        registry.register(tool)
    return registry
