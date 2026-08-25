"""Navigation contracts for FortifyLab's Python TUI migration."""

from .baseline import MAIN_MENU, MENU_TREE
from .controller import MenuController, MenuResult, normalize_menu_key
from .models import ActionKind, ActionRef, MenuItem, MenuNode
from .registry import all_menus, find_item, get_menu, menu_keys, menu_labels, menu_registry

__all__ = [
    "ActionKind",
    "ActionRef",
    "MAIN_MENU",
    "MENU_TREE",
    "MenuController",
    "MenuItem",
    "MenuNode",
    "MenuResult",
    "all_menus",
    "find_item",
    "get_menu",
    "menu_keys",
    "menu_labels",
    "menu_registry",
    "normalize_menu_key",
]
