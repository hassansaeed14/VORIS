from agents.autonomous.tool_selector import choose_tool
from agents.autonomous.coding_agent import write_code
from agents.autonomous.debug_agent import fix_code

import traceback


# -------------------------------
# CLEAN PLAN → STEPS
# -------------------------------

def extract_steps(plan):
    lines = plan.split("\n")
    steps = []

    for line in lines:
        line = line.strip()

        # Ignore empty / titles
        if not line:
            continue

        # Match numbered steps
        if line[0].isdigit():
            step = line.split(".", 1)[-1].strip()
            steps.append(step)

    return steps


# -------------------------------
# EXECUTE SINGLE STEP
# -------------------------------

def execute_step(step):
    try:
        tool = choose_tool(step)

        print(f"\n[Executor] Step: {step}")
        print(f"[Executor] Tool: {tool}")

        if tool == "coding_agent":
            return write_code(step)

        elif tool == "debug_agent":
            return fix_code(step)

        elif tool == "analysis":
            return f"Analyzed: {step}"

        elif tool == "search":
            return f"Searched info for: {step}"

        else:
            return f"Executed: {step}"

    except Exception as e:
        return f"Execution failed for step: {step}\nError: {str(e)}"


# -------------------------------
# MAIN EXECUTOR (HYBRID)
# -------------------------------

def execute_plan(plan):

    print("\nVORIS Executor started...")

    steps = extract_steps(plan)

    if not steps:
        return ["No valid steps found."]

    results = []
    execution_log = []

    for i, step in enumerate(steps, 1):

        result = execute_step(step)

        execution_log.append({
            "step_number": i,
            "step": step,
            "result": str(result)[:500]
        })

        results.append(f"STEP {i}:\n{result}\n")

    return results


# -------------------------------
# SMART EXECUTION (WITH MEMORY)
# -------------------------------

def execute_with_context(plan, context=None):

    print("\nVORIS Smart Execution Mode...")

    steps = extract_steps(plan)
    results = []

    for i, step in enumerate(steps, 1):

        enriched_step = step

        if context:
            enriched_step = f"{step} (Context: {context})"

        result = execute_step(enriched_step)

        results.append(f"STEP {i}:\n{result}\n")

    return results


# -------------------------------
# RETRY FAILED STEPS
# -------------------------------

def retry_failed(results):

    retried = []

    for res in results:
        if "failed" in res.lower():
            retried.append("Retrying...\n" + res)

    return retried if retried else ["No failed steps to retry."]