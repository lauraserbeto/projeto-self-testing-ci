import pytest

from scripts.check_coverage import check


@pytest.mark.parametrize(
    "lines,branches,expected",
    [
        (85, 80, True),
        (100, 100, True),
        (84, 100, False),
        (100, 79, False),
        (84, 79, False),
        (0, 0, False),
    ],
)
def test_gate_enforces_both_limits(lines, branches, expected):
    assert (
        check(
            {
                "covered_lines": lines,
                "num_statements": 100,
                "covered_branches": branches,
                "num_branches": 100,
            }
        )
        is expected
    )
