"""
task_redistribute.py — Import shim for task-redistribute.py

Python cannot import modules with hyphens in their filename using standard
`import` statements. This shim loads task-redistribute.py via importlib and
re-exports the functions needed by kublai-actions.py Rule 2c (K004).

Consumers:
    from task_redistribute import move_task, get_pending_tasks
"""

import importlib.util
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_module_path = os.path.join(_script_dir, "task-redistribute.py")

_spec = importlib.util.spec_from_file_location("task_redistribute_impl", _module_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# Re-export the functions that kublai-actions.py Rule 2c expects
move_task = _module.move_task
get_pending_tasks = _module.get_pending_tasks

# Also expose the full module for any other consumers
redistribute_tasks = _module.redistribute_tasks if hasattr(_module, "redistribute_tasks") else None
