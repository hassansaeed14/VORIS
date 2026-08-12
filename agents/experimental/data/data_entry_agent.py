from agents.agent_fabric import build_agent_exports

CAPABILITY_MODE = "hybrid"

globals().update(build_agent_exports(__file__))
