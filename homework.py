import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException
from telebot import TeleBot

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

OPENING_12_SPRINT = 1741609232
RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens() -> bool:
    """Проверяет доступность обязательных переменных."""
    return all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PRACTICUM_TOKEN])


def send_message(bot: TeleBot, message: str):
    """Отпрвляет сообщение в телеграм чат."""
    try:
        logging.debug('Отравка сообщения')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as error:
        print(error)
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
            raise exceptions.EndpointStatusError(
                f'Ошибка ответа от API практикума.\n'
                f'Статус ответа: {response.status_code}.\n'
                f'Текст ошибки: {error_message}'
            )
        return response.json()
    except RequestException as error:
        logging.error(f'Произошла ошибка при запросе к API: {error}')


def check_response(response):
    """Проверяет ответ API на соотвесвие документации."""
    if not isinstance(response, dict):
        text_error = 'Ответ не является словарем'
        logging.error(text_error)
        raise TypeError(text_error)

    if response.get('homeworks') is None:
        text_error = 'Отсутсвуют ожидаемые ключи в response'
        logging.error(text_error)
        raise KeyError(text_error)

    if not isinstance(response['homeworks'], list):
        text_error = 'Значенеи ключа "homeworks" не является списком'
        logging.error(text_error)
        raise TypeError(text_error)
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
    if not check_tokens():
        logging.critical('Отсутвуют обязательные переменные из окружения')
        return
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = OPENING_12_SPRINT
    last_status = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date')
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Изменений нет')
                continue
            if last_status != homeworks[0].get('status'):
                message = parse_status(homeworks[0])
                send_message(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        finally:
            time.sleep(600)


if __name__ == '__main__':
    main()
