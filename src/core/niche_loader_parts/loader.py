"""NicheLoader main class combining all mixins."""

from ._imports import logger, NICHE_ROOT
from .loading import LoadingMixin
from .query import QueryMixin
from .stats import StatsMixin


class NicheLoader(
    LoadingMixin,
    QueryMixin,
    StatsMixin,
):
    """
    Cargador de plantillas YAML de nichos.

    Escanea el directorio de nichos, carga definiciones YAML,
    y provee busqueda/resolucion por nombre, dominio o keywords.
    """

    def __init__(self, niche_root: str = ""):
        self._root = niche_root or NICHE_ROOT
        self._niches = {}
        self._domain_index = {}
        self._loaded = False
