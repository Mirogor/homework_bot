import os
import time
import logging
from http import HTTPStatus

import requests
import telebot
from requests.exceptions import RequestException

from dotenv import load_dotenv
from exceptions import (MissingEnvironmentVariableError,
                        APIRequestError,
                        APIResponseError
                        )

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

log_file = os.path.expanduser('~/bot.log')

logging.basicConfig(
    level=logging.DEBUG,
    format=(
        '%(asctime)s, %(levelname)s, '
        '[%(funcName)s:%(lineno)d], %(message)s'
    ),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения.

    Raises:
        MissingEnvironmentVariableError:
        Если отсутствуют необходимые переменные окружения.

    Returns:
        bool: True, если все переменные окружения установлены.
    """
    tokens = (
        (PRACTICUM_TOKEN, 'PRACTICUM_TOKEN'),
        (TELEGRAM_TOKEN, 'TELEGRAM_TOKEN'),
        (TELEGRAM_CHAT_ID, 'TELEGRAM_CHAT_ID')
    )

    all_tokens_present = True
    missing_tokens = []

    for token, name in tokens:
        if not token:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: "{name}"')
            all_tokens_present = False
            missing_tokens.append(name)

    if not all_tokens_present:
        raise MissingEnvironmentVariableError(
            f'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}'
        )

    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram.

    Args:
        bot (telebot.TeleBot): Экземпляр бота.
        message (str): Текст сообщения для отправки.

    Returns:
        bool: True, если сообщение успешно отправлено, иначе False.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telebot.apihelper.ApiTelegramException as error:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {error}')
        return False
    logger.debug(f'Бот отправил сообщение: "{message}"')
    return True


def get_api_answer(timestamp):
    """Делает запрос к API Практикум.Домашка.

    Args:
        timestamp (int): Временная метка, с которой начинается запрос.

    Returns:
        dict: Ответ от API в формате Python-словаря.

    Raises:
        APIRequestError: Если произошла ошибка при запросе.
        ConnectionError: Если не удалось подключиться к API.
    """
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }

    logger.debug(
        f'Начинаем запрос к API: "{request_params["url"]}". '
        f'Параметры: {request_params["params"]}, '
        f'Заголовки: {request_params["headers"]}'
    )

    try:
        response = requests.get(**request_params)
    except RequestException as error:
        raise ConnectionError(
            f'Ошибка подключения к API: {error}. '
            f'URL: {request_params["url"]}, '
            f'Параметры: {request_params["params"]}'
            f'Заголовки: {request_params["headers"]}'
        )

    if response.status_code != HTTPStatus.OK:
        raise APIRequestError(
            f'Эндпоинт {request_params["url"]} недоступен. '
            f'Код ответа: {response.status_code} '
            f'({HTTPStatus(response.status_code).phrase}),'
            f'Причина: {response.reason}, Текст ответа: {response.text}'
        )

    return response.json()


def check_response(response):
    """Проверяет корректность ответа API.

    Args:
        response (dict): Ответ от API.

    Returns:
        list: Список домашних работ.

    Raises:
        APIResponseError: Если ответ API не соответствует ожиданиям.
    """
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарём')

    if 'homeworks' not in response:
        raise APIResponseError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError('Поле "homeworks" должно быть списком')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы.

    Args:
        homework (dict): Один элемент из списка домашних работ.

    Returns:
        str: Статус домашней работы в формате строки.

    Raises:
        KeyError: Если отсутствуют обязательные ключи.
        ValueError: Если статус работы неизвестен.
    """
    if 'homework_name' not in homework:
        raise KeyError(
            'В информации о домашней работе отсутствует ключ '
            '"homework_name"'
        )
    if 'status' not in homework:
        raise KeyError(
            'В информации о домашней работе отсутствует ключ '
            '"status"'
        )

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Недокументированный статус работы: {homework_status}')

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logger.debug('Новых статусов нет')
                continue

            homework = homeworks[0]
            message = parse_status(homework)

            if message != last_message:
                if send_message(bot, message):
                    last_message = message

            timestamp = response.get('current_date', timestamp)

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)
            if error_message != last_message:
                if send_message(bot, error_message):
                    last_message = error_message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
