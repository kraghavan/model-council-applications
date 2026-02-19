"""Command-line interface for Model Council."""

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from council.config import get_settings
from council.core.deliberation import run_deliberation, DeliberationResult
from council.core.voting import Verdict
from council.db.schema import init_db, get_db_path
from council.db.storage import CouncilStorage
from council.tasks import get_task, list_tasks

console = Console()


def format_verdict(result: DeliberationResult, task_name: str) -> None:
    """Pretty print the deliberation result."""
    verdict = result.verdict
    
    color = {
        "APPROVE": "green",
        "REQUEST_CHANGES": "red",
        "COMMENT": "yellow",
        "REJECT": "red",
        "ERROR": "red",
    }.get(verdict.decision, "white")
    
    # Main verdict panel
    rounds_info = f" | {result.total_rounds} round(s)" if result.total_rounds > 1 else ""
    console.print()
    console.print(Panel(
        f"[bold {color}]{verdict.emoji} {verdict.decision}[/] — "
        f"Score: {verdict.score:.0%} ({verdict.consensus} consensus){rounds_info}",
        title=f"[bold]Council Verdict: {task_name}[/]",
        border_style=color,
    ))
    
    # Individual results
    console.print("\n[bold]Individual Results:[/]")
    for r in verdict.results:
        if r.error:
            console.print(f"  ⚠️  [red]{r.model_name}[/]: {r.error}")
        else:
            emoji = {"APPROVE": "✅", "REQUEST_CHANGES": "🔴", "COMMENT": "💬"}.get(
                r.decision, "❓"
            )
            console.print(f"  {emoji} [cyan]{r.model_name}[/] ({r.score:.0%}): {r.summary}")
    
    # Opinion changes (if multi-round)
    if result.opinion_changes:
        console.print("\n[bold]Opinion Changes:[/]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Model", width=15)
        table.add_column("Round", width=10)
        table.add_column("Score Change", width=15)
        table.add_column("Verdict Change", width=20)
        
        for change in result.opinion_changes:
            score_before = f"{change['score_before']:.0%}" if change['score_before'] else "?"
            score_after = f"{change['score_after']:.0%}" if change['score_after'] else "?"
            
            score_delta = ""
            if change['score_before'] and change['score_after']:
                delta = change['score_after'] - change['score_before']
                if delta > 0:
                    score_delta = f" [green](+{delta:.0%})[/]"
                elif delta < 0:
                    score_delta = f" [red]({delta:.0%})[/]"
            
            verdict_change = ""
            if change['verdict_before'] != change['verdict_after']:
                verdict_change = f"{change['verdict_before']} → {change['verdict_after']}"
            else:
                verdict_change = "[dim]No change[/]"
            
            table.add_row(
                change['model'],
                f"{change['round_from']} → {change['round_to']}",
                f"{score_before} → {score_after}{score_delta}",
                verdict_change,
            )
        
        console.print(table)
    
    # Issues table - use enriched issues from deliberation
    issue_stats = result.stats.get("issues", {}) if result.stats else {}
    enriched_issues = issue_stats.get("enriched_issues", [])
    
    # Fall back to verdict.issues if no enriched
    if not enriched_issues and verdict.issues:
        enriched_issues = [{"_status": "NEW", **i} for i in verdict.issues]
    
    if enriched_issues:
        # Show issue tracking summary
        summary_parts = []
        new_count = issue_stats.get("new", 0)
        unresolved_count = issue_stats.get("unresolved", 0)
        recurring_count = issue_stats.get("recurring", 0)
        
        if new_count > 0:
            summary_parts.append(f"[cyan]{new_count} new[/]")
        if unresolved_count > 0:
            summary_parts.append(f"[yellow]{unresolved_count} unresolved[/]")
        if recurring_count > 0:
            summary_parts.append(f"[red]{recurring_count} recurring[/]")
        
        if summary_parts:
            console.print(f"\n[bold]Issues:[/] {', '.join(summary_parts)}")
        else:
            console.print("\n[bold]Issues:[/]")
        
        table = Table(show_header=True, header_style="bold", expand=True)
        table.add_column("Severity", width=10)
        table.add_column("Location", no_wrap=False)
        table.add_column("Issue", no_wrap=False)
        table.add_column("Status", width=12)
        
        colors = {"critical": "red", "major": "yellow", "minor": "cyan", "nit": "dim"}
        status_colors = {"NEW": "cyan", "UNRESOLVED": "yellow", "RECURRING": "red"}
        
        for issue in enriched_issues[:15]:  # Limit to 15
            sev = issue.get("severity", "minor")
            loc = issue.get("file") or "-"
            if issue.get("line"):
                loc = f"{loc}:{issue['line']}"
            status = issue.get("_status", "NEW")
            status_color = status_colors.get(status, "white")
            
            table.add_row(
                f"[{colors.get(sev, 'white')}]{sev}[/]",
                loc,
                issue.get("description", ""),
                f"[{status_color}]{status}[/]",
            )
        
        console.print(table)
    
    # Stats (if available)
    if result.stats:
        stats = result.stats
        if stats.get("total_calls"):
            console.print(
                f"\n[dim]Session: {result.session_id} | "
                f"Calls: {stats['total_calls']} | "
                f"Tokens: {stats.get('total_input_tokens', 0) + stats.get('total_output_tokens', 0):,} | "
                f"Time: {stats.get('total_latency_ms', 0)/1000:.1f}s[/]"
            )


