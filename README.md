# 🤖 Telegram Market & Climate Bot

Bot inteligente de Telegram que proporciona análisis financiero en tiempo real e información meteorológica avanzada con arquitectura profesional y análisis predictivo.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Production-brightgreen.svg)

## ✨ Características Principales

### 📊 **Análisis Financiero Avanzado**
- **Datos en tiempo real** de acciones y criptomonedas
- **Múltiples fuentes de datos**: Alpha Vantage, Twelve Data
- **Análisis técnico**: Tendencias, recomendaciones, análisis de volatilidad
- **Noticias financieras** relevantes por símbolo
- **Sistema de cache inteligente** para optimizar API calls

### 🌤️ **Sistema Meteorológico Inteligente**
- **Predicciones precisas** con WeatherAPI
- **Recomendaciones inteligentes** de vestimenta y actividades
- **Calidad del aire** y nivel PM2.5
- **Pronóstico extendido** de 3 días
- **Detección automática** de ciudades ambiguas

### 🖥️ **Monitoreo del Sistema**
- **Estado del servidor** en tiempo real
- **Métricas de rendimiento** y uptime
- **Análisis de dispositivos** móviles y desktop
- **Capturas de pantalla** remotas
- **Información de red** y conectividad

## 🚀 Comandos Disponibles

### 💰 Financiero
```
/accion AAPL     - Análisis completo de acciones
/accion BTC      - Datos de criptomonedas
/accion TSLA     - Con noticias y recomendaciones
```

### 🌍 Clima
```
/clima Madrid              - Clima actual y predicciones
/clima "Buenos Aires"      - Ciudades con espacios
/clima London              - Detección automática de país
```

### 🔧 Sistema
```
/status          - Estado del bot y servidor
/device          - Información del dispositivo
/health          - Verificación completa del sistema
/metrics         - Métricas de rendimiento
```

## 🛠️ Instalación y Configuración

### Prerrequisitos
- Python 3.11+
- Cuenta de Telegram Bot (@BotFather)
- API Keys de servicios financieros (opcional)

### Configuración Rápida

1. **Clona el repositorio:**
```bash
git clone https://github.com/IgnacioGil23/telegram-market-climate-bot.git
cd telegram-market-climate-bot
```

2. **Instala dependencias:**
```bash
pip install -r requirements.txt
```

3. **Configura variables de entorno:**
```bash
cp .env.example .env
# Edita .env con tus credenciales
```

4. **Ejecuta el bot:**
```bash
python akuguard_bot_web.py
```

## 🔑 Variables de Entorno

### Requeridas
```bash
TELEGRAM_BOT_TOKEN=tu_bot_token_de_botfather
```

### Opcionales (para funciones avanzadas)
```bash
WEATHER_API_KEY=tu_weatherapi_key           # Clima avanzado
ALPHA_VANTAGE_API_KEY=tu_alphavantage_key   # Datos financieros
TWELVE_API_KEY=tu_twelve_data_key           # Datos financieros adicionales
```

## 🏗️ Arquitectura

### Diseño Modular
- **`akuguard_bot_web.py`** - Bot principal con webhook
- **`config.py`** - Configuración centralizada
- **`cache.py`** - Sistema de cache inteligente
- **`logger.py`** - Logging estructurado JSON
- **`metrics.py`** - Sistema de métricas avanzado

### Tecnologías
- **Framework**: python-telegram-bot
- **APIs**: Alpha Vantage, Twelve Data, WeatherAPI
- **Cache**: Sistema TTL personalizado
- **Logging**: Structured JSON logging
- **Deployment**: Render Cloud (24/7)

## 🚀 Deployment

### Render.com (Recomendado - Gratuito)
1. Fork este repositorio
2. Conecta con Render.com
3. Configura variables de entorno
4. Deploy automático ✨

### Configuración Render
```bash
Build Command: pip install -r requirements.txt
Start Command: python akuguard_bot_web.py
```

## 📊 Funciones Avanzadas

### Sistema Financiero
- **Multi-API failover**: Redundancia automática entre proveedores
- **Rate limiting inteligente**: Optimización de llamadas API
- **Análisis predictivo**: Recomendaciones basadas en tendencias
- **Cache dinámico**: Datos frescos con eficiencia óptima

### Sistema Meteorológico
- **IA de recomendaciones**: Sugerencias contextuales
- **Detección geográfica**: Resolución automática de ubicaciones
- **Pronósticos precisos**: Datos horarios y extendidos
- **Alertas meteorológicas**: Notificaciones proactivas

## 🔒 Seguridad

- ✅ **Variables de entorno** para datos sensibles
- ✅ **Sin hardcoding** de credenciales
- ✅ **Gitignore robusto** para archivos sensibles
- ✅ **Rate limiting** para prevenir abuso
- ✅ **Logging seguro** sin exposición de datos

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Para contribuir:

1. Fork el proyecto
2. Crea una branch (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a la branch (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Distribuido bajo la Licencia MIT. Ver `LICENSE` para más información.

## 🎯 Autor

**Ignacio Gil** - [LinkedIn](https://www.linkedin.com/in/ignacio-gil-70656026a)

---

⭐ **¡Si este proyecto te resulta útil, dale una estrella!**
