"""
SchemaDesigner main class — inherits from all mixins.
"""

from ._design import DesignMixin
from ._sql_gen import SQLGenMixin
from ._python_gen import PythonGenMixin
from ._fallbacks import FallbackMixin


class SchemaDesigner(DesignMixin, SQLGenMixin, PythonGenMixin, FallbackMixin):
    """
    Diseñador de esquemas de base de datos.

    Convierte descripciones en lenguaje natural a esquemas SQLite
    completos con modelos Python, SQL DDL y migraciones.
    """

    def __init__(self, thinking_engine=None):
        self._thinking = thinking_engine
