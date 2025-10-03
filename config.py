"""
🔧 Configuración centralizada del AkuGuard Bot
Mejores prácticas: Separación de configuración del código
Preparado para deployment en la nube con variables de entorno
"""
import os
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class APIConfig:
    """Configuración de APIs meteorológicas"""
    # IMPORTANTE: Usar SOLO variables de entorno en producción
    weatherapi_key: str = os.getenv('WEATHER_API_KEY', '')
    openweather_key: str = os.getenv('OPENWEATHER_API_KEY', '')
    weatherapi_base_url: str = "http://api.weatherapi.com/v1"
    openweather_base_url: str = "http://api.openweathermap.org/data/2.5"
    
    # Límites de uso
    weatherapi_monthly_limit: int = 1_000_000
    openweather_daily_limit: int = 1_000
    
    # Timeouts y reintentos
    request_timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0

@dataclass
class BotConfig:
    """Configuración principal del bot"""
    # IMPORTANTE: Token debe venir SOLO de variable de entorno
    bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id_file: str = "chat_id.txt"
    log_file: str = "akuguard.log"
    
    # Configuración de caché
    cache_enabled: bool = True
    cache_ttl_weather: int = 600  # 10 minutos
    cache_ttl_stocks: int = 300   # 5 minutos
    cache_ttl_system: int = 60    # 1 minuto
    
    # Configuración de notificaciones
    max_notification_rate: int = 3600  # 1 hora entre notificaciones del mismo tipo
    
    # Configuración de predicciones
    prediction_hours: int = 12
    max_predictions: int = 4

@dataclass
class SystemConfig:
    """Configuración del sistema"""
    debug_mode: bool = False
    performance_monitoring: bool = True
    max_concurrent_requests: int = 10
    memory_limit_mb: int = 512
    
    # Configuración de red y timeouts
    request_timeout: int = 10
    poll_interval: float = 0.5
    
    # Circuit breaker configuration
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 300  # 5 minutos
    
    # Cache configuration
    cache_default_ttl: int = 300  # 5 minutos

# Instancias globales de configuración
API_CONFIG = APIConfig()
BOT_CONFIG = BotConfig()
SYSTEM_CONFIG = SystemConfig()

# Ciudades ambiguas mejoradas con estructura compatible
AMBIGUOUS_CITIES = {
    "córdoba": {
        "opciones": [
            {"pais": "Argentina", "codigo": "AR", "nombre_completo": "Córdoba, Argentina", "population": 1_330_000, "flag": "🇦🇷"},
            {"pais": "España", "codigo": "ES", "nombre_completo": "Córdoba, España", "population": 325_000, "flag": "🇪🇸"}
        ]
    },
    "cordoba": {
        "opciones": [
            {"pais": "Argentina", "codigo": "AR", "nombre_completo": "Córdoba, Argentina", "population": 1_330_000, "flag": "🇦🇷"},
            {"pais": "España", "codigo": "ES", "nombre_completo": "Córdoba, España", "population": 325_000, "flag": "🇪🇸"}
        ]
    },
    "valencia": {
        "opciones": [
            {"pais": "España", "codigo": "ES", "nombre_completo": "Valencia, España", "population": 789_000, "flag": "🇪🇸"},
            {"pais": "Venezuela", "codigo": "VE", "nombre_completo": "Valencia, Venezuela", "population": 1_400_000, "flag": "🇻🇪"}
        ]
    },
    "santiago": {
        "opciones": [
            {"pais": "Chile", "codigo": "CL", "nombre_completo": "Santiago, Chile", "population": 6_158_000, "flag": "🇨🇱"},
            {"pais": "España", "codigo": "ES", "nombre_completo": "Santiago de Compostela, España", "population": 97_000, "flag": "🇪🇸"},
            {"pais": "República Dominicana", "codigo": "DO", "nombre_completo": "Santiago, República Dominicana", "population": 1_200_000, "flag": "🇩🇴"}
        ]
    },
    "san josé": {
        "opciones": [
            {"pais": "Costa Rica", "codigo": "CR", "nombre_completo": "San José, Costa Rica", "population": 342_000, "flag": "🇨🇷"},
            {"pais": "Estados Unidos", "codigo": "US", "nombre_completo": "San José, California, EE.UU.", "population": 1_030_000, "flag": "🇺🇸"}
        ]
    },
    "san jose": {
        "opciones": [
            {"pais": "Costa Rica", "codigo": "CR", "nombre_completo": "San José, Costa Rica", "population": 342_000, "flag": "🇨🇷"},
            {"pais": "Estados Unidos", "codigo": "US", "nombre_completo": "San José, California, EE.UU.", "population": 1_030_000, "flag": "🇺🇸"}
        ]
    },
    "paris": {
        "opciones": [
            {"pais": "Francia", "codigo": "FR", "nombre_completo": "París, Francia", "population": 2_161_000, "flag": "🇫🇷"},
            {"pais": "Estados Unidos", "codigo": "US", "nombre_completo": "Paris, Texas, EE.UU.", "population": 25_000, "flag": "🇺🇸"}
        ]
    },
    "cambridge": {
        "opciones": [
            {"pais": "Reino Unido", "codigo": "GB", "nombre_completo": "Cambridge, Reino Unido", "population": 124_000, "flag": "🇬🇧"},
            {"pais": "Estados Unidos", "codigo": "US", "nombre_completo": "Cambridge, Massachusetts, EE.UU.", "population": 118_000, "flag": "🇺🇸"}
        ]
    },
    "manchester": {
        "opciones": [
            {"pais": "Reino Unido", "codigo": "GB", "nombre_completo": "Manchester, Reino Unido", "population": 547_000, "flag": "🇬🇧"},
            {"pais": "Estados Unidos", "codigo": "US", "nombre_completo": "Manchester, New Hampshire, EE.UU.", "population": 115_000, "flag": "🇺🇸"}
        ]
    }
}

