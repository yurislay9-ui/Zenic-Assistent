"""
ZENIC-AGENTS - Semantic Parser v16 (TF-IDF Real)

Parser de intenciones basado en TF-IDF con similitud coseno.
Soporta ingles y espanol. Sin dependencias externas (no numpy, no fastembed).
Compatible con Android.
"""

import re
import logging
from collections import Counter
from src.core.shared.contracts import IntentPayload, OperationType, GoalType


logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'can', 'shall',
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
    'it', 'its', 'this', 'that', 'these', 'those', 'and', 'or',
    'but', 'not', 'no', 'if', 'then', 'than', 'so', 'as', 'up',
})


class SemanticParser:
    """
    Parser semantico basado en TF-IDF mejorado.
    Usa frecuencia de terminos y similitud coseno para clasificar
    la intencion del usuario, sin depender de fastembed/numpy.
    """

    def __init__(self):
        self._semantic_engine = None  # Optional SemanticEngine for better classification
        self._smart_memory = None     # Optional SmartMemory for caching parsed results
        self.op_corpus = {
            OperationType.CREATE: [
                "create new file implement function add feature",
                "crear nuevo archivo implementar funcion agregar caracteristica",
                "generate new code create module build component",
                "write new class implement interface add endpoint",
                "nuevo modulo nueva funcion crear componente nuevo archivo",
                "scaffold new project create service add handler",
            ],
            OperationType.REFACTOR: [
                "optimize refactor improve performance clean code",
                "optimizar refactorizar mejorar rendimiento limpiar codigo",
                "restructure reorganize simplify reduce complexity",
                "modernize update pattern upgrade migrate legacy",
                "mejorar estructura simplificar logica reducir complejidad",
                "refactor extract method rename reorganize modules",
            ],
            OperationType.DELETE: [
                "delete remove eliminate unused code dead code",
                "eliminar borrar quitar codigo muerto sin usar",
                "remove deprecated strip out clean up remove function",
                "prune cut delete file remove class",
                "borrar funcion eliminar modulo quitar import",
            ],
            OperationType.SEARCH: [
                "search find where used locate definition reference",
                "buscar encontrar donde se usa localizar definicion referencia",
                "grep find all usages trace call hierarchy",
                "where is defined find implementation search pattern",
                "encontrar implementacion buscar referencia rastrear llamadas",
            ],
            OperationType.ANALYZE: [
                "analyze review check inspect examine code quality",
                "analizar revisar verificar inspeccionar calidad codigo",
                "audit scan evaluate assess code review",
                "detect issues find problems identify patterns",
                "revisar codigo analizar estructura evaluar calidad",
            ],
            OperationType.EXPLAIN: [
                "explain how does this work what does understand",
                "explicar como funciona que hace entender codigo",
                "describe clarify document walkthrough guide",
                "what is the purpose why does how to",
                "explicar proposito describir funcion documento",
            ],
            OperationType.DEBUG: [
                "debug fix error bug crash exception trace",
                "depurar corregir error fallo excepcion traza",
                "troubleshoot diagnose resolve issue stack trace",
                "fix broken repair patch solve bug",
                "corregir fallo arreglar parche solucionar error",
            ],
            OperationType.OPTIMIZE: [
                "optimize speed performance faster efficient improve",
                "optimizar velocidad rendimiento rapido eficiente mejorar",
                "accelerate reduce latency cache parallel async",
                "profile bottleneck slow memory optimization",
                "acelerar reducir latencia mejorar rendimiento cache",
            ],
        }

        self.goal_corpus = {
            GoalType.COMPLEXITY_REDUCTION: [
                "reduce complexity simplify shorter cleaner cyclomatic",
                "reducir complejidad simplificar mas corto limpio",
                "decrease nesting flatten refactor extract method",
                "lower cognitive load readable maintainable",
            ],
            GoalType.MODERN_PATTERN: [
                "modern pattern update latest standard best practice",
                "patron moderno actualizar ultimo estandar mejor practica",
                "upgrade migrate newer version current idiomatic",
                "contemporary style conventional recommended approach",
            ],
            GoalType.BUG_FIX: [
                "fix bug error correct wrong broken crash",
                "corregir error fallo arreglo reparar arreglar",
                "patch resolve issue unexpected behavior defect",
                "solve problem address failure handle edge case",
            ],
            GoalType.FEATURE_ADD: [
                "add feature new functionality extend enhance capability",
                "agregar funcion nueva caracteristica extender mejorar",
                "implement support introduce enable additional",
                "augment supplement expand grow incorporate",
            ],
            GoalType.SECURITY_HARDEN: [
                "security vulnerability injection auth crypto sanitize",
                "seguridad vulnerabilidad inyeccion autenticacion cifrado",
                "harden protect validate escape prevent exploit",
                "OWASP XSS CSRF SQL injection token encryption",
            ],
            GoalType.PERFORMANCE: [
                "performance speed fast latency throughput benchmark",
                "rendimiento velocidad rapido latencia rendimiento",
                "optimize cache async parallel concurrent efficient",
                "bottleneck profile memory CPU reduce overhead",
            ],
            GoalType.READABILITY: [
                "readability clean clear documented naming convention",
                "legibilidad limpio claro documentado nombre convencion",
                "self-documenting expressive meaningful comments style",
                "maintainable understandable organized structured",
            ],
        }

        self.op_tfidf = self._build_tfidf(self.op_corpus)
        self.goal_tfidf = self._build_tfidf(self.goal_corpus)

    def _tokenize(self, text):
        text = text.lower()
        text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.split()
        return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]

    def _build_tfidf(self, corpus):
        doc_freq = Counter()
        all_tokens = {}
        for key, docs in corpus.items():
            all_tokens[key] = []
            for doc in docs:
                tokens = self._tokenize(doc)
                all_tokens[key].append(tokens)
                unique_tokens = set(tokens)
                for t in unique_tokens:
                    doc_freq[t] += 1
        total_docs = sum(len(docs) for docs in corpus.values())
        idf = {}
        for term, freq in doc_freq.items():
            idf[term] = max(1.0, (total_docs / (freq + 1)))
        return {"tokens": all_tokens, "idf": idf}

    def _cosine_similarity(self, vec_a, vec_b):
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        if not common_keys:
            return 0.0
        dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
        norm_a = sum(v ** 2 for v in vec_a.values()) ** 0.5
        norm_b = sum(v ** 2 for v in vec_b.values()) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _score_against_corpus(self, query_tokens, tfidf_data):
        query_tf = Counter(query_tokens)
        query_vec = {}
        for token, freq in query_tf.items():
            idf_val = tfidf_data["idf"].get(token, 1.0)
            query_vec[token] = freq * idf_val
        scores = {}
        for key, doc_lists in tfidf_data["tokens"].items():
            max_sim = 0.0
            for doc_tokens in doc_lists:
                doc_tf = Counter(doc_tokens)
                doc_vec = {}
                for token, freq in doc_tf.items():
                    idf_val = tfidf_data["idf"].get(token, 1.0)
                    doc_vec[token] = freq * idf_val
                sim = self._cosine_similarity(query_vec, doc_vec)
                max_sim = max(max_sim, sim)
            scores[key] = max_sim
        return scores

    def set_semantic_engine(self, engine):
        """Inyecta un SemanticEngine para clasificacion basada en embeddings."""
        self._semantic_engine = engine

    def set_smart_memory(self, memory):
        """Inyecta SmartMemory para almacenar/recuperar resultados parseados."""
        self._smart_memory = memory

    def parse(self, text):
        # Try SmartMemory cache first
        if self._smart_memory:
            cached = self._smart_memory.check_cache(text)
            if cached and cached.get("operation") and cached.get("goal"):
                try:
                    return IntentPayload(
                        op=cached["operation"],
                        goal=cached["goal"],
                        target=cached.get("target", "unknown"),
                        confidence=cached.get("importance", 0.5),
                        language=cached.get("language", "python"),
                        context=text,
                    )
                except (ValueError, KeyError, TypeError):
                    pass  # Fall through to normal parsing

        # Try SemanticEngine for better classification if available
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                classification = self._semantic_engine.classify_intent(text)
                if classification and hasattr(classification, 'operation') and classification.operation:
                    # SemanticEngine returned a SemanticResult dataclass
                    result = IntentPayload(
                        op=classification.operation,
                        goal=classification.goal if hasattr(classification, 'goal') else "FEATURE_ADD",
                        confidence=classification.confidence if hasattr(classification, 'confidence') else 0.8,
                        context=text,
                    )
                    # Cache the result in SmartMemory
                    if self._smart_memory:
                        self._smart_memory.save_to_cache(
                            query=text,
                            response=f"op={result.op},goal={result.goal}",
                            operation=result.op,
                            goal=result.goal,
                            importance=result.confidence,
                        )
                    return result
            except Exception as e:
                logger.debug(f"SemanticParser: SemanticEngine classification failed, falling back to TF-IDF: {e}")

        # Fallback: existing TF-IDF classification
        tokens = self._tokenize(text)
        if not tokens:
            return IntentPayload(op=OperationType.SEARCH, confidence=0.0)

        op_scores = self._score_against_corpus(tokens, self.op_tfidf)
        best_op = max(op_scores, key=op_scores.get)
        best_op_score = op_scores[best_op]

        goal_scores = self._score_against_corpus(tokens, self.goal_tfidf)
        best_goal = max(goal_scores, key=goal_scores.get)
        best_goal_score = goal_scores[best_goal]

        tgt = re.search(r'([\w\.\-]+(?:\.kt|\.py|\.go|\.js|\.ts|\.java|\.rs|\.c|\.cpp|\.h))', text)
        target = tgt.group(1) if tgt else "unknown"

        lang = "python"
        if ".kt" in target: lang = "kotlin"
        elif ".go" in target: lang = "go"
        elif ".js" in target: lang = "javascript"
        elif ".ts" in target: lang = "typescript"
        elif ".java" in target: lang = "java"
        elif ".rs" in target: lang = "rust"

        code_lang, raw_code = self._extract_code(text)
        scrap_query = ""
        if best_op in [OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR]:
            scrap_query = f"modern {best_goal} {best_op} {lang}"

        confidence = round((best_op_score + best_goal_score) / 2, 3)
        result = IntentPayload(
            op=best_op, target=target, goal=best_goal,
            scrap_query=scrap_query, confidence=confidence,
            language=code_lang or lang, raw_code=raw_code or "",
            context=text
        )

        # Cache the TF-IDF result in SmartMemory for future lookups
        if self._smart_memory:
            try:
                self._smart_memory.save_to_cache(
                    query=text,
                    response=f"op={result.op},goal={result.goal}",
                    operation=result.op,
                    goal=result.goal,
                    importance=result.confidence,
                )
            except Exception as e:
                logger.debug(f"SemanticParser: Failed to cache TF-IDF result in SmartMemory: {e}")

        return result

    def _extract_code(self, text):
        """Extrae bloques de codigo de un mensaje."""
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            lang, code = matches[0]
            lang_map = {
                'python': 'python', 'py': 'python',
                'kotlin': 'kotlin', 'kt': 'kotlin',
                'go': 'go',
                'javascript': 'javascript', 'js': 'javascript',
                'typescript': 'typescript', 'ts': 'typescript',
                'java': 'java', 'rust': 'rust', 'rs': 'rust',
                'c': 'c', 'cpp': 'cpp', 'c++': 'cpp',
            }
            return lang_map.get(lang.lower(), 'python'), code
        code_indicators = ['def ', 'class ', 'function ', 'fun ', 'func ', 'import ', 'from ']
        lines = text.strip().split('\n')
        code_lines = [l for l in lines if any(ind in l for ind in code_indicators)]
        if code_lines:
            return 'python', text.strip()
        return None, None
