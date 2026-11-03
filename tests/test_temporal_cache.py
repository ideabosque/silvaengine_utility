"""Mutation replay must return GraphQL-compatible temporal values."""

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import graphene

from silvaengine_utility.idempotency import IdempotencyRepository, idempotent_mutation
from silvaengine_utility.idempotency_codec import decode_result, encode_result


def test_typed_nested_roundtrip_preserves_dates_and_plain_strings():
    value = {
        "updated_at": datetime(2026, 11, 2, 9, 1, tzinfo=timezone.utc),
        "nested": [{"day": date(2026, 11, 2), "text": "2026-11-02T09:01:00+00:00"}],
    }
    restored = decode_result(json.loads(json.dumps(encode_result(value))))
    assert restored == value
    assert isinstance(restored["nested"][0]["text"], str)


def test_legacy_timestamp_fields_restore_but_arbitrary_text_does_not():
    value = {
        "updated_at": "2026-11-02 09:01:00+00:00",
        "createdAt": "2026-11-02T09:01:00Z",
        "content": "2026-11-02T09:01:00Z",
        "invalid_at": "not a date",
    }
    restored = decode_result(value)
    assert isinstance(restored["updated_at"], datetime)
    assert isinstance(restored["createdAt"], datetime)
    assert restored["content"] == value["content"]
    assert restored["invalid_at"] == "not a date"


def test_mutation_replay_serializes_and_does_not_write_again():
    class Item(graphene.ObjectType):
        id = graphene.ID()
        updated_at = graphene.DateTime()

    cached = decode_result(
        {"id": "original", "updated_at": "2026-11-02 09:01:00+00:00"}
    )
    writes = []

    @idempotent_mutation("CreateItem")
    def mutate(root, info, idempotency_key):
        writes.append(True)
        return {}

    with patch("silvaengine_utility.idempotency.check_and_store", return_value=cached):
        result = mutate(None, SimpleNamespace(context={}), idempotency_key="same-key")
    assert not writes
    assert (
        graphene.DateTime.serialize(result["updated_at"]) == "2026-11-02T09:01:00+00:00"
    )


def test_repository_decode_restores_cached_result():
    from unittest.mock import MagicMock

    pool = MagicMock()
    row = {
        "idempotency_key": "key",
        "mutation_name": "CreateMemory",
        "result_payload": {"updated_at": "2026-11-02 09:01:00+00:00"},
    }
    pool.return_value.connection.return_value.__enter__.return_value.execute.return_value.mappings.return_value.first.return_value = (
        row
    )
    with patch("silvaengine_utility.idempotency.ConnectionPoolManager", pool):
        result = IdempotencyRepository.find("tenant", "key")
    assert isinstance(result["result"]["updated_at"], datetime)
