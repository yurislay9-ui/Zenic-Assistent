"""
Mixin: Intent classification (zero-shot via prototype similarity).

FIX (Phase 2): Replaced static `np` import with _get_numpy() lazy loading.
Now _build_prototypes actually works when numpy is available.
"""

from ._imports import SemanticResult, _get_numpy, HAS_NUMPY, logger

# Named constants (previously magic numbers)
_KEYWORD_CONFIDENCE_DIVISOR = 10.0
_MAX_FALLBACK_CONFIDENCE = 0.5


class ClassifyMixin:
    """Intent classification and prototype building for SemanticEngine."""

    def classify_intent(self, text: str) -> SemanticResult:
        """
        Clasifica intención del usuario usando similitud con prototypes.

        Zero-shot: compara el embedding del texto con los embeddings
        promedio de cada categoría de intención (multilingual).

        Esto es lo que Qwen NO hace bien → SemanticEngine lo compensa.
        """
        if self.is_loaded:
            query_emb = self.embed(text)
            if query_emb is not None:
                # Compute similarity with each intent prototype
                op_sims = {}
                for intent, proto_emb in self._prototype_embeddings.items():
                    op_sims[intent] = self.similarity(query_emb, proto_emb)

                # Find best operation
                best_op = max(op_sims, key=op_sims.get)
                best_op_sim = op_sims[best_op]

                # Compute goal similarities
                goal_sims = {}
                for goal, proto_emb in self._goal_prototype_embeddings.items():
                    goal_sims[goal] = self.similarity(query_emb, proto_emb)

                best_goal = max(goal_sims, key=goal_sims.get)
                best_goal_sim = goal_sims[best_goal]

                # Confidence: average of operation and goal similarity
                confidence = (best_op_sim + best_goal_sim) / 2.0

                return SemanticResult(
                    operation=best_op,
                    goal=best_goal,
                    confidence=confidence,
                    source="embedding",
                    similarities={**op_sims, **{f"goal_{k}": v for k, v in goal_sims.items()}},
                )

        # Fallback: keyword matching (same as MiniAIEngine fallback)
        return self._fallback_classify(text)

    def _build_prototypes(self):
        """Pre-computa embeddings promedio para cada intención."""
        np = _get_numpy()
        if np is None:
            logger.warning(
                "SemanticEngine: numpy not available, skipping prototype building. "
                "Install numpy to enable prototype-based classification."
            )
            return

        # Build operation prototypes
        for intent, examples in self._intent_prototypes.items():
            embeddings = self.embed_batch(examples)
            if embeddings:
                # Mean of all prototype embeddings, then normalize
                mean_emb = np.mean(embeddings, axis=0)
                norm = np.linalg.norm(mean_emb)
                if norm > 0:
                    mean_emb = mean_emb / norm
                self._prototype_embeddings[intent] = mean_emb

        # Build goal prototypes
        for goal, examples in self._goal_prototypes_data.items():
            embeddings = self.embed_batch(examples)
            if embeddings:
                mean_emb = np.mean(embeddings, axis=0)
                norm = np.linalg.norm(mean_emb)
                if norm > 0:
                    mean_emb = mean_emb / norm
                self._goal_prototype_embeddings[goal] = mean_emb

        logger.info(
            "SemanticEngine: Built %d op prototypes, %d goal prototypes",
            len(self._prototype_embeddings),
            len(self._goal_prototype_embeddings),
        )

    def _fallback_classify(self, text: str) -> SemanticResult:
        """Fallback: keyword-based classification (same as MiniAIEngine)."""
        text_lower = text.lower()

        op_keywords = {
            "CREATE": ["create", "new", "add", "implement", "crear", "nuevo", "agregar", "generar"],
            "REFACTOR": ["refactor", "restructure", "reorganize", "refactorizar", "reestructurar"],
            "DELETE": ["delete", "remove", "eliminate", "eliminar", "borrar", "quitar"],
            "SEARCH": ["search", "find", "where", "locate", "buscar", "encontrar", "donde"],
            "ANALYZE": ["analyze", "review", "check", "analizar", "revisar", "verificar"],
            "EXPLAIN": ["explain", "describe", "what does", "explicar", "describir", "como funciona"],
            "DEBUG": ["debug", "fix", "correct", "bug", "error", "corregir", "arreglar", "depurar"],
            "OPTIMIZE": ["optimize", "improve", "faster", "optimizar", "mejorar", "acelerar"],
        }

        best_op, best_score = "SEARCH", 0
        for op, keywords in op_keywords.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_score:
                best_score, best_op = score, op

        goal_keywords = {
            "BUG_FIX": ["bug", "fix", "error", "corregir", "arreglar"],
            "FEATURE_ADD": ["add", "new", "feature", "agregar", "nueva"],
            "SECURITY_HARDEN": ["security", "auth", "login", "seguridad"],
            "PERFORMANCE": ["optimize", "fast", "slow", "optimizar", "rapido"],
        }

        best_goal, best_gscore = "FEATURE_ADD", 0
        for goal, keywords in goal_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_gscore:
                best_gscore, best_goal = score, goal

        return SemanticResult(
            operation=best_op,
            goal=best_goal,
            confidence=min(best_score / _KEYWORD_CONFIDENCE_DIVISOR, _MAX_FALLBACK_CONFIDENCE),
            source="fallback",
        )
