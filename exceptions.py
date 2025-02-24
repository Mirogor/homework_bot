class MissingEnvironmentVariableError(Exception):
    """Ошибка отсутствия обязательной переменной окружения."""

    pass


class APIRequestError(Exception):
    """Ошибка при запросе к API."""

    pass


class APIResponseError(Exception):
    """Ошибка в ответе API."""

    pass
