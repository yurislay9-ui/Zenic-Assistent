"""Logic Builder - Facade module for backward compatibility.

All logic block classes have been moved to the logic_blocks sub-package.
This module re-exports all public symbols for backward compatibility.

Original architecture:
  1. LogicBlock: Clase base abstracta para bloques de logica
  2. LogicChain: Pipeline composable de bloques secuenciales con branching
  3. LogicBuilder: Builder principal que compone chains desde descripciones o templates
  4. 30+ bloques pre-construidos en 6 categorias:
     - Flow: conditional, loop, parallel, switch, try_catch
     - Validation: required, types, ranges, unique, sanitize
     - Business Logic: invoice, inventory, crm, task, report, notification, analyzer
     - Data: crud_create, crud_read, crud_update, crud_delete, transform
     - Integration: email, http, webhook, file
     - Auth: login, register, verify, rbac
  5. generate_inline_block_code(): Genera codigo fuente _process() real por bloque

Principios:
  - Todos los bloques son independientemente testeable
  - Todos los bloques manejan errores gracefulmente (retornan dict, no raise)
  - Sin dependencias externas requeridas (fallbacks para SMTP, HTTP, etc.)
  - Cada bloque logea su ejecucion
  - Compatible con TemplateEngine para resolucion de templates
"""

from .logic_blocks.chain import LogicBlock, LogicChain, _validate_identifier
from .logic_blocks.flow import (ConditionalBlock, LoopBlock, ParallelBlock, SwitchBlock, TryCatchBlock)
from .logic_blocks.validation import (ValidateRequiredBlock, ValidateTypesBlock, ValidateRangesBlock, ValidateUniqueBlock, SanitizeBlock)
from .logic_blocks.business_logic import (InvoiceCalculatorBlock, InventoryTrackerBlock, CRMPipelineBlock, TaskSchedulerBlock)
from .logic_blocks.business_analytics import (ReportGeneratorBlock, NotificationDispatchBlock, DataAnalyzerBlock)
from .logic_blocks.data import (CRUDCreateBlock, CRUDReadBlock, CRUDUpdateBlock, CRUDDeleteBlock)
from .logic_blocks.data_transform import DataTransformBlock
from .logic_blocks.integration import (EmailSendBlock, HTTPRequestBlock, WebhookCallBlock, FileOperationBlock)
from .logic_blocks.auth import (AuthLoginBlock, AuthRegisterBlock, AuthVerifyBlock, AuthRBACBlock)
from .logic_blocks.builder import LogicBuilder

__all__ = [
    'LogicBlock', 'LogicChain', '_validate_identifier',
    'ConditionalBlock', 'LoopBlock', 'ParallelBlock', 'SwitchBlock', 'TryCatchBlock',
    'ValidateRequiredBlock', 'ValidateTypesBlock', 'ValidateRangesBlock', 'ValidateUniqueBlock', 'SanitizeBlock',
    'InvoiceCalculatorBlock', 'InventoryTrackerBlock', 'CRMPipelineBlock', 'TaskSchedulerBlock', 'ReportGeneratorBlock', 'NotificationDispatchBlock', 'DataAnalyzerBlock',
    'CRUDCreateBlock', 'CRUDReadBlock', 'CRUDUpdateBlock', 'CRUDDeleteBlock', 'DataTransformBlock',
    'EmailSendBlock', 'HTTPRequestBlock', 'WebhookCallBlock', 'FileOperationBlock',
    'AuthLoginBlock', 'AuthRegisterBlock', 'AuthVerifyBlock', 'AuthRBACBlock',
    'LogicBuilder',
]
