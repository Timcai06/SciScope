"""Paper model alias re-export.

Routes and services in backend import ``Paper`` through this module to avoid a
hard dependency on pipeline package paths and to keep model ownership centralized.
"""

from src.data_contracts.models import Paper

__all__ = ["Paper"]
