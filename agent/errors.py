"""Domain errors for the agent runtime."""


class ToolError(Exception):
    """Raised when a tool fails in a non-recoverable way for the current attempt."""


class VerificationError(Exception):
    """Raised when independent verification cannot complete."""


class EscalationNeeded(Exception):
    """Raised when the agent needs human input to continue."""

    def __init__(self, question: str, options: list[str] | None = None) -> None:
        self.question = question
        self.options = options or []
        super().__init__(question)
