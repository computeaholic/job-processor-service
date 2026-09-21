class DomainError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or message


class NonRetryableJobError(Exception):
    def __init__(self, message: str, *, code: str = "JOB_NON_RETRYABLE_FAILURE") -> None:
        super().__init__(message)
        self.code = code
