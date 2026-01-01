"""
Parsing Diff Tracer Module

Provides character-level diffing for subprocess output before and after
the entire parsing pipeline, enabling easy debugging of output filtering.
"""

import difflib
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


class ParsingDiffTracer:
    """
    Traces character-level differences in subprocess output as it passes
    through the parsing pipeline.
    """

    def __init__(self, enabled: bool = None):
        """
        Initialize the diff tracer.

        Args:
            enabled: If None, uses PARSING_DEBUG environment variable.
                    If True/False, explicitly enable/disable.
        """
        if enabled is None:
            self.enabled = os.getenv("PARSING_DEBUG", "").lower() in ("1", "true", "yes")
        else:
            self.enabled = enabled

        self.output_count = 0

    def log_diff(
        self,
        before: str,
        after: str,
        filters_applied: Optional[List[str]] = None,
        queue_size: int = 0,
        current_command: Optional[str] = None,
    ) -> None:
        """
        Log a before/after diff of parsed output.

        Args:
            before: Raw output before parsing pipeline
            after: Output after all filtering
            filters_applied: List of filter rules that matched
            queue_size: Current output queue size
            current_command: The command that triggered this output
        """
        if not self.enabled:
            return

        self.output_count += 1

        # Skip if no changes
        if before == after:
            if before.strip():  # Don't log empty outputs
                self._print_no_change(before, current_command)
            return

        # Calculate metrics
        chars_removed = len(before) - len(after)
        percent_removed = (chars_removed / len(before) * 100) if before else 0

        # Generate the diff
        self._print_diff_header(self.output_count, current_command)
        self._print_raw_section(before)
        self._print_final_section(after)
        self._print_character_diff(before, after)
        self._print_analysis(
            chars_removed, percent_removed, filters_applied, queue_size
        )
        self._print_separator()

    def _print_diff_header(self, count: int, command: Optional[str]) -> None:
        """Print the header for a diff section."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print("\n")
        print("╔" + "═" * 78 + "╗")
        print(
            f"║ PARSING DEBUG #{count:<4} | {timestamp}{'   ' + f'CMD: {command}' if command else '':<37} ║"
        )
        print("╚" + "═" * 78 + "╝")

    def _print_raw_section(self, raw_output: str) -> None:
        """Print the raw output section."""
        lines = raw_output.split("\n")
        preview = (
            raw_output[:80].replace("\n", "\\n")
            if len(raw_output) > 80
            else raw_output.replace("\n", "\\n")
        )
        print(f"\n📥 RAW OUTPUT ({len(raw_output)} chars):")
        print(f"   Preview: {repr(preview)}")
        if len(lines) <= 5:
            for line in lines:
                print(f"   {repr(line)}")

    def _print_final_section(self, final_output: str) -> None:
        """Print the final output section."""
        lines = final_output.split("\n")
        preview = (
            final_output[:80].replace("\n", "\\n")
            if len(final_output) > 80
            else final_output.replace("\n", "\\n")
        )
        print(f"\n📤 FINAL OUTPUT ({len(final_output)} chars):")
        print(f"   Preview: {repr(preview)}")
        if len(lines) <= 5:
            for line in lines:
                print(f"   {repr(line)}")

    def _print_character_diff(self, before: str, after: str) -> None:
        """Print character-level diff using difflib."""
        print(f"\n🔍 CHARACTER-LEVEL DIFF:")
        print(f"   {'-' * 74}")

        # Split into lines for diffing
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)

        # Use ndiff for character-level comparison
        diff_gen = difflib.ndiff(before_lines, after_lines)
        diff_lines = list(diff_gen)

        if not diff_lines or len(diff_lines) == 0:
            # No visible diff, show byte-by-byte
            print(f"   No line-based diff (content differs at byte level)")
            return

        # Print first 10 diff lines to avoid spam
        max_lines = 10
        shown = 0

        for line in diff_lines:
            if shown >= max_lines:
                remaining = len(diff_lines) - shown
                if remaining > 0:
                    print(
                        f"   ... ({remaining} more diff lines) ..."
                    )
                break

            if line[0] == "-":
                # Removed content
                content = line[2:].rstrip("\n")
                print(f"   \033[91m- {repr(content)}\033[0m")  # Red
                shown += 1
            elif line[0] == "+":
                # Added content
                content = line[2:].rstrip("\n")
                print(f"   \033[92m+ {repr(content)}\033[0m")  # Green
                shown += 1
            elif line[0] == "?":
                # Highlight changes
                content = line[2:].rstrip("\n")
                if content.strip():
                    print(f"   \033[93m? {content}\033[0m")  # Yellow
                    shown += 1

        print(f"   {'-' * 74}")

    def _print_analysis(
        self,
        chars_removed: int,
        percent_removed: float,
        filters_applied: Optional[List[str]],
        queue_size: int,
    ) -> None:
        """Print analysis of the changes."""
        print(f"\n📊 ANALYSIS:")
        print(f"   Characters removed: {chars_removed} ({percent_removed:.1f}%)")
        print(f"   Output queue size: {queue_size}")

        if filters_applied:
            print(f"   Filters matched:")
            for filter_name in filters_applied:
                print(f"      ✓ {filter_name}")

    def _print_no_change(self, output: str, command: Optional[str]) -> None:
        """Print when output passes through unchanged."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.output_count += 1

        print("\n")
        print("╔" + "═" * 78 + "╗")
        print(
            f"║ PARSING PASS-THROUGH #{self.output_count:<3} | {timestamp}{'   ' + f'CMD: {command}' if command else '':<37} ║"
        )
        print("╚" + "═" * 78 + "╝")

        preview = (
            output[:80].replace("\n", "\\n")
            if len(output) > 80
            else output.replace("\n", "\\n")
        )
        print(f"\n✅ NO FILTERING APPLIED:")
        print(f"   {len(output)} chars passed through unchanged")
        print(f"   Preview: {repr(preview)}")
        self._print_separator()

    def _print_separator(self) -> None:
        """Print a visual separator."""
        print()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about traced outputs."""
        return {
            "outputs_traced": self.output_count,
            "enabled": self.enabled,
        }


# Global instance
_tracer_instance: Optional[ParsingDiffTracer] = None


def get_tracer(enabled: bool = None) -> ParsingDiffTracer:
    """
    Get or create the global diff tracer instance.

    Args:
        enabled: Enable/disable the tracer (only used on first call)

    Returns:
        ParsingDiffTracer instance
    """
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = ParsingDiffTracer(enabled=enabled)
    return _tracer_instance
