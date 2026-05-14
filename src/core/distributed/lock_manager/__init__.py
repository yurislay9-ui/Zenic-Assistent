'''lock_manager - refactored into sub-modules.'''

from ._core import DistributedLock, DistributedLockManager

__all__ = ['DistributedLock', 'DistributedLockManager']
