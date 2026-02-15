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


class TestArchitectureFileFiltering:
    """Tests for architecture file filtering feature."""

    def test_find_architecture_files_mermaid(self, tmp_path):
        (tmp_path / "system-architecture.mermaid").write_text("graph TD\n  A-->B")
        (tmp_path / "api-design.mermaid").write_text("graph LR\n  X-->Y")
        (tmp_path / "random.txt").write_text("not architecture")
        
        task = ArchitectureTask()
        files = task._find_architecture_files(tmp_path)
        
        assert len(files) == 2
        assert any("system-architecture.mermaid" in str(f) for f in files)
        assert any("api-design.mermaid" in str(f) for f in files)

    def test_find_architecture_files_plantuml(self, tmp_path):
        (tmp_path / "sequence-diagram.puml").write_text("@startuml\nA -> B\n@enduml")
        
        task = ArchitectureTask()
        files = task._find_architecture_files(tmp_path)
        
        assert len(files) == 1
        assert "sequence-diagram.puml" in str(files[0])

    def test_find_architecture_files_nested(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "architecture.mermaid").write_text("graph TD")
        
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        (diagrams / "system-design.mermaid").write_text("graph LR")
        
        task = ArchitectureTask()
        files = task._find_architecture_files(tmp_path)
        
        assert len(files) == 2

    def test_filter_files_exact_match(self, tmp_path):
        file1 = tmp_path / "system.mermaid"
        file2 = tmp_path / "api.mermaid"
        file1.write_text("graph TD")
        file2.write_text("graph LR")
        
        all_files = [file1, file2]
        task = ArchitectureTask()
        
        matched, missing = task._filter_files(all_files, ["system.mermaid"])
        
        assert len(matched) == 1
        assert matched[0].name == "system.mermaid"
        assert missing == []

    def test_filter_files_partial_match(self, tmp_path):
        file1 = tmp_path / "system-architecture.mermaid"
        file2 = tmp_path / "api-design.mermaid"
        file1.write_text("graph TD")
        file2.write_text("graph LR")
        
        all_files = [file1, file2]
        task = ArchitectureTask()
        
        # "system" should match "system-architecture.mermaid"
        matched, missing = task._filter_files(all_files, ["system"])
        
        assert len(matched) == 1
        assert "system" in matched[0].name

    def test_filter_files_stem_match(self, tmp_path):
        file1 = tmp_path / "architecture.mermaid"
        file1.write_text("graph TD")
        
        all_files = [file1]
        task = ArchitectureTask()
        
        # "architecture" (without extension) should match
        matched, missing = task._filter_files(all_files, ["architecture"])
        
        assert len(matched) == 1

    def test_filter_files_missing(self, tmp_path):
        file1 = tmp_path / "system.mermaid"
        file1.write_text("graph TD")
        
        all_files = [file1]
        task = ArchitectureTask()
        
        matched, missing = task._filter_files(all_files, ["system.mermaid", "nonexistent.mermaid"])
        
        assert len(matched) == 1
        assert missing == ["nonexistent.mermaid"]

    def test_combine_files(self, tmp_path):
        file1 = tmp_path / "system.mermaid"
        file2 = tmp_path / "api.mermaid"
        file1.write_text("graph TD\n  A-->B")
        file2.write_text("graph LR\n  X-->Y")
        
        task = ArchitectureTask()
        combined = task._combine_files([file1, file2])
        
        assert "system.mermaid" in combined
        assert "api.mermaid" in combined
        assert "graph TD" in combined
        assert "graph LR" in combined
        assert "2 file(s)" in combined

    @pytest.mark.asyncio
    async def test_fetch_input_with_filter(self, tmp_path):
        # Create architecture files
        (tmp_path / "system-architecture.mermaid").write_text("graph TD\n  A-->B")
        (tmp_path / "api-design.mermaid").write_text("graph LR\n  X-->Y")
        (tmp_path / "database-diagram.mermaid").write_text("erDiagram")
        
        task = ArchitectureTask()
        result = await task.fetch_input(str(tmp_path), file_filter=["system", "api"])
        
        assert result["type"] == "collection"
        assert len(result["files_reviewed"]) == 2
        assert "system-architecture.mermaid" in result["files_reviewed"]
        assert "api-design.mermaid" in result["files_reviewed"]
        assert "graph TD" in result["content"]
        assert "graph LR" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_input_filter_missing_file_raises(self, tmp_path):
        (tmp_path / "system-architecture.mermaid").write_text("graph TD")
        
        task = ArchitectureTask()
        
        with pytest.raises(ValueError, match="Files not found"):
            await task.fetch_input(str(tmp_path), file_filter=["nonexistent.mermaid"])

    @pytest.mark.asyncio
    async def test_fetch_input_filter_no_matches_raises(self, tmp_path):
        (tmp_path / "system-architecture.mermaid").write_text("graph TD")
        
        task = ArchitectureTask()
        
        with pytest.raises(ValueError, match="(Files not found|No matching files)"):
            await task.fetch_input(str(tmp_path), file_filter=["something_completely_different"])

    @pytest.mark.asyncio
    async def test_fetch_input_all_arch_files_no_filter(self, tmp_path):
        # Create architecture files
        (tmp_path / "system-architecture.mermaid").write_text("graph TD")
        (tmp_path / "api-design.mermaid").write_text("graph LR")
        
        task = ArchitectureTask()
        result = await task.fetch_input(str(tmp_path))
        
        assert result["type"] == "collection"
        assert len(result["files_reviewed"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_input_directory_no_arch_files(self, tmp_path):
        # Create non-architecture files only
        (tmp_path / "README.md").write_text("# Hello")
        (tmp_path / "random.txt").write_text("random stuff")
        
        task = ArchitectureTask()
        result = await task.fetch_input(str(tmp_path))
        
        # Falls back to directory analysis
        assert result["type"] == "repo"

    def test_build_prompt_shows_filtered_files(self):
        task = ArchitectureTask()
        input_data = {
            "content": "graph TD\n  A-->B",
            "source": "./docs",
            "type": "collection",
            "files_reviewed": ["system.mermaid", "api.mermaid"],
            "total_files": 5,
        }
        system, user = task.build_prompt(input_data)
        
        assert "system.mermaid" in user
        assert "api.mermaid" in user
        assert "2 of 5" in user
