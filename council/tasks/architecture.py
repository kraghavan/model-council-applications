"""Architecture review task implementation."""

import re
from pathlib import Path

import httpx

from council.tasks.base import BaseTask, TaskResult


class ArchitectureTask(BaseTask):
    """Review system architecture diagrams and design documents."""

    name = "architecture"
    description = "Evaluate system design decisions from diagrams or design docs"

    # Supported architecture file extensions
    ARCHITECTURE_EXTENSIONS = {
        ".mermaid", ".mmd",          # Mermaid diagrams
        ".puml", ".plantuml",        # PlantUML
        ".drawio", ".dio",           # Draw.io
        ".md", ".markdown",          # Markdown docs
        ".yaml", ".yml",             # YAML configs (docker-compose, k8s)
        ".json",                     # JSON schemas
        ".txt",                      # Plain text
    }

    async def fetch_input(self, source: str, file_filter: list[str] | None = None) -> dict:
        """Fetch architecture content from file, URL, directory, or raw text.
        
        Args:
            source: File path, URL, directory, or raw text
            file_filter: Optional list of specific files to review from a directory
        """
        
        # URL
        if source.startswith(("http://", "https://")):
            async with httpx.AsyncClient() as client:
                response = await client.get(source)
                response.raise_for_status()
                content = response.text
                return {
                    "content": content, 
                    "source": source, 
                    "type": "url",
                    "files_reviewed": [source],
                    "total_files": 1,
                }
        
        path = Path(source)
        
        # Single file
        if path.exists() and path.is_file():
            content = path.read_text()
            file_type = path.suffix.lstrip(".")
            return {
                "content": content, 
                "source": str(path), 
                "type": file_type,
                "files_reviewed": [path.name],
                "total_files": 1,
            }
        
        # Directory - analyze structure or specific files
        if path.exists() and path.is_dir():
            return self._process_directory(path, file_filter)
        
        # Raw text input
        return {
            "content": source, 
            "source": "input", 
            "type": "text",
            "files_reviewed": [],
            "total_files": 0,
        }

    def _process_directory(self, path: Path, file_filter: list[str] | None = None) -> dict:
        """Process a directory, optionally filtering to specific files.
        
        Args:
            path: Directory path
            file_filter: Optional list of files to include
        
        Returns:
            Input data dict with combined content
        """
        # Find all architecture-related files
        all_arch_files = self._find_architecture_files(path)
        
        if file_filter:
            # Filter to specific files
            matched_files, missing_files = self._filter_files(all_arch_files, file_filter)
            
            if missing_files:
                missing_str = ", ".join(missing_files)
                available_str = ", ".join([f.name for f in all_arch_files]) if all_arch_files else "(none)"
                raise ValueError(
                    f"Files not found: {missing_str}\n\n"
                    f"Architecture files in directory: {available_str}"
                )
            
            if not matched_files:
                available_str = ", ".join([f.name for f in all_arch_files]) if all_arch_files else "(none)"
                raise ValueError(
                    f"No matching files found.\n\n"
                    f"Architecture files in directory: {available_str}"
                )
            
            files_to_process = matched_files
        else:
            # No filter - process all architecture files, or fall back to directory analysis
            if all_arch_files:
                files_to_process = all_arch_files
            else:
                # No architecture files found, do general directory analysis
                content = self._analyze_directory(path)
                return {
                    "content": content,
                    "source": str(path),
                    "type": "repo",
                    "files_reviewed": [],
                    "total_files": 0,
                }
        
        # Combine content from selected files
        content = self._combine_files(files_to_process)
        
        return {
            "content": content,
            "source": str(path),
            "type": "collection",
            "files_reviewed": [f.name for f in files_to_process],
            "total_files": len(all_arch_files),
        }

    def _find_architecture_files(self, path: Path) -> list[Path]:
        """Find all architecture-related files in a directory."""
        arch_files = []
        
        # Also look for common architecture file names regardless of extension
        arch_names = {
            "architecture", "design", "system", "diagram", 
            "infrastructure", "topology", "flowchart", "sequence",
            "component", "deployment", "network"
        }
        
        for file in path.rglob("*"):
            if file.is_file():
                # Check extension
                if file.suffix.lower() in self.ARCHITECTURE_EXTENSIONS:
                    # Check if it's likely an architecture file by name
                    name_lower = file.stem.lower()
                    if any(arch_name in name_lower for arch_name in arch_names):
                        arch_files.append(file)
                    elif file.suffix.lower() in {".mermaid", ".mmd", ".puml", ".plantuml", ".drawio", ".dio"}:
                        # Diagram files are always included
                        arch_files.append(file)
        
        # Sort by path for consistent ordering
        return sorted(arch_files, key=lambda f: str(f))

    def _filter_files(
        self, 
        all_files: list[Path], 
        file_filter: list[str]
    ) -> tuple[list[Path], list[str]]:
        """Filter files based on user-provided patterns.
        
        Returns:
            Tuple of (matched_files, missing_filters)
        """
        def matches_filter(filepath: Path, filters: list[str]) -> bool:
            for f in filters:
                # Exact name match
                if f == filepath.name:
                    return True
                # Stem match (without extension)
                if f == filepath.stem:
                    return True
                # Partial/contains match
                if f in filepath.name:
                    return True
                # Path contains match
                if f in str(filepath):
                    return True
            return False
        
        matched_files = [f for f in all_files if matches_filter(f, file_filter)]
        
        # Also check for direct file paths (not in arch_files but exists)
        for f in file_filter:
            filter_path = Path(f)
            if filter_path.exists() and filter_path.is_file():
                if filter_path not in matched_files:
                    matched_files.append(filter_path)
        
        # Find missing filters
        missing_filters = []
        for f in file_filter:
            filter_path = Path(f)
            matched = any(matches_filter(af, [f]) for af in all_files)
            exists_directly = filter_path.exists() and filter_path.is_file()
            if not matched and not exists_directly:
                missing_filters.append(f)
        
        return matched_files, missing_filters

    def _combine_files(self, files: list[Path]) -> str:
        """Combine multiple architecture files into a single content string."""
        sections = []
        
        for file in files:
            try:
                content = file.read_text()
                file_type = file.suffix.lstrip(".") or "text"
                
                section = f"""## File: {file.name}
**Type:** {file_type}
**Path:** {file}

```{file_type}
{content}
```
"""
                sections.append(section)
            except Exception as e:
                sections.append(f"## File: {file.name}\n\n*Error reading file: {e}*\n")
        
        header = f"# Architecture Review: {len(files)} file(s)\n\n"
        return header + "\n---\n\n".join(sections)

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
            is_last = i == len(entries) - 1 or i == 19
            current_prefix = "└── " if is_last else "├── "
            lines.append(f"{prefix}{current_prefix}{entry.name}")
            
            if entry.is_dir():
                next_prefix = prefix + ("    " if is_last else "│   ")
                lines.extend(self._get_tree(entry, next_prefix, max_depth, depth + 1))
        
        return lines

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build architecture review prompts."""
        
        # Show files being reviewed
        files_info = ""
        if input_data.get("files_reviewed"):
            files = input_data["files_reviewed"]
            total = input_data.get("total_files", len(files))
            if len(files) < total:
                files_info = f"\n**Reviewing:** {', '.join(files)} ({len(files)} of {total} architecture files)"
            elif len(files) > 0:
                files_info = f"\n**Files:** {', '.join(files)}"
        
        system_prompt = """You are a senior software architect reviewing system designs.
Evaluate architecture for scalability, reliability, security, and maintainability.
Be direct and specific. Identify both strengths and concerns.
Respond with ONLY valid JSON."""

        user_prompt = f"""Review this system architecture and provide your assessment.

## Input Type: {input_data['type']}
## Source: {input_data['source']}{files_info}

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
