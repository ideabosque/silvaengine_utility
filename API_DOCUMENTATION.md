# API Documentation

## JSON Utilities

### `silvaengine_utility.json_handler.HighPerformanceJSONHandler`
- `dumps(obj, *, default=None) -> str`: Serialises payloads using `orjson`, supporting SQLAlchemy models, `Decimal`, `Enum`, `bytes`, and custom objects via a depth-aware walker.
- `loads(data, *, parse_decimal=True) -> Any`: Deserialises strings or bytes, returning `Decimal` instances for numeric values when `parse_decimal` is `True` and converting ISO-like strings to Pendulum datetimes.

### `silvaengine_utility.datetime_handler`
- `parse_datetime_in_json(value: str) -> Optional[pendulum.DateTime]`: Parses strings that resemble ISO 8601 timestamps.
- `ensure_datetime(value: str) -> Optional[pendulum.DateTime]`: Convenience wrapper for parsing with caching semantics.

### `silvaengine_utility.performance_monitor.JSONPerformanceMonitor`
- `monitor_json_operation(name)`: Decorator that captures duration, payload size, and error counts for decorated functions.
- `snapshot() -> Dict[str, Dict[str, float]]`: Returns current aggregate metrics.
- `reset()`: Clears stored metrics.

`Utility.json_performance_snapshot()` and `Utility.reset_json_performance_metrics()` expose the shared monitor instance to callers.

## AWS Helpers

### `Utility.invoke_funct_on_aws_lambda`
```
Utility.invoke_funct_on_aws_lambda(
    logger,
    endpoint_id,
    funct,
    params=None,
    setting=None,
    test_mode=None,
    execute_mode=None,
    aws_lambda=None,
    invocation_type="RequestResponse",
    message_group_id=None,
    task_queue=None,
)
```
- `execute_mode` controls local fallbacks (`local_for_all`, `local_for_sqs`, `local_for_aws_lambda`). `test_mode` is retained for compatibility but emits warnings.
- When `message_group_id` and `task_queue` are provided, the payload is routed to SQS without invoking Lambda.
- Remote invocations now serialise payloads through `HighPerformanceJSONHandler` before dispatch, ensuring consistent formatting and monitoring.

### Other Utilities
- `Utility.invoke_funct_on_local(...)`: Executes configured local functions, returning parsed results from the high-performance JSON stack.
- `Utility.execute_graphql_query(...)` and `Utility.fetch_graphql_schema(...)`: Accept the new `execute_mode` parameter and continue to return decoded responses.

## Monitoring Usage Example
```python
from silvaengine_utility.utility import Utility

Utility.reset_json_performance_metrics()
Utility.json_dumps({"event": "test"})
Utility.json_loads('{"event": "test"}')
print(Utility.json_performance_snapshot())
```

## Packaging

- Install development dependencies with `python -m pip install -e .[dev]`.
- Build distributables using `python -m build`; outputs are written to `dist/`.

Refer to `MIGRATION_GUIDE.md` for upgrade steps and `AGENTS.md` for contributor workflows.
