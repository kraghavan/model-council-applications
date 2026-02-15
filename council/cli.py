"""Command-line interface for Model Council."""

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from council.config import get_settings
from council.core.runner import run_council
from council.core.voting import aggregate_results, Verdict
from council.tasks import get_task, list_tasks

console = Console()


def format_verdict(verdict: Verdict, task_name: str) -> None:
    """Pretty print the verdict."""
    color = {
        "APPROVE": "green",
        "REQUEST_CHANGES": "red",
        "COMMENT": "yellow",
        "REJECT": "red",
        "ERROR": "red",
    }.get(verdict.decision, "white")
    
    console.print()
    console.print(Panel(
        f"[bold {color}]{verdict.emoji} {verdict.decision}[/] — "
        f"Score: {verdict.score:.0%} ({verdict.consensus} consensus)",
        title=f"[bold]Council Verdict: {task_name}[/]",
        border_style=color,
    ))
    
    # Individual results
    console.print("\n[bold]Individual Results:[/]")
    for result in verdict.results:
        if result.error:
            console.print(f"  ⚠️  [red]{result.model_name}[/]: {result.error}")
        else:
            emoji = {"APPROVE": "✅", "REQUEST_CHANGES": "🔴", "COMMENT": "💬"}.get(
                result.decision, "❓"
            )
            summary = result.summary[:80] + "..." if len(result.summary) > 80 else result.summary
            console.print(f"  {emoji} [cyan]{result.model_name}[/] ({result.score:.0%}): {summary}")
    
    # Issues table
    if verdict.issues:
        console.print("\n[bold]Key Issues:[/]")
        table = Table(show_header=True, header_style="bold", expand=True)
        table.add_column("Severity", width=10)
        table.add_column("Location", width=20)
        table.add_column("Issue", no_wrap=False)
        table.add_column("Flagged By", width=15)
        
        colors = {"critical": "red", "major": "yellow", "minor": "cyan", "nit": "dim"}
        
        for issue in verdict.issues[:10]:
            sev = issue.get("severity", "minor")
            loc = issue.get("file") or "-"
            if issue.get("line"):
                loc = f"{loc}:{issue['line']}"
            table.add_row(
                f"[{colors.get(sev, 'white')}]{sev}[/]",
                loc[:20],
                issue.get("description", ""),
                ", ".join(issue.get("raised_by", [])),
            )
        
        console.print(table)


async def execute_task(task_name: str, source: str, models: list[str], file_filter: list[str] | None = None) -> Verdict:
    """Execute a task and return the verdict."""
    settings = get_settings()
    task = get_task(task_name)
    
    # Fetch input with optional file filter
    with console.status(f"[bold blue]Fetching input for {task_name}..."):
        if file_filter and hasattr(task, 'fetch_input'):
            input_data = await task.fetch_input(source, file_filter=file_filter)
        else:
            input_data = await task.fetch_input(source)
    
    # Display task info
    if task_name == "pr-review" and "title" in input_data:
        console.print(f"📋 [bold]{input_data['title']}[/]")
        console.print(f"   {input_data.get('url', source)}")
        console.print(f"   Author: {input_data.get('author', 'unknown')} | "
                     f"{input_data.get('base', '?')} ← {input_data.get('head', '?')}")
        
        # Show filtered files info
        if input_data.get("files_reviewed"):
            files_reviewed = input_data["files_reviewed"]
            total_files = input_data.get("total_files_in_pr", len(files_reviewed))
            if len(files_reviewed) < total_files:
                console.print(f"   📁 Reviewing [cyan]{len(files_reviewed)}[/] of {total_files} files: {', '.join(files_reviewed)}")
    
    elif task_name == "architecture":
        console.print(f"📐 [bold]Architecture Review[/]")
        console.print(f"   Source: {input_data.get('source', source)}")
        console.print(f"   Type: {input_data.get('type', 'unknown')}")
        
        # Show files being reviewed
        if input_data.get("files_reviewed"):
            files_reviewed = input_data["files_reviewed"]
            total_files = input_data.get("total_files", len(files_reviewed))
            if len(files_reviewed) > 0:
                if total_files > len(files_reviewed):
                    console.print(f"   📁 Reviewing [cyan]{len(files_reviewed)}[/] of {total_files} files: {', '.join(files_reviewed)}")
                else:
                    console.print(f"   📁 Files: {', '.join(files_reviewed)}")
    else:
        console.print(f"📋 Input: {source}")
    console.print()
    
    # Run council
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for model in models:
            progress.add_task(f"[cyan]{model}[/] analyzing...", total=None)
        
        results = await run_council(task, input_data, models)
    
    # Aggregate
    return aggregate_results(results, settings.threshold)


