"""
ZENIC-AGENTS - Logic Blocks Sub-Package

Composable business logic engine that replaces the _process() placeholder
with real, executable business logic blocks.

Architecture:
  1. LogicBlock: Abstract base class for logic blocks
  2. LogicChain: Composable pipeline of sequential blocks with branching
  3. LogicBuilder: Main builder that composes chains from descriptions or templates
  4. 30+ pre-built blocks in 6 categories:
     - Flow: conditional, loop, parallel, switch, try_catch
     - Validation: required, types, ranges, unique, sanitize
     - Business Logic: invoice, inventory, crm, task, report, notification, analyzer
     - Data: crud_create, crud_read, crud_update, crud_delete, transform
     - Integration: email, http, webhook, file
     - Auth: login, register, verify, rbac
  5. generate_inline_block_code(): Generates real _process() source code per block

Modules:
  - chain: LogicBlock ABC, LogicChain, _validate_identifier
  - flow: ConditionalBlock, LoopBlock, ParallelBlock, SwitchBlock, TryCatchBlock
  - validation: ValidateRequiredBlock, ValidateTypesBlock, ValidateRangesBlock,
                ValidateUniqueBlock, SanitizeBlock
  - business_logic: InvoiceCalculatorBlock, InventoryTrackerBlock, CRMPipelineBlock,
                    TaskSchedulerBlock
  - business_analytics: ReportGeneratorBlock, NotificationDispatchBlock, DataAnalyzerBlock
  - data: CRUDCreateBlock, CRUDReadBlock, CRUDUpdateBlock, CRUDDeleteBlock
  - data_transform: DataTransformBlock
  - integration: EmailSendBlock, HTTPRequestBlock, WebhookCallBlock, FileOperationBlock
  - auth: AuthLoginBlock, AuthRegisterBlock, AuthVerifyBlock, AuthRBACBlock
  - builder: LogicBuilder
  - builder_registry: build_keyword_map, map_template_block, get_block_template_code,
                      generate_inline_block_code, safe_var_name
"""

from .chain import (
    LogicBlock,
    LogicChain,
    _validate_identifier,
)

from .flow import (
    ConditionalBlock,
    LoopBlock,
    ParallelBlock,
    SwitchBlock,
    TryCatchBlock,
)

from .validation import (
    ValidateRequiredBlock,
    ValidateTypesBlock,
    ValidateRangesBlock,
    ValidateUniqueBlock,
    SanitizeBlock,
)

from .business_logic import (
    InvoiceCalculatorBlock,
    InventoryTrackerBlock,
    CRMPipelineBlock,
    TaskSchedulerBlock,
)

from .business_analytics import (
    ReportGeneratorBlock,
    NotificationDispatchBlock,
    DataAnalyzerBlock,
)

from .data import (
    CRUDCreateBlock,
    CRUDReadBlock,
    CRUDUpdateBlock,
    CRUDDeleteBlock,
)

from .data_transform import (
    DataTransformBlock,
)

from .integration import (
    EmailSendBlock,
    HTTPRequestBlock,
    WebhookCallBlock,
    FileOperationBlock,
)

from .auth import (
    AuthLoginBlock,
    AuthRegisterBlock,
    AuthVerifyBlock,
    AuthRBACBlock,
)

from .builder import LogicBuilder

from .builder_registry import (
    build_keyword_map,
    map_template_block,
    get_block_template_code,
    generate_inline_block_code,
    safe_var_name,
)

__all__ = [
    # Chain module
    'LogicBlock',
    'LogicChain',
    '_validate_identifier',
    # Flow blocks
    'ConditionalBlock',
    'LoopBlock',
    'ParallelBlock',
    'SwitchBlock',
    'TryCatchBlock',
    # Validation blocks
    'ValidateRequiredBlock',
    'ValidateTypesBlock',
    'ValidateRangesBlock',
    'ValidateUniqueBlock',
    'SanitizeBlock',
    # Business logic blocks
    'InvoiceCalculatorBlock',
    'InventoryTrackerBlock',
    'CRMPipelineBlock',
    'TaskSchedulerBlock',
    'ReportGeneratorBlock',
    'NotificationDispatchBlock',
    'DataAnalyzerBlock',
    # Data blocks
    'CRUDCreateBlock',
    'CRUDReadBlock',
    'CRUDUpdateBlock',
    'CRUDDeleteBlock',
    'DataTransformBlock',
    # Integration blocks
    'EmailSendBlock',
    'HTTPRequestBlock',
    'WebhookCallBlock',
    'FileOperationBlock',
    # Auth blocks
    'AuthLoginBlock',
    'AuthRegisterBlock',
    'AuthVerifyBlock',
    'AuthRBACBlock',
    # Builder
    'LogicBuilder',
    # Builder registry helpers
    'build_keyword_map',
    'map_template_block',
    'get_block_template_code',
    'generate_inline_block_code',
    'safe_var_name',
]