async def execute_task(
    task_name: str, 
    source: str, 
    models: list[str], 
    file_filter: list[str] | None = None,
    rounds: int = 1,
    deep_analysis: bool = False,
    fresh: bool = False,
) -> DeliberationResult:
    """Execute a task and return the result."""
    settings = get_settings()
    task = get_task(task_name)
    
    # Fetch input with optional file filter and deep analysis
    status_msg = f"[bold blue]Fetching input for {task_name}..."
    if deep_analysis:
        if fresh:
            status_msg = f"[bold blue]Fetching input for {task_name} (deep analysis, fresh)..."
        else:
            status_msg = f"[bold blue]Fetching input for {task_name} (deep analysis)..."
    
    with console.status(status_msg):
        kwargs = {}
        if file_filter:
            kwargs["file_filter"] = file_filter
        if deep_analysis and task_name == "pr-review":
            kwargs["deep_analysis"] = True
            kwargs["fresh"] = fresh
        
        input_data = await task.fetch_input(source, **kwargs)
    
    # Display task info
    if task_name == "pr-review" and "title" in input_data:
        console.print(f"📋 [bold]{input_data['title']}[/]")
        console.print(f"   {input_data.get('url', source)}")
        console.print(f"   Author: {input_data.get('author', 'unknown')} | "
                     f"{input_data.get('base', '?')} ← {input_data.get('head', '?')}")
        
        if input_data.get("files_reviewed"):
            files_reviewed = input_data["files_reviewed"]
            total_files = input_data.get("total_files_in_pr", len(files_reviewed))
            if len(files_reviewed) < total_files:
                console.print(f"   📁 Reviewing [cyan]{len(files_reviewed)}[/] of {total_files} files: {', '.join(files_reviewed)}")
        
        if input_data.get("deep_analysis"):
            if input_data.get("context_from_cache"):
                console.print(f"   🔬 [cyan]Deep analysis[/] (using cached context)")
            else:
                console.print(f"   🔬 [cyan]Deep analysis enabled[/] (code context fetched)")
    
    elif task_name == "architecture":
        console.print(f"📐 [bold]Architecture Review[/]")
        console.print(f"   Source: {input_data.get('source', source)}")
        console.print(f"   Type: {input_data.get('type', 'unknown')}")
        
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
    
    # Show rounds info
    if rounds > 1:
        console.print(f"   🔄 Deliberation: {rounds} rounds")
    
    console.print()
    
    # Run deliberation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for i, model in enumerate(models):
            round_info = f" (round 1/{rounds})" if rounds > 1 else ""
            progress.add_task(f"[cyan]{model}[/] analyzing...{round_info}", total=None)
        
        result = await run_deliberation(
            task=task,
            input_data=input_data,
            models=models,
            rounds=rounds,
            storage_enabled=settings.storage_enabled,
        )
    
    return result


@click.group()
@click.version_option(package_name="model-council")
def main():
    """Model Council - Multi-model AI consensus framework."""
    pass


