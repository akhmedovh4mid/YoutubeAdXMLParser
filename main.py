import argparse
from multiprocessing import Process
from pathlib import Path
import subprocess
from typing import List
import requests
from uiautomator2 import Device

from src.core import YoutubeParser


def parse_args():
    parser = argparse.ArgumentParser(description="Настройка параметров парсинга")

    parser.add_argument(
        "-s", "--serials",
        nargs="+",
        help="Список Serials",
        required=True
    )

    return parser.parse_args()


def get_adb_devices() -> None:
    """Получает список подключенных ADB устройств."""
    try:
        print("Попытка получить список ADB устройств")
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        devices = []
        for line in result.stdout.splitlines():
            if "\tdevice" in line:
                device = line.split("\t")[0]
                devices.append(device)
                print(f"Найдено устройство: {device}")

        if not devices:
            print("Не найдено ни одного подключенного устройства")

        return devices

    except FileNotFoundError:
        print("ADB не найден! Убедитесь, что он установлен и добавлен в PATH.")
        return []
    except Exception as e:
        print(f"Произошла непредвиденная ошибка при получении устройств: {e}")
        return []


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Ошибка отправки: {e}")
        return False


def worker(serial: str, links: List[str]) -> None:
    device = Device(serial)
    parser = YoutubeParser(device=device)

    try:
        parser.run(links=links)
    except Exception as e:
        send_telegram_message(bot_token=parser.telegram_bot_api, chat_id=parser.telegram_chat_id, text=e)
        raise e

if __name__ == "__main__":
    args = parse_args()
    links_file = Path("links.txt")
    
    if not links_file.is_file():
        print("Файл links.txt не найден в рабочей директории")
        exit()

    print("Запуск приложения")
    
    try:
        phone_series = []
        attach_phone_series = get_adb_devices()
        for serial in args.serials:
            if serial not in attach_phone_series:
                print(f"Устройство {serial} не существует!")
            else:
                phone_series.append(serial)

        if not phone_series:
            print("Не найдено ни одного устройства для работы. Выход.")
            exit()

        print(f"Найденные устройства: {phone_series}")


        with open(file="links.txt", mode="r") as file:
            links = file.readlines()
            print(f"Загружено {len(links)} ссылок из файла")

        if not links:
            print("Файл links.txt пуст")
            exit()

        processes = []
        for serial in phone_series:
            print(f"Создание процесса для устройства {serial} с {len(links)} ссылками")

            process = Process(
                name=serial,
                target=worker,
                args=(serial, links),
                daemon=True
            )
            processes.append(process)

        print("Запуск процессов...")
        for process in processes:
            process.start()
            print(f"Процесс {process.name} запущен")

        print("Ожидание завершения процессов...")
        for process in processes:
            process.join()
            print(f"Процесс {process.name} завершил работу")

        print("Все процессы завершены. Работа приложения завершена.")

    except Exception as e:
        print(f"Критическая ошибка в main: {e}")
        raise
