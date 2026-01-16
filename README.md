# SilvaEngine Utility

A high-performance utility library providing JSON serialization, AWS integration, and utility functions with comprehensive performance monitoring.

## Features

- **High-Performance JSON Handling**: Unified JSON serialization with automatic fallback from orjson to standard library
- **SQLAlchemy Integration**: Smart serialization of SQLAlchemy models with relationship handling and circular reference prevention
- **Hybrid Cache System**: Redis-primary caching with disk fallback, optimized for AWS Lambda serverless environments
- **AWS Integration**: Simplified Lambda invocation, SQS messaging, and GraphQL query execution
- **Performance Monitoring**: Built-in performance tracking for JSON operations with detailed metrics
- **Datetime Handling**: Advanced datetime parsing with Pendulum integration and caching
- **Type Safety**: Comprehensive type handling for Decimal, datetime, bytes, and custom objects

## Installation

```bash
# Basic installation
pip install silvaengine-utility

# With performance optimizations (recommended)
pip install silvaengine-utility[performance]

# For development
pip install silvaengine-utility[dev]

# All features
pip install silvaengine-utility[all]
```

## Quick Start

### JSON Operations

```python
from silvaengine_utility import Serializer

# Serialize data with optimized performance
data = {"user": "john", "timestamp": datetime.now(), "amount": Decimal("100.50")}
json_string = Serializer.json_dumps(data)

# Deserialize with automatic type conversion
parsed_data = Serializer.json_loads(json_string)

# Performance monitoring
Serializer.reset_json_performance_stats()
# ... perform operations ...
stats = Serializer.get_json_performance_stats()
print(f"Operations: {stats['json_dumps']['count']}")
```

### Cache Operations

```python
from silvaengine_utility import hybrid_cache, authorization_cache, method_cache

# Basic function caching
@hybrid_cache(ttl=300)
def expensive_function(param):
    return complex_calculation(param)

# Authorization caching for Lambda functions
@authorization_cache(ttl=300)
def _dynamic_authorization(self, event, context, action):
    return authorize_user(event, action)

# Method caching with custom cache names
@method_cache(ttl=1800, cache_name="settings")
def get_settings(setting_key):
    return settings_lookup(setting_key)
```

### AWS Lambda Integration

```python
# Invoke AWS Lambda function
result = Utility.invoke_funct_on_aws_lambda(
    logger=logger,
    endpoint_id="my-endpoint",
    funct="process_data",
    params={"data": "value"},
    execute_mode="local_for_all",  # For local testing
    aws_lambda=lambda_client
)

# Execute GraphQL queries
response = Utility.execute_graphql_query(
    logger=logger,
    endpoint_id="graphql-endpoint",
    funct="execute_query",
    query="{ users { id name } }",
    variables={"limit": 10}
)
```

### Utility Functions

```python
# Network utilities
is_in_subnet = Utility.in_subnet("192.168.1.100", "192.168.1.0/24")

# Dynamic imports
func = Utility.import_dynamically(
    module_name="mymodule",
    function_name="myfunction",
    class_name="MyClass"
)

# Database session creation
session = Utility.create_database_session({
    "user": "username",
    "password": "password",
    "host": "localhost",
    "port": 3306,
    "schema": "mydb"
})
```

## Core Components

### JSON Handler

The `HighPerformanceJSONHandler` provides:

- **Unified Serialization**: Single handler for all object types
- **Performance Optimization**: Uses orjson when available, falls back gracefully
- **SQLAlchemy Support**: Deep serialization of models with relationship handling
- **Type Intelligence**: Smart handling of Decimal (int for whole numbers, float for decimals)
- **Datetime Consistency**: ISO format serialization with automatic parsing
- **Depth Control**: Prevents infinite recursion with configurable depth limits
- **Performance Monitoring**: Automatic tracking of all operations

### Performance Monitor

Built-in monitoring provides:

