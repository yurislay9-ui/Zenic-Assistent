"""Tests for code merging: Python, Go, block code, and merge_subtask_results routing."""

import pytest

from src.core.abortive_protocol import AbortiveProtocol


# ============================================================
#  Test: Merge Python Code
# ============================================================

class TestAbortiveMergePython:
    """Tests for Python code merging."""

    def test_merge_deduplicates_imports(self):
        """Should deduplicate imports when merging Python code."""
        parts = [
            "import os\nimport sys\n\ndef foo():\n    pass\n",
            "import os\nimport json\n\ndef bar():\n    pass\n",
        ]
        result = AbortiveProtocol.merge_python_code(parts)
        # "import os" should appear only once
        assert result.count("import os") == 1
        assert "import sys" in result
        assert "import json" in result
        assert "def foo()" in result
        assert "def bar()" in result

    def test_merge_preserves_bodies(self):
        """Should preserve all function bodies when merging."""
        parts = [
            "def hello():\n    print('hello')\n",
            "def world():\n    print('world')\n",
        ]
        result = AbortiveProtocol.merge_python_code(parts)
        assert "def hello()" in result
        assert "def world()" in result
        assert "print('hello')" in result
        assert "print('world')" in result

    def test_merge_single_part(self):
        """Should handle single code part correctly."""
        parts = ["import os\n\ndef main():\n    pass\n"]
        result = AbortiveProtocol.merge_python_code(parts)
        assert "import os" in result
        assert "def main()" in result

    def test_merge_empty_parts(self):
        """Should handle empty parts list."""
        result = AbortiveProtocol.merge_python_code([])
        assert result == ""


# ============================================================
#  Test: Merge Go Code
# ============================================================

class TestAbortiveMergeGo:
    """Tests for Go code merging."""

    def test_merge_go_deduplicates_imports(self):
        """Should deduplicate Go imports."""
        parts = [
            'package main\n\nimport "fmt"\n\nfunc hello() {\n    fmt.Println("hi")\n}\n',
            'package main\n\nimport "fmt"\nimport "os"\n\nfunc world() {\n    os.Exit(0)\n}\n',
        ]
        result = AbortiveProtocol.merge_go_code(parts)
        assert "package main" in result
        assert "fmt" in result
        assert "os" in result
        assert "func hello()" in result
        assert "func world()" in result

    def test_merge_go_preserves_package(self):
        """Should preserve package declaration."""
        parts = [
            'package mypkg\n\nfunc hello() {}\n',
        ]
        result = AbortiveProtocol.merge_go_code(parts)
        assert "package mypkg" in result


# ============================================================
#  Test: Merge Block Code (C-style)
# ============================================================

class TestAbortiveMergeBlockCode:
    """Tests for generic C-style block code merging."""

    def test_merge_with_skip_prefix(self):
        """Should deduplicate lines with skip_prefix."""
        parts = [
            "package com.example\n\nclass A {}\n",
            "package com.example\n\nclass B {}\n",
        ]
        result = AbortiveProtocol.merge_block_code(parts, "//", "package")
        # "package com.example" should appear only once
        assert result.count("package com.example") == 1
        assert "class A" in result
        assert "class B" in result

    def test_merge_without_skip_prefix(self):
        """Should include all lines when no skip_prefix."""
        parts = [
            "function a() {}\n",
            "function b() {}\n",
        ]
        result = AbortiveProtocol.merge_block_code(parts, "//", None)
        assert "function a" in result
        assert "function b" in result


# ============================================================
#  Test: merge_subtask_results routing
# ============================================================

class TestAbortiveMergeSubtaskResults:
    """Tests for the merge_subtask_results() routing method."""

    def test_merge_python_language(self, protocol):
        """Should route to merge_python_code for Python."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "import os\ndef a(): pass"},
            {"status": "SUCCESS", "code": "import sys\ndef b(): pass"},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert "def a" in result
        assert "def b" in result

    def test_merge_go_language(self, protocol):
        """Should route to merge_go_code for Go."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": 'package main\n\nfunc a() {}'},
        ]
        result = ap.merge_subtask_results(results, "go")
        assert "package main" in result

    def test_merge_kotlin_language(self, protocol):
        """Should route to merge_block_code for Kotlin."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "package com.test\n\nclass A {}"},
        ]
        result = ap.merge_subtask_results(results, "kotlin")
        assert "class A" in result

    def test_merge_skips_error_results(self, protocol):
        """Should skip ERROR and MAX_DEPTH_REACHED results."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "def a(): pass"},
            {"status": "ERROR", "code": "bad code"},
            {"status": "MAX_DEPTH_REACHED", "code": "", "message": "too deep"},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert "def a" in result
        # ERROR code should not be included
        assert "bad code" not in result

    def test_merge_no_successful_results(self, protocol):
        """Should return empty string when all results failed."""
        ap, _ = protocol
        results = [
            {"status": "ERROR", "code": "bad"},
            {"status": "MAX_DEPTH_REACHED", "code": ""},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert result == ""
