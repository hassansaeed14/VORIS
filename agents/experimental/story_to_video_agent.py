from agents.agent_fabric import build_agent_exports

CAPABILITY_MODE = "placeholder"

globals().update(build_agent_exports(__file__))
