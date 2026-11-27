"""Sandbox for generated code (T2.7). See docs/sandbox.md.

The code run here is untrusted model output. It runs on Windows only, in a
less-privileged AppContainer on top of a restricted token, on a desktop of its
own, inside a job object with limits; elsewhere the sandbox refuses to run.
"""

TOOL = "sandbox"
# Change whenever the same output could get a different outcome or detail,
# such as a new limit, a new package in the runtime or a new shim.
TOOL_VERSION = "1"
