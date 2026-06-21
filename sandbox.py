"""
Restricted exec environment for learner-submitted Python (Modules 1 & 3).

This is NOT a hardened sandbox against a malicious adversary — it's a teaching
tool for a single learner running their own code. It blocks the most obvious
escape hatches (imports of os/sys/subprocess, file I/O, network) suitable for
an educational context. Do not expose this endpoint to untrusted multi-tenant
traffic without a real sandboxing layer (e.g. subprocess + resource limits,
or a container-per-execution model) if this is ever opened to the public internet.
"""
import builtins
import re as _re_module
import sqlite3 as _sqlite3_module

BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "input",
    "exit", "quit", "help", "globals", "locals", "vars", "breakpoint",
}

ALLOWED_IMPORTS = {"sqlite3": _sqlite3_module, "re": _re_module}


def _restricted_import(name, *args, **kwargs):
    if name in ALLOWED_IMPORTS:
        return ALLOWED_IMPORTS[name]
    raise ImportError(f"Import of '{name}' is not permitted in this sandbox.")


SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in dir(builtins)
    if name not in BLOCKED_NAMES and not name.startswith("_")
}
SAFE_BUILTINS["__import__"] = _restricted_import

FORBIDDEN_SOURCE_TOKENS = [
    "import os", "import sys", "import subprocess", "import socket",
    "open(", "exec(", "eval(", "compile(",
    "os.", "sys.", "subprocess.", "socket.",
]


def is_source_safe(source_code):
    lowered = source_code.lower()
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token.lower() in lowered:
            return False, f"Disallowed code pattern detected: '{token}'"
    return True, None


def run_submission(source_code, extra_globals=None, timeout_note=True):
    """
    Executes learner source in a restricted namespace.
    Returns (success: bool, namespace_or_error: dict|str).
    """
    safe, reason = is_source_safe(source_code)
    if not safe:
        return False, reason

    namespace = {"__builtins__": SAFE_BUILTINS}
    if extra_globals:
        namespace.update(extra_globals)

    try:
        exec(source_code, namespace)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    return True, namespace
