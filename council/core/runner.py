"""Runner for executing tasks across multiple models in parallel."""

import asyncio
from typing import TYPE_CHECKING

from council.core.models import get_model_client, ModelResponse

if TYPE_CHECKING:
    from council.tasks.base import BaseTask, TaskResult


async def run_single_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    task: "BaseTask",
) -> "TaskResult":
    """Run a single model and parse its response."""
    client = get_model_client(model_name)
    response = await client.generate(system_prompt, user_prompt)
    
    if response.error:
        from council.tasks.base import TaskResult
        return TaskResult.from_error(model_name, response.error)
    
    return task.parse_response(response.model_name, response.content)


async def run_council(
    task: "BaseTask",
    input_data: dict,
    models: list[str],
) -> list["TaskResult"]:
    """Run all models in parallel on the given task."""
    system_prompt, user_prompt = task.build_prompt(input_data)
    
    # Execute all models concurrently
    tasks = [
        run_single_model(model, system_prompt, user_prompt, task)
        for model in models
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error results
    from council.tasks.base import TaskResult
    final_results = []
    for model, result in zip(models, results):
        if isinstance(result, Exception):
            final_results.append(TaskResult.from_error(model, str(result)))
        else:
            final_results.append(result)
    
    return final_results
