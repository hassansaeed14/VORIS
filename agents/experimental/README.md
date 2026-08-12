# Experimental / Quarantined Agents

Everything in this directory is **not** wired into live routing.

These are placeholder or thin-wrapper agents moved here during the truth-first
cleanup (per MASTER_SPEC: "build fewer stronger agents instead of many thin
wrappers" and "placeholder capabilities must not be advertised as real").

Rules:

- Nothing in `brain/`, `api/`, or `tools/` may import from this tree.
- The `/api/agents` catalog excludes placeholder agents, so nothing here is
  advertised in the UI.
- To promote an agent to live status: move it back to its category directory,
  give it a real backend, tag it `real` or `hybrid` in `agents/registry.py`,
  and add tests.
