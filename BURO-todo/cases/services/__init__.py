"""
cases/services package.

Re-exports all public symbols that callers import from `cases.services`
so that existing imports continue to work after the migration from a
single-file module to a package.
"""

from cases.services._core import (
    filter_cases_by_status,
    calculate_final_grade,
    SanctionService,
)
from cases.services.assignment_service import assign_students_to_pending_cases

__all__ = [
    'filter_cases_by_status',
    'calculate_final_grade',
    'SanctionService',
    'assign_students_to_pending_cases',
]