@main.command("init")
@click.option("--force", is_flag=True, help="Force recreate database (WARNING: destroys data)")
def init_command(force: bool):
    """Initialize Model Council storage.
    
    Creates the database and necessary tables for storing
    review sessions, deliberations, and observations.
    """
    settings = get_settings()
    
    if not settings.storage_enabled:
        console.print("[yellow]Warning:[/] Storage is disabled in config.")
        console.print("Set COUNCIL_STORAGE_ENABLED=true or update council.yaml")
        return
    
    if force:
        console.print("[yellow]Warning:[/] This will delete all existing data!")
        if not click.confirm("Are you sure?"):
            return
    
    try:
        db_path = init_db(settings.storage_path, force=force)
        console.print(f"[green]✓[/] Database initialized at: {db_path}")
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)


@main.command("pr-review")
@click.argument("pr_url")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--files", "-f", help="Only review these files (comma-separated)")
@click.option("--rounds", "-r", type=int, default=None, help="Number of deliberation rounds (default: from config)")
@click.option("--deep", "-d", is_flag=True, help="Deep analysis: fetch code context and suggest patterns")
@click.option("--fresh", is_flag=True, help="Force fresh context fetch (ignore cache)")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def pr_review(pr_url: str, models: str | None, files: str | None, rounds: int | None, deep: bool, fresh: bool, output_json: bool):
    """Review a GitHub pull request.
    
    PR_URL: GitHub PR URL or owner/repo#number
    
    Examples:
    
        council pr-review owner/repo#123
        
        council pr-review owner/repo#123 --files "auth.py,utils.py"
        
        council pr-review owner/repo#123 --rounds 3
        
        council pr-review owner/repo#123 --deep
        
        council pr-review owner/repo#123 --deep --fresh
    """
    file_filter = None
    if files:
        file_filter = [f.strip() for f in files.split(",")]
    
    _run_task("pr-review", pr_url, models, output_json, file_filter=file_filter, rounds=rounds, deep_analysis=deep, fresh=fresh)


@main.command("architecture")
@click.argument("source")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--files", "-f", help="Only review these files from directory (comma-separated)")
@click.option("--rounds", "-r", type=int, default=None, help="Number of deliberation rounds")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def architecture(source: str, models: str | None, files: str | None, rounds: int | None, output_json: bool):
    """Review system architecture.
    
    SOURCE: File path, URL, directory, or raw text
    
    Examples:
    
        council architecture ./design.md
        
        council architecture ./docs --files "system.mermaid,api.mermaid"
        
        council architecture ./my-project/ --rounds 2
    """
    file_filter = None
    if files:
        file_filter = [f.strip() for f in files.split(",")]
    
    _run_task("architecture", source, models, output_json, file_filter=file_filter, rounds=rounds)


@main.command("run")
@click.argument("task_name")
@click.argument("source")
@click.option("--models", "-m", help="Comma-separated list of models")
@click.option("--rounds", "-r", type=int, default=None, help="Number of deliberation rounds")
@click.option("--json", "output_json", is_flag=True, help="Output JSON")
def run_task(task_name: str, source: str, models: str | None, rounds: int | None, output_json: bool):
    """Run any registered task.
    
    TASK_NAME: Name of the task (see 'council tasks')
    
    SOURCE: Input source for the task
    """
    _run_task(task_name, source, models, output_json, rounds=rounds)


def _run_task(
    task_name: str, 
    source: str, 
    models_str: str | None, 
    output_json: bool, 
    file_filter: list[str] | None = None,
    rounds: int | None = None,
    deep_analysis: bool = False,
    fresh: bool = False,
):
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
    
    # Get rounds
    if rounds is None:
        rounds = settings.deliberation_rounds if settings.deliberation_enabled else 1
    
    # Validate rounds
    if rounds > settings.deliberation_max_rounds:
        console.print(f"[yellow]Warning:[/] Reducing rounds from {rounds} to max {settings.deliberation_max_rounds}")
        rounds = settings.deliberation_max_rounds
    
    console.print(f"🤖 Council: [bold]{', '.join(models)}[/]\n")
    
    try:
        result = asyncio.run(execute_task(task_name, source, models, file_filter, rounds, deep_analysis, fresh))
        
        if output_json:
            import json
            output = {
                "task": task_name,
                "session_id": result.session_id,
                "score": result.verdict.score,
                "decision": result.verdict.decision,
                "consensus": result.verdict.consensus,
                "total_rounds": result.total_rounds,
                "opinion_changes": result.opinion_changes,
                "issues": result.verdict.issues,
                "stats": result.stats,
                "results": [
                    {
                        "model": r.model_name,
                        "score": r.score,
                        "decision": r.decision,
                        "summary": r.summary,
                        "error": r.error,
                    }
                    for r in result.verdict.results
                ],
            }
            console.print_json(json.dumps(output))
        else:
            format_verdict(result, task_name)
            
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
        version = settings.get_model_version(model)
        if model in available:
            console.print(f"  ✅ [green]{model}[/] — {version}")
        elif model in settings.enabled_models:
            console.print(f"  ❌ [red]{model}[/] — enabled but missing API key")
        else:
            console.print(f"  ⬜ [dim]{model}[/] — not enabled")
    
    console.print(f"\n[dim]Enabled: {', '.join(settings.enabled_models)}[/]")


