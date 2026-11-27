"""Every tracked file has exactly one owning workstream (PLAN §5.1, C73)."""

from _repo import load_owners, match, owners_of, tracked_files


def test_owners_cover_every_file_exactly_once():
    ws = load_owners()
    zero, many = [], []
    for f in tracked_files():
        o = owners_of(f, ws)
        if not o:
            zero.append(f)
        elif len(o) > 1:
            many.append(f"{f} -> {','.join(o)}")
    assert not zero, "files with no owner (add to docs/OWNERS.yaml):\n" + "\n".join(zero)
    assert not many, "files with two owners:\n" + "\n".join(many)


def test_owners_schema():
    ws = load_owners()
    assert set(ws) == set("ABCDEFGH")
    for name, spec in ws.items():
        assert spec.get("owner"), name
        assert spec.get("paths"), name
        assert f"tools/edith_tools/commands/{name.lower()}.py" in spec["paths"] or name == "A"


def test_matcher():
    assert match("common/edith_common/px4/a.py", "common/**")
    assert match("companion/tests/voice/x/test_a.py", "companion/tests/voice/**")
    assert not match("companion/tests_voice.py", "companion/tests/**")
