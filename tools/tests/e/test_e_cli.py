from edith_tools.commands import e


def test_goal2_is_pending_d9():
    assert e.main(["bench", "goal2"]) == 2
