"""Types and constants for graph_engine."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from .types import GraphDomain, KnowledgeEdge, KnowledgeNode, KnowledgeQuery, KnowledgeSearchResult

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"

DB_PATH = DB_DIR / "knowledge_graph.sqlite"
