#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from typing import Optional
import concurrent.futures, atexit, functools

class ThreadPoolManager:
    _instance: Optional['ThreadPoolManager'] = None
    _pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_pool(self, max_workers: int = None) -> concurrent.futures.ThreadPoolExecutor:
        """Get thread pool instance, lazy initialize if not exists.
        
        Args:
            max_workers: Maximum number of threads in the pool. If None, use default.
        
        Returns:
            ThreadPoolExecutor instance
        """
        if self._pool is None:
            # Accept max_workers from argument or environment variable
            self._pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers or self._get_default_workers()
            )
            # Register cleanup function on exit
            atexit.register(self._shutdown_pool)
        return self._pool
    
    def _get_default_workers(self) -> int:
        """Get default number of threads, typically CPU cores * 2.
        
        Returns:
            Default number of threads
        """
        import os
        default = min(32, (os.cpu_count() or 1) * 2)
        return default
    
    def _shutdown_pool(self, wait: bool = True):
        """Shutdown thread pool, release resources.
        
        Args:
            wait: Whether to wait for pending tasks to complete before shutting down.
        """
        if self._pool is not None:
            self._pool.shutdown(wait=wait)
            self._pool = None
    
    @property
    def pool(self) -> concurrent.futures.ThreadPoolExecutor:
        """Property-style access to thread pool instance.
        
        Returns:
            ThreadPoolExecutor instance
        """
        return self.get_pool()

# Create global available singleton instance
thread_pool_manager = ThreadPoolManager()

# Provide convenient global access functions
def get_global_thread_pool(max_workers: int = None) -> concurrent.futures.ThreadPoolExecutor:
    return thread_pool_manager.get_pool(max_workers)

def shutdown_global_thread_pool(wait: bool = True):
    thread_pool_manager._shutdown_pool(wait)

    """Shutdown global thread pool, release resources.
    
    Args:
        wait: Whether to wait for pending tasks to complete before shutting down.
    """
