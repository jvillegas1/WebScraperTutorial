# Web Scraper de Inmuebles — Venezuela y Argentina

Sistema automatizado para recolectar inmuebles en venta desde múltiples portales inmobiliarios, mantener una base de datos histórica, detectar oportunidades de precio y enviar alertas automáticas.

El proyecto está dividido en **dos tiers independientes**:

| Tier | Alcance | Portales | Frecuencia scheduler |
|------|---------|----------|----------------------|
| **Venezuela** | Nacional | 7 | Cada 6 horas |
| **Argentina** | Nacional | 10 | Cada 3 horas |

Incluye **CLI** para scraping y consultas, **dashboard web** (Streamlit) con pestañas por país, y **scheduler** para ejecución continua.

---

## Características

- **Multi-portal por región**: scrapers dedicados para Venezuela y Argentina
- **Base de datos histórica**: SQLite con historial de precios y columna `region`
- **Detección de oportunidades**: precio bajo relativo, bajadas de precio y umbrales absolutos
- **Alertas automáticas**: Email (SMTP) y Telegram (opcional)
- **Dashboard visual**: métricas, gráficos, listado de propiedades y oportunidades
- **Robusto**: reintentos automáticos, Playwright para sitios dinámicos, logging estructurado

### Portales — Venezuela

- MercadoLibre Venezuela
- TuInmueble.com
- Corotos.com.ve
- InfoCasas Venezuela
- OLX Venezuela
- RentaHouse
- REMAX Venezuela

### Portales — Argentina

- MercadoLibre Argentina
- Zonaprop
- Argenprop
- Properati
- Toctoc
- BuscaInmueble
- Lamudi
- Clarín Clasificados
- REMAX Argentina
- Century 21

---

## Requisitos previos

| Requisito | Detalle |
|-----------|---------|
| Python | 3.11 o superior |
| pip | Incluido con Python |
| Internet | Para scrapear portales y descargar dependencias |
| Chromium | Lo instala Playwright (portales con JavaScript) |
| Opcional | Cuenta Gmail y/o bot de Telegram para alertas |

Verifica Python:

```bash
python --version
```

---

## Instalación paso a paso

### 1. Obtener el proyecto

```bash
cd Web-scraper-Data
```

### 2. Crear y activar entorno virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

Deberías ver `(venv)` al inicio de la línea de comandos.

### 3. Instalar dependencias del scraper

```bash
pip install -r requirements.txt
```

### 4. Instalar dependencias del dashboard

Estas librerías no están en `requirements.txt` y son necesarias para la interfaz web:

```bash
pip install streamlit pandas plotly sqlalchemy
```

### 5. Instalar Playwright (obligatorio para varios portales)

```bash
playwright install chromium
```

En Linux, si hay errores de dependencias del sistema:

```bash
playwright install chromium --with-deps
```

### 6. Configurar variables de entorno (opcional)

Copia el archivo de ejemplo y edítalo:

```bash
# Windows
copy scraper\env_example.txt .env

# Linux/Mac
cp scraper/env_example.txt .env
```

También puedes colocar el `.env` dentro de `scraper/`.

Contenido mínimo (sin alertas):

```env
DEBUG=false
EMAIL_ENABLED=false
TELEGRAM_ENABLED=false
```

Para alertas por email (Gmail con contraseña de aplicación):

```env
EMAIL_ENABLED=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=contraseña_de_aplicacion
FROM_EMAIL=tu_email@gmail.com
TO_EMAILS=destinatario@email.com
```

