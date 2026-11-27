from pathlib import Path

from edith_tools.commands.d import main

ROOT = Path(__file__).resolve().parents[3]


def test_scenario_lint_all_and_infeasible(capsys):
    assert main(["scenario", "lint", str(ROOT / "scenarios" / "*.yaml"), "-q"]) == 0
    assert main(["scenario", "lint", str(ROOT / "scenarios/tests/infeasible_vignette.yaml")]) == 1
    assert "expect[2] after ovw" in capsys.readouterr().out


def test_lint_beats_live():
    assert main(["scenario", "lint", "--beats", str(ROOT / "scenarios/demo_live.yaml")]) == 0


def test_record_px4_explains_approval(capsys):
    assert main(["sim", "record-px4"]) == 3
    assert "approval-gated" in capsys.readouterr().err


def test_unknown():
    assert main(["sim", "nope"]) == 2
