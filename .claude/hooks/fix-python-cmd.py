#!/usr/bin/env python3
"""
PreToolUse hook: rewrite bare `python`/`python3`/`pip`/`pip3` to use the
project venv (.venv/bin/python, .venv/bin/pip) when the venv exists.

Addresses SCUE pitfall #1: agents using system Python instead of .venv.
"""
import json
import os
import re
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")

# Only apply when .venv exists in the current working directory
if not os.path.exists(".venv/bin/python"):
    sys.exit(0)

new_cmd = cmd

# Rewrite bare `python` or `python3` → `.venv/bin/python`
# Negative lookbehind avoids rewriting paths like /usr/bin/python or .venv/bin/python
new_cmd = re.sub(r'(?<![/\w])python3?(?=\s)', '.venv/bin/python', new_cmd)

# Rewrite bare `pip` or `pip3` → `.venv/bin/pip`
new_cmd = re.sub(r'(?<![/\w])pip3?(?=\s)', '.venv/bin/pip', new_cmd)

if new_cmd != cmd:
    print(json.dumps({"updatedInput": {"command": new_cmd}}))
