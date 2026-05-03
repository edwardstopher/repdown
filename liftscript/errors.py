"""Error types for LiftScript."""


class LiftScriptError(Exception):
    """Base exception for LiftScript errors."""


class ParseError(LiftScriptError):
    """Raised when LiftScript input cannot be parsed."""

    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"Line {line_number}: {reason}")
