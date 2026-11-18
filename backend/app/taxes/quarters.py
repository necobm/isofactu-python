"""Calendar quarters: the period Spanish freelancers file VAT (modelo 303) and IRPF
(modelo 130) for."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class Quarter:
    year: int
    number: int  # 1..4

    def __post_init__(self) -> None:
        if not 1 <= self.number <= 4:
            raise ValueError("a quarter is numbered 1 to 4")

    @classmethod
    def of(cls, day: date) -> "Quarter":
        return cls(day.year, (day.month - 1) // 3 + 1)

    @property
    def start(self) -> date:
        return date(self.year, 3 * self.number - 2, 1)

    @property
    def end(self) -> date:
        """The last day (inclusive)."""
        if self.number == 4:
            return date(self.year, 12, 31)
        return date(self.year, 3 * self.number + 1, 1) - timedelta(days=1)
