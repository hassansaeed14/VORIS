"""Shared test helpers.

Kept unittest-native on purpose: CI runs `python -m unittest discover`
(.github/workflows/tests.yml), so a pytest conftest fixture would green the
suite locally and do nothing where it matters.
"""

from unittest.mock import patch

import api.api_server as api_server


class SetupGateBypassMixin:
    """Neutralise the first-run setup gate for the duration of each test.

    The middleware in api/api_server.py returns 503 for every /api/ route
    until first-run setup completes. Tests assert against real routes, so
    without this their result depends on whether the machine running them
    happens to be configured -- the same suite passes or fails on identical
    code. Individual tests were patching `requires_first_run_setup` one by
    one and the ones that forgot were exactly the ones failing.

    Mix in *before* unittest.TestCase, and call super().setUp() from any
    subclass that defines its own setUp:

        class MyTests(SetupGateBypassMixin, unittest.TestCase):
            def setUp(self):
                super().setUp()
                self.client = TestClient(api_server.app)

    A test that wants the gate *active* should not use this mixin, and can
    patch `requires_first_run_setup` to return True itself.
    """

    def setUp(self):
        super().setUp()
        patcher = patch.object(api_server, "requires_first_run_setup", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
