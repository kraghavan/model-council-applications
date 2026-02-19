"""Tests for analysis module."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from council.analysis.embeddings import (
    get_embedding,
    cosine_similarity,
    _fallback_embedding,
    EmbeddingProvider,
)
from council.analysis.code_context import (
    CodeContextAnalyzer,
    ImportInfo,
)


class TestEmbeddings:
    """Tests for embedding generation."""
    
    def test_fallback_embedding(self):
        """Test fallback hash-based embedding."""
        result = _fallback_embedding("test content")
        
        assert result.provider == EmbeddingProvider.FALLBACK
        assert result.dimensions == 384
        assert len(result.vector) == 384
        assert all(-1 <= v <= 1 for v in result.vector)
    
    def test_fallback_embedding_deterministic(self):
        """Test that fallback embeddings are deterministic."""
        result1 = _fallback_embedding("same text")
        result2 = _fallback_embedding("same text")
        
        assert result1.vector == result2.vector
    
    def test_fallback_embedding_different_inputs(self):
        """Test that different inputs produce different embeddings."""
        result1 = _fallback_embedding("text one")
        result2 = _fallback_embedding("text two")
        
        assert result1.vector != result2.vector
    
    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        vec = [1.0, 0.0, 0.5]
        
        sim = cosine_similarity(vec, vec)
        
        assert abs(sim - 1.0) < 0.001
    
    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        
        sim = cosine_similarity(vec1, vec2)
        
        assert abs(sim) < 0.001
    
    def test_cosine_similarity_opposite(self):
        """Test cosine similarity of opposite vectors."""
        vec1 = [1.0, 0.5, 0.0]
        vec2 = [-1.0, -0.5, 0.0]
        
        sim = cosine_similarity(vec1, vec2)
        
        assert abs(sim + 1.0) < 0.001
    
    def test_cosine_similarity_different_lengths(self):
        """Test cosine similarity returns 0 for different length vectors."""
        vec1 = [1.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        
        sim = cosine_similarity(vec1, vec2)
        
        assert sim == 0.0
    
    @pytest.mark.asyncio
    async def test_get_embedding_fallback(self):
        """Test get_embedding uses fallback when no API keys."""
        with patch("council.analysis.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = None
            mock_settings.return_value.google_api_key = None
            
            result = await get_embedding("test text")
            
            assert result.provider == EmbeddingProvider.FALLBACK


class TestCodeContext:
    """Tests for code context analysis."""
    
    def test_detect_language_python(self):
        analyzer = CodeContextAnalyzer()
        
        assert analyzer._detect_language("file.py") == "python"
        assert analyzer._detect_language("path/to/file.py") == "python"
    
    def test_detect_language_javascript(self):
        analyzer = CodeContextAnalyzer()
        
        assert analyzer._detect_language("file.js") == "javascript"
        assert analyzer._detect_language("file.jsx") == "javascript"
    
    def test_detect_language_typescript(self):
        analyzer = CodeContextAnalyzer()
        
        assert analyzer._detect_language("file.ts") == "typescript"
        assert analyzer._detect_language("file.tsx") == "typescript"
    
    def test_detect_language_unknown(self):
        analyzer = CodeContextAnalyzer()
        
        assert analyzer._detect_language("file.xyz") == "unknown"
    
    def test_parse_python_imports_simple(self):
        analyzer = CodeContextAnalyzer()
        code = """
import os
import json
from pathlib import Path
"""
        
        imports = analyzer._parse_python_imports(code)
        
        assert len(imports) >= 3
        modules = [i.module for i in imports]
        assert "os" in modules
        assert "json" in modules
    
    def test_parse_python_imports_from_import(self):
        analyzer = CodeContextAnalyzer()
        code = "from council.tasks import BaseTask, TaskResult"
        
        imports = analyzer._parse_python_imports(code)
        
        assert len(imports) >= 1
        assert any(i.module == "council.tasks" for i in imports)
    
    def test_parse_python_imports_relative(self):
        analyzer = CodeContextAnalyzer()
        code = "from ..utils import helper"
        
        imports = analyzer._parse_python_imports(code)
        
        assert len(imports) >= 1
        assert any(i.is_relative for i in imports)
    
    def test_parse_python_imports_stdlib_detection(self):
        analyzer = CodeContextAnalyzer()
        code = """
