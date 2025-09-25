# Migration Guide

## Overview

This guide documents the changes introduced in SilvaEngine Utility v0.0.6, focusing on the JSON performance overhaul and the AWS execution workflow updates. Existing consumers should review the breaking-surface analysis below and follow the step-by-step checklist when upgrading from v0.0.5 or earlier.

## Key Changes

- JSON serialisation now routes through `silvaengine_utility.json_handler.HighPerformanceJSONHandler`, which uses `orjson` and applies depth-limited SQLAlchemy serialisation.
- ISO-like datetime strings are parsed via Pendulum with LRU caching. python-dateutil is no longer used at runtime.
- The AWS helper `Utility.invoke_funct_on_aws_lambda` introduces a new `execute_mode` argument. The legacy `test_mode` flag still works but emits a `DeprecationWarning` and is ignored when `execute_mode` is present.
- JSON dumps and loads are monitored through `JSONPerformanceMonitor`. Aggregated metrics are available via `Utility.json_performance_snapshot()`.
- Repository packaging is now managed exclusively through `pyproject.toml`; `setup.py` is retained only as a thin shim.

## Upgrade Checklist

1. **Update Dependencies**
   - Ensure your environment installs the project with the `dev` extras for testing (`python -m pip install -e .[dev]`).
   - Verify that `orjson` and `pendulum` wheels are available on your deployment platform.

2. **Adjust AWS Integrations**
   - Replace references to `test_mode` with `execute_mode`. Valid values are `local_for_all`, `local_for_sqs`, or `local_for_aws_lambda`.
   - Review warning logs; remove any lingering `test_mode` usage to silence deprecation notices.

3. **Review Serialisation Contracts**
   - If your payloads previously relied on python-dateutil objects, confirm that Pendulum instances meet consumer expectations (they remain `datetime` compatible).
   - Validate custom SQLAlchemy models against the new depth limit. Override behaviour by supplying a custom default serializer if deeper traversals are required.

4. **Adopt Monitoring Hooks**
   - Use `Utility.json_performance_snapshot()` during load testing to capture aggregate counts and timings.
   - Reset metrics between scenarios with `Utility.reset_json_performance_metrics()`.

5. **Re-run Test Suites**
   - Execute `pytest --cov=silvaengine_utility --cov-report=term-missing` to confirm coverage goals and inspect the new benchmark group output.

## Compatibility Notes

- The new JSON handler gracefully falls back to the standard library when `orjson` is unavailable, but performance improvements will be limited.
- Existing AWS Lambda invocation paths remain unchanged when `execute_mode` is `None`.
- Pendulum returns timezone-aware `DateTime` instances; ensure downstream systems handle offsets explicitly.

For additional details, consult `API_DOCUMENTATION.md` and the updated `PERFORMANCE_IMPROVEMENT_PLAN.md`.
