
import math
import time
import requests
import numpy as np

from io import BytesIO
from pathlib import Path
from PIL import Image, ImageChops
from dataclasses import dataclass
from PIL.Image import Image as PILImage
from typing import List, Tuple, Optional
from urllib.parse import parse_qs, urlparse
from uiautomator2 import Device, UiObject, UiObjectNotFoundError

from src.node_selectors import AdNodesSelectors, ClassNodesSelectors
from src.nodes import (
    AdNodes, 
    MainNodes, 
    ClassNodes, 
    PlayerNodes, 
    ChromeNodes, 
    ContentNodes
)


@dataclass
class Coords:
    center: Tuple[int, int]
    bounds: Tuple[int, int, int, int]
    
    
@dataclass
class AdInfo:
    url: str
    image: PILImage


class YoutubeApp:
    package_name: str = "com.google.android.youtube"
    
    def __init__(self, device: Device) -> None:
        self.device = device

    def start(self) -> None:
        self.device.app_start(package_name=self.package_name)

    def close(self) -> None:
        self.device.app_stop(package_name=self.package_name)

    def open_link(self, link: str) -> None:
        self.device.shell(f'am start -a android.intent.action.VIEW -d "{link}"')
        

class MobileSettings:
    def __init__(self, device: Device) -> None:
        self._device = device
        
    def notification_enable(self) -> None:
        self._device.shell(["cmd", "notification", "set_dnd", "off"])
    
    def notification_disable(self) -> None:
        self._device.shell(["cmd", "notifiaction", "set_dnd", "on"])
        
    def change_rotation(self) -> None:
        self._device.shell(["settings", "put", "system", "user_rotation", "0"])


