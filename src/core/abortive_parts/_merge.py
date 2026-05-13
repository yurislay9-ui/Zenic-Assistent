"""
AbortiveProtocol merge methods mixin.
"""

import logging

from ._imports import logger


class MergeMixin:
    """Code merge methods for AbortiveProtocol."""

    def merge_subtask_results(self, subtask_results, language="python"):
        """
        Combine code from multiple subtasks into one coherent module (Gap 4 Fix).
        """
        code_parts = []
        for result in subtask_results:
            if isinstance(result, dict):
                code = result.get("code", "")
                if code and result.get("status") not in ["ERROR", "MAX_DEPTH_REACHED"]:
                    code_parts.append(code)

        if not code_parts:
            return ""

        if language == "python":
            return self.merge_python_code(code_parts)
        elif language == "kotlin":
            return self.merge_block_code(code_parts, "//", "package")
        elif language == "go":
            return self.merge_go_code(code_parts)
        elif language == "javascript":
            return self.merge_block_code(code_parts, "//", None)
        return self.merge_python_code(code_parts)

    @staticmethod
    def merge_python_code(code_parts):
        """Merge Python code blocks: collect imports, deduplicate, then concatenate bodies."""
        all_imports = []
        all_bodies = []

        for code in code_parts:
            lines = code.split('\n')
            imports = []
            body = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
                    imports.append(stripped)
                else:
                    body.append(line)

            all_imports.extend(imports)
            all_bodies.append('\n'.join(body))

        seen_imports = set()
        unique_imports = []
        for imp in all_imports:
            if imp not in seen_imports:
                seen_imports.add(imp)
                unique_imports.append(imp)

        result = '\n'.join(unique_imports)
        if unique_imports:
            result += '\n\n'
        result += '\n\n'.join(all_bodies)
        return result

    @staticmethod
    def merge_go_code(code_parts):
        """Merge Go code: collect package + imports, then concatenate functions."""
        all_imports = []
        all_bodies = []
        package_line = "package main"

        for code in code_parts:
            lines = code.split('\n')
            in_import_block = False
            import_lines = []
            body_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('package '):
                    package_line = stripped
                    continue
                if stripped == 'import (' or stripped.startswith('import '):
                    if stripped.startswith('import '):
                        import_lines.append(stripped.replace('import ', '').strip('"'))
                    in_import_block = stripped == 'import ('
                    continue
                if in_import_block:
                    if stripped == ')':
                        in_import_block = False
                    else:
                        import_lines.append(stripped.strip('"'))
                    continue
                body_lines.append(line)

            all_imports.extend(import_lines)
            all_bodies.append('\n'.join(body_lines))

        seen = set()
        unique_imports = [i for i in all_imports if i not in seen and not seen.add(i)]

        result = package_line + '\n\n'
        if unique_imports:
            result += 'import (\n'
            for imp in unique_imports:
                result += f'\t"{imp}"\n'
            result += ')\n\n'
        result += '\n\n'.join(all_bodies)
        return result

    @staticmethod
    def merge_block_code(code_parts, comment_prefix, skip_prefix):
        """Generic merge for C-style languages: skip duplicate headers."""
        seen_headers = set()
        all_lines = []
        for code in code_parts:
            lines = code.split('\n')
            for line in lines:
                stripped = line.strip()
                if skip_prefix and stripped.startswith(skip_prefix):
                    if stripped not in seen_headers:
                        seen_headers.add(stripped)
                        all_lines.append(line)
                    continue
                all_lines.append(line)
            all_lines.append('')
        return '\n'.join(all_lines)
