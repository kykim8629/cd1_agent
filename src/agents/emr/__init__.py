"""
EMR Batch Agent - Oracle Connection Pool Management.

Manages Oracle connection pool usage across 1000+ daily batch jobs
to prevent connection exhaustion failures.
"""

from src.agents.emr.handler import lambda_handler

__all__ = ["lambda_handler"]
