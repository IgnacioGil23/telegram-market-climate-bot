"""
🎯 Sistema de métricas y monitoreo para AkuGuard Bot
Recolección y análisis de métricas de rendimiento y uso
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json
import psutil
import sys

@dataclass
class MetricPoint:
    """Punto de métrica individual"""
    timestamp: datetime
    value: float
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class MetricSummary:
    """Resumen estadístico de una métrica"""
    count: int
    sum: float
    min: float
    max: float
    avg: float
    percentile_95: float

class MetricsCollector:
    """Recolector de métricas del sistema"""
    
    def __init__(self, retention_minutes: int = 60):
        self.retention_minutes = retention_minutes
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()
        
        # Iniciar limpieza automática
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """Inicia el hilo de limpieza automática"""
        def cleanup_worker():
            while True:
                time.sleep(300)  # Cada 5 minutos
                self._cleanup_old_metrics()
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_old_metrics(self):
        """Limpia métricas antiguas"""
        cutoff_time = datetime.now() - timedelta(minutes=self.retention_minutes)
        
        with self.lock:
            for metric_name, points in self.metrics.items():
                # Mantener solo puntos recientes
                while points and points[0].timestamp < cutoff_time:
                    points.popleft()
    
    def increment_counter(self, name: str, value: int = 1, tags: Dict[str, str] = None):
        """Incrementa un contador"""
        with self.lock:
            key = self._make_key(name, tags or {})
            self.counters[key] += value
            
            # Agregar punto temporal
            self.metrics[key].append(MetricPoint(
                timestamp=datetime.now(),
                value=self.counters[key],
                tags=tags or {}
            ))
    
    def set_gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Establece el valor de un gauge"""
        with self.lock:
            key = self._make_key(name, tags or {})
            self.gauges[key] = value
            
            # Agregar punto temporal
            self.metrics[key].append(MetricPoint(
                timestamp=datetime.now(),
                value=value,
                tags=tags or {}
            ))
    
    def record_histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        """Registra un valor en un histograma"""
        with self.lock:
            key = self._make_key(name, tags or {})
            self.histograms[key].append(value)
            
            # Mantener solo últimos 1000 valores
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
            
            # Agregar punto temporal
            self.metrics[key].append(MetricPoint(
                timestamp=datetime.now(),
                value=value,
                tags=tags or {}
            ))
    
    def _make_key(self, name: str, tags: Dict[str, str]) -> str:
        """Crea una clave única para la métrica"""
        if not tags:
            return name
        
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"
    
    def get_summary(self, name: str, tags: Dict[str, str] = None, minutes: int = 10) -> Optional[MetricSummary]:
        """Obtiene resumen estadístico de una métrica"""
        key = self._make_key(name, tags or {})
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        with self.lock:
            if key not in self.metrics:
                return None
            
            # Filtrar puntos recientes
            recent_points = [
                p.value for p in self.metrics[key] 
                if p.timestamp >= cutoff_time
            ]
            
            if not recent_points:
                return None
            
            recent_points.sort()
            count = len(recent_points)
            
            return MetricSummary(
                count=count,
                sum=sum(recent_points),
                min=min(recent_points),
                max=max(recent_points),
                avg=sum(recent_points) / count,
                percentile_95=recent_points[int(count * 0.95)] if count > 0 else 0
            )
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Obtiene todas las métricas actuales"""
        with self.lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "histogram_counts": {k: len(v) for k, v in self.histograms.items()},
                "system": self._get_system_metrics()
            }
    
    def _get_system_metrics(self) -> Dict[str, float]:
        """Obtiene métricas del sistema"""
        try:
            process = psutil.Process()
            
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "cpu_process_percent": process.cpu_percent(),
                "open_files": len(process.open_files()),
                "threads": process.num_threads(),
                "disk_usage_percent": psutil.disk_usage('/').percent if sys.platform != 'win32' else psutil.disk_usage('C:').percent
            }
        except Exception:
            return {}

class PerformanceMonitor:
    """Monitor de rendimiento del bot"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.start_time = datetime.now()
    
    def record_command_execution(self, command: str, execution_time: float, success: bool):
        """Registra la ejecución de un comando"""
        self.metrics.increment_counter("commands_total", tags={"command": command, "success": str(success)})
        self.metrics.record_histogram("command_duration_ms", execution_time, tags={"command": command})
    
    def record_api_call(self, endpoint: str, duration: float, status_code: int, cached: bool = False):
        """Registra una llamada a API"""
        self.metrics.increment_counter("api_calls_total", tags={"endpoint": endpoint, "cached": str(cached)})
        self.metrics.record_histogram("api_duration_ms", duration, tags={"endpoint": endpoint})
        self.metrics.increment_counter("api_responses_total", tags={"endpoint": endpoint, "status_code": str(status_code)})
    
    def record_cache_operation(self, operation: str, hit: bool):
        """Registra operación de caché"""
        self.metrics.increment_counter("cache_operations_total", tags={"operation": operation, "hit": str(hit)})
    
    def record_user_activity(self, user_id: int, activity_type: str):
        """Registra actividad del usuario"""
        self.metrics.increment_counter("user_activities_total", tags={"activity": activity_type})
        self.metrics.set_gauge("last_user_activity", time.time(), tags={"user_id": str(user_id)})
        
        # Almacenar estadísticas por usuario
        if not hasattr(self, '_user_activity'):
            self._user_activity = {}
        
        user_key = str(user_id)
        if user_key not in self._user_activity:
            self._user_activity[user_key] = {}
        
        if activity_type not in self._user_activity[user_key]:
            self._user_activity[user_key][activity_type] = 0
        
        self._user_activity[user_key][activity_type] += 1
    
    def record_error(self, error_type: str, component: str):
        """Registra un error"""
        self.metrics.increment_counter("errors_total", tags={"type": error_type, "component": component})
    
    def update_system_metrics(self):
        """Actualiza métricas del sistema"""
        system_metrics = self.metrics._get_system_metrics()
        
        for metric_name, value in system_metrics.items():
            self.metrics.set_gauge(f"system_{metric_name}", value)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Obtiene el estado de salud del bot"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        # Obtener métricas de los últimos 5 minutos
        error_summary = self.metrics.get_summary("errors_total", minutes=5)
        command_summary = self.metrics.get_summary("commands_total", minutes=5)
        api_duration_summary = self.metrics.get_summary("api_duration_ms", minutes=5)
        
        health_status = {
            "status": "healthy",
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "errors_5min": error_summary.sum if error_summary else 0,
                "commands_5min": command_summary.sum if command_summary else 0,
                "avg_api_duration_ms": api_duration_summary.avg if api_duration_summary else 0
            }
        }
        
        # Determinar estado de salud
        if error_summary and error_summary.sum > 10:  # Más de 10 errores en 5 min
            health_status["status"] = "unhealthy"
        elif api_duration_summary and api_duration_summary.avg > 5000:  # APIs muy lentas
            health_status["status"] = "degraded"
        
        return health_status
    
    def get_user_activity(self, user_id: int) -> Dict[str, int]:
        """Obtiene la actividad de un usuario específico"""
        try:
            # Buscar métricas de actividad del usuario
            user_commands = {}
            
            # Simular conteo de comandos por usuario (en una implementación real 
            # esto vendría de una base de datos o cache persistente)
            if hasattr(self, '_user_activity'):
                user_commands = self._user_activity.get(str(user_id), {})
            else:
                # Inicializar si no existe
                self._user_activity = {}
                user_commands = {}
            
            return user_commands
        except Exception as e:
            print(f"Error obteniendo actividad del usuario {user_id}: {e}")
            return {}

def timing_decorator(metrics_collector: MetricsCollector, metric_name: str):
    """Decorador para medir tiempo de ejecución"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = (time.time() - start_time) * 1000  # En millisegundos
                metrics_collector.record_histogram(
                    metric_name, 
                    duration, 
                    tags={"function": func.__name__, "success": str(success)}
                )
        return wrapper
    return decorator

# Instancia global del recolector de métricas
metrics_collector = MetricsCollector()
performance_monitor = PerformanceMonitor(metrics_collector)

def get_metrics_collector() -> MetricsCollector:
    """Obtiene la instancia global del recolector de métricas"""
    return metrics_collector

def get_performance_monitor() -> PerformanceMonitor:
    """Obtiene la instancia global del monitor de rendimiento"""
    return performance_monitor