Para Telegram:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
TELEGRAM_CHAT_IDS=tu_chat_id
```

---

## Configuración

### Archivo `scraper/regions.py`

Aquí se define la configuración de cada tier:

- Portales activos (`active_sources`)
- Frecuencia de scraping (`scraping_interval_hours`)
- Delays, reintentos y páginas máximas por portal
- Reglas de detección de oportunidades por región

Para desactivar un portal sin modificar código:

```python
"active_sources": {
    "mercadolibre": True,
    "zonaprop": False,  # desactivado
}
```

### Archivo `scraper/config.py`

Configuración global: rutas de la base de datos, alertas, logging y compatibilidad con código legacy.

---

## Verificación inicial

Desde la raíz del proyecto, con el entorno virtual activo:

```bash
python scraper/main.py version
```

Probar conexión a los portales:

```bash
python scraper/main.py test-connections --region venezuela
python scraper/main.py test-connections --region argentina
```

---

## Uso — Scraper y carga de datos

Los datos se guardan en `scraper/data/inmuebles.db`. Hasta que ejecutes el scraper, el dashboard mostrará la región correspondiente vacía.

### Scrapear Venezuela (todos los portales activos)

```bash
python scraper/main.py run --region venezuela
```

Portal específico:

```bash
python scraper/main.py run --region venezuela --source mercadolibre
python scraper/main.py run --region venezuela --source olx
```

Fuentes disponibles: `mercadolibre`, `tuinmueble`, `infocasas`, `olx`, `rentahouse`, `remax`.

### Scrapear Argentina (todos los portales activos)

```bash
python scraper/main.py run --region argentina
```

Portal específico:

```bash
python scraper/main.py run --region argentina --source zonaprop
python scraper/main.py run --region argentina --source mercadolibre
```

Fuentes disponibles: `mercadolibre`, `zonaprop`, `argenprop`, `properati`, `toctoc`, `buscainmueble`, `lamudi`, `clarin`, `remax`, `century21`.

### Scrapear ambas regiones

```bash
python scraper/main.py run --region venezuela
python scraper/main.py run --region argentina
```

### Modo debug

```bash
python scraper/main.py --debug run --region argentina --source mercadolibre
```

### Qué hace cada ejecución

1. Consulta cada portal activo de la región (HTTP o Playwright)
2. Recolecta inmuebles en venta a nivel nacional
3. Guarda o actualiza registros en SQLite (con columna `region`)
4. Registra historial de cambios de precio
5. Detecta oportunidades y envía alertas si están habilitadas

**Tiempo estimado:** Venezuela ~30–90 min (7 portales). Argentina ~45–120 min (10 portales), según red y bloqueos de los sitios.

---

## Uso — Consultas desde terminal

```bash
# Estadísticas (todas las regiones o filtradas)
python scraper/main.py stats
python scraper/main.py stats --region venezuela
python scraper/main.py stats --region argentina

# Oportunidades detectadas
python scraper/main.py opportunities
python scraper/main.py opportunities --region argentina

# Logs de ejecuciones recientes
python scraper/main.py logs

# Enviar alerta de prueba (requiere .env configurado)
python scraper/main.py test-alerts

# Ayuda general
python scraper/main.py --help
```

---

## Uso — Dashboard web

Desde la raíz del proyecto:

```bash
python run_dashboard.py
```

Abre en el navegador: **http://localhost:8501**

### Estructura del dashboard

| Pestaña principal | Contenido |
|-------------------|-----------|
| **Venezuela** | Datos del tier VE |
| **Argentina** | Datos del tier AR |

Cada tier incluye sub-pestañas:

- **Dashboard** — métricas y gráficos
- **Propiedades** — listado filtrable por portal, tipo y precio
- **Oportunidades** — inmuebles destacados por las reglas de detección
- **Sistema** — portales activos, estadísticas y comandos útiles

Si una región no tiene datos, el dashboard muestra un aviso con el comando para ejecutar el scraper. Usa el botón **Refrescar** en la pestaña Sistema después de scrapear.

Puerto alternativo si 8501 está ocupado:

```bash
python -m streamlit run scraper/dashboard.py --server.port 8502
```

---

## Uso — Scheduler (scraping automático)

Para ejecución continua sin intervención manual:

```bash
python scraper/main.py scheduler
```

| Job | Frecuencia |
|-----|------------|
| Scraping Venezuela | Cada 6 horas |
| Scraping Argentina | Cada 3 horas |
| Detección de oportunidades | Periódica (configurable por región) |

Detener con `Ctrl + C`.

---

## Flujo recomendado (primera vez)

```bash
# 1. Entorno
cd Web-scraper-Data
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 2. Dependencias
pip install -r requirements.txt
pip install streamlit pandas plotly sqlalchemy
playwright install chromium

# 3. Configuración mínima
copy scraper\env_example.txt .env

# 4. Verificar
python scraper/main.py version
python scraper/main.py test-connections --region venezuela

# 5. Cargar datos
python scraper/main.py run --region venezuela
python scraper/main.py run --region argentina

