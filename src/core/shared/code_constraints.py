"""
ZENIC-AGENTS - Code Constraint Builder v16

Construye restricciones de verificacion a partir de analisis AST.
Permite al Solver (Z3 o AC-3) verificar invariantes de codigo.

Los constraints generados llevan descripciones semánticas ricas
que el Z3 Deep Native Encoder puede interpretar como expresiones
Z3 nativas (Implies, aritmética, lógica) en vez de valid-pair tables.
"""

from .constraint_solver import Constraint

__all__ = ["CodeConstraintBuilder"]


# ============================================================
#  CODE CONSTRAINT BUILDER - Construye restricciones de codigo
# ============================================================

class CodeConstraintBuilder:
    """
    Construye restricciones de verificacion a partir de analisis AST.
    Permite al Solver (Z3 o AC-3) verificar invariantes de codigo.

    Los constraints generados llevan descripciones semánticas ricas
    que el Z3 Deep Native Encoder puede interpretar como expresiones
    Z3 nativas (Implies, aritmética, lógica) en vez de valid-pair tables.
    """

    @staticmethod
    def build_null_safety_constraints(variables):
        """
        Construye restricciones para verificar null-safety.

        Genera constraints con descripciones que el encoder Z3 puede
        interpretar como Implies(non_null_var == None, False) en vez
        de enumerar todos los pares válidos.
        """
        constraints = []
        noneable = [v["name"] for v in variables if v.get("can_be_none", True)]
        non_noneable = [v["name"] for v in variables if not v.get("can_be_none", False)]

        for var in non_noneable:
            for none_var in noneable:
                # Correct null-safety: if none_var is None, then var must not be None
                # The lambda checks: if y (the nullable var) is None, then x (the non-nullable) must not be None
                c = Constraint(
                    var, none_var,
                    lambda x, y: y is not None or x is not None,
                    description=f"implies {none_var} == None then {var} != None (null-safety)"
                )
                constraints.append(c)

        return constraints

    @staticmethod
    def build_type_safety_constraints(variables):
        """
        Construye restricciones para verificar type-safety.

        Usa el type lattice de Z3Solver para generar constraints
        con descripciones de compatibilidad semántica.
        """
        # Type compatibility lattice (same as Z3Solver._TYPE_LATTICE)
        TYPE_LATTICE = {
            "int": {"int", "float", "object", "unknown"},
            "float": {"float", "object", "unknown"},
            "str": {"str", "object", "unknown"},
            "bool": {"bool", "int", "float", "object", "unknown"},
            "list": {"list", "object", "unknown"},
            "dict": {"dict", "object", "unknown"},
            "None": {"None", "object", "unknown"},
            "object": {"object", "unknown"},
            "unknown": {"unknown"},
        }

        constraints = []
        for i, v1 in enumerate(variables):
            for j, v2 in enumerate(variables):
                if i < j:
                    # Build a type-compatibility constraint
                    v1_types = v1.get("types", ["unknown"])
                    v2_types = v2.get("types", ["unknown"])

                    def type_compat(x, y, lt=TYPE_LATTICE):
                        compat = lt.get(x, {"unknown"})
                        return y in compat

                    c = Constraint(
                        v1["name"], v2["name"],
                        type_compat,
                        description=f"type_compatible({v1['name']}:{v1_types}, {v2['name']}:{v2_types})"
                    )
                    constraints.append(c)
        return constraints

    @staticmethod
    def build_domains_from_code(analysis):
        """
        Construye dominios de variables a partir de analisis AST.

        Los dominios se generan con tipos nativos de Python (str, int, bool)
        para que el Z3 Deep Encoder pueda clasificarlos correctamente:
        - Dominios de strings -> EnumSort
        - Dominios de enteros -> z3.Int
        - Dominios de booleanos -> z3.Bool
        """
        domains = {}
        # String domains (will become EnumSort in Z3)
        type_values = ["int", "str", "float", "bool", "None", "list", "dict", "object"]
        domains["return_type"] = type_values
        domains["input_type"] = type_values
        domains["nullability"] = ["nullable", "non_null"]
        domains["operation"] = ["safe", "unsafe", "unknown"]

        # Numeric domains (will become z3.Int in Z3)
        domains["complexity"] = list(range(1, 21))

        # If AST analysis provides extracted variable info, add specific domains
        if isinstance(analysis, dict):
            variables = analysis.get("variables", [])
            for var_info in variables:
                var_name = var_info.get("name", "")
                if var_name:
                    annotation = var_info.get("annotation", "unknown")
                    if annotation and annotation != "unknown":
                        # Add type domain for this variable
                        domains[f"type_{var_name}"] = type_values

                    # Nullability domain
                    nullable = var_info.get("nullable", False)
                    if nullable:
                        domains[f"null_{var_name}"] = ["nullable", "non_null"]

        return domains
