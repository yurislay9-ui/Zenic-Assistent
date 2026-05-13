"""
EvidenceCollector - Recolector de evidencia determinística.

Recolecta evidencia a favor y en contra de una decisión
usando SOLO sistemas determinísticos (sin IA).

Tipos de evidencia que puede recolectar:
  - AST validation (sintaxis válida?)
  - Pattern matching (coincide con patrón conocido?)
  - Security checks (es seguro?)
  - Type safety (tipos correctos?)
  - Regex matching (coincide por regex?)
  - Keyword classification (clasificación por keywords?)
  - Cache lookup (ya verificado antes?)
  - Rule engine (cumple las reglas?)
  - Sandbox trial (pasó sandbox?)
"""

import re
import ast
import logging
from typing import Dict, Any, List, Optional

from .types import Evidence, EvidenceType, Verdict, DeterministicResult


logger = logging.getLogger(__name__)


# === Seguridad: Patrones peligrosos que NUNCA deben aprobarse ===
DANGEROUS_PATTERNS = [
    (r'\bexec\s*\(', "exec() call - arbitrary code execution"),
    (r'\beval\s*\(', "eval() call - arbitrary code execution"),
    (r'\b__import__\s*\(', "__import__() call - dynamic import"),
    (r'\bos\.system\s*\(', "os.system() - shell command execution"),
    (r'\bsubprocess\.call\s*\(', "subprocess.call() - process execution"),
    (r'\bsubprocess\.Popen\s*\(', "subprocess.Popen() - process execution"),
    (r'\bopen\s*\(["\'](/etc|/proc|/sys)', "sensitive file access"),
    (r'\brm\s+-rf', "dangerous rm -rf command"),
    (r'\bshutil\.rmtree', "directory tree deletion"),
    (r'\bpickle\.loads?\s*\(', "pickle deserialization - RCE risk"),
    (r'\byaml\.load\s*\([^)]*\)', "yaml.load without SafeLoader"),
    (r'\bsocket\s*\(', "raw socket creation"),
    (r'\bctypes\b', "ctypes - FFI access"),
]

# === Patrones seguros que siempre aprueban ===
SAFE_PATTERNS = [
    (r'\bdef\s+\w+\s*\(', "function definition"),
    (r'\bclass\s+\w+', "class definition"),
    (r'\breturn\s+', "return statement"),
    (r'\bimport\s+\w+', "standard import"),
    (r'\bfrom\s+\w+\s+import', "from import"),
    (r'@\w+', "decorator"),
    (r'\bif\s+__name__\s*==\s*["\']__main__["\']', "main guard"),
]

# === Keywords para clasificación de intención ===
OP_KEYWORDS = {
    "CREATE": ["create", "new", "add", "implement", "crear", "nuevo", "agregar", "generar", "build", "make", "escribir", "write"],
    "REFACTOR": ["refactor", "restructure", "reorganize", "refactorizar", "reestructurar", "clean", "simplify", "mejorar", "limpiar"],
    "DELETE": ["delete", "remove", "eliminate", "eliminar", "borrar", "quitar", "drop", "remover"],
    "SEARCH": ["search", "find", "where", "locate", "buscar", "encontrar", "donde", "localizar"],
    "ANALYZE": ["analyze", "review", "check", "analizar", "revisar", "verificar", "examine", "inspeccionar"],
    "EXPLAIN": ["explain", "describe", "what does", "explicar", "describir", "como funciona", "que hace"],
    "DEBUG": ["debug", "fix", "correct", "bug", "error", "corregir", "arreglar", "depurar", "reparar"],
    "OPTIMIZE": ["optimize", "improve", "faster", "optimizar", "mejorar", "acelerar", "performance", "rendimiento"],
}

