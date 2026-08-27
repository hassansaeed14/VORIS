#!/usr/bin/env python
"""Run every test in the repository, not just tests/.

`python -m unittest discover -s tests` -- what CI used to run -- reaches the 35
modules under tests/ and nothing else. It misses 16 modules in security/tests/
and 4 in agents/experimental/tests/, because neither directory is an importable
package (no __init__.py) and unittest's discover refuses a namespace package as
a start directory.

Those modules do import and run perfectly well by dotted name, so this runner
loads them explicitly rather than adding __init__.py files, which would change
import semantics for the security package.

Usage:
    python run_tests.py            # everything
    python run_tests.py --quiet    # summary only
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Discovered normally: a plain directory of test modules.
DISCOVER_ROOT = "tests"

# Loaded by dotted name: importable as namespace packages, but not discoverable.
EXPLICIT_ROOTS = [
    "security/tests",
    "agents/experimental/tests",
]


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.discover(start_dir=str(ROOT / DISCOVER_ROOT), pattern="test_*.py"))

    for rel in EXPLICIT_ROOTS:
        directory = ROOT / rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("test_*.py")):
            module = f"{rel.replace('/', '.')}.{path.stem}"
            suite.addTests(loader.loadTestsFromName(module))

    return suite


def main() -> int:
    sys.path.insert(0, str(ROOT))
    verbosity = 1 if "--quiet" not in sys.argv else 0
    result = unittest.TextTestRunner(verbosity=verbosity).run(build_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
