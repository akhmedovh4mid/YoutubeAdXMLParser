from uiautomator2 import Device
from typing import Any, ClassVar, Optional

from src.node_selectors import (
    AdNodesSelectors, 
    MainNodesSelectors, 
    ClassNodesSelectors, 
    ChromeNodesSelectors, 
    PlayerNodesSelectors,
    ContentNodesSelectors, 
)


class BaseNode:
    def __init__(self, device: Device) -> None:
        self.device = device
        self._init_nodes()
        
    def _init_nodes(self) -> None:
        raise NotImplementedError


class MainNodes(BaseNode):
    def _init_nodes(self) -> None:
        self.main_node = self.device(**MainNodesSelectors.main_node)
        self.time_bar_node = self.main_node.child(**MainNodesSelectors.time_bar_node)
        self.video_player_node = self.main_node.child(**MainNodesSelectors.video_player_node)
        self.video_metadata_node = self.main_node.child(**MainNodesSelectors.video_metadata_node)
        self.engagement_panel_node = self.main_node.child(**MainNodesSelectors.engagement_panel_node)


class PlayerNodes(MainNodes):
    def _init_nodes(self) -> None:
        super()._init_nodes()
        self.control_button = self.video_player_node.child(**PlayerNodesSelectors.control_button)


class ContentNodes(MainNodes):
    def _init_nodes(self) -> None:
        super()._init_nodes()
        self.ad_block_node = self.video_metadata_node.child(**ContentNodesSelectors.ad_block_node)
        self.watch_list_node = self.video_metadata_node.child(**ContentNodesSelectors.watch_list_node)
        self.relative_container_node = self.video_metadata_node.child(**ContentNodesSelectors.relative_container_node)


class AdNodes(MainNodes):
    def _init_nodes(self) -> None:
        super()._init_nodes()
        self.close_button = self.engagement_panel_node.child(**AdNodesSelectors.close_ad_button)
        self.header_panel_node = self.engagement_panel_node.child(**AdNodesSelectors.header_panel_node)
        self.drag_handle_button = self.engagement_panel_node.child(**AdNodesSelectors.drag_handle_button)
        

class ClassNodes(MainNodes):
    def _init_nodes(self) -> None:
        super()._init_nodes()
        self.relative_layouts = self.video_metadata_node.child(**ClassNodesSelectors.relative_layout)
        
        
class ChromeNodes(BaseNode):
    def _init_nodes(self) -> None:
        self.tool_bar_node = self.device(**ChromeNodesSelectors.toolbar_node)
        self.app_menu_list = self.device(**ChromeNodesSelectors.app_menu_list_node)
        self.menu_button = self.tool_bar_node.child(**ChromeNodesSelectors.menu_button)
        self.page_info_url_text = self.device(**ChromeNodesSelectors.page_info_url_text)
        self.truncated_url_button = self.device(**ChromeNodesSelectors.truncated_url_button)
        self.page_info_button = self.app_menu_list.child(**ChromeNodesSelectors.page_info_button)
        
        self.tabcontent_node = self.device(**ChromeNodesSelectors.tabcontent_node)
        self.action_button = self.tool_bar_node.child(**ChromeNodesSelectors.action_button)
        self.content_preview_text = self.tabcontent_node.child(**ChromeNodesSelectors.content_preview_text)
