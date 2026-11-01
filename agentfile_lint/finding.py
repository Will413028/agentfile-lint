from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One problem. `line` is 1-based; 0 means the finding is about the whole file."""

    path: str
    line: int
    rule: str
    message: str
    level: str = "error"  # error | warn

    def format(self) -> str:
        # Stable output contract: `file:line: rule-id: message`, line 0 is printed as `:0`.
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"

    def sort_key(self) -> tuple:
        return (self.path, self.line, self.rule, self.message)
