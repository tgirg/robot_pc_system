"""Calibration helpers for encoder counts and servo settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median


@dataclass
class EncoderResolutionSession:
    """Collect one-wheel manual revolution count measurements."""

    wheel: int
    samples: list[int] = field(default_factory=list)

    def add_sample(self, count: int) -> None:
        """Add one absolute one-revolution count sample."""
        if count <= 0:
            raise ValueError("count sample must be positive")
        self.samples.append(abs(int(count)))

    def candidate_median(self) -> int:
        """Return the median count candidate."""
        if not self.samples:
            raise ValueError("no samples")
        return int(round(median(self.samples)))

    def candidate_average(self) -> int:
        """Return the average count candidate."""
        if not self.samples:
            raise ValueError("no samples")
        return int(round(mean(self.samples)))

