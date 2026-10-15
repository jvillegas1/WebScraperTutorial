"""
Dashboard de Inmuebles - Venezuela y Argentina
Interfaz con dos tiers independientes por país.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import sys
import os
from pathlib import Path

# Configurar paths
SCRAPER_DIR = Path(__file__).parent
PROJECT_ROOT = SCRAPER_DIR.parent
DB_PATH = SCRAPER_DIR / "data" / "inmuebles.db"

# Agregar al path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importar configuración directamente (sin imports relativos)
try:
    from scraper.regions import REGIONS, get_region_config, list_regions
    from scraper.geo.locations import list_divisions, list_sub_localities
except ImportError:
    REGIONS = {}
    list_regions = lambda: ["venezuela", "argentina"]
    get_region_config = lambda r: {}
    list_divisions = lambda r: []
    list_sub_localities = lambda r, d: []

# =============================================================================
# MODELOS SQLAlchemy (definidos localmente para evitar imports)
# =============================================================================
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Property(Base):
    """Modelo de propiedad para el dashboard."""
    __tablename__ = 'properties'
    
    id = Column(Integer, primary_key=True)
    id_externo = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False)
    region = Column(String(20), default='venezuela')
    titulo = Column(String(500))
    precio = Column(Float)
    moneda = Column(String(10), default='USD')
    ubicacion = Column(String(200))
    tipo_inmueble = Column(String(50))
    url = Column(String(500))
    fecha_primera_vista = Column(DateTime)
    fecha_ultima_vista = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_opportunity = Column(Boolean, default=False)
    metros_cuadrados = Column(Float)
    habitaciones = Column(Integer)
    banos = Column(Integer)
    estacionamientos = Column(Integer)
    descripcion = Column(Text)
    estado_provincia = Column(String(100), default='')
    localidad = Column(String(100), default='')
    sub_localidad = Column(String(100), default='')
    operacion = Column(String(20), default='venta')

# =============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Practica taller de WEB Scrapping",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# ESTILOS CSS PERSONALIZADOS
# =============================================================================
st.markdown("""
<style>
    /* Fuente principal */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
    }
    
    /* Tema oscuro elegante */
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
    }
    
    /* Métricas */
    .metric-card {
        background: linear-gradient(145deg, #1e1e3f, #2d2d5a);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00d4ff, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .metric-label {
        color: #94a3b8;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Cards de propiedades */
    .property-card {
        background: rgba(30, 30, 60, 0.6);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        border: 1px solid rgba(255, 255, 255, 0.08);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .property-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(124, 58, 237, 0.2);
    }
    
    .price-tag {
        font-size: 1.5rem;
        font-weight: 700;
        color: #10b981;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .opportunity-badge {
        background: linear-gradient(90deg, #f59e0b, #ef4444);
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background: rgba(15, 15, 35, 0.95);
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #e2e8f0 !important;
    }
    
    /* Tablas */
    .dataframe {
        background: rgba(30, 30, 60, 0.4) !important;
    }
    
    /* Botones */
    .stButton > button {
        background: linear-gradient(90deg, #7c3aed, #2563eb);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: 600;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.4);
    }
    
    /* Inputs */
    .stSelectbox, .stMultiSelect, .stSlider {
        background: rgba(30, 30, 60, 0.6);
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# Columnas esperadas en el DataFrame de propiedades
PROPERTY_DF_COLUMNS = [
    'id', 'id_externo', 'source', 'region', 'operacion', 'estado_provincia', 'localidad',
    'sub_localidad', 'titulo', 'precio', 'moneda',
    'ubicacion', 'tipo_inmueble', 'url', 'fecha_primera_vista', 'fecha_ultima_vista',
    'is_opportunity', 'metros_cuadrados', 'habitaciones', 'banos',
]


def empty_properties_df() -> pd.DataFrame:
    return pd.DataFrame(columns=PROPERTY_DF_COLUMNS)
@st.cache_resource
def get_database():
    """Obtiene conexión a la base de datos y aplica migraciones."""
    from scraper.storage.database import Database
    Database(DB_PATH)
    engine = create_engine(f'sqlite:///{DB_PATH}')
    Session = sessionmaker(bind=engine)
    return engine, Session


@st.cache_data(ttl=60)
def load_properties(region: str = None):
    """Carga propiedades de la base de datos, opcionalmente filtradas por región."""
    engine, Session = get_database()
    session = Session()
    try:
        query = session.query(Property).filter_by(is_active=True)
        if region:
            query = query.filter_by(region=region)
        properties = query.all()
        
        data = []
        for p in properties:
            data.append({
                'id': p.id,
                'id_externo': p.id_externo,
                'source': p.source,
                'region': getattr(p, 'region', 'venezuela') or 'venezuela',
                'operacion': getattr(p, 'operacion', 'venta') or 'venta',
                'estado_provincia': getattr(p, 'estado_provincia', '') or '',
                'localidad': getattr(p, 'localidad', '') or '',
                'sub_localidad': getattr(p, 'sub_localidad', '') or '',
                'titulo': p.titulo or '',
                'precio': p.precio or 0,
                'moneda': p.moneda or 'USD',
                'ubicacion': p.ubicacion or '',
                'tipo_inmueble': p.tipo_inmueble or 'otro',
                'url': p.url or '',
                'fecha_primera_vista': p.fecha_primera_vista,
                'fecha_ultima_vista': p.fecha_ultima_vista,
                'is_opportunity': p.is_opportunity or False,
                'metros_cuadrados': p.metros_cuadrados,
                'habitaciones': p.habitaciones,
                'banos': p.banos,
            })

        return pd.DataFrame(data) if data else empty_properties_df()
    finally:
        session.close()


@st.cache_data(ttl=60)
def get_stats(region: str = None):
    """Obtiene estadísticas generales, opcionalmente por región."""
    engine, Session = get_database()
    session = Session()
    try:
        base_query = session.query(Property)
        active_query = session.query(Property).filter_by(is_active=True)
        opp_query = session.query(Property).filter_by(is_opportunity=True, is_active=True)

        if region:
            base_query = base_query.filter_by(region=region)
            active_query = active_query.filter_by(region=region)
            opp_query = opp_query.filter_by(region=region)

        total = base_query.count()
        active = active_query.count()
        opportunities = opp_query.count()
        
        by_source = session.query(
            Property.source, 
            func.count(Property.id)
        )
        if region:
            by_source = by_source.filter(Property.region == region)
        by_source = by_source.filter(Property.is_active == True).group_by(Property.source).all()
        by_source_dict = {source: count for source, count in by_source}
        
        by_type = session.query(
            Property.tipo_inmueble, 
            func.count(Property.id)
        )
        if region:
            by_type = by_type.filter(Property.region == region)
        by_type = by_type.filter(Property.is_active == True).group_by(Property.tipo_inmueble).all()
        by_type_dict = {ptype: count for ptype, count in by_type}
        
        return {
            'total_properties': total,
            'active_properties': active,
            'opportunities': opportunities,
            'properties_by_source': by_source_dict,
            'properties_by_type': by_type_dict,
        }
    finally:
        session.close()


def format_price(price, currency="USD"):
    """Formatea precio para mostrar."""
    if pd.isna(price):
        return "N/A"
    return f"${price:,.0f} {currency}"


# =============================================================================
# SIDEBAR - FILTROS
# =============================================================================
def render_filters(region: str):
    """Renderiza filtros dentro del tab de la región."""
    region_cfg = get_region_config(region)
    st.markdown(f"### {region_cfg.get('flag', '')} {region_cfg.get('label', region.title())}")

    df = load_properties(region)
    
    if df.empty:
        st.warning("No hay propiedades cargadas para esta región. Ejecuta el scraper primero.")
        return {}

    col1, col2, col3, col4 = st.columns(4)

    division_label = "Estado" if region == "venezuela" else "Provincia"
    divisions = list_divisions(region)
    db_divisions = sorted(df['estado_provincia'].dropna().replace('', pd.NA).dropna().unique().tolist())
    division_options = ['Todos'] + sorted(set(divisions + db_divisions))

    with col1:
        selected_division = st.selectbox(
            f"📍 {division_label}",
            division_options,
            key=f"division_{region}",
        )

    sub_locality_options = ['Todos']
    if region == "argentina" and selected_division != 'Todos':
        if selected_division == "Ciudad Autónoma de Buenos Aires":
            sub_label = "Barrio (CABA)"
            sub_locality_options += list_sub_localities(region, selected_division)
        elif selected_division == "Buenos Aires":
            sub_label = "Partido (GBA)"
            sub_locality_options += list_sub_localities(region, selected_division)
        else:
            sub_label = "Localidad"
            db_subs = sorted(
                df[df['estado_provincia'] == selected_division]['sub_localidad']
                .dropna().replace('', pd.NA).dropna().unique().tolist()
            )
            sub_locality_options += db_subs
    elif region == "venezuela" and selected_division != 'Todos':
        sub_label = "Ciudad / Municipio"
        db_subs = sorted(
            df[df['estado_provincia'] == selected_division]['sub_localidad']
            .dropna().replace('', pd.NA).dropna().unique().tolist()
        )
        sub_locality_options += db_subs
    else:
        sub_label = "Detalle"

    with col2:
        selected_sub = st.selectbox(
            f"🏘️ {sub_label}",
            sub_locality_options,
            key=f"sub_locality_{region}",
            disabled=len(sub_locality_options) <= 1,
        )

    with col3:
        sources = ['Todos'] + sorted(df['source'].unique().tolist())
        selected_source = st.selectbox("📡 Portal", sources, key=f"source_{region}")

    with col4:
        operaciones = ['Todos', 'Venta', 'Alquiler']
        selected_operation = st.selectbox(
            "📋 Operación",
            operaciones,
            key=f"operation_{region}",
        )

    col5, col6, col7, col8 = st.columns(4)

    with col5:
        types = ['Todos'] + sorted(df['tipo_inmueble'].dropna().unique().tolist())
        selected_type = st.selectbox("🏠 Tipo", types, key=f"type_{region}")

    with col6:
        default_currency = region_cfg.get("default_currency", "USD")
        is_rent = selected_operation == 'Alquiler'
        if region == "argentina":
            if is_rent:
                price_min, price_max, price_default = 100, 500000, (100, 500000)
            else:
                price_min, price_max, price_default = 10000, 2000000, (10000, 2000000)
        else:
            if is_rent:
                price_min, price_max, price_default = 50, 5000, (50, 5000)
            else:
                price_min, price_max, price_default = 200, 1000000, (200, 1000000)
        price_range = st.slider(
            f"💰 Precio ({default_currency})",
            min_value=price_min, max_value=price_max, value=price_default,
            step=50 if is_rent else (1000 if region == "venezuela" else 5000),
            key=f"price_{region}",
        )

    with col7:
        only_opportunities = st.checkbox("🔥 Solo oportunidades", value=False, key=f"opp_{region}")

    with col8:
        st.caption(f"{len(df):,} propiedades en base de datos")

    with st.expander("📊 Portales activos y configuración"):
        cols = st.columns(3)
        active_sources = region_cfg.get("active_sources", {})
        for i, (source, active) in enumerate(active_sources.items()):
            with cols[i % 3]:
                st.markdown(f"{'✅' if active else '❌'} {source.capitalize()}")
        st.caption(
            f"Scraping automático cada {region_cfg.get('scraping_interval_hours', 6)} horas · "
            f"Operaciones: {', '.join(region_cfg.get('scraping', {}).get('operations', ['venta']))}"
        )

    op_value = selected_operation.lower() if selected_operation != 'Todos' else 'Todos'
    return {
        'division': selected_division,
        'sub_locality': selected_sub,
        'source': selected_source,
        'operation': op_value,
        'type': selected_type,
        'price_range': price_range,
        'only_opportunities': only_opportunities
    }


def apply_filters(df, filters):
    """Aplica filtros al DataFrame."""
    if df.empty:
        return df
    
    filtered = df.copy()

    if filters.get('division') and filters['division'] != 'Todos':
        if 'estado_provincia' in filtered.columns:
            filtered = filtered[filtered['estado_provincia'] == filters['division']]
        else:
            filtered = filtered[
                filtered['ubicacion'].str.contains(filters['division'], case=False, na=False)
            ]

    if filters.get('sub_locality') and filters['sub_locality'] != 'Todos':
        if 'sub_localidad' in filtered.columns:
            mask = filtered['sub_localidad'] == filters['sub_locality']
            if not mask.any() and 'ubicacion' in filtered.columns:
                mask = filtered['ubicacion'].str.contains(
                    filters['sub_locality'], case=False, na=False
                )
            filtered = filtered[mask]
    
    if filters.get('source') and filters['source'] != 'Todos':
        filtered = filtered[filtered['source'] == filters['source']]

    if filters.get('operation') and filters['operation'] != 'Todos':
        if 'operacion' in filtered.columns:
            filtered = filtered[filtered['operacion'] == filters['operation']]
    
    if filters.get('type') and filters['type'] != 'Todos':
        filtered = filtered[filtered['tipo_inmueble'] == filters['type']]
    
    if filters.get('price_range'):
        min_p, max_p = filters['price_range']
        filtered = filtered[(filtered['precio'] >= min_p) & (filtered['precio'] <= max_p)]
    
    if filters.get('only_opportunities') and 'is_opportunity' in filtered.columns:
        filtered = filtered[filtered['is_opportunity'] == True]
    
    return filtered


# =============================================================================
# MÉTRICAS PRINCIPALES
# =============================================================================
def render_metrics(filtered_df, total_df):
    """Renderiza las métricas principales basadas en los datos filtrados."""
    
    # Métricas del filtro actual
    filtered_count = len(filtered_df)
    total_count = len(total_df)
    opportunities_count = (
        len(filtered_df[filtered_df['is_opportunity'] == True])
        if not filtered_df.empty and 'is_opportunity' in filtered_df.columns
        else 0
    )
    
    # Precio promedio filtrado
    avg_price = filtered_df['precio'].mean() if not filtered_df.empty else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{filtered_count:,}</div>
            <div class="metric-label">Resultados Filtrados</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{total_count:,}</div>
            <div class="metric-label">Total en BD</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{opportunities_count:,}</div>
            <div class="metric-label">Oportunidades</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">${avg_price:,.0f}</div>
            <div class="metric-label">Precio Promedio</div>
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# GRÁFICOS
# =============================================================================
def render_charts(df):
    """Renderiza gráficos de análisis."""
    if df.empty:
        st.warning("No hay datos para mostrar gráficos")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📊 Propiedades por Portal")
        
        source_counts = df['source'].value_counts()
        
        fig_source = px.pie(
            values=source_counts.values,
            names=source_counts.index,
            color_discrete_sequence=px.colors.sequential.Viridis,
            hole=0.4
        )
        fig_source.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#e2e8f0',
            legend=dict(orientation="h", yanchor="bottom", y=-0.2)
        )
        st.plotly_chart(fig_source, use_container_width=True)
    
    with col2:
        st.markdown("### 🏠 Propiedades por Tipo")
        
        type_counts = df['tipo_inmueble'].value_counts()
        
        fig_type = px.bar(
            x=type_counts.index,
            y=type_counts.values,
            color=type_counts.values,
            color_continuous_scale='Viridis'
        )
        fig_type.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#e2e8f0',
            xaxis_title="",
            yaxis_title="Cantidad",
            showlegend=False
        )
        fig_type.update_traces(marker_line_width=0)
        st.plotly_chart(fig_type, use_container_width=True)
    
    # Distribución de precios
    st.markdown("### 💰 Distribución de Precios")
    
    # Filtrar precios razonables para el histograma
    price_df = df[df['precio'] <= df['precio'].quantile(0.95)]
    
    fig_price = px.histogram(
        price_df,
        x='precio',
        nbins=50,
        color='tipo_inmueble',
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig_price.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#e2e8f0',
        xaxis_title="Precio (USD)",
        yaxis_title="Cantidad",
        legend_title="Tipo"
    )
    st.plotly_chart(fig_price, use_container_width=True)
    
    # Precio promedio por tipo
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("### 📈 Precio Promedio por Tipo")
        
        avg_price = df.groupby('tipo_inmueble')['precio'].mean().sort_values(ascending=True)
        
        fig_avg = px.bar(
            x=avg_price.values,
            y=avg_price.index,
            orientation='h',
            color=avg_price.values,
            color_continuous_scale='Turbo'
        )
        fig_avg.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#e2e8f0',
            xaxis_title="Precio Promedio (USD)",
            yaxis_title="",
            showlegend=False
        )
        st.plotly_chart(fig_avg, use_container_width=True)
    
    with col4:
        st.markdown("### 📊 Precio por Portal")
        
        portal_price = df.groupby('source')['precio'].agg(['mean', 'min', 'max']).reset_index()
        
        fig_portal = go.Figure()
        fig_portal.add_trace(go.Bar(
            name='Promedio',
            x=portal_price['source'],
            y=portal_price['mean'],
            marker_color='#7c3aed'
        ))
        fig_portal.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#e2e8f0',
            xaxis_title="",
            yaxis_title="Precio (USD)",
        )
        st.plotly_chart(fig_portal, use_container_width=True)


# =============================================================================
# TABLA DE PROPIEDADES
# =============================================================================
def render_properties_table(df, filters, region: str = "venezuela"):
    """Renderiza la tabla de propiedades."""
    if df.empty:
        if not filters:
            st.warning("⚠️ No hay propiedades en esta región todavía")
            st.info("Ejecuta el scraper para cargar datos.")
        else:
            st.warning("⚠️ No hay propiedades que coincidan con los filtros seleccionados")
            st.info("Intenta ajustar los filtros para ver más resultados.")
        return
    
    # Mostrar resumen de filtros aplicados
    filter_tags = []
    if filters.get('division') and filters['division'] != 'Todos':
        filter_tags.append(f"{'Estado' if region == 'venezuela' else 'Provincia'}: **{filters['division']}**")
    if filters.get('sub_locality') and filters['sub_locality'] != 'Todos':
        filter_tags.append(f"Localidad: **{filters['sub_locality']}**")
    if filters.get('source') and filters['source'] != 'Todos':
        filter_tags.append(f"Portal: **{filters['source']}**")
    if filters.get('operation') and filters['operation'] != 'Todos':
        filter_tags.append(f"Operación: **{filters['operation'].capitalize()}**")
    if filters.get('type') and filters['type'] != 'Todos':
        filter_tags.append(f"Tipo: **{filters['type']}**")
    if filters.get('price_range') and filters['price_range'] != (200, 1000000):
        min_p, max_p = filters['price_range']
        filter_tags.append(f"Precio: **${min_p:,} - ${max_p:,}**")
    if filters.get('only_opportunities'):
        filter_tags.append("**Solo oportunidades**")
    
    st.markdown(f"### 📋 Listado de Propiedades ({len(df)} resultados)")
    
    if filter_tags:
        st.markdown("🔍 Filtros: " + " | ".join(filter_tags))
    
    # Ordenamiento
    sort_options = {
        'Precio (menor a mayor)': ('precio', True),
        'Precio (mayor a menor)': ('precio', False),
        'Más recientes': ('fecha_ultima_vista', False),
        'Más antiguos': ('fecha_primera_vista', True),
    }
    
    sort_by = st.selectbox(
        "Ordenar por:",
        list(sort_options.keys()),
        key=f"sort_{region}",
    )
    sort_col, ascending = sort_options[sort_by]
    
    df_sorted = df.sort_values(by=sort_col, ascending=ascending)
    
    # Mostrar propiedades
    for idx, row in df_sorted.head(50).iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                opportunity_badge = "🔥 " if row['is_opportunity'] else ""
                st.markdown(f"**{opportunity_badge}{row['titulo'][:80]}...**" if len(str(row['titulo'])) > 80 else f"**{opportunity_badge}{row['titulo']}**")
                loc_parts = [
                    p for p in [
                        row.get('estado_provincia', ''),
                        row.get('sub_localidad', '') or row.get('localidad', ''),
                    ] if p
                ]
                loc_detail = " · ".join(loc_parts) if loc_parts else row['ubicacion']
                op_label = row.get('operacion', 'venta')
                st.caption(
                    f"📍 {loc_detail} | 📋 {op_label.capitalize()} | "
                    f"🏷️ {row['tipo_inmueble']} | 📡 {row['source']}"
                )
            
            with col2:
                st.markdown(f"### ${row['precio']:,.0f}")
                st.caption(row['moneda'])
            
            with col3:
                st.link_button(
                    "🔗 Ver",
                    row['url'],
                    use_container_width=True,
                    key=f"link_{region}_{row['id']}",
                )
            
            st.markdown("---")


# =============================================================================
# OPORTUNIDADES
# =============================================================================
def render_opportunities(df, region: str):
    """Renderiza sección de oportunidades."""
    region_cfg = get_region_config(region)

    if df.empty or 'is_opportunity' not in df.columns:
        st.info("No hay propiedades cargadas para esta región todavía.")
        st.markdown(f"""
        ```bash
        python scraper/main.py run --region {region}
        ```
        """)
        return

    opportunities = df[df['is_opportunity'] == True]

    if opportunities.empty:
        st.info("No se han detectado oportunidades aún.")
        st.markdown(f"""
        ```bash
        python scraper/main.py run --region {region}
        ```
        """)
        return
    
    st.markdown(f"### 🔥 Oportunidades Detectadas ({len(opportunities)})")
    
    with st.expander("📋 Reglas de Detección"):
        st.json(region_cfg.get("opportunity_rules", {}))
    
    # Mostrar oportunidades
    for idx, row in opportunities.iterrows():
        st.markdown(f"""
        <div class="property-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span class="opportunity-badge">OPORTUNIDAD</span>
                    <h4 style="margin: 10px 0; color: #e2e8f0;">{row['titulo'][:60]}...</h4>
                    <p style="color: #94a3b8;">📍 {row['ubicacion']} | 🏷️ {row['tipo_inmueble']}</p>
                </div>
                <div class="price-tag">${row['precio']:,.0f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# =============================================================================
# PÁGINA PRINCIPAL
# =============================================================================
def render_region_dashboard(region: str):
    """Renderiza el dashboard completo de una región."""
    region_cfg = get_region_config(region)
    filters = render_filters(region)
    df = load_properties(region)
    filtered_df = apply_filters(df, filters)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🏠 Propiedades", "🔥 Oportunidades", "⚙️ Sistema"])

    with tab1:
        if df.empty:
            st.warning("No hay propiedades cargadas para esta región.")
            st.info(f"Ejecuta: `python scraper/main.py run --region {region}`")
        else:
            render_metrics(filtered_df, df)
            st.markdown("---")
            render_charts(filtered_df)

    with tab2:
        render_properties_table(filtered_df, filters, region)

    with tab3:
        render_opportunities(filtered_df, region)

    with tab4:
        st.markdown("### ⚙️ Estado del Sistema")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 📡 Portales Configurados")
            for source, active in region_cfg.get("active_sources", {}).items():
                status_icon = "🟢" if active else "🔴"
                st.markdown(f"{status_icon} **{source.capitalize()}**")

        with col2:
            st.markdown("#### 📊 Estadísticas")
            stats = get_stats(region)
            st.json(stats)

        st.markdown("---")
        st.markdown("#### 🚀 Comandos Útiles")
        st.code(f"""
# Ejecutar todos los scrapers de {region_cfg.get('label', region)}
python scraper/main.py run --region {region}

# Portal específico
python scraper/main.py run --region {region} --source mercadolibre

# Estadísticas
python scraper/main.py stats --region {region}

# Scheduler (ambas regiones)
python scraper/main.py scheduler
        """, language="bash")

        if st.button(f"🔄 Refrescar {region_cfg.get('label', region)}", key=f"refresh_{region}", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


def main():
    """Función principal del dashboard."""
    st.markdown("""
    <div style="text-align: center; padding: 20px 0;">
        <h1 style="font-size: 3rem; margin-bottom: 0;">
            🏠 Taller de web scrapping PRACTICA 01
        </h1>
        <p style="color: #94a3b8; font-size: 1.2rem;">
            Venezuela · Argentina
        </p>
    </div>
    """, unsafe_allow_html=True)

    tab_ve, tab_ar = st.tabs(["🇻🇪 Venezuela", "🇦🇷 Argentina"])

    with tab_ve:
        render_region_dashboard("venezuela")

    with tab_ar:
        render_region_dashboard("argentina")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #64748b; padding: 20px;">
        <p>Venezuela: cobertura nacional · Argentina: 10 portales con scraping cada 3 horas</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

