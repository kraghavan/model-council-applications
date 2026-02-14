"""Command-line interface for PR Council."""

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from council.config import get_settings
from council.github import fetch_pull_request
from council.models import get_reviewer, ReviewResult
from council.aggregator import aggregate_reviews, CouncilVerdict

console = Console()


def format_verdict(verdict: CouncilVerdict) -> None:
    """Pretty print the council verdict."""
    # Header
    color = {"APPROVE": "green", "REQUEST_CHANGES": "red", "COMMENT": "yellow"}.get(
        verdict.verdict, "white"
    )
    
    console.print()
    console.print(Panel(
        f"[bold {color}]{verdict.emoji} {verdict.verdict}[/] — Score: {verdict.score:.0%} ({verdict.consensus} consensus)",
        title="[bold]Council Verdict[/]",
        border_style=color,
    ))
    
    # Individual reviews
    console.print("\n[bold]Individual Reviews:[/]")
    for review in verdict.individual_reviews:
        if review.error:
            console.print(f"  ❌ [red]{review.model_name}[/]: {review.error}")
        else:
            emoji = {"APPROVE": "✅", "REQUEST_CHANGES": "🔴", "COMMENT": "💬"}.get(
                review.verdict, "❓"
            )
            console.print(f"  {emoji} [cyan]{review.model_name}[/] ({review.score:.0%}): {review.summary[:100]}...")
    
    # Issues table
    if verdict.key_issues:
        console.print("\n[bold]Key Issues:[/]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity", width=10)
        table.add_column("File", width=30)
        table.add_column("Issue", width=50)
        table.add_column("Flagged By", width=20)
        
        severity_colors = {
            "critical": "red",
            "major": "yellow", 
            "minor": "cyan",
            "nit": "dim",
        }
        
        for issue in verdict.key_issues[:10]:
            color = severity_colors.get(issue["severity"], "white")
            table.add_row(
                f"[{color}]{issue['severity']}[/]",
                issue.get("file") or "-",
                issue["description"][:50],
                ", ".join(issue["raised_by"]),
            )
        
        console.print(table)


async def run_review(pr_url: str, models: list[str]) -> CouncilVerdict:
    """Run the council review process."""
    settings = get_settings()
    
    # Fetch PR
    with console.status("[bold blue]Fetching PR from GitHub..."):
        pr = await fetch_pull_request(pr_url)
    
    console.print(f"📋 Reviewing: [bold]{pr.title}[/]")
    console.print(f"   {pr.url}")
    console.print(f"   Author: {pr.author} | {pr.base} ← {pr.head}")
    console.print()
    
    pr_info = {
        "title": pr.title,
        "body": pr.body,
        "author": pr.author,
        "base": pr.base,
        "head": pr.head,
    }
    
    # Run reviews in parallel
    reviewers = [get_reviewer(m) for m in models]
    
    async def review_with_status(reviewer) -> ReviewResult:
        return await reviewer.review(pr_info, pr.diff)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        tasks = []
        for reviewer in reviewers:
            task = progress.add_task(f"[cyan]{reviewer.name}[/] reviewing...", total=None)
            tasks.append((task, reviewer))
        
        # Run all reviews concurrently
        results = await asyncio.gather(
            *[review_with_status(r) for _, r in tasks],
            return_exceptions=True,
        )
        
        # Convert exceptions to error results
        final_results = []
        for (_, reviewer), result in zip(tasks, results):
            if isinstance(result, Exception):
                final_results.append(ReviewResult.from_error(reviewer.name, str(result)))
            else:
                final_results.append(result)
    
    # Aggregate
    return aggregate_reviews(final_results, settings.approval_threshold)


@click.group()
@click.version_option()
def main():
    """PR Council - AI-powered pull request reviews."""
    pass


@main.command()
@click.argument("pr_url")
@click.option(
    "--models", "-m",
    help="Comma-separated list of models (default: from config)",
)
@click.option(
    "--json", "output_json",
    is_flag=True,
    help="Output raw JSON instead of formatted output",
)
def review(pr_url: str, models: str | None, output_json: bool):
    """Review a pull request with the AI council.
    
    PR_URL: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)
    """
    settings = get_settings()
    
    # Determine which models to use
    if models:
        model_list = [m.strip().lower() for m in models.split(",")]
    else:
        model_list = settings.validate_api_keys()
    
    if not model_list:
        console.print("[red]Error:[/] No models available. Check your API keys in .env")
        sys.exit(1)
    
    console.print(f"🤖 Council members: [bold]{', '.join(model_list)}[/]\n")
    
    try:
        verdict = asyncio.run(run_review(pr_url, model_list))
        
        if output_json:
            import json
            output = {
                "score": verdict.score,
                "verdict": verdict.verdict,
                "consensus": verdict.consensus,
                "issues": verdict.key_issues,
                "reviews": [
                    {
                        "model": r.model_name,
                        "score": r.score,
                        "verdict": r.verdict,
                        "summary": r.summary,
                        "error": r.error,
                    }
                    for r in verdict.individual_reviews
                ],
            }
            console.print_json(json.dumps(output))
        else:
            format_verdict(verdict)
            
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)


@main.command()
def models():
    """List available models and their status."""
    settings = get_settings()
    available = settings.validate_api_keys()
    
    console.print("[bold]Available Models:[/]\n")
    
    all_models = ["claude", "gemini", "ollama"]
    for model in all_models:
        if model in available:
            console.print(f"  ✅ [green]{model}[/] - configured")
        elif model in settings.enabled_models:
            console.print(f"  ❌ [red]{model}[/] - enabled but missing API key")
        else:
            console.print(f"  ⬜ [dim]{model}[/] - not enabled")
    
    console.print(f"\n[dim]Enabled in config: {settings.council_models}[/]")


if __name__ == "__main__":
    main()
