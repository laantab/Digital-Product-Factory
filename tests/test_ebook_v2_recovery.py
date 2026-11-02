"""Failure injection for the reconstructed engine; no provider calls."""
from concurrent.futures import ThreadPoolExecutor
import os
import time
import pytest
from services.ebook_v2.recovery import Store, CorruptCheckpoint, InputConflict
from services.ebook_v2.worker import Worker, Policy, Repairable


def echo(payload, repair):
    return {"value": payload.get("value",1)}


def valid(output):
    return output.get("value") == 1


def bad(payload, repair):
    return {"value": 0}


def repair_once(payload, repair):
    if not repair:
        raise Repairable("BROKEN", {"value":0,"feedback":"Use the verified repair"})
    assert payload["_recovery"]["feedback"] == "Use the verified repair"
    return {"value":1}


def hangs(payload, repair):
    time.sleep(10)
    return {"value":1}


def validator_hangs(output):
    time.sleep(10)
    return True


def crashes(payload, repair):
    os._exit(4)


def unknown_error(payload, repair):
    raise RuntimeError("PRIVATE CONTENT MUST NOT BE LOGGED")


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "recovery.sqlite")
    result.initialize()
    return result


def task(store, key="request-1", **kwargs):
    return store.enqueue("alice",key,"chapter","chapter-1",{"value":1},**kwargs)


def test_restart_reuses_verified_output_without_work(store):
    unit = task(store)
    worker = Worker(store,{"chapter":Policy("chapter-1",echo,valid)})
    assert worker.run_once("alice",unit)
    restarted = Store(store.path)
    assert restarted.get("alice",unit)["output"] == {"value":1}
    assert not Worker(restarted,worker.policies).run_once("alice",unit)
    assert restarted.get("alice",unit)["attempts"] == 1


def test_deduplication_and_input_conflict(store):
    unit = task(store)
    assert task(store) == unit
    with pytest.raises(InputConflict):
        store.enqueue("alice","request-1","chapter","chapter-1",{"value":2})
    with pytest.raises(InputConflict):
        store.enqueue("alice","request-1","chapter","chapter-2",{"value":1})


def test_tenants_are_isolated_including_dependencies(store):
    unit = task(store)
    other = store.enqueue("bob","request-1","chapter","chapter-1",{"value":1})
    assert unit != other
    with pytest.raises(LookupError):
        store.get("bob",unit)
    with pytest.raises(LookupError):
        store.enqueue("bob","next","chapter","chapter-1",{},parents=[unit])


def test_prerequisite_barrier_and_verified_parent(store):
    parent = task(store)
    child = task(store,"child",parents=[parent])
    assert store.claim("alice",child,10) is None
    claim = store.claim("alice",parent,10)
    assert store.complete("alice",parent,claim["token"],{"value":1})
    assert store.claim("alice",child,10)


def test_concurrent_claim_has_one_winner(store):
    unit = task(store)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: Store(store.path).claim("alice",unit,10),range(8)))
    assert sum(result is not None for result in results) == 1
    assert store.get("alice",unit)["attempts"] == 1


def test_expired_worker_cannot_commit_fail_or_teach(store):
    clock = [1000.125]
    store.clock = lambda:clock[0]
    unit = task(store)
    first = store.claim("alice",unit,.25)
    clock[0] += .3
    second = store.claim("alice",unit,10)
    assert not store.complete("alice",unit,first["token"],{"value":1})
    assert not store.fail("alice",unit,first["token"],"BROKEN","repair")
    assert store.complete("alice",unit,second["token"],{"value":1})
    assert store.get("alice",unit)["attempts"] == 2


def test_repeated_crashed_workers_exhaust_attempt_budget(store):
    clock = [1000.0]; store.clock = lambda:clock[0]
    unit = task(store,max_attempts=2)
    assert store.claim("alice",unit,1)
    clock[0] += 2
    assert store.claim("alice",unit,1)
    clock[0] += 2
    assert store.claim("alice",unit,1) is None
    assert store.get("alice",unit)["state"] == "NEEDS_ATTENTION"