```python
# Get comprehensive statistics
stats = Utility.get_json_performance_stats()
# {
#   "json_dumps": {
#     "count": 1250,
#     "total_time": 0.125,
#     "avg_time": 0.0001,
#     "errors": 0
#   },
#   "json_loads": { ... }
# }

# Get human-readable summary
summary = Utility.get_json_performance_summary()

# Reset metrics
Utility.reset_json_performance_stats()
```

### AWS Integration

#### Execution Modes

- `"local_for_all"`: Execute all functions locally
- `"local_for_sqs"`: Execute SQS functions locally, others on AWS
- `"local_for_aws_lambda"`: Execute Lambda functions locally when possible

#### SQS Integration

```python
# Send message to SQS queue
Utility.invoke_funct_on_aws_lambda(
    logger=logger,
    endpoint_id="endpoint",
    funct="process",
    params={"data": "value"},
    message_group_id="group-1",
    task_queue=sqs_queue
)
```

### Datetime Handling

Advanced datetime processing with caching:

```python
from silvaengine_utility.datetime_handler import PendulumDateTimeHandler

# Parse ISO datetime strings
dt = PendulumDateTimeHandler.parse_datetime_in_json("2023-01-01T12:00:00Z")

# Get library info
info = Utility.get_library_info()
# {
#   "json": {"library": "orjson", "high_performance": true},
#   "datetime": {"library": "pendulum", "version": "2.1.0"}
# }
```

## Configuration

### Optional Dependencies

- **orjson**: High-performance JSON serialization (3-5x faster)
- **pendulum**: Advanced datetime handling with caching
- **graphql-core**: GraphQL query support

### Environment Variables

The library automatically detects and uses available performance libraries:

- If `orjson` is available: Uses for high-performance serialization
- If `pendulum` is available: Uses for datetime parsing with caching
- Falls back to standard library gracefully

## API Reference

### Utility Class

#### JSON Operations
- `json_dumps(data, **kwargs)` - Serialize to JSON with performance monitoring
- `json_loads(data, parser_number=True, validate=True)` - Parse JSON with type conversion
- `is_json_string(string)` - Validate JSON string

#### Performance Monitoring
- `get_json_performance_stats()` - Get detailed performance metrics
- `get_json_performance_summary()` - Get human-readable summary
- `reset_json_performance_stats()` - Reset performance counters
- `get_library_info()` - Get information about loaded performance libraries

#### AWS Integration
- `invoke_funct_on_aws_lambda(...)` - Invoke Lambda with local fallback support
- `invoke_funct_on_local(...)` - Execute configured local functions
- `execute_graphql_query(...)` - Execute GraphQL queries with normalization
- `fetch_graphql_schema(...)` - Fetch and parse GraphQL schemas

#### Utilities
- `in_subnet(ip, subnet)` - Check IP subnet membership
- `import_dynamically(...)` - Dynamic module/function imports
- `create_database_session(settings)` - Create SQLAlchemy database sessions
- `convert_camel_to_underscore(text)` - Convert camelCase to snake_case
- `format_error(error)` - Format GraphQL and generic errors

## Hybrid Cache System

A high-performance caching system optimized for AWS Lambda serverless environments with Redis primary cache and disk fallback.

### Cache Features

- **Hybrid Architecture**: Redis primary with automatic disk fallback
- **Serverless Optimized**: Designed for AWS Lambda cold/warm starts
- **Decorator-Based**: Easy-to-use decorators for common caching patterns
- **Multiple Cache Types**: Specialized decorators for different use cases
- **Graceful Degradation**: Works even when Redis is unavailable
- **Performance Monitoring**: Built-in cache statistics and management

### Cache Usage

#### Basic Function Caching

```python
from silvaengine_utility import hybrid_cache

@hybrid_cache(ttl=300)  # 5 minutes
def expensive_calculation(x: int, y: int) -> int:
    # Expensive operation
    return x * y + complex_computation()

# First call - executes function
result1 = expensive_calculation(5, 10)

# Second call - returns cached result
result2 = expensive_calculation(5, 10)  # Fast!
```

#### Authorization Caching

