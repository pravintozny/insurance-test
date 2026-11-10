class ValidationError(ValueError):
    """Raised with a list of field-level problems."""

    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


class NotFoundError(KeyError):
    pass


class WorkflowError(Exception):
    """Illegal lifecycle transition or operation in the current state."""
