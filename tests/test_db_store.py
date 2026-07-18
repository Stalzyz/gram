import os
import tempfile

from exporter.db import ResultStore


def make_store():
    tmp_dir = tempfile.mkdtemp()
    return ResultStore(os.path.join(tmp_dir, "test.sqlite3"))


def test_seed_and_pending():
    store = make_store()
    store.seed_pending(["alice", "bob", "carol"])
    pending = store.pending_usernames()
    assert set(pending) == {"alice", "bob", "carol"}


def test_mark_success_removes_from_pending():
    store = make_store()
    store.seed_pending(["alice", "bob"])
    store.mark_success("alice", {"Instagram Username": "alice"})
    pending = store.pending_usernames()
    assert pending == ["bob"]


def test_mark_failed_keeps_in_pending_for_retry():
    store = make_store()
    store.seed_pending(["alice"])
    store.mark_failed("alice", "timeout")
    assert "alice" in store.pending_usernames()
    stats = store.stats()
    assert stats["failed"] == 1


def test_resume_skips_already_successful():
    store = make_store()
    store.seed_pending(["alice", "bob"])
    store.mark_success("alice", {"Instagram Username": "alice"})

    # Simulate a fresh run seeding the same usernames again (resume=True path)
    store.seed_pending(["alice", "bob"])
    pending = store.pending_usernames()
    assert pending == ["bob"]


def test_all_results_only_returns_successes():
    store = make_store()
    store.seed_pending(["alice", "bob"])
    store.mark_success("alice", {"Instagram Username": "alice"})
    store.mark_failed("bob", "error")
    results = store.all_results()
    assert len(results) == 1
    assert results[0]["Instagram Username"] == "alice"


def test_stats_counts():
    store = make_store()
    store.seed_pending(["a", "b", "c"])
    store.mark_success("a", {"Instagram Username": "a"})
    store.mark_failed("b", "err")
    stats = store.stats()
    assert stats["total"] == 3
    assert stats["success"] == 1
    assert stats["failed"] == 1
    assert stats["pending"] == 1
