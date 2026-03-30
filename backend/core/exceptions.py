class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(code="unauthorized", message=message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(code="forbidden", message=message, status_code=403)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(code="not_found", message=message, status_code=404)


class CircuitOpenError(AppError):
    def __init__(self, message: str = "Dependency temporarily unavailable") -> None:
        super().__init__(code="circuit_open", message=message, status_code=503)
