"""Task implementations for Model Council."""

from council.tasks.base import BaseTask, TaskResult
from council.tasks.pr_review import PRReviewTask
from council.tasks.architecture import ArchitectureTask  # Add this

# Registry of available tasks
TASKS: dict[str, type[BaseTask]] = {
    "pr-review": PRReviewTask,
    "architecture": ArchitectureTask,  # Add this
}


def get_task(name: str) -> BaseTask:
    """Get a task instance by name."""
    if name not in TASKS:
        available = ", ".join(TASKS.keys())
        raise ValueError(f"Unknown task: {name}. Available: {available}")
    return TASKS[name]()


def list_tasks() -> list[dict]:
    """List all available tasks."""
    return [
        {"name": name, "description": task.description}
        for name, task in TASKS.items()
    ]


__all__ = [
    "BaseTask",
    "TaskResult",
    "PRReviewTask",
    "ArchitectureTask",
    "TASKS",
    "get_task",
    "list_tasks",
]