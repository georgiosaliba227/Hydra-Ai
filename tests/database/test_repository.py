from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from database.repository import BeverageRepository, IdempotencyConflict, StorageUnavailable


def record(identifier=None, consumed_at="2026-10-26T14:00:00Z"):
    return {
        "id": identifier or str(uuid4()), "revision": 1,
        "category": "coffee", "consumed_ml": 250,
        "consumed_at": consumed_at, "timezone": "America/New_York",
        "source": "manual", "nutrition": None,
        "provenance": ["confirmed-manual"],
        "contribution": {"beverage_total_ml": 250, "estimated_water_ml": None},
    }


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "beverages.sqlite3"
        self.repo = BeverageRepository(self.path)

    def test_restart_preserves_response_and_replay_identity(self):
        original = record()
        self.assertEqual(self.repo.create("a", "key", "hash", original), (original, True))
        reopened = BeverageRepository(self.path)
        self.assertEqual(reopened.list_all("a"), [original])
        self.assertEqual(reopened.create("a", "key", "hash", record()), (original, False))
        self.assertEqual(reopened.list_all("a"), [original])

    def test_conflict_never_replaces_original(self):
        original = record()
        self.repo.create("a", "key", "hash", original)
        with self.assertRaises(IdempotencyConflict):
            self.repo.create("a", "key", "changed", record())
        self.assertEqual(self.repo.list_all("a"), [original])

    def test_owner_scope_and_same_key_for_different_owners(self):
        a, b = record(), record()
        self.repo.create("a", "shared", "a", a)
        self.repo.create("b", "shared", "b", b)
        self.assertEqual(self.repo.list_all("a"), [a])
        self.assertEqual(self.repo.list_all("b"), [b])
        self.assertEqual(self.repo.list_all("unknown"), [])

    def test_concurrent_retries_commit_exactly_once(self):
        def create(_):
            return BeverageRepository(self.path).create("a", "same", "hash", record())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(24)))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({value["id"] for value, _ in results}), 1)
        self.assertEqual(len(self.repo.list_all("a")), 1)

    def test_concurrent_conflicting_requests_keep_one_winner(self):
        def create(index):
            try:
                return self.repo.create("a", "same", str(index), record())
            except IdempotencyConflict:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(16)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(len(self.repo.list_all("a")), 1)

    def test_duplicate_record_id_rolls_back_key_reservation(self):
        first = record()
        self.repo.create("a", "first", "hash", first)
        with self.assertRaises(StorageUnavailable):
            self.repo.create("a", "second", "hash2", first)
        second = record()
        self.assertEqual(self.repo.create("a", "second", "hash2", second), (second, True))
        self.assertEqual(len(self.repo.list_all("a")), 2)

    def test_normalized_time_order_and_id_tiebreak(self):
        # .1 seconds sorts after zero seconds regardless of RFC3339 spelling.
        earlier = record("00000000-0000-0000-0000-000000000001")
        later = record("00000000-0000-0000-0000-000000000002", "2026-10-26T10:00:00.1-04:00")
        tie = record("00000000-0000-0000-0000-000000000003", "2026-10-26T14:00:00.100000Z")
        for index, value in enumerate((tie, earlier, later)):
            self.repo.create("a", str(index), str(index), value)
        self.assertEqual(self.repo.list_all("a"), [tie, later, earlier])

    def test_nonfinite_payload_is_not_written(self):
        value = record()
        value["contribution"]["beverage_total_ml"] = float("nan")
        with self.assertRaises(ValueError):
            self.repo.create("a", "k", "h", value)
        self.assertEqual(self.repo.list_all("a"), [])

    def test_corrupted_json_fails_closed_without_leaking_payload(self):
        value = record()
        self.repo.create("a", "k", "h", value)
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE beverages SET record_json=?", ('sensitive-invalid-json',))
        with self.assertRaises(StorageUnavailable) as caught:
            self.repo.list_all("a")
        self.assertNotIn("sensitive", str(caught.exception))
        with self.assertRaises(StorageUnavailable):
            self.repo.create("a", "k", "h", record())

    def test_nonfinite_stored_json_fails_closed(self):
        self.repo.create("a", "k", "h", record())
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE beverages SET record_json=?", ('{"consumed_ml":NaN}',))
        with self.assertRaises(StorageUnavailable):
            self.repo.list_all("a")

    def test_invalid_path_and_database_errors_are_sanitized(self):
        with self.assertRaises(StorageUnavailable) as caught:
            BeverageRepository(Path(self.temp.name))
        self.assertNotIn(self.temp.name, str(caught.exception))
        self.path.unlink()
        self.path.write_text("not a sqlite database")
        with self.assertRaises(StorageUnavailable):
            self.repo.list_all("a")

    def test_memory_database_is_rejected(self):
        with self.assertRaises(ValueError):
            BeverageRepository(":memory:")

    def test_new_file_is_private(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
