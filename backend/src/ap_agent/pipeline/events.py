"""Events: every node writes what it does to the case record, and listeners (the live UI) are woken up."""
from __future__ import annotations

import threading
import time


class EventBus:
    def __init__(self, store, pace_ms: int = 0, sleep=time.sleep):
        self.store = store
        self.pace_ms = pace_ms
        self.sleep = sleep
        self._cond = threading.Condition()
        self._version = 0
        self.pace_by_case: dict[str, int] = {}

    def publish(self, case_id: str, type: str, payload: dict) -> int:
        seq = self.store.add_event(case_id, type, payload)
        with self._cond:
            self._version += 1
            self._cond.notify_all()
        pace = self.pace_by_case.get(case_id, self.pace_ms)
        if type in ("finding", "node_started") and pace:
            self.sleep(pace / 1000 / (3 if type == "node_started" else 1))
        return seq

    def wait(self, last_version: int, timeout: float) -> int:
        """Block until something is published after `last_version` (or the timeout). Returns the new version."""
        with self._cond:
            if self._version == last_version:
                self._cond.wait(timeout)
            return self._version
