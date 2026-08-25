"""Navigation contracts for FortifyLab's Python TUI migration."""

from .baseline import MAIN_MENU, MENU_TREE
from .models import ActionKind, ActionRef, MenuItem, MenuNode
from .registry import all_menus, find_item, get_menu, menu_keys, menu_labels, menu_registry

__all__ = [
    "ActionKind",
    "ActionRef",
    "MAIN_MENU",
    "MENU_TREE",
    "MenuItem",
    "MenuNode",
    "all_menus",
    "find_item",
    "get_menu",
    "menu_keys",
    "menu_labels",
    "menu_registry",
]
