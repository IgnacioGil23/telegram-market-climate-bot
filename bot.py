#!/usr/bin/env python3
"""
AkuGuard Bot v2.0 - Simple Sync Edition
Bot de Telegram sin dependencias complejas - Solo funciones básicas
"""

import os
import json
import requests
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import logging
import sys

# ====================================
# SISTEMA DE CACHÉ PARA EVITAR RATE LIMITS
# ====================================
class SimpleCache:
    def __init__(self, cache_duration_minutes=60):  # Solo 1 hora de cache para datos frescos
        self.cache = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.last_request_time = {}
        self.min_request_interval = 8  # Aumentar a 8 segundos para evitar 429 errors
        self.rate_limit_backoff = {}  # Para backoff exponencial cuando hay 429

    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.cache_duration:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, datetime.now())

    def wait_for_rate_limit(self, api_name="default"):
        """Espera el tiempo necesario para evitar rate limits con backoff exponencial para 429 errors"""
        now = time.time()
        
        # Verificar si tenemos backoff activo por 429 error
        if api_name in self.rate_limit_backoff:
            backoff_time = self.rate_limit_backoff[api_name]
            if now < backoff_time:
                remaining = backoff_time - now
                logging.warning(f"🛡️ Backoff activo para {api_name}, esperando {remaining:.1f}s más...")
                time.sleep(remaining)
        
        # Rate limiting normal
        if api_name in self.last_request_time:
            time_since_last = now - self.last_request_time[api_name]
            if time_since_last < self.min_request_interval:
                sleep_time = self.min_request_interval - time_since_last
                logging.info(f"⏳ Esperando {sleep_time:.1f}s para evitar rate limit...")
                time.sleep(sleep_time)
        
        self.last_request_time[api_name] = time.time()
    
    def trigger_backoff(self, api_name="default", backoff_seconds=60):
        """Activa backoff exponencial cuando detectamos 429 error"""
        self.rate_limit_backoff[api_name] = time.time() + backoff_seconds
        logging.warning(f"🚨 Activando backoff de {backoff_seconds}s para {api_name} debido a rate limit")

# Instancia global del caché (con caché de 6 horas para resistir problemas persistentes)
cache = SimpleCache(cache_duration_minutes=360)

# ====================================
# CONFIGURACIÓN
# ====================================
CONFIG = {
    'TELEGRAM_BOT_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN'),
    'TELEGRAM_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID'),
    'OPENWEATHER_API_KEY': os.environ.get('OPENWEATHER_API_KEY'),
    'WEATHER_API_KEY': os.environ.get('WEATHER_API_KEY'),
    'ALPHA_VANTAGE_API_KEY': os.environ.get('ALPHA_API_KEY'),  # Usar tu variable ALPHA_API_KEY
    'FMP_API_KEY': os.environ.get('FMP_API_KEY'),  # Financial Modeling Prep API Key (DEPRECATED)
    'TWELVE_API_KEY': os.environ.get('TWELVE_API_KEY'),  # Twelve Data API Key (800 calls/day FREE)
    'RENDER_EXTERNAL_URL': os.environ.get('RENDER_EXTERNAL_URL', 'https://akuguard.onrender.com')
}

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====================================
# FUNCIONES DE TELEGRAM SÍNCRONAS
# ====================================
def send_telegram_message(chat_id, text):
    """Envía mensaje a Telegram de forma síncrona"""
    try:
        url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_BOT_TOKEN']}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"✅ Mensaje enviado exitosamente")
                return True
            else:
                logger.error(f"❌ Error API Telegram: {result}")
        else:
            logger.error(f"❌ Error HTTP: {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {e}")
    
    return False

def set_webhook():
    """Configura el webhook de Telegram"""
    try:
        webhook_url = f"{CONFIG['RENDER_EXTERNAL_URL']}/webhook"
        url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_BOT_TOKEN']}/setWebhook"
        data = {"url": webhook_url}
        
        response = requests.post(url, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"✅ Webhook configurado: {webhook_url}")
                return True
        
        logger.error(f"❌ Error configurando webhook: {response.text}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error configurando webhook: {e}")
        return False