# 6. Ver resultados
python scraper/main.py stats
python run_dashboard.py
```

---

## Referencia rápida de comandos

| Acción | Comando |
|--------|---------|
| Scrapear Venezuela | `python scraper/main.py run --region venezuela` |
| Scrapear Argentina | `python scraper/main.py run --region argentina` |
| Un portal | `python scraper/main.py run --region argentina --source zonaprop` |
| Estadísticas | `python scraper/main.py stats --region venezuela` |
| Oportunidades | `python scraper/main.py opportunities` |
| Scheduler | `python scraper/main.py scheduler` |
| Dashboard | `python run_dashboard.py` |
| Ver portales | `python scraper/main.py version` |

---

## Estructura del proyecto

```
Web-scraper-Data/
├── run_dashboard.py          # Launcher del dashboard Streamlit
├── requirements.txt
├── README.md
└── scraper/
    ├── main.py               # CLI principal
    ├── config.py             # Configuración global
    ├── regions.py            # Configuración por tier (VE / AR)
    ├── dashboard.py          # Interfaz web
    ├── env_example.txt       # Plantilla de variables de entorno
    ├── sources/
    │   ├── base_scraper.py
    │   ├── mercadolibre.py   # Venezuela
    │   ├── tuinmueble.py
    │   ├── corotos.py
    │   ├── infocasas.py
    │   ├── olx.py
    │   ├── rentahouse.py
    │   ├── remax.py
    │   └── argentina/        # 10 scrapers para Argentina
    ├── parsers/
    ├── alerts/
    ├── storage/
    │   ├── database.py
    │   └── models.py
    ├── scheduler/
    ├── detection/
    ├── data/
    │   └── inmuebles.db      # Base de datos SQLite
    └── logs/
        └── scraper.log
```

---

## Detección de oportunidades

El sistema aplica 3 reglas (umbrales configurables por región en `scraper/regions.py`):

### 1. Precio bajo relativo

```
Precio < Promedio del tipo de inmueble × (1 - umbral%)
```

Venezuela: 15% por debajo del promedio. Argentina: 12%.

### 2. Bajada de precio

```
Precio actual < Precio anterior × (1 - umbral%)
```

Venezuela: 5%. Argentina: 3%.

### 3. Precio absoluto

```
Precio < Umbral definido por tipo de inmueble
```

Ejemplo Venezuela (USD): casa $50,000 · apartamento $35,000 · terreno $20,000.

Ejemplo Argentina (USD): casa $120,000 · apartamento $80,000 · terreno $40,000.

---

## Base de datos

SQLite en `scraper/data/inmuebles.db`:

| Tabla | Contenido |
|-------|-----------|
| `properties` | Inmuebles con columna `region` (`venezuela` / `argentina`) |
| `price_history` | Historial de cambios de precio |
| `alerts_sent` | Registro de alertas enviadas |
| `scraping_logs` | Log de cada ejecución del scraper |

---

## Agregar nuevos portales

1. Crear scraper en `scraper/sources/` (Venezuela) o `scraper/sources/argentina/` (Argentina)
2. Heredar de `BaseScraper` o `PlaywrightBaseScraper` / `ArgentinaPortalScraper`
3. Implementar: `_build_search_url()`, `_parse_listing_page()`, `_parse_property_detail()`, `_has_next_page()`
4. Registrar en `scraper/sources/__init__.py` o `scraper/sources/argentina/__init__.py`
5. Agregar URL y activación en `scraper/regions.py`

---

## Troubleshooting

### `no such column: region`

La base de datos es anterior a la versión con tiers. Ejecuta cualquier comando que inicialice la DB (aplica migración automática):

```bash
python scraper/main.py stats
```

### Argentina vacía en el dashboard

Es normal si aún no scrapeaste esa región:

```bash
python scraper/main.py run --region argentina
```

Recarga el dashboard o usa **Refrescar** en la pestaña Sistema.

### Error de conexión a portales

- Verifica tu conexión a internet
- Algunos portales bloquean IPs; espera unos minutos
- Aumenta los delays en `scraper/regions.py`
- Prueba un solo portal en debug: `python scraper/main.py --debug run --region argentina --source mercadolibre`

### Alertas no llegan

- Verifica `.env` (`EMAIL_ENABLED` / `TELEGRAM_ENABLED`)
- Para Gmail, usa contraseña de aplicación, no la contraseña normal
- Para Telegram, verifica token y `chat_id`

### Playwright no funciona

```bash
playwright install chromium
# Linux:
playwright install chromium --with-deps
```

### Dashboard no arranca

```bash
pip install streamlit pandas plotly sqlalchemy
```

### Base de datos corrupta

```bash
# Windows — backup y recrear
move scraper\data\inmuebles.db scraper\data\inmuebles.db.bak
python scraper/main.py run --region venezuela
```

---

## Licencia

MIT License — uso libre con atribución.

---

## Contribuciones

Las contribuciones son bienvenidas:

1. Fork el repositorio
2. Crea una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commit tus cambios
4. Push a la rama
5. Abre un Pull Request

Para reportar bugs o sugerir mejoras, abre un Issue en el repositorio.
