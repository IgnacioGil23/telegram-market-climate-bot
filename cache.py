"""
📊 Sistema de caché inteligente para AkuGuard Bot
Optimiza el rendimiento y reduce llamadas a APIs
"""
import time
import json
import hashlib
from typing import Any, Optional, Dict
from threading import Lock
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

@dataclass
class CacheEntry:
    """Entrada de caché con metadatos"""
    data: Any
    timestamp: float
    ttl: int
    access_count: int = 0
    last_access: float = 0.0
    
    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado"""
        return time.time() - self.timestamp > self.ttl
    
    def touch(self) -> None:
        """Actualiza estadísticas de acceso"""
        self.access_count += 1
        self.last_access = time.time()

class IntelligentCache:
    """Caché inteligente con limpieza automática y estadísticas"""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self._lock = Lock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "cleanups": 0
        }
    
    def _generate_key(self, namespace: str, *args, **kwargs) -> str:
        """Genera una clave única para el caché"""
        key_data = f"{namespace}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, namespace: str, *args, **kwargs) -> Optional[Any]:
        """Obtiene un valor del caché"""
        key = self._generate_key(namespace, *args, **kwargs)
        
        with self._lock:
            if key not in self.cache:
                self.stats["misses"] += 1
                return None
            
            entry = self.cache[key]
            
            if entry.is_expired():
                del self.cache[key]
                self.stats["misses"] += 1
                return None
            
            entry.touch()
            self.stats["hits"] += 1
            return entry.data
    
    def set(self, namespace: str, data: Any, ttl: int, *args, **kwargs) -> None:
        """Establece un valor en el caché"""
        key = self._generate_key(namespace, *args, **kwargs)
        
        with self._lock:
            # Limpieza automática si se excede el tamaño
            if len(self.cache) >= self.max_size:
                self._cleanup()
            
            self.cache[key] = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=ttl,
                last_access=time.time()
            )
    
    def _cleanup(self) -> None:
        """Limpia entradas expiradas y menos usadas"""
        current_time = time.time()
        
        # Eliminar entradas expiradas
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        # Si aún hay muchas entradas, eliminar las menos usadas
        if len(self.cache) > self.max_size * 0.8:
            # Ordenar por frecuencia de uso y tiempo de último acceso
            sorted_entries = sorted(
                self.cache.items(),
                key=lambda x: (x[1].access_count, x[1].last_access)
            )
            
            # Eliminar 20% de las entradas menos usadas
            to_remove = int(len(sorted_entries) * 0.2)
            for key, _ in sorted_entries[:to_remove]:
                del self.cache[key]
                self.stats["evictions"] += 1
        
        self.stats["cleanups"] += 1
    
    def clear(self, namespace: Optional[str] = None) -> None:
        """Limpia el caché completamente o por namespace"""
        with self._lock:
            if namespace is None:
                self.cache.clear()
            else:
                keys_to_remove = [
                    key for key in self.cache.keys()
                    if key.startswith(hashlib.md5(f"{namespace}:".encode()).hexdigest()[:8])
                ]
                for key in keys_to_remove:
                    del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del caché"""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "hit_rate": f"{hit_rate:.2f}%",
            "total_requests": total_requests,
            "memory_usage": self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> str:
        """Estima el uso de memoria del caché"""
        try:
            # Estimación básica del uso de memoria
            total_size = sum(
                len(str(entry.data)) + len(key)
                for key, entry in self.cache.items()
            )
            
            if total_size < 1024:
                return f"{total_size} B"
            elif total_size < 1024 * 1024:
                return f"{total_size / 1024:.2f} KB"
            else:
                return f"{total_size / (1024 * 1024):.2f} MB"
        except:
            return "N/A"
    
    def get_system_info(self) -> Dict[str, Any]:
        """Obtiene información del sistema"""
        try:
            import psutil
            
            # Información del proceso actual
            process = psutil.Process()
            
            return {
                "memory_usage": process.memory_info().rss / 1024 / 1024,  # MB
                "cpu_percent": process.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "threads": process.num_threads(),
                "cache_entries": len(self.cache),
                "cache_memory_mb": self._estimate_memory_usage_mb()
            }
        except Exception as e:
            return {
                "memory_usage": 0,
                "cpu_percent": 0,
                "memory_percent": 0,
                "threads": 0,
                "cache_entries": len(self.cache),
                "cache_memory_mb": 0,
                "error": str(e)
            }
    
    def cleanup(self):
        """Limpia el cache y libera recursos"""
        try:
            self.cache.clear()
            self.hit_count = 0
            self.miss_count = 0
        except Exception as e:
            print(f"Error durante cleanup del cache: {e}")

# Decorador para cachear automáticamente funciones
def cached(namespace: str, ttl: int = 300):
    """Decorador para cachear automáticamente el resultado de funciones"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Obtener del caché
            cached_result = app_cache.get(namespace, func.__name__, *args, **kwargs)
            if cached_result is not None:
                return cached_result
            
            # Ejecutar función y cachear resultado
            result = func(*args, **kwargs)
            app_cache.set(namespace, result, ttl, func.__name__, *args, **kwargs)
            return result
        
        return wrapper
    return decorator

# Instancia global del caché
app_cache = IntelligentCache(max_size=1000)