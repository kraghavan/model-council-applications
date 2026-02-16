"""Task registry for Model Council."""

from council.tasks.base import BaseTask, TaskResult
from council.tasks.pr_review import PRReviewTask
from council.tasks.architecture import ArchitectureTask


# Register all available tasks
TASKS: dict[str, type[BaseTask]] = {
    "pr-review": PRReviewTask,
    "architecture": ArchitectureTask,
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
        {"name": task_cls.name, "description": task_cls.description}
        for task_cls in TASKS.values()
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
