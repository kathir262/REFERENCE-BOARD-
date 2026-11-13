"""Timed classes, memory mode and practice history."""
from datetime import date, timedelta

from refpad.core import history
from refpad.core.store import Pose, State
from refpad.core.timer import CLASSES, PracticeTimer, parse_plan, plan_text


def test_class_plans():
    assert parse_plan("10x30s, 5x1m") == [30] * 10 + [60] * 5
    assert parse_plan("3 x 90s; 2x1.5m") == [90] * 5
    assert parse_plan("5x2") == [120] * 5           # small numbers mean minutes
    assert parse_plan("4x45") == [45] * 4           # big numbers mean seconds
    for bad in ("", "abc", "2x3h", "0x30s", "500x30s", "3x2s"):
        assert parse_plan(bad) is None
    for name, text in CLASSES:
        minutes = int(name.split("·")[1].split()[0])
        assert sum(parse_plan(text)) == minutes * 60
    assert plan_text([30, 30, 60, 300]) == "2×30s, 1×1m, 1×5m"


def _timer(app, n=4):
    st = State()
    st.items.clear()
    st.set_practice([Pose("file", f"C:/pics/{i}.jpg") for i in range(n)])
    return st, PracticeTimer(st)


def test_class_runs_and_finishes(app):
    history.clear()
    st, tm = _timer(app)
    messages = []
    st.status.connect(lambda t, b, u: messages.append(t))
    tm.start_class([30, 60, 90], "Test class")
    assert tm.total_ms == 30000 and tm.running
    for expected_pos in (1, 2):
        tm._pose_ms, tm.remaining_ms = tm.total_ms, 0
        tm._clock.restart()
        tm._on_tick()
        assert tm.plan_pos == expected_pos and st.practice_index == expected_pos
    assert tm.total_ms == 90000
    tm._pose_ms, tm.remaining_ms = 90000, 0
    tm._clock.restart()
    tm._on_tick()
    assert tm.plan is None and not tm.running
    assert any("Test class finished" in m for m in messages)
    assert history.summary()["today"]["poses"] == 3


def test_memory_mode_hides_then_moves_on(app):
    st, tm = _timer(app)
    tm.set_memory(True)
    tm.start()
    tm._pose_ms, tm.remaining_ms = tm.total_ms, 0
    tm._clock.restart()
    tm._on_tick()
    assert tm.hidden and st.practice_index == 0        # time's up: the pose hides
    assert tm.remaining_ms > 0
    tm.remaining_ms = 0
    tm._clock.restart()
    tm._on_tick()
    assert not tm.hidden and st.practice_index == 1    # drawing time over: next pose
    tm.set_memory(False)


def test_short_glances_dont_count(app):
    history.clear()
    st, tm = _timer(app)
    tm.start()
    tm._pose_ms = 2000            # skipped after 2 seconds
    tm.advance()
    assert history.summary()["today"]["poses"] == 0


def test_history_streak():
    history.clear()
    today = date.today()
    for n in (0, 1, 2, 4):
        history.add(120, today - timedelta(days=n))
    s = history.summary(today)
    assert s["streak"] == 3 and s["today"]["poses"] == 1
    assert s["week"]["poses"] == 4 and s["week"]["seconds"] == 480
    assert len(s["days"]) == 14 and s["days"][-1][0] == today
    history.clear()
