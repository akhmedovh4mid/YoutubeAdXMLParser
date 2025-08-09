import argparse
from multiprocessing import Process
import os
from pathlib import Path
import subprocess
import time
from typing import List
from uiautomator2 import Device

from src.core import YoutubeAdParser, AdvertiserInfo
from src.common import ClassNodesSelectors

from PIL import Image


def save_ad(serial: str, text: str, advertiser_info: AdvertiserInfo, url: str, image_block: Image.Image, text_block: Image.Image):
    result_path = Path("results")
    result_path.mkdir(exist_ok=True, parents=True)
    
    serial_path = result_path.joinpath(serial)
    serial_path.mkdir(exist_ok=True, parents=True)
    
    unique_name = str(int(time.time()))
    folder_path = serial_path.joinpath(unique_name)
    folder_path.mkdir(exist_ok=True, parents=True)
    
    data_file = folder_path.joinpath("info.txt")
    data = f"Text: {text}\nAvertiser Name: {advertiser_info.name}\nAdvertiser Location: {advertiser_info.location}\nURL: {url}"
    with data_file.open("w", encoding="UTF-8") as file:
        file.write(data)
    
    image_file = folder_path.joinpath("image.png")
    combine_images_vertically(image_block, text_block, output_path=image_file)


def combine_images_vertically(
    top_img: Image.Image, 
    bottom_img: Image.Image,
    output_path: str = None,
    background_color: tuple = (255, 255, 255)
) -> Image.Image:
    width = max(top_img.width, bottom_img.width)
    height = top_img.height + bottom_img.height
    
    combined = Image.new("RGB", (width, height), background_color)
    
    x_offset = (width - top_img.width) // 2
    combined.paste(top_img, (x_offset, 0))
    
    x_offset = (width - bottom_img.width) // 2
    combined.paste(bottom_img, (x_offset, top_img.height))
    
    if output_path:
        combined.save(output_path)
        return None
    return combined


def main(serial: str, links: List[str]) -> None:
    device = Device(serial=serial)
    parser = YoutubeAdParser(device=device)

    for link in links:
        parser.app.open_link(link)
        time.sleep(0.2)
        
        is_loaded = parser.wait_load_video()
        time.sleep(0.2)
        
        if is_loaded:
            children = parser.content_watch_list_node.child()
            if children.count == 0:
                continue
        time.sleep(2.25)
        
        count = 0
        while count != 3:
            if parser.stop_video():
                break
            count += 1
            time.sleep(1.5)

        time.sleep(0.2)

        parser.preparing_app()
        time.sleep(0.2)
        
        swipe_count = 0
        while swipe_count != 8:
            print(f"{swipe_count=}")
            if parser.content_ad_block_node.exists:
                swipe_count = 0
                ad_block_coords = parser.content_ad_block_node.bounds()
                watch_list_coords = parser.content_watch_list_node.bounds()
                if ad_block_coords[3] == watch_list_coords[3]:
                    parser.easy_swipe()
                    continue
                else:
                    center_x = (ad_block_coords[2] + ad_block_coords[0]) // 2
                    parser.device.swipe_points(
                        points=[
                            (center_x, ad_block_coords[3]),
                            (center_x, watch_list_coords[3])
                        ],
                        duration=parser.down_swipe_duration
                    )
                    time.sleep(parser.time_sleep)
                    
                    view_count = parser.content_ad_block_node.child(**ClassNodesSelectors.view_group).count
                    image_count = parser.content_ad_block_node.child(**ClassNodesSelectors.image_view).count

                    print(f"{view_count} | {image_count}")
                    if not (
                        (view_count <= 2 and image_count <= 3) 
                        or 
                        (view_count == 8 and image_count == 5)
                    ):
                        result = parser.get_ad_coords()
                        
                        try:
                            text = parser.get_ad_text(coords=result.text)
                            print(f"{text=}")
                            
                            advertiser_info = parser.get_advertiser_info(coords=result.options)
                            print(f"{advertiser_info=}")
                            parser.content_watch_list_node.wait(timeout=2)
                            
                            ad_block_coords = parser.content_ad_block_node.bounds()
                            watch_list_coords = parser.content_watch_list_node.bounds()
                            text_block = parser.device.screenshot().crop(box=(
                                watch_list_coords[0], result.image.bounds[3],
                                watch_list_coords[2], ad_block_coords[3]
                            ))
                            
                            url = parser.get_ad_url(coords=result.button)
                            parser.content_watch_list_node.wait(timeout=2)
                            print(f"{url=}")
                            
                            image_coords = parser._get_ad_image_coords()
                            image_block = parser.device.screenshot().crop(box=image_coords.bounds)
                            
                            save_ad(serial=parser.device.serial, text=text, advertiser_info=advertiser_info, url=url, image_block=image_block, text_block=text_block)
                        
                        except Exception as e:
                            print(e)
                            while True:
                                if parser.content_watch_list_node.exists:
                                    break
                                else:
                                    parser.device.press("back")
                                    time.sleep(1)
                            
                    parser.swipe()
                    parser.swipe()
                    swipe_count += 2
                    
                    time.sleep(parser.time_sleep)
                    continue
                
            parser.swipe()
            swipe_count += 1
            time.sleep(parser.time_sleep)

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
                target=main,
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