GOAL_KEYWORDS = {
    "BUG_FIX": ["bug", "fix", "error", "corregir", "arreglar", "wrong", "broken", "falla", "defecto"],
    "FEATURE_ADD": ["add", "new", "feature", "agregar", "nueva", "implement", "crear", "nueva funcionalidad"],
    "SECURITY_HARDEN": ["security", "auth", "login", "token", "crypto", "vulnerability", "seguridad", "autenticar"],
    "PERFORMANCE": ["optimize", "fast", "slow", "performance", "optimizar", "rapido", "lento", "velocidad"],
    "MODERN_PATTERN": ["modern", "update", "upgrade", "moderno", "actualizar", "migrate", "migrar"],
    "COMPLEXITY_REDUCTION": ["simplify", "reduce", "complex", "simplificar", "reducir", "complejo"],
    "READABILITY": ["readable", "clean", "comment", "legible", "limpio", "documentar", "claro"],
}


class EvidenceCollector:
    """
    Recolector de evidencia puramente determinístico.

    NO usa IA. Solo usa análisis estático, regex, reglas y patrones.
    Cada método devuelve una lista de Evidence objects que luego
    el ConsensusResolver evalúa.
    """

    def collect_intent_evidence(self, text: str) -> List[Evidence]:
        """
        Recolecta evidencia sobre la intención del texto.

        Usa keyword matching con scoring ponderado.
        Produce evidencia a favor de cada operación posible.
        """
        evidence = []
        text_lower = text.lower()
        words = text_lower.split()

        for op, keywords in OP_KEYWORDS.items():
            score = 0
            matched_keywords = []
            for kw in keywords:
                if kw in words:
                    score += 2  # Match de palabra completa (más fuerte)
                    matched_keywords.append(kw)
                elif kw in text_lower:
                    score += 1  # Match de substring (más débil)
                    matched_keywords.append(kw)

            if score > 0:
                # Normalizar score a peso de evidencia
                weight = min(score / 8.0, 1.0)
                evidence.append(Evidence(
                    evidence_type=EvidenceType.KEYWORD_CLASSIFY,
                    favors=Verdict.YES,
                    weight=weight,
                    source=f"keyword_{op}",
                    detail=f"Keywords matched: {', '.join(matched_keywords[:5])}",
                    metadata={"operation": op, "score": score, "keywords": matched_keywords},
                ))
            else:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.KEYWORD_CLASSIFY,
                    favors=Verdict.NO,
                    weight=0.1,
                    source=f"keyword_{op}",
                    detail=f"No keywords matched for {op}",
                    metadata={"operation": op, "score": 0},
                ))

        return evidence

    def collect_goal_evidence(self, text: str) -> List[Evidence]:
        """Recolecta evidencia sobre el goal del texto."""
        evidence = []
        text_lower = text.lower()

        for goal, keywords in GOAL_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                weight = min(score / 4.0, 1.0)
                evidence.append(Evidence(
                    evidence_type=EvidenceType.KEYWORD_CLASSIFY,
                    favors=Verdict.YES,
                    weight=weight,
                    source=f"goal_{goal}",
                    detail=f"Goal keywords: {score} matched",
                    metadata={"goal": goal, "score": score},
                ))

        return evidence

    def collect_code_safety_evidence(self, code: str) -> List[Evidence]:
        """
        Recolecta evidencia sobre la seguridad del código.

        Escanea patrones peligrosos y seguros.
        Si encuentra patrones peligrosos → evidencia en contra (NO).
        Si solo encuentra patrones seguros → evidencia a favor (YES).
        """
        evidence = []

        # Check dangerous patterns
        danger_found = []
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                danger_found.append(description)
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SECURITY_CHECK,
                    favors=Verdict.NO,
                    weight=0.9,  # Muy fuerte: código peligroso
                    source="security_scanner",
                    detail=f"Pattern: {description}",
                    metadata={"pattern": pattern, "danger_level": "high"},
                ))

        if not danger_found:
            evidence.append(Evidence(
                evidence_type=EvidenceType.SECURITY_CHECK,
                favors=Verdict.YES,
                weight=0.6,
                source="security_scanner",
                detail="No dangerous patterns detected",
            ))

        # Check safe patterns
        safe_count = 0
        for pattern, description in SAFE_PATTERNS:
            if re.search(pattern, code):
                safe_count += 1

        if safe_count > 0:
            evidence.append(Evidence(
                evidence_type=EvidenceType.PATTERN_MATCH,
                favors=Verdict.YES,
                weight=0.3,
                source="safe_pattern_scanner",
                detail=f"{safe_count} safe patterns detected",
            ))

        return evidence

    def collect_syntax_evidence(self, code: str, language: str = "python") -> List[Evidence]:
        """
        Recolecta evidencia sobre la validez sintáctica del código.

        Usa ast.parse() para Python, regex básico para otros lenguajes.
        """
        evidence = []

        if language == "python":
            try:
                ast.parse(code)
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors=Verdict.YES,
                    weight=0.8,
                    source="ast_parser",
                    detail="Python code parses successfully",
                ))
            except SyntaxError as e:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors=Verdict.NO,
                    weight=0.9,
                    source="ast_parser",
                    detail=f"Syntax error: {e.msg} at line {e.lineno}",
                    metadata={"line": e.lineno, "msg": e.msg},
                ))

        elif language in ("javascript", "typescript"):
            # Basic JS/TS validation: balanced braces, no obvious syntax errors
            open_braces = code.count('{') + code.count('(') + code.count('[')
            close_braces = code.count('}') + code.count(')') + code.count(']')
            if open_braces == close_braces:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors=Verdict.YES,
                    weight=0.5,
                    source="brace_counter",
                    detail="Braces are balanced",
                ))
            else:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors=Verdict.NO,
                    weight=0.7,
                    source="brace_counter",
                    detail=f"Unbalanced braces: {open_braces} open vs {close_braces} close",
                ))

        return evidence

    def collect_entity_evidence(self, text: str) -> List[Evidence]:
        """
        Recolecta evidencia sobre entidades extraídas del texto.

        Usa regex para detectar archivos, lenguajes y funciones.
        """
        evidence = []

        # File detection
        file_match = re.search(r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text)
        if file_match:
            evidence.append(Evidence(
                evidence_type=EvidenceType.REGEX_MATCH,
                favors=Verdict.YES,
                weight=0.7,
                source="file_extractor",
                detail=f"File detected: {file_match.group(1)}",
                metadata={"file": file_match.group(1)},
            ))

        # Function detection
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        if func_match:
            evidence.append(Evidence(
                evidence_type=EvidenceType.REGEX_MATCH,
                favors=Verdict.YES,
                weight=0.6,
                source="function_extractor",
                detail=f"Function detected: {func_match.group(1)}",
                metadata={"function": func_match.group(1)},
            ))

        # Code block detection
        if '```' in text or 'def ' in text or 'class ' in text or 'function ' in text:
            evidence.append(Evidence(
                evidence_type=EvidenceType.REGEX_MATCH,
                favors=Verdict.YES,
                weight=0.5,
                source="code_block_detector",
                detail="Code block detected in input",
            ))

        return evidence

    def collect_all_evidence(self, text: str, code: str = "",
                             language: str = "python") -> List[Evidence]:
        """
        Recolecta TODA la evidencia disponible para una decisión.

        Este es el método principal que se llama antes del consenso.
        No usa IA en absoluto.
        """
        all_evidence = []

        # Intent evidence
        all_evidence.extend(self.collect_intent_evidence(text))

        # Goal evidence
        all_evidence.extend(self.collect_goal_evidence(text))

        # Entity evidence
        all_evidence.extend(self.collect_entity_evidence(text))

        # Code evidence (if code provided)
        if code:
            all_evidence.extend(self.collect_code_safety_evidence(code))
            all_evidence.extend(self.collect_syntax_evidence(code, language))

        return all_evidence
