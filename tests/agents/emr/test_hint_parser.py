"""Tests for hint_parser module."""

import pytest
from src.agents.emr.services.hint_parser import (
    parse_parallel_hint,
    build_parallel_hint,
    adjust_hint,
)


class TestParseParallelHint:
    """Tests for parse_parallel_hint function."""

    def test_parse_standard_hint(self):
        """Standard Oracle parallel hint."""
        assert parse_parallel_hint("/*+ PARALLEL(8) FULL(A) */") == 8

    def test_parse_parallel_only(self):
        """Parallel hint without other hints."""
        assert parse_parallel_hint("/*+ PARALLEL(16) */") == 16

    def test_parse_with_spaces(self):
        """Hint with extra spaces."""
        assert parse_parallel_hint("/*+ PARALLEL( 32 ) */") == 32

    def test_parse_lowercase(self):
        """Lowercase hint."""
        assert parse_parallel_hint("/*+ parallel(4) */") == 4

    def test_parse_mixed_case(self):
        """Mixed case hint."""
        assert parse_parallel_hint("/*+ Parallel(12) Full(A) */") == 12

    def test_parse_no_parallel(self):
        """Hint without PARALLEL."""
        assert parse_parallel_hint("/*+ FULL(A) INDEX(B) */") == 1

    def test_parse_empty_string(self):
        """Empty string."""
        assert parse_parallel_hint("") == 1

    def test_parse_none(self):
        """None value."""
        assert parse_parallel_hint(None) == 1

    def test_parse_with_custom_default(self):
        """Custom default value."""
        assert parse_parallel_hint("", default=8) == 8
        assert parse_parallel_hint(None, default=4) == 4

    def test_parse_complex_hint(self):
        """Complex hint with multiple options."""
        hint = "/*+ PARALLEL(24) FULL(A) USE_HASH(B) INDEX(C IDX_C) */"
        assert parse_parallel_hint(hint) == 24


class TestBuildParallelHint:
    """Tests for build_parallel_hint function."""

    def test_build_with_full(self):
        """Build hint with FULL."""
        assert build_parallel_hint(8) == "/*+ PARALLEL(8) FULL(A) */"

    def test_build_without_full(self):
        """Build hint without FULL."""
        assert build_parallel_hint(16, include_full=False) == "/*+ PARALLEL(16) */"

    def test_build_various_degrees(self):
        """Build hints with various parallel degrees."""
        assert build_parallel_hint(1) == "/*+ PARALLEL(1) FULL(A) */"
        assert build_parallel_hint(32) == "/*+ PARALLEL(32) FULL(A) */"
        assert build_parallel_hint(128) == "/*+ PARALLEL(128) FULL(A) */"


class TestAdjustHint:
    """Tests for adjust_hint function."""

    def test_adjust_standard_hint(self):
        """Adjust standard hint."""
        original = "/*+ PARALLEL(8) FULL(A) */"
        assert adjust_hint(original, 4) == "/*+ PARALLEL(4) FULL(A) */"

    def test_adjust_preserves_other_hints(self):
        """Other hints are preserved."""
        original = "/*+ PARALLEL(16) INDEX(B) USE_HASH(C) */"
        adjusted = adjust_hint(original, 2)
        assert "PARALLEL(2)" in adjusted
        assert "INDEX(B)" in adjusted
        assert "USE_HASH(C)" in adjusted

    def test_adjust_empty_hint(self):
        """Empty hint creates new one."""
        assert "PARALLEL(8)" in adjust_hint("", 8)

    def test_adjust_none_hint(self):
        """None hint creates new one."""
        assert "PARALLEL(4)" in adjust_hint(None, 4)

    def test_adjust_with_spaces(self):
        """Hint with spaces in PARALLEL."""
        original = "/*+ PARALLEL( 16 ) FULL(A) */"
        adjusted = adjust_hint(original, 4)
        assert "PARALLEL(4)" in adjusted
