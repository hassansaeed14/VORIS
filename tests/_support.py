"""Shared helpers for the VORIS test suite.

Named with a leading underscore so `unittest discover -p "test_*.py"` does not
pick it up as a test module.
"""

from unittest.mock import patch

import api.api_server as api_server


def bypass_first_run_setup(test_case):
    """Pin the first-run setup gate to "already set up" for one test.

    `aura_private_access_middleware` (api/api_server.py) returns 503 for every
    /api/ route and redirects every page route to /setup until an owner user
    exists in the user store. Tests that exercise real routes therefore pass or
    fail depending on whether the machine running them happens to have a
    provisioned owner -- not on the code under test.

    Call from setUp(). Registers its own cleanup, and an individual test can
    still override the value with a narrower patch if it needs to.
    """
    patcher = patch.object(api_server, "requires_first_run_setup", return_value=False)
    patcher.start()
    test_case.addCleanup(patcher.stop)


# The order VORIS uses when SAMBANOVA_API_KEY is absent (config/settings.py).
GROQ_LEADS_PRIORITY = ("groq", "sambanova", "gemini", "openai", "openrouter", "claude", "ollama")


def pin_provider_routing(test_case, priority=GROQ_LEADS_PRIORITY, default_reasoning="groq"):
    """Pin provider routing order for one test, independent of local API keys.

    PROVIDER_PRIORITY and DEFAULT_REASONING_PROVIDER are both derived from the
    environment: config/settings.py puts SambaNova first the moment
    SAMBANOVA_API_KEY is set, and Groq first otherwise. Routing tests that read
    those values therefore assert whichever keys the developer happens to have
    configured. Pinning them keeps the assertions about routing logic.
    """
    import brain.provider_hub as provider_hub

    for name, value in (("PROVIDER_PRIORITY", tuple(priority)),
                        ("DEFAULT_REASONING_PROVIDER", default_reasoning)):
        patcher = patch.object(provider_hub, name, value)
        patcher.start()
        test_case.addCleanup(patcher.stop)
