#!/usr/bin/env python3
"""
Live AMI inventory cache.

Discover the extension list, extension display names and queue names directly from
Asterisk over AMI (PJSIPShowEndpoints / SIPpeers / QueueSummary) and cache them here.
db_manager reads from this cache so the rest of the app sees a single inventory source.

The AMI monitor calls set_inventory() at startup and on every "sync"; the getters are
safe to call from synchronous code (they only read in-memory dicts under a lock).
"""

import threading
from typing import Dict, List

_lock = threading.Lock()
_names: Dict[str, str] = {}    # extension -> display name
_queues: Dict[str, str] = {}   # queue extension/name -> display name


def set_inventory(names: Dict[str, str], queues: Dict[str, str]) -> None:
    """Replace the cached inventory. Called by the AMI monitor after a discovery pass."""
    global _names, _queues
    with _lock:
        _names = {str(k): (str(v) if v else str(k)) for k, v in (names or {}).items() if k}
        _queues = {str(k): (str(v) if v else str(k)) for k, v in (queues or {}).items() if k}


def get_extensions() -> List[str]:
    """Return the cached extension numbers (sorted; numeric-first ordering)."""
    with _lock:
        keys = list(_names.keys())

    def _sort_key(e: str):
        return (0, int(e)) if e.isdigit() else (1, e)

    return sorted(keys, key=_sort_key)


def get_extension_names() -> Dict[str, str]:
    """Return a copy of the extension -> name mapping."""
    with _lock:
        return dict(_names)


def get_queue_names() -> Dict[str, str]:
    """Return a copy of the queue -> name mapping."""
    with _lock:
        return dict(_queues)
