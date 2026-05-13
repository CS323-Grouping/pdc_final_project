"""Pytest fixtures and test-run defaults.

Disables bytecode emission so `python -m pytest` does not litter tests/__pycache__
with tracked .pyc files (repository .gitignore already ignores them).
"""

import sys

sys.dont_write_bytecode = True
