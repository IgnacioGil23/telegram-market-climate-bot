"""
📝 Sistema de logging profesional para AkuGuard Bot
Logging estructurado con niveles, rotación y análisis
"""
import logging
import logging.handlers
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

class StructuredFormatter(logging.Formatter):
    """Formateador que crea logs estructurados en JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Crear diccionario base del log
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Agregar información adicional si existe
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        
        if hasattr(record, 'command'):
            log_entry["command"] = record.command
        
        if hasattr(record, 'execution_time'):
            log_entry["execution_time_ms"] = record.execution_time
        
        if hasattr(record, 'api_endpoint'):
            log_entry["api_endpoint"] = record.api_endpoint
        
        if hasattr(record, 'cache_hit'):
            log_entry["cache_hit"] = record.cache_hit
        
        # Agregar información de excepción si existe
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)

class SimpleFormatter(logging.Formatter):
    """Formateador simple para consola"""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

class BotLogger:
    """Sistema de logging centralizado del bot"""
    
    def __init__(self, name: str = "AkuGuard", log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Crear logger principal
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Evitar duplicar handlers
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Configura los diferentes handlers de logging"""
        
        # Handler para archivo con rotación
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "akuguard.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(StructuredFormatter())
        file_handler.setLevel(logging.DEBUG)
        
        # Handler para consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(SimpleFormatter())
        console_handler.setLevel(logging.INFO)
        
        # Handler para errores críticos
        error_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "errors.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setFormatter(StructuredFormatter())
        error_handler.setLevel(logging.ERROR)
        
        # Agregar handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(error_handler)
    
    def info(self, message: str, **kwargs):
        """Log de información con contexto adicional"""
        self._log_with_context(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log de advertencia con contexto adicional"""
        self._log_with_context(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log de error con contexto adicional"""
        self._log_with_context(logging.ERROR, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log de debug con contexto adicional"""
        self._log_with_context(logging.DEBUG, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log crítico con contexto adicional"""
        self._log_with_context(logging.CRITICAL, message, **kwargs)
    
    def _log_with_context(self, level: int, message: str, **kwargs):
        """Registra un log con contexto adicional"""
        # Crear record personalizado
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        
        # Agregar contexto adicional
        for key, value in kwargs.items():
            setattr(record, key, value)
        
        self.logger.handle(record)
    
    def log_command(self, command: str, user_id: int, execution_time: float = None, success: bool = True):
        """Registra la ejecución de un comando"""
        self.info(
            f"Comando ejecutado: {command}",
            command=command,
            user_id=user_id,
            execution_time=execution_time,
            success=success
        )
    
    def log_api_call(self, endpoint: str, status_code: int, response_time: float, cached: bool = False):
        """Registra llamadas a APIs"""
        level = logging.INFO if status_code < 400 else logging.WARNING
        self._log_with_context(
            level,
            f"API call: {endpoint} -> {status_code}",
            api_endpoint=endpoint,
            status_code=status_code,
            response_time=response_time,
            cache_hit=cached
        )
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any]):
        """Registra errores con contexto detallado"""
        self.error(
            f"Error: {str(error)}",
            exception_type=type(error).__name__,
            **context
        )

# Funciones de utilidad para logging
def log_execution_time(func):
    """Decorador para medir y registrar tiempo de ejecución"""
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            success = True
        except Exception as e:
            success = False
            logger.error(f"Error en {func.__name__}: {str(e)}")
            raise
        finally:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(
                f"Función {func.__name__} ejecutada",
                function=func.__name__,
                execution_time=execution_time,
                success=success
            )
        return result
    return wrapper

# Instancia global del logger
logger = BotLogger()

def get_logger(name: str = None) -> BotLogger:
    """Obtiene una instancia del logger"""
    if name:
        return BotLogger(name)
    return logger