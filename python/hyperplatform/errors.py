class ApiError(Exception):
    def __init__(self, message: str, status_code: int = None, data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.data = data
