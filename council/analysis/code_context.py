"""Code context analysis for deep PR review.

Parses imports, identifies dependencies, and fetches relevant context
to enhance the review with understanding of the broader codebase.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from council.config import get_settings


@dataclass
class ImportInfo:
    """Information about an import."""
    module: str
    name: Optional[str] = None  # Specific import (from X import Y)
    alias: Optional[str] = None
    is_relative: bool = False
    is_stdlib: bool = False


@dataclass
class FileContext:
    """Context fetched for a file."""
    path: str
    content: str
    language: str
    imports: list[ImportInfo] = field(default_factory=list)


@dataclass
class CodeContext:
    """Aggregated code context for deep analysis."""
    changed_files: list[FileContext]
    related_files: list[FileContext]
    summary: str


# Common Python stdlib modules (partial list)
PYTHON_STDLIB = {
    "os", "sys", "re", "json", "typing", "pathlib", "collections",
    "dataclasses", "functools", "itertools", "datetime", "time",
    "hashlib", "uuid", "logging", "unittest", "asyncio", "abc",
    "contextlib", "copy", "enum", "io", "math", "random", "string",
    "subprocess", "tempfile", "threading", "traceback", "warnings",
}


class CodeContextAnalyzer:
    """Analyze code to extract context for deep review."""
    
    def __init__(self, owner: str = "", repo: str = "", branch: str = "main"):
        """Initialize analyzer.
        
        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
            branch: Branch to fetch files from
        """
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.settings = get_settings()
    
    async def analyze_diff(
        self,
        diff: str,
        max_context_files: int = 5,
        max_context_tokens: int = 10000,
    ) -> CodeContext:
        """Analyze a diff and fetch relevant context.
        
        Args:
            diff: The PR diff
            max_context_files: Maximum number of related files to fetch
            max_context_tokens: Approximate token limit for context
            
        Returns:
            CodeContext with analyzed information
        """
        # Parse changed files from diff
        changed_files = self._parse_diff_files(diff)
        
        # Extract imports from changed files
        all_imports: list[ImportInfo] = []
        for file_ctx in changed_files:
            imports = self._parse_imports(file_ctx.content, file_ctx.language)
            file_ctx.imports = imports
            all_imports.extend(imports)
        
        # Identify related files to fetch
        related_paths = self._identify_related_files(all_imports, changed_files)
        
        # Fetch related files (limited)
        related_files = await self._fetch_related_files(
            related_paths[:max_context_files]
        )
        
        # Build summary
        summary = self._build_context_summary(changed_files, related_files, all_imports)
        
        return CodeContext(
            changed_files=changed_files,
            related_files=related_files,
            summary=summary,
        )
    
    def _parse_diff_files(self, diff: str) -> list[FileContext]:
        """Parse files and their content from a unified diff."""
        files = []
        current_file = None
        current_content = []
        
        for line in diff.split("\n"):
            # New file header
            if line.startswith("+++ b/"):
                # Save previous file
                if current_file:
                    files.append(FileContext(
                        path=current_file,
                        content="\n".join(current_content),
                        language=self._detect_language(current_file),
                    ))
                
                current_file = line[6:]  # Remove "+++ b/"
                current_content = []
            
            # Added lines (the new code)
            elif line.startswith("+") and not line.startswith("+++"):
                current_content.append(line[1:])  # Remove "+"
        
        # Save last file
        if current_file:
            files.append(FileContext(
                path=current_file,
                content="\n".join(current_content),
                language=self._detect_language(current_file),
            ))
        
        return files
    
    def _detect_language(self, filepath: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(filepath).suffix.lower()
        
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
        }
        
        return language_map.get(ext, "unknown")
    
    def _parse_imports(self, code: str, language: str) -> list[ImportInfo]:
        """Parse imports from code based on language."""
        if language == "python":
            return self._parse_python_imports(code)
        elif language in ("javascript", "typescript"):
            return self._parse_js_imports(code)
        else:
            return []
    
    def _parse_python_imports(self, code: str) -> list[ImportInfo]:
        """Parse Python import statements."""
        imports = []
        
        # Match: import X, import X as Y
        for match in re.finditer(r"^import\s+([\w.]+)(?:\s+as\s+(\w+))?", code, re.MULTILINE):
            module = match.group(1)
            imports.append(ImportInfo(
                module=module,
                alias=match.group(2),
                is_stdlib=module.split(".")[0] in PYTHON_STDLIB,
            ))
        
        # Match: from X import Y, from X import Y as Z
        for match in re.finditer(
            r"^from\s+(\.*)?([\w.]*)\s+import\s+(.+?)(?:\s+as\s+(\w+))?$",
            code, re.MULTILINE
        ):
            relative_dots = match.group(1) or ""
            module = match.group(2) or ""
            names = match.group(3)
            
            is_relative = len(relative_dots) > 0
            
            # Handle multiple imports: from X import A, B, C
            for name in names.split(","):
                name = name.strip()
                if " as " in name:
                    name, alias = name.split(" as ")
                    name = name.strip()
                    alias = alias.strip()
                else:
                    alias = None
                
                imports.append(ImportInfo(
                    module=module,
                    name=name,
                    alias=alias,
                    is_relative=is_relative,
                    is_stdlib=module.split(".")[0] in PYTHON_STDLIB if module else False,
                ))
        
        return imports
    
    def _parse_js_imports(self, code: str) -> list[ImportInfo]:
        """Parse JavaScript/TypeScript import statements."""
        imports = []
        
        # Match: import X from 'Y', import { X } from 'Y'
        for match in re.finditer(
            r"import\s+(?:{[^}]+}|[\w*]+(?:\s*,\s*{[^}]+})?)\s+from\s+['\"]([^'\"]+)['\"]",
            code
        ):
            module = match.group(1)
            imports.append(ImportInfo(
                module=module,
                is_relative=module.startswith("."),
            ))
        
        # Match: require('X')
        for match in re.finditer(r"require\(['\"]([^'\"]+)['\"]\)", code):
            module = match.group(1)
            imports.append(ImportInfo(
                module=module,
                is_relative=module.startswith("."),
            ))
        
        return imports
    
    def _identify_related_files(
        self,
        imports: list[ImportInfo],
        changed_files: list[FileContext],
    ) -> list[str]:
        """Identify related files to fetch based on imports."""
        related = set()
        changed_paths = {f.path for f in changed_files}
        
        for imp in imports:
            # Skip stdlib
            if imp.is_stdlib:
                continue
            
            # Convert module to potential file paths
            paths = self._module_to_paths(imp)
            
            for path in paths:
                if path not in changed_paths:
                    related.add(path)
        
        return list(related)
    
    def _module_to_paths(self, imp: ImportInfo) -> list[str]:
        """Convert a module import to potential file paths."""
        paths = []
        module = imp.module.replace(".", "/")
        
        if imp.is_relative:
            # Relative imports - harder to resolve without context
            return []
        
        # Python module possibilities
        paths.extend([
            f"{module}.py",
            f"{module}/__init__.py",
            f"src/{module}.py",
            f"lib/{module}.py",
        ])
        
        # If specific name imported, might be in the module file
        if imp.name:
            paths.append(f"{module}/{imp.name}.py")
        
        return paths
    
    async def _fetch_related_files(self, paths: list[str]) -> list[FileContext]:
        """Fetch related files from GitHub."""
        if not self.owner or not self.repo:
            return []
        
        if not self.settings.github_token:
            return []
        
        files = []
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github.v3.raw",
        }
        
        async with httpx.AsyncClient() as client:
            for path in paths:
                try:
                    url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{path}"
                    params = {"ref": self.branch}
                    
                    response = await client.get(url, headers=headers, params=params)
                    
                    if response.status_code == 200:
                        content = response.text
                        
                        # Limit file size
                        if len(content) > 10000:
                            content = content[:10000] + "\n# ... truncated ..."
                        
                        files.append(FileContext(
                            path=path,
                            content=content,
                            language=self._detect_language(path),
                        ))
                        
                        # Limit total files
                        if len(files) >= 5:
                            break
                            
                except Exception:
                    continue
        
        return files
    
    def _build_context_summary(
        self,
        changed_files: list[FileContext],
        related_files: list[FileContext],
        imports: list[ImportInfo],
    ) -> str:
        """Build a summary of the code context."""
        lines = []
        
        # Changed files summary
        lines.append(f"**Changed Files:** {len(changed_files)}")
        for f in changed_files:
            lines.append(f"  - {f.path} ({f.language})")
        
        # Imports summary
        external_imports = [i for i in imports if not i.is_stdlib and not i.is_relative]
        if external_imports:
            unique_modules = list(set(i.module for i in external_imports))[:10]
            lines.append(f"\n**Key Dependencies:** {', '.join(unique_modules)}")
        
        # Related files
        if related_files:
            lines.append(f"\n**Related Files Analyzed:** {len(related_files)}")
            for f in related_files:
                lines.append(f"  - {f.path}")
        
        return "\n".join(lines)


def format_code_context(context: CodeContext, max_chars: int = 15000) -> str:
    """Format code context for injection into prompt.
    
    Args:
        context: The CodeContext to format
        max_chars: Maximum characters to include
        
    Returns:
        Formatted string for prompt context
    """
    sections = []
    current_chars = 0
    
    # Summary
    sections.append("## Code Context Analysis\n")
    sections.append(context.summary)
    sections.append("")
    
    current_chars = sum(len(s) for s in sections)
    
    # Related files content (most valuable for context)
    if context.related_files:
        sections.append("## Related Source Files\n")
        
        for file in context.related_files:
            if current_chars + len(file.content) > max_chars:
                break
            
            sections.append(f"### {file.path}\n")
            sections.append(f"```{file.language}")
            sections.append(file.content)
            sections.append("```\n")
            
            current_chars += len(file.content) + 100
    
    return "\n".join(sections)
