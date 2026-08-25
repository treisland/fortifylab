"""Lookup helpers for FortifyLab navigation models."""

from __future__ import annotations

from .baseline import MENU_TREE
from .models import MenuItem, MenuNode


def all_menus() -> tuple[MenuNode, ...]:
    return MENU_TREE


def menu_registry() -> dict[str, MenuNode]:
    return {menu.id: menu for menu in MENU_TREE}


def get_menu(menu_id: str) -> MenuNode:
    try:
        return menu_registry()[menu_id]
    except KeyError as exc:
        raise KeyError(f"unknown navigation menu: {menu_id}") from exc


def menu_keys(menu_id: str) -> tuple[str, ...]:
    return get_menu(menu_id).keys()


def menu_labels(menu_id: str) -> tuple[str, ...]:
    return get_menu(menu_id).labels()


def find_item(menu_id: str, key: str) -> MenuItem | None:
    return get_menu(menu_id).item_for_key(key)