```python
from silvaengine_utility import authorization_cache

class AuthHandler:
    @authorization_cache(ttl=300)
    def _dynamic_authorization(self, event, context, action):
        # Expensive authorization logic
        return authorize_user(event, action)
```

#### Method Caching (Class Methods)

```python
from silvaengine_utility import method_cache

class DataService:
    @method_cache(ttl=1800, cache_name="settings")  # 30 min for settings
    def get_settings(self, setting_key: str) -> dict:
        return expensive_settings_lookup(setting_key)

    @method_cache(ttl=600, cache_name="database")   # 10 min for DB queries
    def get_user_data(self, user_id: str) -> dict:
        return database.query(user_id)

    @method_cache(ttl=300, cache_name="validation") # 5 min for validation
    def validate_permission(self, user_id: str, action: str) -> bool:
        return expensive_permission_check(user_id, action)
```

### Cache Configuration

#### Environment Variables

```bash
# Redis Configuration (optional)
REDIS_HOST=your-redis-host.com
REDIS_PORT=6379
REDIS_PASSWORD=your-password
REDIS_DB=0

# Cache Directory
CACHE_DIR=/tmp/silvaengine_cache
```

#### Cache Names

Different cache instances for different use cases:

- `default` - General purpose caching
- `authorization` - Authorization results
- `method` - General method caching (default)
- `settings` - Configuration data (via method_cache)
- `database` - Database query results (via method_cache)
- `validation` - Permission validation (via method_cache)

### Cache Management

```python
# Clear specific function cache
my_function.cache_clear()

# Delete specific cache entry
my_function.cache_delete(arg1, arg2)

# Get cache statistics
stats = my_function.cache_stats()
print(stats)
# Output: {
#   'cache_name': 'default',
#   'redis_available': True,
#   'disk_available': True,
#   'disk_path': '/tmp/silvaengine_cache/default'
# }
```

### Performance Benefits

#### Lambda Cold Start Optimization

```python
# Without caching
def get_settings(setting_id):
    return expensive_db_lookup(setting_id)  # 200ms every time

# With caching
@method_cache(ttl=1800, cache_name="settings")  # 30 minutes
def get_settings(setting_id):
    return expensive_db_lookup(setting_id)  # 200ms first time, ~1ms after
```

#### Redis + Disk Hybrid Performance

| Scenario | Redis | Disk | No Cache |
|----------|-------|------|----------|
| Cold Start | N/A | ~5ms | 200ms |
| Warm Start (Redis) | ~1ms | N/A | 200ms |
| Warm Start (Disk) | N/A | ~3ms | 200ms |
| Redis Down | N/A | ~3ms | 200ms |

This integration can improve Lambda performance by 80-95% for cached operations while maintaining full functionality when caches are unavailable.

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests with coverage
pytest --cov=silvaengine_utility --cov-report=term-missing

# Run performance benchmarks
pytest -m performance
```

### Code Quality

```bash
# Format code
black silvaengine_utility/

# Lint code
flake8 silvaengine_utility/

# Type checking
mypy silvaengine_utility/
```

## Performance

### Benchmarks

With orjson enabled:
- JSON serialization: 3-5x faster than standard library
- JSON deserialization: 2-3x faster than standard library
- SQLAlchemy model serialization: Optimized with depth limiting

### Memory Usage

- Efficient SQLAlchemy relationship handling
- LRU caching for datetime parsing
- Depth-limited recursion prevents memory exhaustion

## Migration from v0.0.5

The library maintains backward compatibility while providing enhanced performance:

1. **JSON Operations**: Existing `json_dumps`/`json_loads` calls work unchanged
2. **AWS Integration**: Replace `test_mode` with `execute_mode` (old parameter still works with deprecation warning)
3. **Performance**: Install `[performance]` extras for optimal speed
4. **Monitoring**: New performance monitoring is automatically enabled

## License

MIT License - see LICENSE file for details.

## Support

- **Repository**: https://github.com/silvaengine/silvaengine-utility
- **Issues**: https://github.com/silvaengine/silvaengine-utility/issues
- **Documentation**: https://silvaengine-utility.readthedocs.io
