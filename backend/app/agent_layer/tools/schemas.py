# tools/schemas.py

from pydantic import BaseModel
from typing import Any
from pydantic import BaseModel, Field


class ToolSelection(BaseModel):
    selected_tool: str = Field(
        description="The tool to execute"
    )

    reason: str = Field(
        description="Why the tool was selected"
    )
    
class ToolResult(BaseModel):

    success: bool

    tool_name: str

    data: Any = None

    error: str | None = None