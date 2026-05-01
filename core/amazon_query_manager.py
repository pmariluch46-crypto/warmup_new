"""
core/amazon_query_manager.py  --  CRUD helpers for data/amazon_queries.json.
"""

import json
import os

from core.paths import data_file

_PATH = data_file("amazon_queries.json")


def load_amazon_queries() -> dict:
    with open(_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_amazon_queries(data: dict):
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_amazon_categories() -> list:
    return list(load_amazon_queries().keys())


def add_amazon_query(category: str, query: str) -> bool:
    data = load_amazon_queries()
    if category not in data:
        data[category] = []
    if query not in data[category]:
        data[category].append(query)
        save_amazon_queries(data)
        return True
    return False


def remove_amazon_query(category: str, query: str) -> bool:
    data = load_amazon_queries()
    if category in data and query in data[category]:
        data[category].remove(query)
        save_amazon_queries(data)
        return True
    return False


def update_amazon_query(category: str, old_query: str, new_query: str) -> bool:
    data = load_amazon_queries()
    if category in data and old_query in data[category]:
        idx = data[category].index(old_query)
        data[category][idx] = new_query
        save_amazon_queries(data)
        return True
    return False
