#!/usr/bin/env python3
"""Launch the Codex ACP CLI via `codex-acp` or a portable `npx` fallback."""

from __future__ import annotations

import os
import shutil
import sys

NPX_PACKAGE = os.getenv("CODEX_ACP_NPX_PACKAGE", "@zed-industries/codex-acp")


def _find_codex_command() -> list[str]:
    """Return the command to execute, preferring a native binary before falling back to `npx`."""
    if path := shutil.which("codex-acp"):
        return [path]

    if (npx := shutil.which("npx")) is None:
        sys.stderr.write(
            "error: Could not locate `codex-acp` or `npx`; please install one of them first.\n"
        )
        sys.exit(1)

    return [npx, NPX_PACKAGE]


def main() -> None:
    cmd = _find_codex_command()
    cmd.extend(sys.argv[1:])
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
