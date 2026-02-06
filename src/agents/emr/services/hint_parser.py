"""Oracle Parallel Hint Parser."""

import re
from typing import Optional


def parse_parallel_hint(hint: Optional[str], default: int = 1) -> int:
    """
    Extract parallel degree from Oracle hint string.

    Args:
        hint: Oracle hint string, e.g., "/*+ PARALLEL(8) FULL(A) */"
        default: Default value if hint is empty or unparseable

    Returns:
        Parallel degree as integer

    Examples:
        >>> parse_parallel_hint("/*+ PARALLEL(8) FULL(A) */")
        8
        >>> parse_parallel_hint("/*+ PARALLEL(16) */")
        16
        >>> parse_parallel_hint("/*+ FULL(A) */")
        1
        >>> parse_parallel_hint(None)
        1
        >>> parse_parallel_hint("")
        1
    """
    if not hint:
        return default

    # Match PARALLEL(N) or PARALLEL (N) patterns
    # Case insensitive, allows spaces
    match = re.search(r"PARALLEL\s*\(\s*(\d+)\s*\)", hint, re.IGNORECASE)

    if match:
        return int(match.group(1))

    return default


def build_parallel_hint(parallel: int, include_full: bool = True) -> str:
    """
    Build Oracle parallel hint string.

    Args:
        parallel: Parallel degree
        include_full: Whether to include FULL(A) hint

    Returns:
        Oracle hint string

    Examples:
        >>> build_parallel_hint(8)
        '/*+ PARALLEL(8) FULL(A) */'
        >>> build_parallel_hint(16, include_full=False)
        '/*+ PARALLEL(16) */'
    """
    if include_full:
        return f"/*+ PARALLEL({parallel}) FULL(A) */"
    return f"/*+ PARALLEL({parallel}) */"


def adjust_hint(original_hint: str, new_parallel: int) -> str:
    """
    Adjust the parallel degree in an existing hint string.

    Preserves other hint components (FULL, INDEX, etc.)

    Args:
        original_hint: Original hint string
        new_parallel: New parallel degree

    Returns:
        Modified hint string

    Examples:
        >>> adjust_hint("/*+ PARALLEL(8) FULL(A) */", 4)
        '/*+ PARALLEL(4) FULL(A) */'
        >>> adjust_hint("/*+ PARALLEL(16) INDEX(B) */", 2)
        '/*+ PARALLEL(2) INDEX(B) */'
    """
    if not original_hint:
        return build_parallel_hint(new_parallel)

    # Replace PARALLEL(N) with new value
    adjusted = re.sub(
        r"PARALLEL\s*\(\s*\d+\s*\)",
        f"PARALLEL({new_parallel})",
        original_hint,
        flags=re.IGNORECASE,
    )

    return adjusted