@pytest.mark.parametrize("column,value",[("payload",'{"value":9}'),("output",'{"value":9}')])
def test_corrupt_checkpoint_stops_before_reuse(store,column,value):
    unit = task(store)
    claim = store.claim("alice",unit,10)
    store.complete("alice",unit,claim["token"],{"value":1})
    with store.transaction() as conn:
        conn.execute(f"UPDATE ebook_v2_units SET {column}=? WHERE id=?",(value,unit))
    with pytest.raises(CorruptCheckpoint):
        store.get("alice",unit)


def test_bad_output_never_completes_or_teaches(store):
    unit = task(store,max_attempts=2)
    worker = Worker(store,{"chapter":Policy("chapter-1",bad,valid,{"VALIDATION_FAILED":("fix",)},retry_delay=0)})
    worker.run_once("alice",unit); worker.run_once("alice",unit)
    result = store.get("alice",unit)
    assert result["state"] == "NEEDS_ATTENTION"
    assert result["output"] == {"value":0}
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM ebook_v2_lessons").fetchone()[0] == 0


def test_successful_repair_keeps_feedback_and_teaches_versioned_lesson(store):
    unit = task(store)
    policy = Policy("chapter-1",repair_once,valid,{"BROKEN":("safe_fix",)},retry_delay=0)
    worker = Worker(store,{"chapter":policy})
    worker.run_once("alice",unit)
    assert store.get("alice",unit)["state"] == "QUEUED"
    worker.run_once("alice",unit)
    assert store.get("alice",unit)["state"] == "COMPLETE"
    assert store.best_repair("chapter","chapter-1","BROKEN",("alternative","safe_fix")) == "safe_fix"
    assert store.best_repair("chapter","chapter-2","BROKEN",("alternative","safe_fix")) == "alternative"
    assert store.best_repair("chapter","chapter-1","BROKEN",("alternative",)) == "alternative"


def test_stored_repair_cannot_expand_error_allowlist(store):
    unit = task(store)
    claim = store.claim("alice",unit,10)
    store.fail("alice",unit,claim["token"],"BROKEN","not_approved",0)
    worker = Worker(store,{"chapter":Policy("chapter-1",echo,valid,{"OTHER":("not_approved",)})})
    assert not worker.run_once("alice",unit)
    assert store.get("alice",unit)["error"] == "UNAPPROVED_REPAIR"


def test_retry_delay_is_durable(store):
    clock = [1000.0]; store.clock = lambda:clock[0]
    unit = task(store); claim = store.claim("alice",unit,10)
    store.fail("alice",unit,claim["token"],"TIMEOUT","retry",20)
    restarted = Store(store.path,clock=store.clock)
    assert restarted.claim("alice",unit,10) is None
    clock[0] += 21
    assert restarted.claim("alice",unit,10)


@pytest.mark.parametrize("handler,validator,expected",[
    (hangs,valid,"TIMEOUT"),(echo,validator_hangs,"TIMEOUT"),
    (crashes,valid,"WORKER_EXITED"),(unknown_error,valid,"UNEXPECTED_ERROR")])
def test_child_failures_are_bounded_and_redacted(store,handler,validator,expected):
    unit = task(store)
    start = time.monotonic()
    Worker(store,{"chapter":Policy("chapter-1",handler,validator,timeout=1)}).run_once("alice",unit)
    assert time.monotonic()-start < 5
    result = store.get("alice",unit)
    assert result["error"] == expected
    assert result["state"] == "NEEDS_ATTENTION"
    assert "PRIVATE" not in str(result)


def test_policy_version_must_match_before_claim(store):
    unit = task(store)
    with pytest.raises(ValueError):
        Worker(store,{"chapter":Policy("chapter-2",echo,valid)}).run_once("alice",unit)
    assert store.get("alice",unit)["attempts"] == 0


@pytest.mark.parametrize("budget",[0,11,True])
def test_invalid_attempt_limits_rejected(store,budget):
    with pytest.raises(ValueError):
        task(store,max_attempts=budget)
