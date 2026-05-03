"""Error types for Repdown."""


class RepdownError(Exception):
    """Base exception for Repdown errors."""


class ParseError(RepdownError):
    """Raised when Repdown input cannot be parsed."""

    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"Line {line_number}: {reason}")