import os
import json
import mypackage
"""
        
        imports = analyzer._parse_python_imports(code)
        
        stdlib_imports = [i for i in imports if i.is_stdlib]
        external_imports = [i for i in imports if not i.is_stdlib]
        
        assert any(i.module == "os" for i in stdlib_imports)
        assert any(i.module == "mypackage" for i in external_imports)
    
    def test_parse_js_imports_es6(self):
        analyzer = CodeContextAnalyzer()
        code = """
import React from 'react';
import { useState, useEffect } from 'react';
import './styles.css';
"""
        
        imports = analyzer._parse_js_imports(code)
        
        assert len(imports) >= 2
        modules = [i.module for i in imports]
        assert "react" in modules
    
    def test_parse_js_imports_require(self):
        analyzer = CodeContextAnalyzer()
        code = """
const express = require('express');
const path = require('path');
"""
        
        imports = analyzer._parse_js_imports(code)
        
        assert len(imports) >= 2
        modules = [i.module for i in imports]
        assert "express" in modules
        assert "path" in modules
    
    def test_parse_diff_files(self):
        analyzer = CodeContextAnalyzer()
        diff = """diff --git a/file1.py b/file1.py
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,4 @@
+import os
 def hello():
     pass
diff --git a/file2.py b/file2.py
--- a/file2.py
+++ b/file2.py
@@ -1,3 +1,4 @@
+import json
 def world():
     pass
"""
        
        files = analyzer._parse_diff_files(diff)
        
        assert len(files) == 2
        assert files[0].path == "file1.py"
        assert files[1].path == "file2.py"
        assert "import os" in files[0].content
        assert "import json" in files[1].content
    
    @pytest.mark.asyncio
    async def test_analyze_diff(self):
        analyzer = CodeContextAnalyzer()
        diff = """diff --git a/app.py b/app.py
+++ b/app.py
+import os
+from flask import Flask
+
+app = Flask(__name__)
"""
        
        context = await analyzer.analyze_diff(diff)
        
        assert len(context.changed_files) >= 1
        assert context.changed_files[0].language == "python"
        assert len(context.changed_files[0].imports) >= 1


class TestSimilarity:
    """Tests for similarity search."""
    
    @pytest.mark.asyncio
    async def test_find_similar_empty(self):
        """Test find_similar with no past reviews."""
        from council.analysis.similarity import SimilaritySearch
        
        mock_storage = MagicMock()
        mock_storage._conn.return_value.cursor.return_value.fetchall.return_value = []
        
        search = SimilaritySearch(mock_storage)
        
        results = await search.find_similar("test content", "pr-review")
        
        assert results == []


class TestFingerprinting:
    """Tests for issue fingerprinting."""
    
    def test_categorize_issue_sql_injection(self):
        """Test SQL injection categorization."""
        from council.analysis.fingerprint import categorize_issue
        
        assert categorize_issue("SQL injection vulnerability in query") == "sql_injection"
        assert categorize_issue("Unsanitized user input in raw query") == "sql_injection"
    
    def test_categorize_issue_null_check(self):
        """Test null check categorization."""
        from council.analysis.fingerprint import categorize_issue
        
        assert categorize_issue("Missing null check before access") == "null_check"
        assert categorize_issue("Could raise AttributeError if None") == "null_check"
    
    def test_categorize_issue_security(self):
        """Test security categorization."""
        from council.analysis.fingerprint import categorize_issue
        
        assert categorize_issue("Hardcoded password in config") == "security"
        assert categorize_issue("API key exposed in source") == "security"
    
    def test_categorize_issue_performance(self):
        """Test performance categorization."""
        from council.analysis.fingerprint import categorize_issue
        
        assert categorize_issue("N+1 query in loop") == "performance"
        assert categorize_issue("Inefficient O(n^2) algorithm") == "performance"
    
    def test_categorize_issue_other(self):
        """Test unknown issues fall back to 'other'."""
        from council.analysis.fingerprint import categorize_issue
        
        assert categorize_issue("Some random issue description") == "other"
    
    def test_extract_function_python(self):
        """Test Python function extraction."""
        from council.analysis.fingerprint import extract_function_name
        
        code = """
class AuthService:
    def login(self, username, password):
        # Issue here at line 4
        query = f"SELECT * FROM users WHERE name = '{username}'"
        return self.db.execute(query)
"""
        
        result = extract_function_name("auth.py", 4, code)
        assert result == "login"
    
    def test_extract_function_python_class(self):
        """Test Python class extraction when no function."""
        from council.analysis.fingerprint import extract_function_name
        
        code = """
