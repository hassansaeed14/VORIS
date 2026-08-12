CAPABILITY_MODE = "placeholder"

from agents.cognitive.planner_core import generate_plan
from agents.cognitive.reasoning_core import reasoning_chain
from agents.cognitive.evaluator_core import evaluate_response
from agents.cognitive.evolution_core import evolve_system
from agents.cognitive.memory_core import store_interaction


def cognitive_process(user_input):

    plan = generate_plan(user_input)

    reasoning = reasoning_chain(user_input)

    score = evaluate_response(user_input, reasoning)

    store_interaction(user_input, reasoning)

    if score < 6:
        evolve_system()

    return reasoning