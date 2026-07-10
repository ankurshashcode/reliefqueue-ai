from __future__ import annotations

from reliefqueue.operator_console import clamp_verbose, full_json_section, status_text, true_false, yes_no


def test_operator_console_helpers_are_stable() -> None:
    assert clamp_verbose(None) == 0
    assert clamp_verbose(9) == 4
    assert yes_no(True) == "yes"
    assert true_false(False) == "false"
    assert status_text("REFUSED") == "BLOCKED AS EXPECTED"


def test_full_json_section_is_readable_and_complete() -> None:
    lines: list[str] = []
    full_json_section(lines, "Full captured report JSON", {"b": 2, "a": {"nested": True}})

    text = "\n".join(lines)
    assert "Full captured report JSON:" in text
    assert "```json" in text
    assert '"nested": true' in text