class AuthService:
    SECRET_KEY = "hardcoded"  # Issue at line 3
"""
        
        result = extract_function_name("auth.py", 3, code)
        assert result == "class:AuthService"
    
    def test_extract_function_javascript(self):
        """Test JavaScript function extraction."""
        from council.analysis.fingerprint import extract_function_name
        
        code = """
function processUser(data) {
    // Issue here
    return data.name;
}
"""
        
        result = extract_function_name("utils.js", 3, code)
        assert result == "processUser"
    
    def test_extract_function_javascript_arrow(self):
        """Test JavaScript arrow function extraction."""
        from council.analysis.fingerprint import extract_function_name
        
        code = """
const handleSubmit = async (event) => {
    // Issue here
    return fetch(url);
}
"""
        
        result = extract_function_name("form.js", 3, code)
        assert result == "handleSubmit"
    
    def test_generate_fingerprint_stable(self):
        """Test fingerprint is deterministic."""
        from council.analysis.fingerprint import generate_fingerprint
        
        fp1 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection in query",
        )
        
        fp2 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection in query",
        )
        
        assert fp1 == fp2
    
    def test_generate_fingerprint_ignores_description_wording(self):
        """Test that different description wording produces SAME fingerprint."""
        from council.analysis.fingerprint import generate_fingerprint
        
        # Same issue, different wording (as models would produce)
        fp1 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection vulnerability in query execution",
        )
        
        fp2 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="User input passed directly to SQL without sanitization",
        )
        
        # Should be SAME because file + function + type are same
        assert fp1 == fp2
    
    def test_generate_fingerprint_different_files(self):
        """Test different files produce different fingerprints."""
        from council.analysis.fingerprint import generate_fingerprint
        
        fp1 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection",
        )
        
        fp2 = generate_fingerprint(
            file_path="user.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection",
        )
        
        assert fp1 != fp2
    
    def test_generate_fingerprint_different_functions(self):
        """Test different functions produce different fingerprints."""
        from council.analysis.fingerprint import generate_fingerprint
        
        fp1 = generate_fingerprint(
            file_path="auth.py",
            function_name="login",
            issue_type="sql_injection",
            description="SQL injection",
        )
        
        fp2 = generate_fingerprint(
            file_path="auth.py",
            function_name="logout",
            issue_type="sql_injection",
            description="SQL injection",
        )
        
        assert fp1 != fp2
    
    def test_create_issue_fingerprint(self):
        """Test full fingerprint creation."""
        from council.analysis.fingerprint import create_issue_fingerprint
        
        code = """
def login(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
"""
        
        fp = create_issue_fingerprint(
            file_path="auth.py",
            line_number=3,
            description="SQL injection vulnerability",
            severity="critical",
            file_content=code,
        )
        
        assert fp.file_path == "auth.py"
        assert fp.function_name == "login"
        assert fp.issue_type == "sql_injection"
        assert fp.severity == "critical"
        assert fp.fingerprint is not None
        assert len(fp.fingerprint) == 16
    
    def test_format_previous_issues_same_pr(self):
        """Test formatting issues from same PR."""
        from council.analysis.fingerprint import format_previous_issues
        
        issues = [
            {
                "file_path": "auth.py",
                "function_name": "login",
                "severity": "critical",
                "issue_description": "SQL injection",
                "occurrences": 1,
                "first_seen_pr": 10,
            },
        ]
        
        result = format_previous_issues(issues, current_pr=10)
        
        assert "Unresolved Issues (from this PR)" in result
        assert "auth.py" in result
        assert "SQL injection" in result
    
    def test_format_previous_issues_cross_pr(self):
        """Test formatting issues from different PRs."""
        from council.analysis.fingerprint import format_previous_issues
        
        issues = [
            {
                "file_path": "auth.py",
                "function_name": "login",
                "severity": "critical",
                "issue_description": "SQL injection",
                "occurrences": 3,
                "first_seen_pr": 5,
            },
        ]
        
        result = format_previous_issues(issues, current_pr=10)
        
        assert "Recurring Issues (from previous PRs)" in result
        assert "seen in 3 PRs" in result
    
    def test_format_previous_issues_empty(self):
        """Test empty issues returns empty string."""
        from council.analysis.fingerprint import format_previous_issues
        
        result = format_previous_issues([])
        
        assert result == ""
