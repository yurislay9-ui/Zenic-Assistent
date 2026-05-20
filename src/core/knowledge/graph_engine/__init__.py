"""Re-exports for graph_engine package."""

from ._types import *
from ._helpers import *
from ._mixin_queries import *
from ._mixin_core import *

import threading
from typing import Optional

_instance: Optional[KnowledgeGraphEngine] = None
_instance_lock = threading.Lock()
def get_knowledge_graph() -> KnowledgeGraphEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KnowledgeGraphEngine()
    return _instance


def reset_knowledge_graph() -> None:
    global _instance
    with _instance_lock:
        _instance = None
