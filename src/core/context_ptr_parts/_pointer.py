"""
ContextPointer class — pointer referencing code on disk.
"""

import os
import hashlib
import logging
from typing import Optional, List

from ._imports import logger, FunctionSignature


class ContextPointer:
    """
    Puntero de contexto que referencia código en disco.

    En vez de pasar el código completo al modelo, se pasa un puntero
    compacto con las coordenadas del código relevante.
    """

    def __init__(self, signature: FunctionSignature, relevance_score: float = 0.0,
                 reason: str = ""):
        self.signature = signature
        self.relevance_score = relevance_score
        self.reason = reason  # Why this function is relevant

    def to_model_context(self) -> str:
        """Genera la representación compacta para enviar al modelo."""
        pointer = self.signature.to_pointer()
        doc = f'  """{self.signature.docstring[:100]}"""' if self.signature.docstring else ""
        reason = f"  # Relevante: {self.reason}" if self.reason else ""
        calls = f"  # Llama a: {', '.join(self.signature.calls[:5])}" if self.signature.calls else ""
        return f"{pointer}{doc}{reason}{calls}"

    def load_code_from_disk(self) -> str:
        """Carga el código real desde el archivo en disco."""
        try:
            if os.path.isfile(self.signature.file_path):
                with open(self.signature.file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                start = max(0, self.signature.line_start - 1)
                end = min(len(lines), self.signature.line_end)
                return "".join(lines[start:end])
        except Exception as e:
            logger.error(f"ContextPointer: Error loading code from disk: {e}")
        return ""

    def apply_modification(self, new_code: str,
                           sibling_pointers: Optional[List['ContextPointer']] = None) -> bool:
        """
        Aplica una modificación directamente al archivo en disco
        usando coordenadas del puntero.

        Args:
            new_code: The replacement code for this pointer's range.
            sibling_pointers: Other ContextPointer objects for the same file whose
                line numbers should be adjusted after this modification. If not
                provided, sibling pointers will NOT be adjusted (known limitation).
        """
        try:
            if not os.path.isfile(self.signature.file_path):
                logger.error(f"ContextPointer: File not found: {self.signature.file_path}")
                return False

            with open(self.signature.file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            start = max(0, self.signature.line_start - 1)
            end = min(len(lines), self.signature.line_end)

            old_line_count = end - start

            # Reemplazar las líneas
            new_lines = new_code.splitlines(keepends=True)
            new_line_count = len(new_lines)
            lines[start:end] = new_lines

            with open(self.signature.file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            # Calculate line delta for sibling adjustment
            line_delta = new_line_count - old_line_count

            # Save original end before updating (needed for sibling comparison)
            original_line_end = self.signature.line_end

            # Update own signature
            self.signature.line_end = self.signature.line_start + new_line_count - 1
            new_hash = hashlib.sha256(new_code.encode()).hexdigest()[:16]
            self.signature.hash = new_hash

            # Adjust sibling pointers' line numbers for the same file
            if sibling_pointers:
                self._adjust_siblings(sibling_pointers, line_delta, original_line_end)
            elif line_delta != 0:
                # TODO: Without sibling_pointers, modifications that change line counts
                # will cause other ContextPointer objects for the same file to have
                # stale line_start/line_end values. Callers should pass sibling_pointers
                # obtained from SignatureIndex._signatures[file_path] to ensure
                # all pointers remain consistent after modifications.
                logger.warning(
                    f"ContextPointer: Line delta={line_delta} but no sibling pointers "
                    f"provided. Other pointers for {self.signature.file_path} may "
                    f"have stale line numbers."
                )

            logger.info(
                f"ContextPointer: Applied modification to {self.signature.name} "
                f"@ {self.signature.file_path}:{self.signature.line_start}"
            )
            return True

        except Exception as e:
            logger.error(f"ContextPointer: Error applying modification: {e}")
            return False

    def _adjust_siblings(self, sibling_pointers: List['ContextPointer'],
                         line_delta: int, original_line_end: int = None):
        """
        Adjust line numbers of sibling ContextPointer objects that come AFTER
        this pointer in the same file.

        When a modification changes the number of lines, all subsequent
        pointers in the same file need their line_start and line_end
        shifted by the same delta.
        """
        if line_delta == 0:
            return

        # Use original line_end for comparison to avoid skipping siblings
        # that start at the same line as our new (expanded) end
        my_end = original_line_end if original_line_end is not None else self.signature.line_end
        for sibling in sibling_pointers:
            # Skip self and pointers that start before or at our original range
            if sibling is self:
                continue
            if sibling.signature.file_path != self.signature.file_path:
                continue
            if sibling.signature.line_start <= my_end:
                continue

            # Shift this sibling's line numbers
            sibling.signature.line_start += line_delta
            sibling.signature.line_end += line_delta
            logger.debug(
                f"ContextPointer: Adjusted sibling '{sibling.signature.name}' "
                f"by delta={line_delta} -> L{sibling.signature.line_start}-{sibling.signature.line_end}"
            )