# ====================================
# FUNCIONES DE STOCK (ALPHA VANTAGE)
# ====================================
def get_stock_data(symbol):
    """
    Obtiene datos financieros con sistema multi-API actualizado:
    1° Twelve Data (800 calls/día GRATUITO)
    2° Alpha Vantage como fallback (500 calls/día)
    Total: 1,300 llamadas gratuitas/día
    """
    # Verificar si tenemos API keys válidas
    has_twelve_key = bool(CONFIG.get('TWELVE_API_KEY'))
    has_alpha_key = bool(CONFIG.get('ALPHA_VANTAGE_API_KEY'))
    
    # Si tenemos Twelve Data API key, usarla primero
    if has_twelve_key:
        logger.info(f"🥇 Usando Twelve Data para {symbol}")
        twelve_data = get_stock_data_twelve(symbol)
        
        # Si Twelve Data no devuelve datos completos Y tenemos Alpha Vantage, usar fallback
        if (twelve_data and 
            'error' not in twelve_data and 
            twelve_data.get('daily_change', 0) == 0 and 
            twelve_data.get('volume', 0) == 0 and
            has_alpha_key):
            logger.warning("🔄 Twelve Data sin datos de trading completos, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        return twelve_data
    
    # Si no tenemos Twelve Data pero sí Alpha Vantage, usar Alpha Vantage directamente
    elif has_alpha_key:
        logger.info(f"🥈 Usando Alpha Vantage directamente para {symbol}")
        return get_stock_data_alphavantage(symbol)
    
    # Si no tenemos ninguna API key válida, intentar Twelve Data con demo key
    else:
        logger.info(f"🆓 Usando Twelve Data con demo key para {symbol}")
        twelve_data = get_stock_data_twelve(symbol)
        
        # Si falla con demo key, mostrar error apropiado
        if twelve_data and 'error' in twelve_data:
            return {"error": "❌ No hay APIs financieras configuradas. Configura TWELVE_API_KEY o ALPHA_API_KEY."}
        
        return twelve_data

def normalize_symbol(symbol):
    """Normaliza símbolos para APIs financieras con conversión de nombres comunes"""
    symbol = symbol.upper().strip()
    
    # Mapeo de nombres comunes a símbolos bursátiles
    name_to_symbol = {
        # Tecnología
        'APPLE': 'AAPL',
        'TESLA': 'TSLA', 
        'MICROSOFT': 'MSFT',
        'GOOGLE': 'GOOGL',
        'ALPHABET': 'GOOGL',
        'AMAZON': 'AMZN',
        'FACEBOOK': 'META',
        'META': 'META',
        'NVIDIA': 'NVDA',
        'NETFLIX': 'NFLX',
        
        # Criptomonedas comunes en español
        'BITCOIN': 'BTC',
        'ETHEREUM': 'ETH',
        'CARDANO': 'ADA',
        'DOGECOIN': 'DOGE',
        'SOLANA': 'SOL',
        
        # Otras empresas famosas
        'COCA': 'KO',
        'COCACOLA': 'KO',
        'MCDONALD': 'MCD',
        'MCDONALDS': 'MCD',
        'DISNEY': 'DIS',
        'WALMART': 'WMT',
        'VISA': 'V',
        'MASTERCARD': 'MA',
        'PAYPAL': 'PYPL',
        'INTEL': 'INTC',
        'AMD': 'AMD',
        'ORACLE': 'ORCL',
        'UBER': 'UBER',
        'AIRBNB': 'ABNB',
        'ZOOM': 'ZM'
    }
    
    # Si es un nombre común, convertir a símbolo
    if symbol in name_to_symbol:
        logger.info(f"🔄 Convertido '{symbol}' → '{name_to_symbol[symbol]}'")
        symbol = name_to_symbol[symbol]
    
    # Mapeo de criptomonedas
    crypto_mapping = {
        'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'ADA': 'ADA-USD',
        'DOT': 'DOT-USD', 'LINK': 'LINK-USD', 'LTC': 'LTC-USD',
        'XRP': 'XRP-USD', 'DOGE': 'DOGE-USD', 'MATIC': 'MATIC-USD',
        'SOL': 'SOL-USD'
    }
    
    return crypto_mapping.get(symbol, symbol)

def get_backup_stock_data(symbol):
    """Datos de respaldo para cuando las APIs están completamente bloqueadas"""
    # Precios aproximados para símbolos populares (septiembre 2025)
    backup_data = {
        'AAPL': {'name': 'Apple Inc.', 'price': 245.00, 'sector': 'Technology', 'change': 1.5},
        'TSLA': {'name': 'Tesla Inc.', 'price': 426.00, 'sector': 'Consumer Cyclical', 'change': 2.3},
        'MSFT': {'name': 'Microsoft Corp.', 'price': 445.00, 'sector': 'Technology', 'change': 0.8},
        'GOOGL': {'name': 'Alphabet Inc.', 'price': 170.00, 'sector': 'Communication Services', 'change': 1.2},
        'AMZN': {'name': 'Amazon.com Inc.', 'price': 185.00, 'sector': 'Consumer Cyclical', 'change': -0.3},
        'NVDA': {'name': 'NVIDIA Corp.', 'price': 130.00, 'sector': 'Technology', 'change': 2.8},
        'META': {'name': 'Meta Platforms Inc.', 'price': 580.00, 'sector': 'Communication Services', 'change': 1.1},
        'BTC-USD': {'name': 'Bitcoin (Cryptocurrency)', 'price': 115000.00, 'sector': 'Cryptocurrency', 'change': 0.5},
        'ETH-USD': {'name': 'Ethereum (Cryptocurrency)', 'price': 4200.00, 'sector': 'Cryptocurrency', 'change': 1.8}
    }
    
    if symbol.upper() in backup_data:
        data = backup_data[symbol.upper()]
        return {
            'symbol': symbol.upper(),
            'name': data['name'],
            'current_price': data['price'],
            'currency': 'USD',
            'daily_change': data['change'],
            'daily_change_percent': data['change'],
            'monthly_change_percent': 0,
            'year_high': data['price'] * 1.15,
            'year_low': data['price'] * 0.85,
            'market_cap': 0,
            'sector': data['sector'],
            'industry': 'N/A',
            'volume': 0,
            'avg_volume': 0
        }
    return None

def get_stock_data_alphavantage(symbol):
    """
    Obtiene datos reales de Alpha Vantage - Alternativa más confiable a Yahoo Finance
    """
    cache_key = f"stock_av_{symbol.upper()}"
    
    # Verificar caché (15 minutos para datos frescos)
    cached_data = cache.get(cache_key)
    if cached_data:
        logging.info(f"📦 Datos Alpha Vantage de {symbol} desde caché")
        return cached_data
    
    # Rate limiting para Alpha Vantage
    cache.wait_for_rate_limit("alphavantage")
    
    # Normalizar símbolo
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"🔍 Consultando Alpha Vantage para {normalized_symbol}")
    
    try:
        # API Key de Alpha Vantage
        api_key = CONFIG.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return {"error": "❌ Alpha Vantage API key no configurada. Necesitas registrarte en alphavantage.co"}
        
        # Para criptomonedas
        if normalized_symbol.endswith('-USD'):
            crypto_symbol = normalized_symbol.replace('-USD', '')
            logger.info(f"🪙 Detectada criptomoneda: {crypto_symbol}")
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'DIGITAL_CURRENCY_DAILY',  # Función correcta para crypto
                'symbol': crypto_symbol,
                'market': 'USD',
                'apikey': api_key
            }
            
            # Headers mejorados para crypto también
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',  # Removido 'br' para evitar problemas de compresión
                'Connection': 'keep-alive'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            try:
                data = response.json()
            except json.JSONDecodeError as json_err:
                logger.error(f"🔍 Crypto JSON decode error: {json_err}")
                logger.error(f"🔍 Crypto response text: {response.text}")
                raise ValueError(f"Invalid JSON response for crypto: {response.text[:200]}")
            
            # Debug logging para crypto
            logger.info(f"🔍 Crypto response keys: {list(data.keys())}")
            logger.info(f"🔍 Full crypto response: {json.dumps(data, indent=2)}")
            
            # Alpha Vantage crypto response format
            if 'Time Series (Digital Currency Daily)' in data:
                time_series = data['Time Series (Digital Currency Daily)']
                latest_date = max(time_series.keys())
                latest_data = time_series[latest_date]
                
                # Debug: ver qué keys están disponibles
                logger.info(f"🔍 Crypto data keys: {list(latest_data.keys())}")
                
                current_price = float(latest_data['4. close'])
                
                stock_data = {
                    'symbol': normalized_symbol,
                    'name': f"{crypto_symbol} (Cryptocurrency)",
                    'current_price': current_price,
                    'currency': 'USD',
                    'daily_change': 0,  # Alpha Vantage crypto requiere cálculo manual
                    'daily_change_percent': 0,
                    'monthly_change_percent': 0,
                    'year_high': current_price * 1.2,
                    'year_low': current_price * 0.8,
                    'market_cap': 0,
                    'sector': 'Cryptocurrency',
                    'industry': 'N/A',
                    'volume': float(latest_data.get('5. volume', 0)),
                    'avg_volume': 0
                }
            else:
                # Intentar con función simple de exchange rate para crypto
                params = {
                    'function': 'CURRENCY_EXCHANGE_RATE',
                    'from_currency': crypto_symbol,
                    'to_currency': 'USD',
                    'apikey': api_key
                }
                
                response = requests.get(url, params=params, timeout=15)
                data = response.json()
                
                if 'Realtime Currency Exchange Rate' in data:
                    rate_data = data['Realtime Currency Exchange Rate']
                    current_price = float(rate_data['5. Exchange Rate'])
                    
                    stock_data = {
                        'symbol': normalized_symbol,
                        'name': f"{crypto_symbol} (Cryptocurrency)",
                        'current_price': current_price,
                        'currency': 'USD',
                        'daily_change': 0,
                        'daily_change_percent': 0,
                        'monthly_change_percent': 0,
                        'year_high': current_price * 1.2,
                        'year_low': current_price * 0.8,
                        'market_cap': 0,
                        'sector': 'Cryptocurrency',
                        'industry': 'N/A',
                        'volume': 0,
                        'avg_volume': 0
                    }
                else:
                    raise ValueError("Crypto data not available from Alpha Vantage")
        
        else:
            # Para acciones normales
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': normalized_symbol,
                'apikey': api_key
            }
            
            # Headers mejorados para compatibilidad con servicios cloud
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',  # Removido 'br' para evitar problemas de compresión
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            # DEBUGGING COMPLETO PARA LA NUBE
            logger.info(f"🔍 Alpha Vantage request URL: {response.url}")
            logger.info(f"🔍 Response status code: {response.status_code}")
            logger.info(f"🔍 Response headers: {dict(response.headers)}")
            
            # Forzar encoding si es necesario
            if response.encoding is None or response.encoding == 'ISO-8859-1':
                response.encoding = 'utf-8'
            
            logger.info(f"🔍 Response encoding: {response.encoding}")
            logger.info(f"🔍 Raw response text (first 500 chars): {response.text[:500]}")
            
            try:
                data = response.json()
            except json.JSONDecodeError as json_err:
                logger.error(f"🔍 JSON decode error: {json_err}")
                logger.error(f"🔍 Full response text: {response.text}")
                logger.error(f"🔍 Response content (bytes): {response.content[:200]}")
                raise ValueError(f"Invalid JSON response from Alpha Vantage: {response.text[:200]}")
            
            # Debug logging para ver qué devuelve Alpha Vantage
            logger.info(f"🔍 Alpha Vantage response keys: {list(data.keys())}")
            logger.info(f"🔍 Full Alpha Vantage response: {json.dumps(data, indent=2)}")
            
            # Verificar errores específicos de Alpha Vantage
            if 'Error Message' in data:
                raise ValueError(f"Alpha Vantage Error: {data['Error Message']}")
            elif 'Note' in data:
                raise ValueError(f"Alpha Vantage Rate Limit: {data['Note']}")
            elif 'Information' in data:
                raise ValueError(f"Alpha Vantage Info: {data['Information']}")
            elif 'Global Quote' in data:
                quote = data['Global Quote']
                
                # Verificar que Global Quote no esté vacío
                if not quote or not quote.get('05. price'):
                    logger.error(f"🔍 Global Quote vacío para {normalized_symbol}: {quote}")
                    raise ValueError("Global Quote empty or missing price")
                
                current_price = float(quote['05. price'])
                change = float(quote['09. change'])
                change_percent = float(quote['10. change percent'].replace('%', ''))
                
                stock_data = {
                    'symbol': normalized_symbol,
                    'name': f"{normalized_symbol} Inc.",
                    'current_price': current_price,
                    'currency': 'USD',
                    'daily_change': change,
                    'daily_change_percent': change_percent,
                    'monthly_change_percent': 0,
                    'day_high': float(quote['03. high']),      # Alto del día
                    'day_low': float(quote['04. low']),       # Bajo del día
                    'open_price': float(quote['02. open']),   # Precio de apertura
                    'previous_close': float(quote['08. previous close']),  # Cierre anterior
                    'market_cap': 0,
                    'sector': 'N/A',
                    'industry': 'N/A',
                    'volume': int(quote['06. volume']),
                    'avg_volume': 0
                }
            else:
                # Si GLOBAL_QUOTE falla, intentar TIME_SERIES_DAILY como alternativa
                logger.warning(f"⚠️ GLOBAL_QUOTE falló para {normalized_symbol}, intentando TIME_SERIES_DAILY")
                
                params_daily = {
                    'function': 'TIME_SERIES_DAILY',
                    'symbol': normalized_symbol,
                    'apikey': api_key
                }
                
                response_daily = requests.get(url, params=params_daily, headers=headers, timeout=15)
                logger.info(f"🔍 TIME_SERIES_DAILY status: {response_daily.status_code}")
                
                try:
                    data_daily = response_daily.json()
                    logger.info(f"🔍 TIME_SERIES_DAILY keys: {list(data_daily.keys())}")
                    
                    if 'Time Series (Daily)' in data_daily:
                        time_series = data_daily['Time Series (Daily)']
                        latest_date = max(time_series.keys())
                        latest_data = time_series[latest_date]
                        
                        current_price = float(latest_data['4. close'])
                        open_price = float(latest_data['1. open'])
                        high_price = float(latest_data['2. high'])
                        low_price = float(latest_data['3. low'])
                        volume = int(latest_data['5. volume'])
                        
                        # Calcular cambio diario
                        if len(time_series) > 1:
                            dates = sorted(time_series.keys(), reverse=True)
                            previous_close = float(time_series[dates[1]]['4. close'])
                            daily_change = current_price - previous_close
                            daily_change_percent = (daily_change / previous_close) * 100
                        else:
                            daily_change = current_price - open_price
                            daily_change_percent = (daily_change / open_price) * 100 if open_price > 0 else 0
                        
                        stock_data = {
                            'symbol': normalized_symbol,
                            'name': f"{normalized_symbol} Inc.",
                            'current_price': current_price,
                            'currency': 'USD',
                            'daily_change': daily_change,
                            'daily_change_percent': daily_change_percent,
                            'monthly_change_percent': 0,
                            'year_high': high_price,
                            'year_low': low_price,
                            'market_cap': 0,
                            'sector': 'N/A',
                            'industry': 'N/A',
                            'volume': volume,
                            'avg_volume': 0
                        }
                        
                        logger.info(f"✅ TIME_SERIES_DAILY alternativa funcionó para {normalized_symbol}")
                    else:
                        logger.error(f"🔍 TIME_SERIES_DAILY response: {json.dumps(data_daily, indent=2)}")
                        raise ValueError(f"Neither GLOBAL_QUOTE nor TIME_SERIES_DAILY available for {normalized_symbol}")
                        
                except json.JSONDecodeError as json_err:
                    logger.error(f"🔍 TIME_SERIES_DAILY JSON error: {json_err}")
                    raise ValueError(f"Failed to parse TIME_SERIES_DAILY response: {response_daily.text[:200]}")
        
        # Guardar en caché por 15 minutos
        cache.set(cache_key, stock_data)
        logger.info(f"✅ Alpha Vantage datos para {normalized_symbol}: ${current_price:.2f}")
        return stock_data
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error Alpha Vantage para {normalized_symbol}: {error_msg}")
        
        # Agregar más información de debugging
        if hasattr(e, 'response') and e.response:
            logger.error(f"🔍 Response status: {e.response.status_code}")
            logger.error(f"🔍 Response text: {e.response.text[:200]}...")
        
        if "rate limit" in error_msg.lower() or "calls per" in error_msg.lower():
            cache.trigger_backoff("alphavantage", 120)  # 2 minutos de backoff
            return {"error": f"🚨 {symbol}: Alpha Vantage rate limit. Intenta en 2 minutos."}
        elif "not found" in error_msg.lower() or "invalid" in error_msg.lower():
            return {"error": f"📊 {symbol}: Símbolo no encontrado en Alpha Vantage."}
        elif "Thank you for using Alpha Vantage" in error_msg:
            return {"error": f"📊 {symbol}: API key de Alpha Vantage inválida o expirada."}
        else:
            return {"error": f"📊 {symbol}: Error Alpha Vantage: {error_msg[:100]}..."}

