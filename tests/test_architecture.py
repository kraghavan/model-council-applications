"""Tests for architecture review task."""

import pytest
from pathlib import Path

from council.tasks.architecture import ArchitectureTask
from council.tasks.base import TaskResult


class TestArchitectureTask:
    
    def test_task_properties(self):
        task = ArchitectureTask()
        assert task.name == "architecture"
        assert "architecture" in task.description.lower() or "design" in task.description.lower()

    def test_build_prompt_contains_content(self):
        task = ArchitectureTask()
        input_data = {
            "content": "graph TD\n  A-->B-->C",
            "source": "test.mermaid",
            "type": "mermaid",
        }
        system, user = task.build_prompt(input_data)
        
        assert "architect" in system.lower()
        assert "graph TD" in user
        assert "A-->B-->C" in user

    def test_build_prompt_requests_json(self):
        task = ArchitectureTask()
        input_data = {"content": "test", "source": "test", "type": "text"}
        system, user = task.build_prompt(input_data)
        
        assert "json" in system.lower() or "JSON" in user

    def test_parse_valid_response(self):
        task = ArchitectureTask()
        response = '''
        {
            "score": 0.85,
            "verdict": "APPROVE",
            "summary": "Well-designed system",
            "issues": [
                {"severity": "minor", "category": "scalability", "description": "Consider caching"}
            ],
            "strengths": ["Clean separation of concerns"],
            "recommendations": ["Add monitoring"]
        }
        '''
        result = task.parse_response("claude", response)
        
        assert result.score == 0.85
        assert result.decision == "APPROVE"
        assert result.summary == "Well-designed system"
        assert len(result.issues) == 1
        assert result.issues[0]["category"] == "scalability"
        assert result.extras["strengths"] == ["Clean separation of concerns"]

    def test_parse_response_with_markdown(self):
        task = ArchitectureTask()
        response = '''
        Here's my analysis:
```json
        {"score": 0.7, "verdict": "COMMENT", "summary": "Needs work", "issues": [], "strengths": [], "recommendations": []}
```
        '''
        result = task.parse_response("gemini", response)
        
        assert result.score == 0.7
        assert result.decision == "COMMENT"

    def test_parse_invalid_response(self):
        task = ArchitectureTask()
        result = task.parse_response("claude", "not json at all")
        
        assert result.error is not None
        assert result.decision == "ERROR"

    def test_directory_tree_generation(self, tmp_path):
        # Create mock directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("# Project")
        
        task = ArchitectureTask()
        tree_lines = task._get_tree(tmp_path)
        tree_text = "\n".join(tree_lines)
        
        assert "src" in tree_text
        assert "README.md" in tree_text

    def test_directory_analysis_includes_key_files(self, tmp_path):
        (tmp_path / "README.md").write_text("# My Project\nDescription here")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        
        task = ArchitectureTask()
        analysis = task._analyze_directory(tmp_path)
        
        assert "README.md" in analysis
        assert "My Project" in analysis
        assert "package.json" in analysis

    def test_directory_ignores_git_and_node_modules(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git stuff")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package").mkdir()
        (tmp_path / "src").mkdir()
        
        task = ArchitectureTask()
        tree_lines = task._get_tree(tmp_path)
        tree_text = "\n".join(tree_lines)
        
        assert ".git" not in tree_text
        assert "node_modules" not in tree_text
        assert "src" in tree_text


class TestArchitectureFetchInput:
    
    @pytest.mark.asyncio
    async def test_fetch_raw_text(self):
        task = ArchitectureTask()
        result = await task.fetch_input("Client -> Server -> Database")
        
        assert result["content"] == "Client -> Server -> Database"
        assert result["type"] == "text"

    @pytest.mark.asyncio
    async def test_fetch_file(self, tmp_path):
        test_file = tmp_path / "design.md"
        test_file.write_text("# Architecture\nService A -> Service B")
        
        task = ArchitectureTask()
        result = await task.fetch_input(str(test_file))
        
        assert "Architecture" in result["content"]
        assert result["type"] == "md"

    @pytest.mark.asyncio
    async def test_fetch_directory(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("# Test")
        
        task = ArchitectureTask()
        result = await task.fetch_input(str(tmp_path))
        
        assert result["type"] == "repo"
        assert "README.md" in result["content"]