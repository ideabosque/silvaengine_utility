import math
from decimal import Decimal

import pytest

from silvaengine_utility.json_handler import HighPerformanceJSONHandler
from silvaengine_utility.utility import Utility

pendulum = pytest.importorskip("pendulum")

try:
    import pytest_benchmark  # noqa: F401

    HAS_BENCHMARK = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_BENCHMARK = False


def test_high_performance_json_handler_round_trip_decimal_and_datetime():
    handler = HighPerformanceJSONHandler()
    payload = {
        "total": Decimal("42.10"),
        "created_at": pendulum.datetime(2024, 1, 1, 12, 0, tz="UTC"),
    }

    encoded = handler.dumps(payload)
    assert isinstance(encoded, str)

    decoded = handler.loads(encoded)
    assert decoded["total"] == Decimal("42.10")
    assert decoded["created_at"].isoformat() == "2024-01-01T12:00:00+00:00"


def test_json_performance_metrics_snapshot_and_reset():
    Utility.reset_json_performance_metrics()
    Utility.json_dumps({"message": "hello"})
    Utility.json_loads('{"answer": 42}')

    stats = Utility.json_performance_snapshot()
    assert stats["json_dumps"]["count"] >= 1
    assert math.isclose(stats["json_dumps"]["errors"], 0.0)

    Utility.reset_json_performance_metrics()
    assert Utility.json_performance_snapshot() == {}


@pytest.mark.skipif(not HAS_BENCHMARK, reason="pytest-benchmark not installed")
@pytest.mark.benchmark(group="json")
def test_high_performance_json_handler_benchmark(benchmark):
    handler = HighPerformanceJSONHandler()
    payload = {
        "items": [
            {"id": i, "value": Decimal("1.25"), "active": i % 2 == 0}
            for i in range(10)
        ],
        "timestamp": "2024-01-01T00:00:00Z",
    }

    result = benchmark(handler.dumps, payload)
    assert isinstance(result, str)
