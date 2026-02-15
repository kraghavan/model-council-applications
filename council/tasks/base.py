"""Base class for council tasks."""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskResult:
    """Result from a single model on a task."""

    model_name: str
    score: float
    decision: str
    summary: str
    issues: list[dict] = field(default_factory=list)
    extras: dict = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def from_error(cls, model_name: str, error: str) -> "TaskResult":
        """Create an error result."""
        return cls(
            model_name=model_name,
            score=0.0,
            decision="ERROR",
            summary=f"Failed: {error}",
            error=error,
        )


class BaseTask(ABC):
    """Abstract base class for council tasks.
    
    To create a new task:
    1. Inherit from BaseTask
    2. Set `name` and `description` 
    3. Implement all abstract methods
    4. Register in council/tasks/__init__.py
    """

    name: str = "base"
    description: str = "Base task"

    @abstractmethod
    async def fetch_input(self, source: str, **kwargs) -> dict:
        """Fetch and prepare input data from the source.
        
        Args:
            source: Input source (URL, file path, text, etc.)
            **kwargs: Additional arguments (e.g., file_filter)
            
        Returns:
            Dictionary with input data for the task
        """
        pass

    @abstractmethod
    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build prompts for the models.
        
        Args:
            input_data: Data returned from fetch_input()
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        pass

    @abstractmethod
    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse a model's response into a TaskResult.
        
        Args:
            model_name: Name of the model that generated the response
            response: Raw text response from the model
            
        Returns:
            Parsed TaskResult
        """
        pass

    def error_result(self, model_name: str, error: str) -> TaskResult:
        """Create an error result for this task."""
        return TaskResult.from_error(model_name, error)

    def parse_json_response(self, model_name: str, response: str) -> dict | None:
        """Helper to extract JSON from a response.
        
        Handles responses wrapped in markdown code blocks.
        """
        # Try to find JSON in the response
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try parsing the whole response as JSON
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return None