@main.command("history")
@click.option("--limit", "-n", default=10, help="Number of sessions to show")
@click.option("--scope", "-s", help="Filter by scope (owner/repo)")
def show_history(limit: int, scope: str | None):
    """Show recent review sessions."""
    settings = get_settings()
    
    if not settings.storage_enabled:
        console.print("[yellow]Storage is disabled.[/] Enable it to see history.")
        return
    
    try:
        storage = CouncilStorage(settings.storage_path)
        sessions = storage.get_recent_sessions(limit=limit, scope=scope)
        
        if not sessions:
            console.print("[dim]No sessions found.[/]")
            return
        
        console.print("[bold]Recent Sessions:[/]\n")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Session", width=10)
        table.add_column("Source", width=30)
        table.add_column("Verdict", width=15)
        table.add_column("Score", width=10)
        table.add_column("Status", width=12)
        table.add_column("Date", width=20)
        
        for session in sessions:
            verdict = session.get("final_verdict") or "-"
            score = f"{session.get('final_score', 0):.0%}" if session.get("final_score") else "-"
            
            verdict_color = {
                "APPROVE": "green",
                "REQUEST_CHANGES": "red",
                "COMMENT": "yellow",
            }.get(verdict, "white")
            
            source_ref = session.get("source_ref", "")[:28]
            if len(session.get("source_ref", "")) > 28:
                source_ref += "..."
            
            table.add_row(
                session["id"],
                source_ref,
                f"[{verdict_color}]{verdict}[/]",
                score,
                session.get("status", "unknown"),
                str(session.get("started_at", ""))[:19],
            )
        
        console.print(table)
        
    except FileNotFoundError:
        console.print("[yellow]Database not initialized.[/] Run 'council init' first.")
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")


@main.command("stats")
@click.argument("session_id", required=False)
def show_stats(session_id: str | None):
    """Show statistics for a session or overall."""
    settings = get_settings()
    
    if not settings.storage_enabled:
        console.print("[yellow]Storage is disabled.[/] Enable it to see stats.")
        return
    
    try:
        storage = CouncilStorage(settings.storage_path)
        
        if session_id:
            # Show stats for specific session
            stats = storage.get_session_stats(session_id)
            changes = storage.get_opinion_changes(session_id)
            
            console.print(f"[bold]Session: {session_id}[/]\n")
            console.print(f"  API Calls: {stats['total_calls']}")
            console.print(f"  Input Tokens: {stats['total_input_tokens']:,}")
            console.print(f"  Output Tokens: {stats['total_output_tokens']:,}")
            console.print(f"  Total Time: {stats['total_latency_ms']/1000:.2f}s")
            console.print(f"  Errors: {stats['error_count']}")
            
            if changes:
                console.print(f"\n[bold]Opinion Changes:[/]")
                for change in changes:
                    console.print(
                        f"  {change.model}: {change.verdict_before} → {change.verdict_after} "
                        f"({change.score_before:.0%} → {change.score_after:.0%})"
                    )
        else:
            # Show overall stats
            console.print("[dim]Use 'council stats <session_id>' for session details.[/]")
            console.print("[dim]Use 'council history' to see recent sessions.[/]")
            
    except FileNotFoundError:
        console.print("[yellow]Database not initialized.[/] Run 'council init' first.")
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")


if __name__ == "__main__":
    main()
