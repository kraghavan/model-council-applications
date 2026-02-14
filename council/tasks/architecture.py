"""Architecture review task implementation."""

from pathlib import Path

import httpx

from council.tasks.base import BaseTask, TaskResult


class ArchitectureTask(BaseTask):
    """Review system architecture diagrams and design documents."""

    name = "architecture"
    description = "Evaluate system design decisions from diagrams or design docs"

    async def fetch_input(self, source: str) -> dict:
        """Fetch architecture content from file, URL, or raw text."""
        
        # URL
        if source.startswith(("http://", "https://")):
            async with httpx.AsyncClient() as client:
                response = await client.get(source)
                response.raise_for_status()
                content = response.text
                return {"content": content, "source": source, "type": "url"}
        
        # File
        path = Path(source)
        if path.exists() and path.is_file():
            content = path.read_text()
            file_type = path.suffix.lstrip(".")
            return {"content": content, "source": str(path), "type": file_type}
        
        # Directory - analyze structure
        if path.exists() and path.is_dir():
            content = self._analyze_directory(path)
            return {"content": content, "source": str(path), "type": "repo"}
        
        # Raw text input
        return {"content": source, "source": "input", "type": "text"}

    def _analyze_directory(self, path: Path, max_depth: int = 3) -> str:
        """Generate a text representation of directory structure."""
        lines = [f"# Repository Structure: {path.name}\n"]
        
        # Get tree structure
        lines.append("## Directory Tree\n```")
        lines.extend(self._get_tree(path, max_depth=max_depth))
        lines.append("```\n")
        
        # Look for key files
        key_files = [
            "README.md", "package.json", "pyproject.toml", 
            "docker-compose.yml", "Dockerfile", "requirements.txt",
            "architecture.md", "ARCHITECTURE.md", "design.md",
        ]
        
        for key_file in key_files:
            file_path = path / key_file
            if file_path.exists():
                content = file_path.read_text()[:2000]  # First 2000 chars
                lines.append(f"## {key_file}\n```\n{content}\n```\n")
        
        return "\n".join(lines)

    def _get_tree(self, path: Path, prefix: str = "", max_depth: int = 3, depth: int = 0) -> list[str]:
        """Generate directory tree lines."""
        if depth >= max_depth:
            return []
        
        lines = []
        ignore = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"}
        
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return []
        
        entries = [e for e in entries if e.name not in ignore and not e.name.startswith(".")]
        
        for i, entry in enumerate(entries[:20]):  # Limit entries
            is_last = i == len(entries) - 1
            current_prefix = "└── " if is_last else "├── "
            lines.append(f"{prefix}{current_prefix}{entry.name}")
            
            if entry.is_dir():
                next_prefix = prefix + ("    " if is_last else "│   ")
                lines.extend(self._get_tree(entry, next_prefix, max_depth, depth + 1))
        
        return lines

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build architecture review prompts."""
        
        system_prompt = """You are a senior software architect reviewing system designs.
Evaluate architecture for scalability, reliability, security, and maintainability.
Be direct and specific. Identify both strengths and concerns.
Respond with ONLY valid JSON."""

        user_prompt = f"""Review this system architecture and provide your assessment.

## Input Type: {input_data['type']}
## Source: {input_data['source']}

## Content
```
{input_data['content']}
```

## Your Task
Analyze this architecture and respond with ONLY valid JSON:

{{
    "score": <float 0.0-1.0>,
    "verdict": "<APPROVE|REQUEST_CHANGES|COMMENT>",
    "summary": "<one paragraph overall assessment>",
    "issues": [
        {{
            "severity": "<critical|major|minor>",
            "category": "<scalability|reliability|security|complexity|coupling|missing-component|other>",
            "description": "<what's wrong and recommendation>"
        }}
    ],
    "strengths": ["<good architectural decisions>"],
    "recommendations": ["<suggested improvements>"]
}}

Scoring guide:
- 0.9-1.0: Excellent design, production-ready
- 0.7-0.9: Good design, minor improvements suggested
- 0.5-0.7: Acceptable but needs work
- 0.3-0.5: Significant concerns
- 0.0-0.3: Major redesign needed"""

        return system_prompt, user_prompt

    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse model response into TaskResult."""
        data = self.parse_json_response(model_name, response)
        
        if data is None:
            return TaskResult.from_error(model_name, "Could not parse JSON response")
        
        issues = []
        for issue in data.get("issues", []):
            issues.append({
                "severity": issue.get("severity", "minor"),
                "category": issue.get("category", "other"),
                "description": issue.get("description", ""),
            })
        
        return TaskResult(
            model_name=model_name,
            score=float(data.get("score", 0.5)),
            decision=data.get("verdict", "COMMENT"),
            summary=data.get("summary", ""),
            issues=issues,
            extras={
                "strengths": data.get("strengths", []),
                "recommendations": data.get("recommendations", []),
            },
        )