@click.group()
@click.version_option(package_name="model-council")
def main():
    """Model Council - Multi-model AI consensus framework."""
    pass


@main.command("pr-review")
@click.argument("pr_url")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--files", "-f", help="Only review these files (comma-separated). Exits if file not in PR.")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def pr_review(pr_url: str, models: str | None, files: str | None, output_json: bool):
    """Review a GitHub pull request.
    
    PR_URL: GitHub PR URL or owner/repo#number
    
    Examples:
    
        council pr-review owner/repo#123
        
        council pr-review owner/repo#123 --files "auth.py,utils.py"
        
        council pr-review owner/repo#123 -f "src/main.py"
    """
    file_filter = None
    if files:
        file_filter = [f.strip() for f in files.split(",")]
    
    _run_task("pr-review", pr_url, models, output_json, file_filter=file_filter)


@main.command("architecture")
@click.argument("source")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--files", "-f", help="Only review these files from directory (comma-separated)")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def architecture(source: str, models: str | None, files: str | None, output_json: bool):
    """Review system architecture.
    
    SOURCE: File path, URL, directory, or raw text
    
    Examples:
    
        council architecture ./design.md
        
        council architecture ./docs --files "system.mermaid,api.mermaid"
        
        council architecture ./my-project/
    """
    file_filter = None
    if files:
        file_filter = [f.strip() for f in files.split(",")]
    
    _run_task("architecture", source, models, output_json, file_filter=file_filter)


@main.command("run")
@click.argument("task_name")
@click.argument("source")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def run_task(task_name: str, source: str, models: str | None, output_json: bool):
    """Run any registered task.
    
    TASK_NAME: Name of the task (see 'council tasks')
    
    SOURCE: Input source for the task
    """
    _run_task(task_name, source, models, output_json)


def _run_task(task_name: str, source: str, models_str: str | None, output_json: bool, file_filter: list[str] | None = None):
    """Internal task runner."""
    settings = get_settings()
    
    # Get models
    if models_str:
        models = [m.strip().lower() for m in models_str.split(",")]
    else:
        models = settings.get_available_models()
    
    if not models:
        console.print("[red]Error:[/] No models available. Check API keys in .env")
        sys.exit(1)
    
    console.print(f"🤖 Council: [bold]{', '.join(models)}[/]\n")
    
    try:
        verdict = asyncio.run(execute_task(task_name, source, models, file_filter))
        
        if output_json:
            import json
            output = {
                "task": task_name,
                "score": verdict.score,
                "decision": verdict.decision,
                "consensus": verdict.consensus,
                "issues": verdict.issues,
                "results": [
                    {
                        "model": r.model_name,
                        "score": r.score,
                        "decision": r.decision,
                        "summary": r.summary,
                        "error": r.error,
                    }
                    for r in verdict.results
                ],
            }
            console.print_json(json.dumps(output))
        else:
            format_verdict(verdict, task_name)
            
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)


@main.command("tasks")
def show_tasks():
    """List available tasks."""
    console.print("[bold]Available Tasks:[/]\n")
    for task in list_tasks():
        console.print(f"  • [cyan]{task['name']}[/] — {task['description']}")


@main.command("models")
def show_models():
    """Show configured models and their status."""
    settings = get_settings()
    available = settings.get_available_models()
    
    console.print("[bold]Model Status:[/]\n")
    
    all_models = ["claude", "gemini", "mistral", "openai", "deepseek", "groq", "ollama"]
    for model in all_models:
        if model in available:
            console.print(f"  ✅ [green]{model}[/] — ready")
        elif model in settings.enabled_models:
            console.print(f"  ❌ [red]{model}[/] — enabled but missing API key")
        else:
            console.print(f"  ⬜ [dim]{model}[/] — not enabled")
    
    console.print(f"\n[dim]Config: COUNCIL_MODELS={settings.council_models}[/]")


if __name__ == "__main__":
    main()
