"""Online drift monitor: sliding window of recent inputs vs. the training reference.

The reference profile (``reports/drift_reference.json``) is produced by the
``drift_check`` DVC stage. It is re-read automatically when the file changes
(e.g. after retraining), so the gateway always compares against the data the
*current* model was trained on.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections import Counter, deque
from typing import Deque, Dict, List, Optional

from plotgenre.monitoring.drift_core import label_drift, term_drift

from .metrics import DRIFT_THRESHOLD, DRIFT_WINDOW, LIVE_DRIFT, LIVE_LABEL_DRIFT


class DriftMonitor:
    """Thread-safe sliding-window drift computation."""

    def __init__(self, reference_path: str, default_window: int = 100) -> None:
        self.reference_path = reference_path
        self._lock = threading.Lock()
        self._mtime: Optional[float] = None
        self.reference: Dict[str, float] = {}
        self.prior: Dict[str, float] = {}
        self.threshold: Optional[float] = None
        self.floor: Optional[float] = None
        self.data_version: Optional[str] = None
        self.capacity = default_window
        self.texts: Deque[str] = deque(maxlen=default_window)
        self.labels: Deque[List[str]] = deque(maxlen=default_window)
        self.last_score: Optional[float] = None
        self.last_label_drift: Optional[float] = None
        self.reload()

    def reload(self) -> bool:
        """(Re)load the reference profile if the file is new or changed."""
        try:
            mtime = os.path.getmtime(self.reference_path)
        except OSError:
            return False
        if mtime == self._mtime:
            return True
        try:
            with open(self.reference_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        with self._lock:
            self.reference = data.get("terms", {})
            self.prior = data.get("label_prior", {})
            self.threshold = data.get("threshold")
            self.floor = data.get("online_noise_floor_js")
            self.data_version = data.get("data_version")
            window = int(data.get("online_window", self.capacity))
            if window != self.capacity:
                self.capacity = window
                self.texts = deque(self.texts, maxlen=window)
                self.labels = deque(self.labels, maxlen=window)
            self._mtime = mtime
        if self.threshold is not None:
            DRIFT_THRESHOLD.set(self.threshold)
        return True

    @property
    def loaded(self) -> bool:
        """True when a reference profile is available."""
        return bool(self.reference)

    def observe(self, text: str, predicted: List[str]) -> None:
        """Add one request to the window and refresh the gauges."""
        self.reload()
        with self._lock:
            self.texts.append(text)
            self.labels.append(predicted)
            DRIFT_WINDOW.set(len(self.texts))
            n = len(self.texts)
            if not self.reference or n < max(10, self.capacity // 6):
                return
            raw = term_drift(self.reference, list(self.texts))
            # The noise floor was measured for a full window; sampling noise of the
            # JS distance shrinks roughly with 1/sqrt(n), so rescale for partial windows.
            floor = self.floor * math.sqrt(self.capacity / n) if self.floor else None
            self.last_score = raw / floor if floor else raw
            counts = Counter(g for labs in self.labels for g in labs)
            self.last_label_drift = label_drift(self.prior, counts) if self.prior else None
        LIVE_DRIFT.set(self.last_score)
        if self.last_label_drift is not None:
            LIVE_LABEL_DRIFT.set(self.last_label_drift)

    def snapshot(self) -> dict:
        """Current state for the ``/api/v1/monitoring/drift`` endpoint."""
        detected = bool(self.last_score is not None and self.threshold is not None
                        and self.last_score > self.threshold)
        return {"window_size": len(self.texts), "window_capacity": self.capacity,
                "drift_score": self.last_score, "label_drift": self.last_label_drift,
                "threshold": self.threshold, "drift_detected": detected,
                "reference_loaded": self.loaded, "reference_data_version": self.data_version}
