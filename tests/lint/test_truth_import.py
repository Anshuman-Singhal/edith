"""The companion and ML runtime never see simulator ground truth (PLAN §4.4).

- companion/ and ml/ runtime code never imports edith_sim (ground truth lives there; the gt
  detector talks to the companion over UDP like a real detector would).
- companion runtime code never names FrameTruth / truth files.
Tests are exempt: they may score against truth.
"""

import ast
from pathlib import Path

from _repo import ROOT

RUNTIME = [ROOT / "companion" / "edith_companion", ROOT / "ml" / "edith_ml"]
TRUTH_WORDS = ("frametruth", "frame_truth", "truth.jsonl", "gt_truth")


def _py_files():
    for base in RUNTIME:
        if base.is_dir():
            yield from (p for p in base.rglob("*.py") if "tests" not in p.parts)


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module":
            if node.args and isinstance(node.args[0], ast.Constant):
                yield str(node.args[0].value)


def test_runtime_never_imports_edith_sim():
    bad = []
    for p in _py_files():
        tree = ast.parse(p.read_text(), filename=str(p))
        for mod in _imports(tree):
            if mod == "edith_sim" or mod.startswith("edith_sim."):
                bad.append(f"{p.relative_to(ROOT)} imports {mod}")
    assert not bad, "\n".join(bad)


def test_companion_never_reads_truth():
    bad = []
    for p in _py_files():
        if "companion" not in p.parts:
            continue
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value.lower()
                if any(w in v for w in TRUTH_WORDS):
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} {node.value!r}")
    assert not bad, "\n".join(bad)


def test_lint_sees_planted_violation(tmp_path: Path):
    src = "import edith_sim.mover\nfrom edith_sim import gt\n"
    mods = list(_imports(ast.parse(src)))
    assert mods == ["edith_sim.mover", "edith_sim"]
