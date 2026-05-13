"""
SemanticEngine: main class inheriting all mixins.
"""

from ._imports import INTENT_PROTOTYPES, GOAL_PROTOTYPES
from ._mixin_lifecycle import LifecycleMixin
from ._mixin_embed import EmbedMixin
from ._mixin_classify import ClassifyMixin
from ._mixin_search import SearchMixin


class SemanticEngine(LifecycleMixin, EmbedMixin, ClassifyMixin, SearchMixin):
    """
    Especialista semántico multilingual.

    Comprende INTENCIÓN más allá de las palabras clave.
    "crear módulo auth" ≈ "create authentication module" ≈ 0.82 similitud.

    Usa embeddings de 384 dimensiones para:
    - Clasificar intención por similitud con prototypes
    - Buscar en memoria semántica
    - Detectar similitud entre consultas
    - Zero-shot classification
    """

    def __init__(self, auto_load: bool = True):
        # Store prototype data references for _build_prototypes
        self._intent_prototypes = INTENT_PROTOTYPES
        self._goal_prototypes_data = GOAL_PROTOTYPES
        # Initialize lifecycle (which may call load_model → _build_prototypes)
        self._init_lifecycle(auto_load=auto_load)
