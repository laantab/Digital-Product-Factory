"""Spawned handlers and validators share a finite process deadline."""
from dataclasses import dataclass, field
import math
import multiprocessing
from .recovery import encode


class Repairable(Exception):
    def __init__(self, code, candidate=None):
        self.code, self.candidate = code, candidate
        super().__init__(code)


@dataclass(frozen=True)
class Policy:
    version: str
    handler: object
    validator: object
    repairs: dict = field(default_factory=dict)
    timeout: float = 60
    retry_delay: float = 1


def _child(pipe, policy, payload, repair):
    try:
        result = policy.handler(payload, repair)
        encode(result)
        message = {"output": result} if policy.validator(result) is True else {
            "code": "VALIDATION_FAILED", "candidate": result}
    except Repairable as error:
        message = {"code": error.code, "candidate": error.candidate}
    except BaseException:
        message = {"code": "UNEXPECTED_ERROR"}
    try:
        pipe.send(message)
    finally:
        pipe.close()


def execute(policy, payload, repair):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender,policy,payload,repair), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(policy.timeout):
            return {"code": "TIMEOUT"}
        try:
            return receiver.recv()
        except EOFError:
            return {"code": "WORKER_EXITED"}
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join(2)


class Worker:
    def __init__(self, store, policies):
        self.store, self.policies = store, policies
        for policy in policies.values():
            if (not policy.version or not math.isfinite(policy.timeout) or not 0 < policy.timeout <= 3490
                    or not math.isfinite(policy.retry_delay) or not 0 <= policy.retry_delay <= 3600):
                raise ValueError("Invalid worker policy")

    def run_once(self, owner, unit_id):
        prior = self.store.get(owner, unit_id)
        policy = self.policies.get(prior["stage"])
        if policy is None or policy.version != prior["policy"]:
            raise ValueError("Saved work requires its matching policy version")
        unit = self.store.claim(owner, unit_id, policy.timeout + 5)
        if unit is None:
            return False
        repair = unit["repair"]
        if repair and repair not in policy.repairs.get(unit["error"], ()):
            self.store.fail(owner,unit_id,unit["token"],"UNAPPROVED_REPAIR")
            return False
        payload = dict(unit["payload"])
        payload.pop("_recovery", None)
        if unit["output"] is not None:
            payload["_recovery"] = unit["output"]
        message = execute(policy,payload,repair)
        if "output" in message:
            return self.store.complete(owner,unit_id,unit["token"],message["output"])
        code = message.get("code", "UNEXPECTED_ERROR")
        allowed = policy.repairs.get(code, ())
        remedy = self.store.best_repair(unit["stage"],policy.version,code,allowed)
        return self.store.fail(owner,unit_id,unit["token"],code,remedy,
            min(3600,policy.retry_delay * 2 ** (unit["attempts"]-1)),message.get("candidate"))