def get_config() -> Dict[str, Any]:
    """Retorna toda la configuración como diccionario"""
    return {
        "api": API_CONFIG,
        "bot": BOT_CONFIG,
        "system": SYSTEM_CONFIG,
        "ambiguous_cities": AMBIGUOUS_CITIES
    }

def get_api_config() -> APIConfig:
    """Retorna la configuración de APIs"""
    return API_CONFIG

def get_bot_config() -> BotConfig:
    """Retorna la configuración del bot"""
    return BOT_CONFIG

def get_system_config() -> SystemConfig:
    """Retorna la configuración del sistema"""
    return SYSTEM_CONFIG

def validate_config() -> bool:
    """Valida que la configuración sea correcta"""
    try:
        errors = []
        
        # Validar token de bot (crítico)
        if not BOT_CONFIG.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN no está configurada")
        elif len(BOT_CONFIG.bot_token) < 40:
            errors.append("TELEGRAM_BOT_TOKEN parece inválida (muy corta)")
        
        # Validar API de clima (al menos una debe estar configurada)
        weather_apis = 0
        if API_CONFIG.weatherapi_key and len(API_CONFIG.weatherapi_key) > 10:
            weather_apis += 1
        if API_CONFIG.openweather_key and len(API_CONFIG.openweather_key) > 10:
            weather_apis += 1
            
        if weather_apis == 0:
            errors.append("Al menos una API de clima debe estar configurada (WEATHER_API_KEY o OPENWEATHER_API_KEY)")
        
        # Mostrar errores si los hay
        if errors:
            print("❌ Errores de configuración:")
            for error in errors:
                print(f"   • {error}")
            print("\n💡 Asegúrate de configurar las variables de entorno requeridas")
            return False
        
        # Advertencias opcionales
        warnings = []
        if not os.getenv('TELEGRAM_CHAT_ID'):
            warnings.append("TELEGRAM_CHAT_ID no configurada (se obtendrá del primer mensaje)")
            
        if weather_apis == 1:
            warnings.append("Solo una API de clima configurada (se recomienda configurar ambas para failover)")
        
        if warnings:
            print("⚠️ Advertencias de configuración:")
            for warning in warnings:
                print(f"   • {warning}")
            print()
            
        return True
        
    except Exception as e:
        print(f"❌ Error validando configuración: {e}")
        return False