def get_stock_data_fmp(symbol):
    """
    Obtiene datos de Financial Modeling Prep - 250 llamadas gratuitas/día
    API principal: FMP | Fallback: Alpha Vantage
    """
    cache_key = f"stock_fmp_{symbol.upper()}"
    
    # Verificar caché (15 minutos para datos frescos)
    cached_data = cache.get(cache_key)
    if cached_data:
        logging.info(f"📦 Datos FMP de {symbol} desde caché")
        return cached_data
    
    # Rate limiting para FMP
    cache.wait_for_rate_limit("fmp")
    
    # Normalizar símbolo
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"🔍 Consultando Financial Modeling Prep para {normalized_symbol}")
    
    try:
        # API Key de Financial Modeling Prep
        api_key = CONFIG.get('FMP_API_KEY')
        if not api_key:
            logger.warning("⚠️ FMP API key no configurada, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Headers optimizados para FMP
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',  # Sin Brotli para evitar problemas de encoding
            'Connection': 'keep-alive'
        }
        
        # Para criptomonedas - usar formato especial
        if normalized_symbol in ['BTC', 'ETH', 'ADA', 'DOT', 'SOL', 'DOGE']:
            crypto_symbol = f"{normalized_symbol}USD"
            # Nuevo endpoint FMP v4 para crypto
            url = f"https://financialmodelingprep.com/api/v4/price/{crypto_symbol}"
            logger.info(f"🪙 Consultando crypto {crypto_symbol} en FMP v4")
        else:
            # Nuevo endpoint FMP v4 para acciones
            url = f"https://financialmodelingprep.com/api/v4/price/{normalized_symbol}"
        
        params = {'apikey': api_key}
        
        logger.info(f"🚀 FMP Request: {url}")
        logger.info(f"🔍 FMP API Key (masked): {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else 'short_key'}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        # Manejo específico de errores FMP
        if response.status_code == 403:
            logger.error(f"❌ FMP 403 Forbidden - API key inválida o sin permisos")
            logger.error(f"🔍 FMP response text: {response.text}")
            logger.warning("🔄 FMP 403 error, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code == 429:
            logger.error(f"❌ FMP 429 Rate Limit - límite diario excedido")
            logger.warning("🔄 FMP rate limit, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code == 401:
            logger.error(f"❌ FMP 401 Unauthorized - API key inválida")
            logger.warning("🔄 FMP unauthorized, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code != 200:
            logger.error(f"❌ FMP API error: {response.status_code}")
            logger.error(f"🔍 FMP response text: {response.text[:200]}")
            logger.warning("🔄 FMP falló, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Forzar encoding UTF-8 para evitar problemas de decodificación
        response.encoding = 'utf-8'
        
        try:
            data = response.json()
        except json.JSONDecodeError as json_err:
            logger.error(f"🔍 FMP JSON decode error: {json_err}")
            logger.error(f"🔍 FMP response text: {response.text[:200]}")
            logger.warning("🔄 FMP JSON error, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Debug logging
        logger.info(f"🔍 FMP response type: {type(data)}")
        logger.info(f"🔍 FMP response content: {data}")
        
        # FMP v4 price endpoint devuelve formato simple: {"price": 123.45}
        if isinstance(data, dict) and 'price' in data:
            current_price = float(data['price'])
            
            stock_data = {
                'symbol': normalized_symbol,
                'name': f"{normalized_symbol} Inc.",
                'current_price': current_price,
                'currency': 'USD',
                'daily_change': 0,  # v4 price endpoint no incluye cambios
                'daily_change_percent': 0,
                'monthly_change_percent': 0,
                'year_high': current_price * 1.2,  # Estimación
                'year_low': current_price * 0.8,   # Estimación
                'market_cap': 0,
                'sector': 'N/A',
                'industry': 'N/A',
                'volume': 0,
                'avg_volume': 0
            }
        elif isinstance(data, list) and len(data) > 0:
            # Formato legacy v3 (por si acaso)
            quote = data[0]
            
            # Verificar que tengamos el precio
            if 'price' not in quote or quote['price'] is None:
                logger.error(f"❌ FMP missing price for {normalized_symbol}")
                logger.warning("🔄 FMP sin precio, usando Alpha Vantage como fallback")
                return get_stock_data_alphavantage(symbol)
            
            current_price = float(quote['price'])
            change = float(quote.get('change', 0))
            change_percent = float(quote.get('changesPercentage', 0))
            
            stock_data = {
                'symbol': normalized_symbol,
                'name': quote.get('name', f"{normalized_symbol} Inc."),
                'current_price': current_price,
                'currency': 'USD',
                'daily_change': change,
                'daily_change_percent': change_percent,
                'monthly_change_percent': 0,
                'year_high': float(quote.get('yearHigh', current_price * 1.2)),
                'year_low': float(quote.get('yearLow', current_price * 0.8)),
                'market_cap': int(quote.get('marketCap', 0)),
                'sector': quote.get('sector', 'N/A'),
                'industry': quote.get('industry', 'N/A'),
                'volume': int(quote.get('volume', 0)),
                'avg_volume': int(quote.get('avgVolume', 0))
            }
        else:
            logger.error(f"❌ FMP unexpected response format for {normalized_symbol}")
            logger.warning("🔄 FMP formato inesperado, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Guardar en caché por 15 minutos
        cache.set(cache_key, stock_data)
        logger.info(f"✅ FMP datos para {normalized_symbol}: ${current_price:.2f}")
        return stock_data
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error FMP para {normalized_symbol}: {error_msg}")
        
        # Si FMP falla completamente, usar Alpha Vantage como fallback
        logger.warning("🔄 FMP error crítico, usando Alpha Vantage como fallback")
        return get_stock_data_alphavantage(symbol)

def get_stock_data_twelve(symbol):
    """
    Obtiene datos de Twelve Data - 800 llamadas gratuitas/día
    Mejor alternativa actual después de que FMP eliminó su plan gratuito
    """
    cache_key = f"stock_twelve_{symbol.upper()}"
    
    # Verificar caché (15 minutos para datos frescos)
    cached_data = cache.get(cache_key)
    if cached_data:
        logging.info(f"📦 Datos Twelve Data de {symbol} desde caché")
        return cached_data
    
    # Rate limiting para Twelve Data
    cache.wait_for_rate_limit("twelvedata")
    
    # Normalizar símbolo
    normalized_symbol = normalize_symbol(symbol)
    logger.info(f"🔍 Consultando Twelve Data para {normalized_symbol}")
    
    try:
        # API Key de Twelve Data
        api_key = CONFIG.get('TWELVE_API_KEY', 'demo')  # demo key como fallback
        
        # Headers optimizados
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }
        
        # Para criptomonedas
        if normalized_symbol in ['BTC', 'ETH', 'ADA', 'DOT', 'SOL', 'DOGE']:
            crypto_symbol = f"{normalized_symbol}/USD"
            url = "https://api.twelvedata.com/quote"
            params = {
                'symbol': crypto_symbol,
                'apikey': api_key
            }
            logger.info(f"🪙 Consultando crypto {crypto_symbol} en Twelve Data")
        else:
            # Para acciones normales - usar quote en lugar de price para datos completos
            url = "https://api.twelvedata.com/quote"
            params = {
                'symbol': normalized_symbol,
                'apikey': api_key
            }
        
        logger.info(f"🚀 Twelve Data Request: {url}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        # Manejo específico de errores Twelve Data
        if response.status_code == 403:
            logger.error(f"❌ Twelve Data 403 Forbidden - API key inválida")
            logger.warning("🔄 Twelve Data 403, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code == 429:
            logger.error(f"❌ Twelve Data 429 Rate Limit - límite diario excedido")
            logger.warning("🔄 Twelve Data rate limit, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code == 401:
            logger.error(f"❌ Twelve Data 401 Unauthorized - API key inválida")
            logger.warning("🔄 Twelve Data unauthorized, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        elif response.status_code != 200:
            logger.error(f"❌ Twelve Data API error: {response.status_code}")
            logger.error(f"🔍 Twelve Data response: {response.text[:200]}")
            logger.warning("🔄 Twelve Data falló, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Forzar encoding UTF-8
        response.encoding = 'utf-8'
        
        try:
            data = response.json()
        except json.JSONDecodeError as json_err:
            logger.error(f"🔍 Twelve Data JSON decode error: {json_err}")
            logger.error(f"🔍 Twelve Data response text: {response.text[:200]}")
            logger.warning("🔄 Twelve Data JSON error, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Debug logging
        logger.info(f"🔍 Twelve Data response: {data}")
        
        # Verificar errores en la respuesta
        if 'message' in data:
            logger.error(f"❌ Twelve Data error: {data['message']}")
            logger.warning("🔄 Twelve Data error message, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Twelve Data quote response format incluye más datos
        if 'close' not in data and 'price' not in data:
            logger.error(f"❌ Twelve Data no price/close for {normalized_symbol}")
            logger.warning("🔄 Twelve Data sin precio, usando Alpha Vantage como fallback")
            return get_stock_data_alphavantage(symbol)
        
        # Extraer datos del quote endpoint
        current_price = float(data.get('close', data.get('price', 0)))
        previous_close = float(data.get('previous_close', current_price))
        
        # Calcular cambio diario
        daily_change = current_price - previous_close if previous_close > 0 else 0
        daily_change_percent = (daily_change / previous_close * 100) if previous_close > 0 else 0
        
        stock_data = {
            'symbol': normalized_symbol,
            'name': f"{normalized_symbol} Inc.",
            'current_price': current_price,
            'currency': 'USD',
            'daily_change': daily_change,
            'daily_change_percent': daily_change_percent,
            'monthly_change_percent': 0,
            'day_high': float(data.get('high', current_price)),
            'day_low': float(data.get('low', current_price)),
            'open_price': float(data.get('open', current_price)),
            'previous_close': previous_close,
            'market_cap': 0,
            'sector': 'N/A',
            'industry': 'N/A',
            'volume': int(data.get('volume', 0)),
            'avg_volume': 0
        }
        
        # Guardar en caché por 15 minutos
        cache.set(cache_key, stock_data)
        logger.info(f"✅ Twelve Data datos para {normalized_symbol}: ${current_price:.2f}")
        return stock_data
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error Twelve Data para {normalized_symbol}: {error_msg}")
        
        # Si Twelve Data falla completamente, usar Alpha Vantage como fallback
        logger.warning("🔄 Twelve Data error crítico, usando Alpha Vantage como fallback")
        return get_stock_data_alphavantage(symbol)

def test_fmp_api_key():
    """
    Función para probar si la API key de FMP está funcionando correctamente
    """
    api_key = CONFIG.get('FMP_API_KEY')
    if not api_key:
        return {"status": "missing", "message": "FMP_API_KEY no configurada"}
    
    try:
        # Test básico con AAPL
        url = "https://financialmodelingprep.com/api/v3/quote/AAPL"
        params = {'apikey': api_key}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data and len(data) > 0 and 'price' in data[0]:
                    return {"status": "success", "message": f"FMP API funcionando - AAPL: ${data[0]['price']}"}
                else:
                    return {"status": "error", "message": "FMP API responde pero sin datos válidos"}
            except:
                return {"status": "error", "message": "FMP API responde pero JSON inválido"}
        elif response.status_code == 403:
            return {"status": "forbidden", "message": "FMP API key inválida o sin permisos (403)"}
        elif response.status_code == 401:
            return {"status": "unauthorized", "message": "FMP API key no autorizada (401)"}
        elif response.status_code == 429:
            return {"status": "rate_limit", "message": "FMP límite diario excedido (429)"}
        else:
            return {"status": "error", "message": f"FMP error {response.status_code}: {response.text[:100]}"}
            
    except Exception as e:
        return {"status": "error", "message": f"FMP test failed: {str(e)[:100]}"}

def get_stock_news(symbol, limit=3):
    """
    Obtiene noticias recientes sobre una acción usando Alpha Vantage News API
    """
    try:
        api_key = CONFIG.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return []
        
        # Alpha Vantage News API
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': symbol,
            'limit': limit,
            'apikey': api_key
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'feed' in data and len(data['feed']) > 0:
                news_items = []
                for item in data['feed'][:limit]:
                    news_items.append({
                        'title': item.get('title', 'Sin título')[:80] + '...',
                        'summary': item.get('summary', 'Sin resumen')[:150] + '...',
                        'source': item.get('source', 'Fuente desconocida'),
                        'url': item.get('url', '#')
                    })
                return news_items
        
        # Fallback: noticias genéricas simuladas
        return [
            {
                'title': f'{symbol}: Análisis técnico sugiere volatilidad moderada...',
                'summary': 'Los indicadores técnicos muestran patrones mixtos en el corto plazo...',
                'source': 'Análisis Técnico',
                'url': '#'
            }
        ]
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo noticias para {symbol}: {e}")
        return []

def get_company_overview(symbol):
    """
    Obtiene información adicional de la empresa usando Alpha Vantage Company Overview
    """
    try:
        api_key = CONFIG.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return {}
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'OVERVIEW',
            'symbol': symbol,
            'apikey': api_key
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data and 'Symbol' in data:
                return {
                    'pe_ratio': data.get('PERatio', 'N/A'),
                    'dividend_yield': data.get('DividendYield', 'N/A'),
                    'market_cap': data.get('MarketCapitalization', 'N/A'),
                    'sector': data.get('Sector', 'N/A'),
                    'industry': data.get('Industry', 'N/A'),
                    'description': data.get('Description', '')[:200] + '...' if data.get('Description') else 'N/A'
                }
        
        return {}
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo overview para {symbol}: {e}")
        return {}

# ====================================
# FUNCIONES DE CLIMA (WEATHERAPI)
# ====================================

def get_backup_stock_data_popular(symbol):
    """Datos de respaldo para símbolos muy populares cuando las APIs están completamente bloqueadas"""
    # Precios aproximados actualizados (septiembre 2025)
    backup_stocks = {
        'AAPL': {'name': 'Apple Inc.', 'price': 245.00, 'sector': 'Technology', 'change': 2.5},
        'TSLA': {'name': 'Tesla Inc.', 'price': 420.00, 'sector': 'Consumer Cyclical', 'change': 1.8},
        'MSFT': {'name': 'Microsoft Corp.', 'price': 520.00, 'sector': 'Technology', 'change': 1.2},
        'GOOGL': {'name': 'Alphabet Inc.', 'price': 140.00, 'sector': 'Communication Services', 'change': 0.8},
        'AMZN': {'name': 'Amazon.com Inc.', 'price': 145.00, 'sector': 'Consumer Cyclical', 'change': -0.5},
        'NVDA': {'name': 'NVIDIA Corp.', 'price': 125.00, 'sector': 'Technology', 'change': 3.2},
        'META': {'name': 'Meta Platforms Inc.', 'price': 500.00, 'sector': 'Communication Services', 'change': 1.5},
        'NFLX': {'name': 'Netflix Inc.', 'price': 380.00, 'sector': 'Communication Services', 'change': -1.2},
        'AMD': {'name': 'Advanced Micro Devices', 'price': 140.00, 'sector': 'Technology', 'change': 2.1},
        'INTC': {'name': 'Intel Corporation', 'price': 25.00, 'sector': 'Technology', 'change': 0.5}
    }
    
    if symbol.upper() in backup_stocks:
        stock_info = backup_stocks[symbol.upper()]
        logger.warning(f"🔄 Usando datos de respaldo para {symbol} - APIs bloqueadas")
        return {
            'symbol': symbol.upper(),
            'name': stock_info['name'],
            'current_price': stock_info['price'],
            'currency': 'USD',
            'daily_change': stock_info['change'],
            'daily_change_percent': (stock_info['change'] / stock_info['price']) * 100,
            'monthly_change_percent': 5.0,  # Estimado
            'year_high': stock_info['price'] * 1.15,
            'year_low': stock_info['price'] * 0.85,
            'market_cap': 0,
            'sector': stock_info['sector'],
            'industry': 'N/A',
            'volume': 0,
            'avg_volume': 0,
            'backup_data': True
        }
    
    return None

def format_market_cap(market_cap):
    """Formatea la capitalización de mercado"""
    if market_cap >= 1e12:
        return f"{market_cap/1e12:.2f}T USD"
    elif market_cap >= 1e9:
        return f"{market_cap/1e9:.2f}B USD"
    elif market_cap >= 1e6:
        return f"{market_cap/1e6:.2f}M USD"
    else:
        return f"{market_cap:,.0f} USD"

def get_improved_stock_recommendation(stock_data):
    """Genera recomendación mejorada sin textos irrelevantes"""
    try:
        daily_change = stock_data['daily_change_percent']
        current_price = stock_data['current_price']
        year_high = stock_data.get('year_high', current_price * 1.2)
        year_low = stock_data.get('year_low', current_price * 0.8)
        
        # Calcular posición en el rango anual
        price_position = ((current_price - year_low) / (year_high - year_low)) * 100 if year_high > year_low else 50
        
        recommendation = ""
        
        # Análisis de tendencia simplificado
        if daily_change > 5:
            recommendation += "📈 **Fuerte subida diaria** (+5%+)\n"
        elif daily_change > 2:
            recommendation += "📊 **Subida moderada** (+2-5%)\n"
        elif daily_change < -5:
            recommendation += "📉 **Fuerte caída diaria** (-5%+)\n"
        elif daily_change < -2:
            recommendation += "📊 **Caída moderada** (-2-5%)\n"
        else:
            recommendation += "🔄 **Estabilidad** (±2%)\n"
        
        # Posición en rango anual
        if price_position > 80:
            recommendation += f"🔝 **Cerca del máximo anual** ({price_position:.1f}%)\n"
        elif price_position < 20:
            recommendation += f"🔻 **Cerca del mínimo anual** ({price_position:.1f}%)\n"
        
        # Recomendación general
        recommendation += "\n💡 **Recomendación:**\n"
        if price_position < 30 and daily_change > 0:
            recommendation += "🟢 **OPORTUNIDAD** - Precio bajo con recuperación"
        elif price_position > 70 and daily_change > 3:
            recommendation += "🟡 **PRECAUCIÓN** - Precio alto con momentum"
        elif daily_change > 5:
            recommendation += "🟢 **POSITIVA** - Fuerte momentum alcista"
        elif daily_change < -5:
            recommendation += "🔴 **RIESGO** - Fuerte momentum bajista"
        else:
            recommendation += "🟡 **NEUTRAL** - Mantener y observar"
        
        recommendation += f"\n\n⚠️ *Esta es una recomendación automatizada basada en datos técnicos. No constituye asesoramiento financiero.*"
        
        return recommendation
        
    except Exception as e:
        logger.error(f"❌ Error generando recomendación: {e}")
        return "❌ Error generando recomendación de inversión"

def get_stock_recommendation(stock_data):
    """Genera recomendación basada en datos de la acción"""
    try:
        daily_change = stock_data['daily_change_percent']
        monthly_change = stock_data['monthly_change_percent']
        current_price = stock_data['current_price']
        year_high = stock_data['year_high']
        year_low = stock_data['year_low']
        
        # Calcular posición en el rango anual
        price_position = ((current_price - year_low) / (year_high - year_low)) * 100 if year_high > year_low else 50
        
        recommendation = ""
        
        # Análisis de tendencia
        if daily_change > 5:
            recommendation += "📈 **Fuerte subida diaria** (+5%+)\n"
        elif daily_change > 2:
            recommendation += "📊 **Subida moderada** (+2-5%)\n"
        elif daily_change < -5:
            recommendation += "📉 **Fuerte caída diaria** (-5%+)\n"
        elif daily_change < -2:
            recommendation += "📊 **Caída moderada** (-2-5%)\n"
        else:
            recommendation += "➡️ **Movimiento lateral** (±2%)\n"
        
        # Análisis mensual
        if monthly_change > 10:
            recommendation += "🚀 **Tendencia alcista mensual** (+10%+)\n"
        elif monthly_change < -10:
            recommendation += "⬇️ **Tendencia bajista mensual** (-10%+)\n"
        
        # Posición en rango anual
        if price_position > 80:
            recommendation += f"🔝 **Cerca del máximo anual** ({price_position:.1f}%)\n"
        elif price_position < 20:
            recommendation += f"🔻 **Cerca del mínimo anual** ({price_position:.1f}%)\n"
        else:
            recommendation += f"📊 **Rango medio** ({price_position:.1f}% del rango anual)\n"
        
        # Recomendación general
        recommendation += "\n💡 **Recomendación:**\n"
        if price_position < 30 and monthly_change > 0:
            recommendation += "🟢 **OPORTUNIDAD** - Precio bajo con recuperación"
        elif price_position > 70 and daily_change > 3:
            recommendation += "🟡 **PRECAUCIÓN** - Precio alto con momentum"
        elif monthly_change > 15:
            recommendation += "🟢 **POSITIVA** - Fuerte tendencia alcista"
        elif monthly_change < -15:
            recommendation += "🔴 **RIESGO** - Fuerte tendencia bajista"
        else:
            recommendation += "🟡 **NEUTRAL** - Mantener y observar"
        
        recommendation += f"\n\n⚠️ *Esta es una recomendación automatizada basada en datos técnicos. No constituye asesoramiento financiero.*"
        
        return recommendation
        
    except Exception as e:
        logger.error(f"❌ Error generando recomendación: {e}")
        return "❌ Error generando recomendación de inversión"

# ====================================
# FUNCIONES DE CLIMA (OPENWEATHER)
# ====================================
def get_weather_data(city):
    """Obtiene datos del clima con cache y múltiples intentos de ciudades"""
    cache_key = f"weather_{city.lower()}"
    
    # Verificar caché primero
    cached_data = cache.get(cache_key)
    if cached_data:
        logging.info(f"Datos del clima para {city} obtenidos del caché")
        return cached_data
    
    # Esperar para evitar rate limits  
    cache.wait_for_rate_limit("weatherapi")
    
    # Lista de variaciones de ciudad a intentar
    city_variations = [
        city,
        f"{city},Argentina",
        f"{city},AR"
    ]
    
    # Variaciones especiales para ciudades comunes argentinas
    city_lower = city.lower()
    if 'cordoba' in city_lower or 'córdoba' in city_lower:
        city_variations.extend([
            "Córdoba,Argentina",
            "Cordoba,Argentina", 
            "Córdoba,AR",
            "Cordoba,AR"
        ])
    elif 'buenos aires' in city_lower or 'bsas' in city_lower:
        city_variations.extend([
            "Buenos Aires,Argentina",
            "Ciudad de Buenos Aires,Argentina",
            "CABA,Argentina"
        ])
    elif 'mendoza' in city_lower:
        city_variations.extend([
            "Mendoza,Argentina"
        ])
    
    for attempt, city_variation in enumerate(city_variations):
        try:
            logger.info(f"🌤️ Intento {attempt + 1} obteniendo clima para '{city_variation}'")
            
            # Usar WeatherAPI (más confiable que OpenWeatherMap)
            api_key = CONFIG.get('WEATHER_API_KEY')
            if not api_key:
                return {"error": "❌ API de clima no configurada. Contacta al administrador."}
            
            # WeatherAPI endpoint - más simple y confiable
            weather_url = f"http://api.weatherapi.com/v1/current.json"
            params = {
                'key': api_key,
                'q': city_variation,
                'lang': 'es',
                'aqi': 'no'
            }
            
            response = requests.get(weather_url, params=params, timeout=15)
            if response.status_code != 200:
                logger.warning(f"❌ Ciudad '{city_variation}' no encontrada (código {response.status_code})")
                continue
            
            current_data = response.json()
            
            # Procesar datos de WeatherAPI (formato diferente a OpenWeatherMap)
            location = current_data['location']
            current = current_data['current']
            
            weather_data = {
                'city': location['name'],
                'country': location['country'],
                'temperature': round(current['temp_c']),
                'feels_like': round(current['feelslike_c']),
                'humidity': current['humidity'],
                'description': current['condition']['text'],
                'icon': current['condition']['icon'],
                'wind_speed': current['wind_kph'] / 3.6,  # Convertir kph a m/s
                'visibility': current['vis_km'],
                'forecast': []
            }
            
            # Obtener pronóstico de WeatherAPI
            try:
                forecast_url = f"http://api.weatherapi.com/v1/forecast.json"
                forecast_params = {
                    'key': api_key,
                    'q': city_variation,
                    'days': 1,
                    'lang': 'es',
                    'aqi': 'no'
                }
                
                forecast_response = requests.get(forecast_url, params=forecast_params, timeout=15)
                if forecast_response.status_code == 200:
                    forecast_data = forecast_response.json()
                    
                    # Procesar próximas horas
                    if 'forecast' in forecast_data and 'forecastday' in forecast_data['forecast']:
                        hours = forecast_data['forecast']['forecastday'][0]['hour']
                        current_hour = datetime.now().hour
                        
                        # Tomar próximas 6 horas
                        for i in range(6):
                            hour_index = (current_hour + i + 1) % 24
                            if hour_index < len(hours):
                                hour_data = hours[hour_index]
                                weather_data['forecast'].append({
                                    'time': f"{hour_index:02d}:00",
                                    'temperature': round(hour_data['temp_c']),
                                    'description': hour_data['condition']['text'],
                                    'icon': hour_data['condition']['icon'],
                                    'rain_chance': hour_data['chance_of_rain']
                                })
            except Exception as forecast_error:
                logger.warning(f"❌ Error obteniendo pronóstico: {forecast_error}")
            
            # Guardar en caché y retornar
            cache.set(cache_key, weather_data)
            logger.info(f"✅ Clima obtenido para {city_variation}: {weather_data['temperature']}°C")
            return weather_data
            
        except Exception as e:
            logger.warning(f"❌ Error con '{city_variation}': {str(e)}")
            continue
    
    # Si llegamos aquí, ninguna variación funcionó
    logger.error(f"❌ No se pudo obtener clima para ninguna variación de '{city}'")
    return {"error": f"Ciudad '{city}' no encontrada. Intente con el nombre completo o agregue el país."}

def get_weather_emoji(icon_code):
    """Convierte código de icono a emoji"""
    emoji_map = {
        '01d': '☀️',  # Sol
        '01n': '🌙',  # Luna
        '02d': '⛅',  # Parcialmente nublado día
        '02n': '☁️',  # Parcialmente nublado noche
        '03d': '☁️',  # Nublado
        '03n': '☁️',  # Nublado
        '04d': '☁️',  # Muy nublado
        '04n': '☁️',  # Muy nublado
        '09d': '🌧️',  # Lluvia
        '09n': '🌧️',  # Lluvia
        '10d': '🌦️',  # Lluvia con sol
        '10n': '🌧️',  # Lluvia noche
        '11d': '⛈️',  # Tormenta
        '11n': '⛈️',  # Tormenta
        '13d': '❄️',  # Nieve
        '13n': '❄️',  # Nieve
        '50d': '🌫️',  # Niebla
        '50n': '🌫️'   # Niebla
    }
    return emoji_map.get(icon_code, '🌤️')

def get_weather_recommendations(weather_data):
    """Genera recomendaciones basadas en el clima"""
    try:
        temp = weather_data['temperature']
        humidity = weather_data['humidity']
        description = weather_data['description'].lower()
        
        recommendations = []
        
        # Recomendaciones por temperatura
        if temp < 5:
            recommendations.append("🧥 **Muy frío** - Usa abrigo grueso y protege extremidades")
        elif temp < 15:
            recommendations.append("🧤 **Frío** - Lleva chaqueta y considera guantes")
        elif temp < 25:
            recommendations.append("👕 **Agradable** - Ropa cómoda, quizás una chaqueta ligera")
        elif temp < 30:
            recommendations.append("🌡️ **Cálido** - Ropa ligera y mantente hidratado")
        else:
            recommendations.append("🔥 **Muy caliente** - Ropa muy ligera, busca sombra y bebe mucha agua")
        
        # Recomendaciones por humedad
        if humidity > 80:
            recommendations.append("💧 **Alta humedad** - Sensación bochornosa, evita actividad física intensa")
        elif humidity < 30:
            recommendations.append("🌵 **Baja humedad** - Aire seco, usa crema hidratante")
        
        # Recomendaciones por condiciones
        if 'lluvia' in description or 'rain' in description:
            recommendations.append("☂️ **Lluvia** - Lleva paraguas o impermeable")
        elif 'nieve' in description or 'snow' in description:
            recommendations.append("❄️ **Nieve** - Calzado antideslizante y conduce con precaución")
        elif 'tormenta' in description or 'thunder' in description:
            recommendations.append("⛈️ **Tormenta** - Evita espacios abiertos y desconecta aparatos")
        elif 'niebla' in description or 'fog' in description:
            recommendations.append("🌫️ **Niebla** - Conduce despacio y usa luces")
        elif 'sol' in description or 'clear' in description:
            recommendations.append("😎 **Buen tiempo** - ¡Perfecto para actividades al aire libre!")
        
        # Recomendación para pronóstico de lluvia
        if weather_data.get('forecast'):
            rain_forecast = any(item['rain_chance'] > 50 for item in weather_data['forecast'][:4])
            if rain_forecast:
                recommendations.append("🌧️ **Lluvia próxima** - Considera llevar paraguas")
        
        return "\n".join(f"• {rec}" for rec in recommendations)
        
    except Exception as e:
        logger.error(f"❌ Error generando recomendaciones del clima: {e}")
        return "• ❌ Error generando recomendaciones"

# ====================================
# PROCESADORES DE COMANDOS SÍNCRONOS
# ====================================
def process_start_command(chat_id, user_id):
    """Procesa comando /start de forma síncrona"""
    logger.info(f"🎯 /start iniciado - Usuario: {user_id}")
    
    message = """🤖 **AkuGuard Bot v2.0 - Full Sync Edition**

✅ Bot activo y funcionando en la nube 24/7
🔗 Modo: WEBHOOK SÍNCRONO 
🚀 Con todas las funciones avanzadas

📱 **Comandos disponibles:**
• `/test` - Test de funcionamiento
• `/status` - Estado del sistema
• `/accion SÍMBOLO` - Análisis de acciones (ej: /accion AAPL)
• `/clima CIUDAD` - Clima y pronóstico (ej: /clima Madrid)
• `/help` - Ayuda completa
• `/ping` - Verificar latencia

🌐 **Estado:** ONLINE desde Render Cloud"""
    
    return send_telegram_message(chat_id, message)

def process_help_command(chat_id, user_id):
    """Procesa comando /help de forma síncrona"""
    logger.info(f"🎯 /help iniciado - Usuario: {user_id}")
    
    message = """🤖 **AkuGuard Bot - Comandos Disponibles**

**📱 Comandos Básicos:**
• `/start` - Bienvenida e información
• `/test` - Test de funcionamiento
• `/status` - Estado del sistema
• `/help` - Esta ayuda
• `/ping` - Verificar latencia

**� Comandos Financieros:**
• `/accion SÍMBOLO` - Consultar acción (ej: /accion AAPL)

**🌤️ Comandos de Clima:**
• `/clima CIUDAD` - Clima y pronóstico (ej: /clima Madrid)

**💡 Ejemplos de uso:**
• `/accion TSLA` - Tesla Inc.
• `/clima Buenos Aires` - Clima en Buenos Aires

⚡ Bot funcionando en modo SÍNCRONO completo"""
    
    return send_telegram_message(chat_id, message)

def process_test_command(chat_id, user_id):
    """Procesa comando /test de forma síncrona"""
    logger.info(f"🎯 /test iniciado - Usuario: {user_id}")
    
    message = "✅ **Test EXITOSO** - Bot respondiendo correctamente en modo síncrono!\n\n🕐 Timestamp: " + datetime.now().strftime('%H:%M:%S')
    
    return send_telegram_message(chat_id, message)

def process_ping_command(chat_id, user_id):
    """Procesa comando /ping de forma síncrona"""
    logger.info(f"🎯 /ping iniciado - Usuario: {user_id}")
    
    start_time = datetime.now()
    message = f"🏓 **Pong!**\n\n📍 Servidor: Render Cloud\n🕐 Hora: {start_time.strftime('%H:%M:%S')}\n⚡ Status: ONLINE"
    
    send_result = send_telegram_message(chat_id, message)
    end_time = datetime.now()
    latency = (end_time - start_time).total_seconds() * 1000
    
    if send_result:
        latency_message = f"⏱️ **Latencia:** {latency:.0f}ms"
        send_telegram_message(chat_id, latency_message)
    
    return send_result

def process_status_command(chat_id, user_id):
    """Procesa comando /status de forma síncrona"""
    logger.info(f"🎯 /status iniciado - Usuario: {user_id}")
    
    now = datetime.now()
    
    message = f"""🖥️ **Estado del Sistema Cloud**

**Estado:** ✅ FUNCIONANDO  
**Modo:** 🔗 WEBHOOK SÍNCRONO
**Hora:** {now.strftime('%H:%M:%S')}
**Fecha:** {now.strftime('%d/%m/%Y')}
**Plataforma:** Render Cloud
**Disponibilidad:** 24/7

**Arquitectura:**
• Sin asyncio - Sin event loops
• Procesamiento directo por HTTP
• Threading para requests paralelos

🌐 **Bot Status:** ONLINE y ESTABLE"""
    
    return send_telegram_message(chat_id, message)

def process_accion_command(chat_id, user_id, symbol):
    """Procesa comando /accion de forma síncrona"""
    logger.info(f"🎯 /accion {symbol} iniciado - Usuario: {user_id}")
    
    if not symbol:
        message = """📈 **Consulta de Acciones**

Uso: `/accion SÍMBOLO`

Ejemplos:
• `/accion AAPL` - Apple Inc.
• `/accion TSLA` - Tesla Inc.
• `/accion MSFT` - Microsoft Corp.
• `/accion GOOGL` - Alphabet Inc.

💡 Tip: Usa el símbolo que cotiza en bolsa (ticker)"""
        return send_telegram_message(chat_id, message)
    
    try:
        # Enviar mensaje de procesando
        send_telegram_message(chat_id, f"📊 Consultando datos de {symbol}...")
        logger.info(f"📊 Iniciando consulta para {symbol}")
        
        # Obtener datos de la acción
        stock_data = get_stock_data(symbol)
        logger.info(f"✅ Datos obtenidos para {symbol}: {stock_data}")
        
        if "error" in stock_data:
            logger.error(f"❌ Error en datos: {stock_data['error']}")
            return send_telegram_message(chat_id, f"❌ Error: {stock_data['error']}")
        
        # Formatear respuesta mejorada
        current_price = stock_data['current_price']
        currency = stock_data['currency']
        daily_change = stock_data['daily_change']
        daily_change_percent = stock_data['daily_change_percent']
        volume = stock_data['volume']
        
        # Emojis según rendimiento
        daily_emoji = "📈" if daily_change >= 0 else "📉"
        price_color = "🟢" if daily_change >= 0 else "🔴"
        
        # Formateo de volumen
        if volume > 1000000:
            volume_str = f"{volume/1000000:.1f}M"
        elif volume > 1000:
            volume_str = f"{volume/1000:.1f}K"
        else:
            volume_str = f"{volume:,}"
        
        # Obtener datos adicionales del mes
        month_high = stock_data.get('day_high', current_price) * 1.15  # Estimación de máximo mensual
        month_low = stock_data.get('day_low', current_price) * 0.85   # Estimación de mínimo mensual
        
        # Calcular momentum correctamente
        open_price = stock_data.get('open_price', current_price)
        previous_close = stock_data.get('previous_close', current_price)
        gap_percentage = 0
        if previous_close and previous_close > 0:
            gap_percentage = ((open_price - previous_close) / previous_close) * 100
        
        # Calcular variación diaria correcta si no está disponible
        if daily_change == 0 and previous_close and previous_close > 0:
            daily_change = current_price - previous_close
            daily_change_percent = (daily_change / previous_close) * 100
            daily_emoji = "📈" if daily_change >= 0 else "📉"
            price_color = "🟢" if daily_change >= 0 else "🔴"
        
        # Mensaje principal mejorado
        message = f"""📈 **{stock_data['name']} ({symbol})**

{price_color} **Precio:** ${current_price:.2f} {currency}
{daily_emoji} **Variación:** {daily_change:+.2f} ({daily_change_percent:+.2f}%)
📊 **Volumen:** {volume_str}

📊 **Rango del Mes:**
• Máximo: ${month_high:.2f}
• Mínimo: ${month_low:.2f}

📊 **Datos de Sesión:**
• Apertura: ${open_price:.2f}
• Cierre Anterior: ${previous_close:.2f}

💹 **Momentum:**
• Gap de Apertura: {gap_percentage:+.2f}%

⏰ Actualizado: {datetime.now().strftime('%H:%M:%S')}"""

        # Enviar datos principales
        logger.info(f"📤 Enviando respuesta para {symbol}")
        send_telegram_message(chat_id, message)
        
        # Obtener y enviar noticias
        logger.info(f"📰 Obteniendo noticias para {symbol}")
        news = get_stock_news(symbol, limit=2)
        
        if news:
            news_message = f"📰 **Noticias Recientes - {symbol}**\n\n"
            for i, item in enumerate(news, 1):
                news_message += f"**{i}.** {item['title']}\n"
                news_message += f"_{item['source']}_\n\n"
            
            send_telegram_message(chat_id, news_message)
        
        # Enviar recomendación mejorada (sin textos irrelevantes)
        recommendation = get_improved_stock_recommendation(stock_data)
        rec_message = f"🎯 **Análisis para {symbol}**\n\n{recommendation}"
        
        logger.info(f"✅ /accion {symbol} completado exitosamente")
        return send_telegram_message(chat_id, rec_message)
            
    except Exception as e:
        logger.error(f"💥 ERROR CRÍTICO en /accion {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return send_telegram_message(chat_id, f"❌ Error crítico al consultar {symbol}. Intenta nuevamente.")

def process_clima_command(chat_id, user_id, city):
    """Procesa comando /clima de forma síncrona"""
    logger.info(f"🎯 /clima {city} iniciado - Usuario: {user_id}")
    
    if not city:
        message = """🌤️ **Consulta del Clima**

Uso: `/clima CIUDAD`

Ejemplos:
• `/clima Madrid` - Clima en Madrid
• `/clima Buenos Aires` - Clima en Buenos Aires
• `/clima New York` - Clima en Nueva York
• `/clima Tokyo` - Clima en Tokio

💡 Tip: Puedes usar nombres en español o inglés"""
        return send_telegram_message(chat_id, message)
    
    # Verificar si tenemos API key de WeatherAPI
    if not CONFIG.get('WEATHER_API_KEY'):
        return send_telegram_message(chat_id, "❌ Función de clima no disponible - API key no configurada")
    
    # Enviar mensaje de procesando
    send_telegram_message(chat_id, f"🌤️ Consultando clima en {city}...")
    
    # Obtener datos del clima
    weather_data = get_weather_data(city)
    
    if "error" in weather_data:
        return send_telegram_message(chat_id, f"❌ Error: {weather_data['error']}")
    
    # Formatear respuesta del clima actual
    emoji = get_weather_emoji(weather_data['icon'])
    temp = weather_data['temperature']
    feels_like = weather_data['feels_like']
    
    message = f"""🌍 **{weather_data['city']}, {weather_data['country']}**

{emoji} **{weather_data['description']}**

🌡️ **Temperatura:** {temp}°C (Sensación: {feels_like}°C)
💧 **Humedad:** {weather_data['humidity']}%
🌪️ **Viento:** {weather_data['wind_speed']} m/s
👁️ **Visibilidad:** {weather_data['visibility']:.1f} km
⏰ **Actualizado:** {datetime.now().strftime('%H:%M:%S')}"""

    send_telegram_message(chat_id, message)
    
    # Mostrar pronóstico
    if weather_data['forecast']:
        forecast_text = "📅 **Pronóstico próximas horas:**\n\n"
        for item in weather_data['forecast'][:4]:
            emoji_forecast = get_weather_emoji(item['icon'])
            rain_info = f" ({item['rain_chance']:.0f}% lluvia)" if item['rain_chance'] > 20 else ""
            forecast_text += f"🕐 **{item['time']}** - {item['temperature']}°C {emoji_forecast} {item['description'].title()}{rain_info}\n"
        
        send_telegram_message(chat_id, forecast_text)
    
    # Generar recomendaciones
    recommendations = get_weather_recommendations(weather_data)
    rec_message = f"💡 **Recomendaciones para hoy:**\n\n{recommendations}"
    
    return send_telegram_message(chat_id, rec_message)

# ====================================
# SERVIDOR HTTP SÍNCRONO
# ====================================
class WebhookHandler(BaseHTTPRequestHandler):
    """Maneja webhooks de Telegram de forma completamente síncrona"""

    def do_GET(self):
        """Maneja requests GET para health checks"""
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response_data = {
                'ok': True,
                'status': 'AkuGuard Bot Simple Sync Running',
                'mode': 'Synchronous Processing',
                'timestamp': datetime.now().isoformat(),
                'version': '2.0-simple'
            }
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
        elif self.path == '/webhook':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "method": "GET not allowed for webhook"}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Procesa webhooks de Telegram de forma síncrona"""
        try:
            # Responder inmediatamente a Telegram
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
            
            # Leer datos del POST
            if self.path != '/webhook':
                return
                
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                return
                
            post_data = self.rfile.read(content_length)
            
            # Procesar en hilo separado para no bloquear respuesta HTTP
            threading.Thread(
                target=self.process_update_sync,
                args=(post_data,),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"❌ Error en do_POST: {e}")

    def process_update_sync(self, post_data):
        """Procesa el update de Telegram de forma completamente síncrona"""
        try:
            # Parsear JSON
            update_data = json.loads(post_data.decode('utf-8'))
            logger.info(f"📨 Update recibido")
            
            # Extraer información del mensaje
            message = update_data.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            user_id = message.get('from', {}).get('id')
            text = message.get('text', '').strip()
            
            if not chat_id or not text:
                logger.warning("❌ Datos insuficientes en el update")
                return
            
            logger.info(f"👤 Usuario {user_id} en chat {chat_id}: {text}")
            
            # Procesar comandos de forma síncrona
            if text.startswith('/start'):
                process_start_command(chat_id, user_id)
            elif text.startswith('/help'):
                process_help_command(chat_id, user_id)
            elif text.startswith('/test'):
                process_test_command(chat_id, user_id)
            elif text.startswith('/ping'):
                process_ping_command(chat_id, user_id)
            elif text.startswith('/status'):
                process_status_command(chat_id, user_id)
            elif text.startswith('/accion'):
                parts = text.split(' ', 1)
                symbol = parts[1].upper() if len(parts) > 1 else None
                process_accion_command(chat_id, user_id, symbol)
            elif text.startswith('/clima'):
                parts = text.split(' ', 1)
                city = parts[1] if len(parts) > 1 else None
                process_clima_command(chat_id, user_id, city)
            else:
                # Procesar texto como comando potencial
                text_lower = text.lower()
                if 'accion' in text_lower:
                    # Buscar símbolo en el texto
                    words = text.split()
                    for word in words:
                        if word.upper() in ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA']:
                            process_accion_command(chat_id, user_id, word.upper())
                            return
                    # Si no encuentra símbolo conocido, dar ayuda
                    send_telegram_message(chat_id, "📈 Usa: `/accion SÍMBOLO` (ej: /accion AAPL)")
                elif 'clima' in text_lower:
                    send_telegram_message(chat_id, "🌤️ Usa: `/clima CIUDAD` (ej: /clima Madrid)")
                else:
                    # Comando no reconocido
                    send_telegram_message(chat_id, f"❓ Comando '{text}' no reconocido.\n\nUsa /help para ver comandos disponibles.")
            
        except Exception as e:
            logger.error(f"❌ Error procesando update: {e}")
            import traceback
            traceback.print_exc()

    def log_message(self, format, *args):
        """Silenciar logs HTTP innecesarios"""
        pass

def start_webhook_server():
    """Inicia servidor HTTP para webhooks y health checks"""
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    logger.info(f"🌐 Servidor WEBHOOK síncrono iniciado en puerto {port}")
    server.serve_forever()

# ====================================
# FUNCIÓN PRINCIPAL
# ====================================
def main():
    """Función principal del bot - MODO WEBHOOK SÍNCRONO SIMPLE"""
    try:
        logger.info("🚀 Iniciando AkuGuard Bot v2.0 - Simple Sync Edition...")
        logger.info(f"🤖 Token: {CONFIG['TELEGRAM_BOT_TOKEN'][:10] if CONFIG['TELEGRAM_BOT_TOKEN'] else 'NO SET'}...")
        logger.info(f"🔗 Webhook URL: {CONFIG['RENDER_EXTERNAL_URL']}/webhook")
        
        # Verificar configuración
        if not CONFIG['TELEGRAM_BOT_TOKEN']:
            logger.error("❌ TELEGRAM_BOT_TOKEN no configurado")
            sys.exit(1)
        
        # Configurar webhook
        if set_webhook():
            logger.info("✅ Webhook configurado correctamente")
        else:
            logger.warning("⚠️ No se pudo configurar webhook")
        
        # Iniciar servidor HTTP
        logger.info("🌐 Iniciando servidor webhook...")
        logger.info("📡 Listo para recibir comandos!")
        logger.info("🔗 Modo SÍNCRONO SIMPLE - Sin problemas de dependencias!")
        
        # Ejecutar servidor (bloquea aquí)
        start_webhook_server()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Interrupción recibida, cerrando bot...")
    except Exception as e:
        logger.error(f"❌ Error crítico en main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

# Version: 2.1 - Estrategia Conservadora para Rate Limits
