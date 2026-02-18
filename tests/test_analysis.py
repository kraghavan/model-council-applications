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
