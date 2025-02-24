import os
import time
import logging
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

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения.

    Returns:
        bool: True, если все переменные окружения установлены, иначе False.
    """
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for token, name in zip(tokens, ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN',
                                    'TELEGRAM_CHAT_ID']):
        if not token:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: "{name}"')
    return all(tokens)


def send_message(bot, message):
    """Отправляет сообщение в Telegram.

    Args:
        bot (telebot.TeleBot): Экземпляр бота.
        message (str): Текст сообщения для отправки.

    Raises:
        telebot.apihelper.ApiTelegramException:
          Если сообщение не удалось отправить.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Бот отправил сообщение: "{message}"')
    except telebot.apihelper.ApiTelegramException as error:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {error}')
        raise


def get_api_answer(timestamp):
    """Делает запрос к API Практикум.Домашка.

    Args:
        timestamp (int): Временная метка с которой начинается запрос.

    Returns:
        dict: Ответ от API в формате Python-словаря.

    Raises:
        APIRequestError: Если произошла ошибка при запросе.
    """
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params={'from_date': timestamp})
        if response.status_code != 200:
            raise APIRequestError(
                f'Эндпоинт {ENDPOINT} недоступен.\n'
                f'Код ответа API: {response.status_code}'
            )
        return response.json()
    except RequestException as error:
        raise APIRequestError(f'Ошибка при запросе к API: {error}')


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
    if 'homeworks' not in response or 'current_date' not in response:
        raise APIResponseError('В ответе API отсутствуют ожидаемые ключи')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Поле "homeworks" должно быть списком')
    return response['homeworks']


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
    if not check_tokens():
        logger.critical(
            'Программа принудительно остановлена из-за отсутствия '
            'переменных окружения'
        )
        raise MissingEnvironmentVariableError(
            'Отсутствуют обязательные переменные окружения'
        )

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_message:
                    send_message(bot, message)
                    last_message = message
            else:
                logger.debug('Новых статусов нет')

            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            logger.error(f'Сбой в работе программы: {error}')
            error_message = f'Сбой в работе программы: {error}'
            if error_message != last_error_message:
                try:
                    send_message(bot, error_message)
                except telebot.apihelper.ApiTelegramException:
                    logger.error(
                        'Не удалось отправить сообщение об ошибке в Telegram')
                last_error_message = error_message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
