import logging
import os
import sys
import time
from contextlib import suppress
from datetime import datetime
from http import HTTPStatus
from json import JSONDecodeError
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException
from telebot import TeleBot
from telebot.apihelper import ApiException

import exceptions


load_dotenv()
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s',
    handlers=[
        RotatingFileHandler(
            'filelogs.log', maxBytes=5000000, backupCount=3, encoding='utf8'
        ),
        logging.StreamHandler(sys.stdout)
    ]
)

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


def check_tokens() -> list:
    """Проверяет доступность обязательных переменных."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    return [name_token for name_token, token in tokens.items() if not token]


def send_message(bot: TeleBot, message: str):
    """Отпрвляет сообщение в телеграм чат."""
    try:
        logging.debug('Отравка сообщения')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except ApiException as error:
        logging.error(error, exc_info=True)
    else:
        logging.debug('Сообщение успешно отправлено')


def get_api_answer(timestamp):
    """Получает ответ от API и возвращает ответ в формате Python словаря."""
    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params={'from_date': timestamp}
        )
        if response.status_code != HTTPStatus.OK:
            error_message = response.json().get(
                'message', 'Неизвестная ошибка'
            )
            logging.error(error_message)
            raise exceptions.EndpointStatusError(
                f'Ошибка ответа от API практикума.\n'
                f'Статус ответа: {response.status_code}.\n'
                f'Текст ошибки: {error_message}'
            )
        return response.json()
    except RequestException as error:
        logging.error(f'Произошла ошибка при запросе к API: {error}')
        raise ConnectionError
    except JSONDecodeError as error:
        logging.error(
            f'Произошла ошибка при преобразовании json к dict: {error}'
        )
        raise


def check_response(response):
    """Проверяет ответ API на соотвесвие документации."""
    if not isinstance(response, dict):
        text_error = 'Ответ не является словарем'
        logging.error(text_error)
        raise TypeError(text_error)

    if response.get('homeworks') is None:
        text_error = 'Отсутсвуют ожидаемый ключ "homeworks" в response'
        logging.error(text_error)
        raise KeyError(text_error)

    if not isinstance(response['homeworks'], list):
        text_error = 'Значенеи ключа "homeworks" не является списком'
        logging.error(text_error)
        raise TypeError(text_error)

    if response.get('current_date') is None:
        text_error = 'Отсутсвуют ожидаемый ключ "current_date" в response'
        logging.error(text_error)
        raise KeyError(text_error)

    return response['homeworks']


def parse_status(homework):
    """
    Извлекает информацию из последеней домашней работы.
    Возвращает готовое сообщение для отправки в телеграм чат.
    """
    if homework:
        homework_name = homework.get('homework_name')
        status = homework.get('status')
        if status not in HOMEWORK_VERDICTS:
            logging.error(f'Неизвестный статус работы: {status}')
            raise exceptions.NotFoundStatusError('Нет статуса')
        if not homework_name:
            text_error = 'В ответе отсутсвует ключ "homework_name"'
            logging.error(text_error)
            raise KeyError(text_error)
        verdict = HOMEWORK_VERDICTS.get(status)
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    missing_tokens = check_tokens()
    if missing_tokens:
        logging.critical(
            f'Отсутвуют обязательные переменные из окружени: '
            f'{", ".join(missing_tokens)}'
        )
        return
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(datetime.now().timestamp())
    last_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date')
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Изменений нет')
                continue
            message = parse_status(homeworks[0])
            if last_message != message:
                last_message = message
                send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if last_message != message:
                last_message = message
                with suppress(ApiException):
                    send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
