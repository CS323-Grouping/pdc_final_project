import pytest

from network.telemetry import LatencyWindow


def test_latency_window_mean_min_max():
    w = LatencyWindow(maxlen=16)
    assert w.mean() is None
    for x in (10.0, 20.0, 30.0):
        w.add(x)
    assert w.mean() == 20.0
    assert w.minimum() == 10.0
    assert w.maximum() == 30.0


def test_latency_window_stdev():
    w = LatencyWindow(maxlen=16)
    w.add(10.0)
    assert w.stdev() is None
    w.add(30.0)
    s = w.stdev()
    assert s is not None
    assert s == pytest.approx(10.0, rel=0.01)


def test_latency_window_percentiles():
    w = LatencyWindow(maxlen=32)
    for i in range(1, 21):
        w.add(float(i))
    p50 = w.p50()
    p95 = w.p95()
    assert p50 is not None and p95 is not None
    assert p50 <= p95


def test_latency_window_bounded():
    w = LatencyWindow(maxlen=4)
    for i in range(10):
        w.add(float(i))
    assert w.count() == 4
