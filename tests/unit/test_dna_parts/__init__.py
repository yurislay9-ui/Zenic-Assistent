"""Re-export all test classes from test_dna_parts sub-modules."""

from ._dataclasses_and_loading import (
    TestLogicModule,
    TestDomainRule,
    TestDNALoading,
    TestLogicModuleQuery,
    TestDomainRuleQuery,
)
from ._gates_glossary_stats import (
    TestValidationGates,
    TestGlossaryPolish,
    TestDNALoaderStats,
    TestSingleton,
    TestResolveModules,
)

__all__ = [
    "TestLogicModule",
    "TestDomainRule",
    "TestDNALoading",
    "TestLogicModuleQuery",
    "TestDomainRuleQuery",
    "TestValidationGates",
    "TestGlossaryPolish",
    "TestDNALoaderStats",
    "TestSingleton",
    "TestResolveModules",
]
