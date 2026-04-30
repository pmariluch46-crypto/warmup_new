"""
core/query_selector.py  --  Selects queries per category based on session config.
"""

import json
import os
import random

from core.paths import data_file


def load_queries():
    with open(data_file("queries.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def select_queries(selected_categories, browse1_minutes, browse2_minutes,
                   min_per_category=5, max_per_category=20):
    """
    Returns two lists: (block1_phases, block2_phases)
    Each item is a dict: {"category": str, "query": str}

    Logic:
    - Total browse minutes = browse1 + browse2
    - Each phase takes roughly AVG_PHASE_MINUTES minutes
    - Total phases = total_minutes / AVG_PHASE_MINUTES
    - Distribute evenly across selected categories (capped at min/max per category)
    - Split result proportionally between block1 and block2
    """
    AVG_PHASE_MINUTES = 3.5

    all_queries = load_queries()
    total_minutes = browse1_minutes + browse2_minutes
    total_phases  = max(len(selected_categories), int(total_minutes / AVG_PHASE_MINUTES))

    # How many phases per category
    base_per_cat = max(min_per_category,
                       min(max_per_category, total_phases // max(len(selected_categories), 1)))

    selected = []
    for category in selected_categories:
        pool = all_queries.get(category, [])
        if not pool:
            continue
        count = random.randint(
            min(min_per_category, len(pool)),
            min(max_per_category, base_per_cat, len(pool))
        )
        chosen = random.sample(pool, count)
        for query in chosen:
            selected.append({"category": category, "query": query})

    random.shuffle(selected)

    # Split proportionally between block1 and block2
    total = len(selected)
    if total == 0:
        return [], []

    ratio1 = browse1_minutes / max(total_minutes, 1)
    split  = max(1, min(total - 1, round(total * ratio1)))

    block1 = selected[:split]
    block2 = selected[split:]

    return block1, block2


def save_queries(queries_dict):
    with open(data_file("queries.json"), "w", encoding="utf-8") as f:
        json.dump(queries_dict, f, indent=2, ensure_ascii=False)


def add_query(category, query):
    data = load_queries()
    if category not in data:
        data[category] = []
    if query not in data[category]:
        data[category].append(query)
        save_queries(data)
        return True
    return False


def remove_query(category, query):
    data = load_queries()
    if category in data and query in data[category]:
        data[category].remove(query)
        save_queries(data)
        return True
    return False


def update_query(category, old_query, new_query):
    data = load_queries()
    if category in data and old_query in data[category]:
        idx = data[category].index(old_query)
        data[category][idx] = new_query
        save_queries(data)
        return True
    return False


def get_categories():
    return list(load_queries().keys())
