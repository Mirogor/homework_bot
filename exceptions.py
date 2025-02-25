class MissingEnvironmentVariableError(Exception):
    """Ошибка отсутствия обязательной переменной окружения."""


class APIRequestError(Exception):
    """Ошибка при запросе к API."""


class APIResponseError(Exception):
    """Ошибка в ответе API."""
