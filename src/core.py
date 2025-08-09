import time

from typing import List, Optional, Tuple
from uiautomator2 import Device, UiObject
from collections import namedtuple
from dataclasses import dataclass
from bs4 import BeautifulSoup

from src.ocr import Tesseract
from src.common import (
    AdNodesSelectors, 
    MainNodesSelectors, 
    ClassNodesSelectors, 
    ChromeNodesSelectors,
    PlayerNodesSelectors,
    ContentNodesSelectors,
    AdvertiserNodesSelectors,
)


Coords = namedtuple("Coords", ["bounds", "center"])


@dataclass
class AdBlockBounds:
    image: Coords
    text: Coords
    icon: Coords
    options: Coords
    button: Coords
    
    
@dataclass
class AdvertiserInfo:
    name: str
    location: str


class YoutubeApp:
    def __init__(self, device: Device) -> None:
        self.device = device

    def start(self) -> None:
        self.device.app_start(package_name=self.package_name)

    def close(self) -> None:
        self.device.app_stop(package_name=self.package_name)

    def open_link(self, link: str) -> None:
        self.device.shell(f'am start -a android.intent.action.VIEW -d "{link}"')


class YoutubeAdParser:
    package_name: str = "com.google.android.youtube"
    
    def __init__(self, device: Device, lang: str = "eng") -> None:
        self.device = device
        self.lang = lang
        
        self.offset: int = 25
        self.time_sleep = 0.25
        self.ad_wait_time = 5
        self.wait_load_time_sleep = 1
        self.up_swipe_duration = 0.3
        self.easy_swipe_duration = 0.5
        self.down_swipe_duration = 0.35
        
        # ===== Main Nodes =====
        self.main_node = self.device(**MainNodesSelectors.main_node)
        self.time_bar_node = self.main_node.child(**MainNodesSelectors.time_bar_node)
        self.video_player_node = self.main_node.child(**MainNodesSelectors.video_player_node)
        self.video_metadata_node = self.main_node.child(**MainNodesSelectors.video_metadata_node)
        self.engagement_panel_node = self.main_node.child(**MainNodesSelectors.engagement_panel_node)

        # ===== Player Nodes =====
        self.player_control_button = self.video_player_node.child(**PlayerNodesSelectors.control_button)

        # ===== Content Node =====
        self.content_watch_list_node = self.video_metadata_node.child(**ContentNodesSelectors.watch_list_node)
        self.content_relative_container_node = self.video_metadata_node.child(**ContentNodesSelectors.relative_container_node)
        self.content_ad_block_node = self.video_metadata_node.child(**ContentNodesSelectors.ad_block_node)

        # ===== Ad Nodes =====
        self.ad_drag_handle_button = self.engagement_panel_node.child(**AdNodesSelectors.drag_handle_button)
        self.ad_header_panel_node = self.engagement_panel_node.child(**AdNodesSelectors.header_panel_node)
        self.ad_close_button = self.engagement_panel_node.child(**AdNodesSelectors.close_ad_button)

        # ===== Class Nodes =====
        self.relative_layouts = self.video_metadata_node.child(**ClassNodesSelectors.relative_layout)

        # ===== Advertiser Nodes ===== 
        self.advertiser_content_node = self.device(**AdvertiserNodesSelectors.content_node)
        self.advertiser_progress_bar_node = self.advertiser_content_node.child(**AdvertiserNodesSelectors.progress_bar_node)
        self.advertiser_node = self.advertiser_content_node.child(**AdvertiserNodesSelectors.advertiser_node)
        self.advertiser_button = self.advertiser_node.child(**AdvertiserNodesSelectors.advertiser_button)
        
        # ===== Chrome Nodes =====
        self.chrome_tool_bar_node = self.device(**ChromeNodesSelectors.toolbar_node)
        self.chrome_menu_button = self.chrome_tool_bar_node.child(**ChromeNodesSelectors.menu_button)
        self.chrome_app_menu_list = self.device(**ChromeNodesSelectors.app_menu_list_node)
        self.chrome_page_info_button = self.chrome_app_menu_list.child(**ChromeNodesSelectors.page_info_button)
        self.chrome_page_info_url_text = self.device(**ChromeNodesSelectors.page_info_url_text)
        self.truncated_url_button = self.device(**ChromeNodesSelectors.truncated_url_button)

        self.app = YoutubeApp(device=device)
        
        self._dns_disable()
        self._change_rotation()
        self._notification_disable()

    def wait_load_video(self, max_attempts: int = 10) -> bool:
        for attempt in range(1, max_attempts + 1):
            if self.relative_layouts.count == 0:
                return True
            
            if attempt < max_attempts:
                time.sleep(self.wait_load_time_sleep)
                
        return False
    
    def is_stopped_video(self) -> bool:
        if not self.player_control_button.exists:
            self.video_player_node.click()
        try:
            desc = self.player_control_button.info["contentDescription"]
        except:
            return False
        if desc == "Pause video":
            return False
        return True
        
    def stop_video(self) -> bool:
        self.video_player_node.click()
        self.player_control_button.click_exists(0.25)
        time.sleep(self.time_sleep)
        return self.is_stopped_video()
    
    def is_closed_ad(self) -> bool:
        if not self.ad_header_panel_node.exists:
            return True
        return False
    
    def _handle_drag_handle_case(self) -> bool:
        buttons = self.ad_header_panel_node.child(**ClassNodesSelectors.button)
        if buttons.count > 0:
            if buttons[-1].click_exists(timeout=1):
                time.sleep(self.time_sleep)
                return True
            
        drag_coords = self.ad_drag_handle_button.bounds()
        main_node_coords = self.main_node.bounds()
        center_x = (drag_coords[2] + drag_coords[0]) // 2
        self.device.swipe_points(
            points=[
                (center_x, drag_coords[3] + self.offset),
                (center_x, main_node_coords[3] - self.offset)
            ],
            duration=self.down_swipe_duration
        )
        time.sleep(self.time_sleep)
        
        return not self.ad_drag_handle_button.exists
    
    def _handle_close_button_case(self) -> bool:
        button = self.ad_header_panel_node.child(**AdNodesSelectors.close_ad_button)
        if button.exists and button.click_exists(timeout=1):
            time.sleep(self.time_sleep)
            return not button.exists
        
        buttons = self.ad_header_panel_node.child(**ClassNodesSelectors.image_view)
        if buttons.count > 0 and buttons[-1].click_exists(timeout=1):
            time.sleep(self.time_sleep)
            try:
                return not buttons[-1].exists
            except:
                return True
        
        return False
    
    def _handle_close_ad(self) -> bool:
        if not self.ad_header_panel_node.exists:
            return False
        
        if self.ad_drag_handle_button.exists:
            return self._handle_drag_handle_case()
        
        return self._handle_close_button_case()

    def preparing_app(self) -> bool:
        if not self._handle_close_ad():
            time.sleep(self.ad_wait_time)
        
        if not self._handle_close_ad():
            if self.ad_header_panel_node.exists:
                return False
        return True

    def _get_swipe_coords(self) -> Tuple[int, int, int, int]:
        watch_list_coords = self.content_watch_list_node.bounds()
        if self.content_relative_container_node.exists:
            content_relative_container_coords = self.content_relative_container_node.bounds()
            return (
                content_relative_container_coords[0], content_relative_container_coords[3],
                watch_list_coords[2], watch_list_coords[3],
            )
        return watch_list_coords
    
    def swipe(self) -> None:
        coords = self._get_swipe_coords()

        center_x = (coords[2] + coords[0]) // 2
        self.device.swipe_points(
            points=[
                (center_x, coords[3] - self.offset),
                (center_x, coords[1] + self.offset)
            ],
            duration=self.up_swipe_duration
        )

    def easy_swipe(self) -> None:
        coords = self._get_swipe_coords()

        center_x = (coords[2] + coords[0]) // 2
        distance = (coords[3] - coords[1]) // 2
        
        self.device.swipe_points(
            points=[
                (center_x, coords[3] - self.offset),
                (center_x, coords[3] - self.offset - distance),
            ],
            duration=self.easy_swipe_duration
        )
        
    def _get_children_blocks(self, block: UiObject) -> List[Optional[UiObject]]:
        childrens = []

        for child_index in range(block.info["childCount"]):
            childrens.append(block.child(index=child_index)[0])
            
        return childrens
    
    def get_ad_text(self, coords: Coords) -> str:
        image = self.device.screenshot().crop(box=coords.bounds)
        data = Tesseract.get_screen_data(image=image, lang=self.lang)
        text = " ".join(data.text).strip()
        
        return text
    
    def get_advertiser_info(self, coords: Coords) -> AdvertiserInfo:
        self.device.click(*coords.center)
        
        self.advertiser_progress_bar_node.wait(timeout=500)
        self.advertiser_progress_bar_node.wait_gone(timeout=500)
        
        content_center = self.advertiser_content_node.center()
        content_coords = self.advertiser_content_node.bounds()
        self.device.swipe_points(
            points=[
                (content_center[0], content_coords[3] - (self.offset * 3)),
                (content_center[0], content_coords[1] + (self.offset * 3))
            ],
            duration=0.1
        )
        time.sleep(self.time_sleep)
        
        self.advertiser_button.click()
        self.advertiser_button.click()
        
        self.advertiser_node.wait(timeout=5)
        
        text_view_count = self.advertiser_node.child(**ClassNodesSelectors.text_view)
        if text_view_count.count == 0:
            advertiser_node_child = self.advertiser_node.child(**ClassNodesSelectors.view)
            advertiser_name = advertiser_node_child[5].info["text"]
            advertiser_location = advertiser_node_child[7].info["text"]
        else:
            advertiser_node_child = self.advertiser_node.child(**ClassNodesSelectors.text_view)
            advertiser_name = advertiser_node_child[2].info["text"]
            advertiser_location = advertiser_node_child[4].info["text"]

        self.device.press("back")
        return AdvertiserInfo(
            name=advertiser_name,
            location=advertiser_location
        )
    
    def _notification_enable(self) -> None:
        self.device.shell(["cmd", "notification", "set_dnd", "off"])
    
    def _notification_disable(self) -> None:
        self.device.shell(["cmd", "notifiaction", "set_dnd", "on"])
        
    def _dns_disable(self) -> None:
        self.device.shell(["settings", "put", "global", "private_dns_mode", "off"])
        
    def _restart_network_services(self) -> None:
        self.device.shell("svc wifi disable && svc wifi enable")
        self.device.shell("svc data disable && svc data enable")
        time.sleep(1.5)
        
    def _dns_enable(self) -> None:
        self._dns_disable()
        self.device.shell(["settings", "put", "global", "private_dns_specifier", "fake.dns.server"])
        self.device.shell(["settings", "put", "global", "private_dns_mode", "hostname"])
        # self._restart_network_services()
        
    def _change_rotation(self) -> None:
        self.device.shell(["settings", "put", "system", "user_rotation", "0"])
        
    def get_ad_url(self, coords: Coords) -> str:
        self._dns_enable()
        self.device.click(*coords.center)

        self.chrome_menu_button.click(timeout=2.5)    
        self.chrome_page_info_button.click(timeout=2.5)
        self.truncated_url_button.click(timeout=2.5)
        
        url = self.chrome_page_info_url_text.get_text(timeout=2.5)
        self._dns_disable()
        
        self.device.press("back")
        time.sleep(self.time_sleep)
        self.device.press("back")
        time.sleep(self.time_sleep)
        
        return url
    
    def _get_ad_image_coords(self) -> Coords:
        children = self._get_children_blocks(self.content_ad_block_node)
        image = children[0]
        
        if self.content_relative_container_node.exists:
            image_coords = image.bounds()
            relative_container_coords = self.content_relative_container_node.bounds()
            bounds=(
                image_coords[0], relative_container_coords[3],
                image_coords[2], image_coords[3]
            )
            center=(
                (image_coords[2] + image_coords[0]) // 2,
                (image_coords[3] + relative_container_coords[3]) // 2
            )
        else:
            bounds = image.bounds()
            center = image.center()
            
        return Coords(
            bounds=bounds,
            center=center,
        )

    def get_ad_coords(self) -> AdBlockBounds:
        children = self._get_children_blocks(self.content_ad_block_node)
        
        view_group_count = self.content_ad_block_node.child(**ClassNodesSelectors.view_group).count
        image_view_count = self.content_ad_block_node.child(**ClassNodesSelectors.image_view).count
        
        match (view_group_count, image_view_count):
            case (4, 2) | (4, 4): # (3, 4)
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=children[1].bounds(), center=children[0].center())
                options_coords = Coords(bounds=children[2].bounds(), center=children[0].center())
                button_coords = Coords(bounds=children[3].bounds(), center=children[3].center())
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], button_coords.bounds[1]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (button_coords.bounds[1] + image_coords.bounds[3]) // 2
                    )
                )

            case (7, 3) | (7, 4):
                icon, options = children[2].child()
                button = children[3].child(**ClassNodesSelectors.view_group)[-1]
                
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=icon.bounds(), center=icon.center())
                options_coords = Coords(bounds=options.bounds(), center=options.center())
                button_coords = Coords(bounds=button.bounds(), center=button.center())
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], button_coords.bounds[1]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (button_coords.bounds[1] + image_coords.bounds[3]) // 2
                    )
                )
            
            case (8, 3) | (8, 4):
                second_node_childs = children[1].child()
                button = children[2].child(**ClassNodesSelectors.view_group)[-1]
                
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=second_node_childs[0].bounds(), center=second_node_childs[0].center())
                options_coords = Coords(bounds=second_node_childs[3].bounds(), center=second_node_childs[3].center())
                button_coords = Coords(bounds=button.bounds(), center=button.center())
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], button_coords.bounds[1]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (button_coords.bounds[1] + image_coords.bounds[3]) // 2
                    )
                )
        
            case (13, 6) | (13, 5):
                second_node_childs = children[2].child()
                
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=second_node_childs[0].bounds(), center=second_node_childs[0].center())
                options_coords = Coords(bounds=second_node_childs[2].bounds(), center=second_node_childs[2].center())
                button_coords = image_coords
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], self.content_ad_block_node[3]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (self.content_ad_block_node[3] + image_coords.bounds[3]) // 2
                    )
                )

            case (15, 6) | (15, 5):
                second_node_childs = children[2].child()
                button = children[3].child(**ClassNodesSelectors.view_group)[-1]
                
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=second_node_childs[0].bounds(), center=second_node_childs[0].center())
                options_coords = Coords(bounds=second_node_childs[2].bounds(), center=second_node_childs[2].center())
                button_coords = Coords(bounds=button.bounds(), center=button.center())
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], button_coords.bounds[1]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (button_coords.bounds[1] + image_coords.bounds[3]) // 2
                    )
                )
                
            case (17, 8):
                second_node_childs = children[2].child()
                button = children[4].child(**ClassNodesSelectors.view_group)[-1]
                
                image_coords = Coords(bounds=children[0].bounds(), center=children[0].center())
                icon_coords = Coords(bounds=second_node_childs[0].bounds(), center=second_node_childs[0].center())
                options_coords = Coords(bounds=second_node_childs[1].bounds(), center=second_node_childs[1].center())
                button_coords = Coords(bounds=button.bounds(), center=button.center())
                text_coords = Coords(
                    bounds=(
                        icon_coords.bounds[2], image_coords.bounds[3],
                        options_coords.bounds[0], button_coords.bounds[1]
                    ),
                    center=(
                        (options_coords.bounds[0] + icon_coords.bounds[2]) // 2,
                        (button_coords.bounds[1] + image_coords.bounds[3]) // 2
                    )
                )
        
            case _:
                raise Exception("Что-то новое")
        
        return AdBlockBounds(
            image=image_coords,
            icon=icon_coords,
            options=options_coords,
            button=button_coords,
            text=text_coords
        )
        
        
        