class YoutubeParser:
    def __init__(self, device: Device) -> None:
        self.device = device
        
        self.offset = 25
        self.max_swipe_count = 9
        
        self.ad_wait_timeout = 5
        self.action_timeout = 0.25
        self.video_load_timeout = 1
        self.player_hide_timeout = 5
        self.node_spawn_timeout = 2.5
        
        self.telegram_chat_id = None
        self.telegram_bot_api = None
        
        self.hidden_ad_duration = 0.1
        self.next_content_swipe_duration = 0.5
        self.half_content_swipe_duration = 0.5
        self.reposition_content_swipe_duration = 0.5
        
        self.app = YoutubeApp(device=self.device)
        self.mobile = MobileSettings(device=self.device)
        
        self._init_nodes()
        self.mobile.notification_disable()

    def _init_nodes(self) -> None:
        self.ad_nodes = AdNodes(device=self.device)
        self.main_nodes = MainNodes(device=self.device)
        self.class_nodes = ClassNodes(device=self.device)
        self.chrome_nodes = ChromeNodes(device=self.device)
        self.player_nodes = PlayerNodes(device=self.device)
        self.content_nodes = ContentNodes(device=self.device)
        
    @staticmethod
    def combine_images_vertically(
        top_img: PILImage, 
        bottom_img: PILImage,
        output_path: str = None,
        background_color: tuple = (255, 255, 255)
    ) -> Optional[PILImage]:
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
    
    @staticmethod
    def compare_images(image1: PILImage, image2: PILImage, tolerance: int = 5) -> float:
        if image1.size != image2.size or image1.mode != image2.mode:
            width = min(image1.width, image2.width)
            height = min(image1.height, image2.height)
            image1 = image1.resize((width, height))
            image2 = image2.resize((width, height))
            
        if image1.mode != 'RGB':
            image1 = image1.convert('RGB')
        if image2.mode != 'RGB':
            image2 = image2.convert('RGB')
        
        diff = ImageChops.difference(image1, image2)
        
        diff_array = np.array(diff)
        
        similar_pixels = np.sum(np.all(diff_array <= tolerance, axis=2))
        total_pixels = diff_array.shape[0] * diff_array.shape[1]
        
        similarity_percent = (similar_pixels / total_pixels) * 100
        
        return round(similarity_percent, 2)

    def wait_load_video(self, max_attempts: int = 10) -> bool:
        for attempt in range(1, max_attempts + 1):
            if self.class_nodes.relative_layouts.count == 0:
                time.sleep(self.video_load_timeout)
                return True
            
            if attempt < max_attempts:
                time.sleep(self.video_load_timeout)
        
        return False
        
    def stop_video(self) -> bool:
        try:
            if self.player_nodes.control_button.exists:
                if self.player_nodes.control_button.info["contentDescription"] == "Play video":
                    return True
                self.player_nodes.control_button.wait_gone(timeout=self.player_hide_timeout)
                time.sleep(self.action_timeout)
                
            self.main_nodes.video_player_node.click()
            if self.player_nodes.control_button.wait(timeout=self.action_timeout):
                self.player_nodes.control_button.click()
                return True
        
            return False
        except UiObjectNotFoundError as e:
            print(f"[ERROR] [{self.device.serial}] {e}")
            return False
        
    def _handle_drag_handle_case(self) -> bool:
        drag_button_coords = Coords(
            bounds=self.ad_nodes.drag_handle_button.bounds(), 
            center=self.ad_nodes.drag_handle_button.center()
        )
        main_node_coords = Coords(
            bounds=self.main_nodes.main_node.bounds(), 
            center=self.main_nodes.main_node.center()
        )
        self.device.swipe_points(
            points=[
                (drag_button_coords.center[0], drag_button_coords.bounds[3] + self.offset),
                (drag_button_coords.center[0], main_node_coords.bounds[3] - self.offset)
            ],
            duration=self.hidden_ad_duration
        )
        time.sleep(self.action_timeout)
        
        return not self.ad_nodes.drag_handle_button.exists
    
    def _handle_close_button_case(self) -> bool:
        button = self.ad_nodes.header_panel_node.child(**AdNodesSelectors.close_ad_button)
        if button.exists and button.click_exists(timeout=1):
            time.sleep(self.action_timeout)
            return not button.exists

        buttons = self.ad_nodes.header_panel_node.child(**ClassNodesSelectors.image_view)
        if buttons.count > 0 and buttons[-1].click_exists(timeout=1):
            time.sleep(self.action_timeout)
            try:
                return not buttons[-1].exists
            except:
                return True
        
        return False
    
    def _handle_close_ad(self) -> bool:
        if not self.ad_nodes.header_panel_node.exists:
            return False

        if self.ad_nodes.drag_handle_button.exists:
            return self._handle_drag_handle_case()
        
        return self._handle_close_button_case()
    
    def preparing_video(self) -> bool:
        if not self._handle_close_ad():
            time.sleep(self.ad_wait_timeout)
        
        if not self._handle_close_ad():
            if self.ad_nodes.header_panel_node.exists:
                return False
        return True
    
    def _get_content_block_coords(self) -> Coords:
        watch_list_node_coords = Coords(
            bounds=self.content_nodes.watch_list_node.bounds(), 
            center=self.content_nodes.watch_list_node.center()
        )
        if self.content_nodes.relative_container_node.exists:
            relative_container_coords = Coords(
                bounds=self.content_nodes.relative_container_node.bounds(), 
                center=self.content_nodes.relative_container_node.center()
            )
            return Coords(
                bounds=(
                    relative_container_coords.bounds[0], relative_container_coords.bounds[3],
                    watch_list_node_coords.bounds[2], watch_list_node_coords.bounds[3]
                ),
                center=(
                    relative_container_coords.center[0],
                    (watch_list_node_coords.center[1] + relative_container_coords.center[1]) // 2
                )
            )
        return watch_list_node_coords
        
    def swipe_to_next_content(self) -> None:
        coords = self._get_content_block_coords()
        
        self.device.swipe_points(
            points=[
                (coords.center[0], coords.bounds[3] - self.offset),
                (coords.center[0], coords.bounds[1] + self.offset)
            ],
            duration=self.next_content_swipe_duration
        )
        
    def swipe_half_content(self) -> None:
        coords = self._get_content_block_coords()
        distance = (coords.bounds[3] - coords.bounds[1]) // 2
        
        self.device.swipe_points(
            points=[
                (coords.center[0], coords.bounds[3] - self.offset),
                (coords.center[0], coords.bounds[3] - self.offset - distance)
            ],
            duration=self.half_content_swipe_duration
        )
        
    def reposition_content(self, first_point: int, second_point: int) -> None:
        coords = self._get_content_block_coords()

        self.device.swipe_points(
            points=[
                (coords.center[0], first_point),
                (coords.center[0], second_point)
            ],
            duration=self.reposition_content_swipe_duration
        )

    def _get_children_nodes(self, node: UiObject) -> List[Optional[UiObject]]:
        childrens = []

        for child_index in range(node.info["childCount"]):
            childrens.append(node.child(index=child_index)[0])
            
        return childrens
    
    def get_node_screenshot(self, left: int, top: int, right: int, bottom: int) -> PILImage:
        coords = self._get_content_block_coords()
        
        if coords.bounds[1] >= top:
            return self.device.screenshot().crop(
                box=(left, coords.bounds[1], right, bottom)
            )
        return self.device.screenshot().crop(
            box=(left, top, right, bottom)
        )
    
    def get_ad_url(self, point: Tuple[int, int]) -> str:
        self.device.click(*point)
        time.sleep(self.action_timeout)
        
        self.chrome_nodes.action_button.click(timeout=self.node_spawn_timeout)
        time.sleep(self.action_timeout)
        
        url = self.chrome_nodes.content_preview_text.get_text(timeout=self.node_spawn_timeout)
        
        self.device.press("back")
        time.sleep(self.action_timeout)
        self.device.press("back")
        time.sleep(self.action_timeout)
        
        return url
        
    def back_to_watch_list(self, max_attempts: int = 5) -> None:
        for _ in range(max_attempts):
            if self.content_nodes.watch_list_node.exists:
                break
            else:
                self.device.press("back")
                time.sleep(self.video_load_timeout)

    def parse_ad(self) -> AdInfo:
        view_count = self.content_nodes.ad_block_node.child(**ClassNodesSelectors.view_group).count
        image_count = self.content_nodes.ad_block_node.child(**ClassNodesSelectors.image_view).count
        
        print(f"[INFO] [{self.device.serial}] {view_count=} | {image_count=}")
        
        match (view_count, image_count):
            case (8, 4) | (7, 4) | (8, 3) | (7, 3) | (18, 8) | (18, 7) | (18, 9) | (17, 8):
                ...
            case (v, i) if (v <= 2 and i <= 3): 
                return None
            case (8, 5):
                return None
            case _:
                self.send_telegram_message()
                return None
        
        ad_block_node_children = self._get_children_nodes(node=self.content_nodes.ad_block_node)
        ad_block_node_coords = self.content_nodes.ad_block_node.bounds()
        ad_text = self.get_node_screenshot(
            left=ad_block_node_coords[0], top=ad_block_node_children[0].bounds()[3],
            right=ad_block_node_coords[2], bottom=ad_block_node_coords[3]
        )
        
        ad_block_image_coords = Coords(
            bounds=ad_block_node_children[0].bounds(),
            center=ad_block_node_children[0].center()
        )
        watch_list_coords = Coords(
            bounds=self.content_nodes.watch_list_node.bounds(),
            center=self.content_nodes.watch_list_node.center()
        )
        
        self.reposition_content(
            first_point=ad_block_image_coords.bounds[3], 
            second_point=watch_list_coords.bounds[3]
        )
        time.sleep(self.action_timeout)
                
        ad_block_node_children = self._get_children_nodes(node=self.content_nodes.ad_block_node)
        ad_image_block_coords = ad_block_node_children[0].bounds()
        ad_image = self.get_node_screenshot(*ad_image_block_coords)
        
        try:
            ad_url = self.get_ad_url(point=ad_block_node_children[0].center())
        except Exception as e:
            print(f"[ERROR] [{self.device.serial}] {e}")
            self.back_to_watch_list()
            return None
        
        image = self.combine_images_vertically(top_img=ad_image, bottom_img=ad_text)

        return AdInfo(
            url=ad_url,
            image=image
        )
        
    # Переделать
    def save_ad_info(self, ad_info: AdInfo) -> None:
        results_folder_path = Path("results")
        phone_folder_path = results_folder_path.joinpath(self.device.serial)
        
        unique_name = str(int(time.time()))
        
        ad_folder_path = phone_folder_path.joinpath(unique_name)
        ad_folder_path.mkdir(exist_ok=True, parents=True)
        
        info_path = ad_folder_path.joinpath("info.txt")
        image_path = ad_folder_path.joinpath("image.png")
        
        with info_path.open('w') as file:
            file.write(ad_info.url)
            
        ad_info.image.save(image_path)
        
    def send_telegram_message(self) -> None:
        try:
            ad_block_node_children = self._get_children_nodes(node=self.content_nodes.ad_block_node)
            view_count = self.content_nodes.ad_block_node.child(**ClassNodesSelectors.view_group).count
            image_count = self.content_nodes.ad_block_node.child(**ClassNodesSelectors.image_view).count
            coords = self._get_content_block_coords()
            image = self.device.screenshot().crop(box=coords.bounds)
            dump = self.device.dump_hierarchy()

            message_text = (
                "📊 Анализ рекламного блока:\n"
                f"• ViewGroup: {view_count}\n"
                f"• ImageView: {image_count}\n\n"
                "🔍 Дочерние элементы:\n"
            )

            for i, child in enumerate(ad_block_node_children, 1):
                child_info = child.info if hasattr(child, 'info') else {}
                message_text += (
                    f"\n{i}. {child_info.get('className', 'N/A')}\n"
                    f"   - childCount: {child_info.get('childCount', 0)}\n"
                    f"   - contentDescription: {child_info.get('contentDescription', 'N/A')}\n"
                    f"   - resourceName: {child_info.get('resourceName', 'N/A')}\n"
                    f"   - text: {child_info.get('text', 'N/A')}\n"
                )

            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=85)
            screenshot_bytes = img_byte_arr.getvalue()

            dump_bytes = dump.encode('utf-8')
            if len(dump_bytes) > 50 * 1024 * 1024:  # 50MB лимит
                dump_bytes = dump_bytes[:50 * 1024 * 1024]

            requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_api}/sendPhoto",
                files={'photo': ('ad_screenshot.jpg', screenshot_bytes)},
                data={'chat_id': self.telegram_chat_id, 'caption': message_text}
            )

            requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_api}/sendDocument",
                files={'document': ('ui_dump.xml', dump_bytes)},
                data={'chat_id': self.telegram_chat_id}
            )

        except Exception as e:
            print(f"Ошибка отправки: {str(e)}")
        
    def run(self, links: List[str]) -> None:
        self.app.start()
        print(f"[INFO] [{self.device.serial}] Программа запущена")
        time.sleep(self.action_timeout)
        
        self.mobile.change_rotation()
        print(f"[INFO] [{self.device.serial}] Изменено положение экрана")
        time.sleep(self.action_timeout)
        
        print(f"[INFO] [{self.device.serial}] Начало работы с {len(links)} ссылками")
        for link in links:
            video_id = parse_qs(urlparse(link).query).get("v", [None])[0]
            
            self.app.open_link(link=link)
            print(f"[INFO] [{self.device.serial}] Открытие ссылки {link.replace('\n', '')}")
            time.sleep(self.action_timeout)
            
            is_video_loaded = self.wait_load_video()
            time.sleep(self.action_timeout)
            
            if is_video_loaded:
                watch_list_children = self.content_nodes.watch_list_node.child()
                if self.content_nodes.watch_list_node.exists and watch_list_children.count == 0:
                    print(f"[ERROR] [{self.device.serial}] [{video_id}] Не удалось загрузить видео")
                    continue
            print(f"[INFO] [{self.device.serial}] [{video_id}] Видео загружено")
            
            self.stop_video()
            self.stop_video()       
            is_video_stoped = self.stop_video()
            if not is_video_stoped:
                print(f"[ERROR] [{self.device.serial}] [{video_id}] Не получилось остановить видео")
                links.append(link)
                continue
            print(f"[INFO] [{self.device.serial}] [{video_id}] Видео остановлено")
            time.sleep(self.action_timeout)
            
            is_video_prepared = self.preparing_video()
            if not is_video_prepared:
                print(f"[ERROR] [{self.device.serial}] [{video_id}] Не удалось подготовить видео")
                links.append(link)
                continue
            print(f"[INFO] [{self.device.serial}] [{video_id}] Видео успешно подготовлено")
            time.sleep(self.action_timeout)

            swipe_count = 0
            while swipe_count < self.max_swipe_count:
                first_screenshot = self.device.screenshot()
                
                if self.content_nodes.ad_block_node.exists:
                    swipe_count = 0
                    ad_block_coords = Coords(
                        bounds=self.content_nodes.ad_block_node.bounds(),
                        center=self.content_nodes.ad_block_node.center()
                    )
                    watch_list_coords = Coords(
                        bounds=self.content_nodes.watch_list_node.bounds(),
                        center=self.content_nodes.watch_list_node.center()
                    )
                    if ad_block_coords.bounds[3] == watch_list_coords.bounds[3]:
                        self.swipe_half_content()
                        continue
                    else:
                        self.reposition_content(
                            first_point=ad_block_coords.bounds[3], 
                            second_point=watch_list_coords.bounds[3]
                        )
                        time.sleep(self.action_timeout)
                        
                        result = self.parse_ad()
                        if result:
                            print(result)
                            self.save_ad_info(ad_info=result)
                        time.sleep(self.action_timeout)
                        
                        self.swipe_to_next_content()
                        time.sleep(self.action_timeout)
                        self.swipe_to_next_content()
                        time.sleep(self.action_timeout)
                        
                        second_screenshot = self.device.screenshot()
                        match_percentages = self.compare_images(first_screenshot, second_screenshot)
                        if match_percentages >= 70:
                            break
                        
                        swipe_count += 2
                        continue
                
                self.swipe_to_next_content()
                time.sleep(self.action_timeout)
                
                second_screenshot = self.device.screenshot()
                match_percentages = self.compare_images(first_screenshot, second_screenshot)
                if match_percentages >= 70:
                    break
                
                swipe_count += 1
