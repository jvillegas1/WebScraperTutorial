"""
Parser y normalizador de datos de propiedades inmobiliarias.
Define el modelo de datos estándar y funciones de normalización.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum


class PropertyType(str, Enum):
    """Tipos de inmuebles soportados."""
    CASA = "casa"
    APARTAMENTO = "apartamento"
    TERRENO = "terreno"
    LOCAL = "local"
    OFICINA = "oficina"
    TOWNHOUSE = "townhouse"
    PENTHOUSE = "penthouse"
    GALPON = "galpon"
    FINCA = "finca"
    OTRO = "otro"


class Currency(str, Enum):
    """Monedas soportadas."""
    USD = "USD"
    VES = "VES"
    ARS = "ARS"
    EUR = "EUR"


@dataclass
class Property:
    """
    Modelo de datos normalizado para una propiedad inmobiliaria.
    Todos los scrapers deben devolver instancias de esta clase.
    """
    id_externo: str
    source: str
    titulo: str
    precio: float
    moneda: str
    ubicacion: str
    tipo_inmueble: str
    url: str
    region: str = "venezuela"
    estado_provincia: str = ""
    localidad: str = ""
    sub_localidad: str = ""
    operacion: str = "venta"
    fecha_scraping: datetime = field(default_factory=datetime.now)
    
    # Campos opcionales adicionales
    descripcion: Optional[str] = None
    metros_cuadrados: Optional[float] = None
    habitaciones: Optional[int] = None
    banos: Optional[int] = None
    estacionamientos: Optional[int] = None
    imagenes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la propiedad a diccionario."""
        data = asdict(self)
        data['fecha_scraping'] = self.fecha_scraping.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Property':
        """Crea una Property desde un diccionario."""
        if isinstance(data.get('fecha_scraping'), str):
            data['fecha_scraping'] = datetime.fromisoformat(data['fecha_scraping'])
        return cls(**data)


class PropertyParser:
    """
    Clase para parsear y normalizar datos de propiedades desde diferentes fuentes.
    """
    
    # Patrones para extraer precios
    PRICE_PATTERNS = [
        r'\$\s*([\d,\.]+)',  # $50,000 o $50.000
        r'USD\s*([\d,\.]+)',  # USD 50000
        r'([\d,\.]+)\s*(?:USD|\$)',  # 50000 USD
        r'Bs\.?\s*([\d,\.]+)',  # Bs. 50000
        r'VES\s*([\d,\.]+)',  # VES 50000
        r'ARS\s*([\d,\.]+)',  # ARS 50000
        r'([\d,\.]+)\s*ARS',  # 50000 ARS
    ]
    
    # Mapeo de palabras clave a tipos de inmueble
    TYPE_KEYWORDS = {
        PropertyType.CASA: ['casa', 'house', 'vivienda', 'chalet', 'quinta'],
        PropertyType.APARTAMENTO: ['apartamento', 'apto', 'apartment', 'flat', 'piso'],
        PropertyType.TERRENO: ['terreno', 'lote', 'parcela', 'land', 'solar'],
        PropertyType.LOCAL: ['local', 'comercial', 'tienda', 'shop', 'store'],
        PropertyType.OFICINA: ['oficina', 'office', 'consultorio'],
        PropertyType.TOWNHOUSE: ['townhouse', 'town house', 'adosado'],
        PropertyType.PENTHOUSE: ['penthouse', 'ph', 'ático'],
        PropertyType.GALPON: ['galpon', 'galpón', 'bodega', 'warehouse'],
        PropertyType.FINCA: ['finca', 'hacienda', 'granja', 'farm'],
    }
    
    @classmethod
    def normalize_price(cls, price_str: str) -> tuple[Optional[float], str]:
        """
        Extrae y normaliza el precio de una cadena de texto.
        
        Args:
            price_str: Cadena con el precio (ej: "$50,000", "50.000 USD")
            
        Returns:
            Tupla (precio_numerico, moneda)
        """
        if not price_str:
            return None, Currency.USD.value
        
        price_str = price_str.strip().upper()
        
        # Determinar moneda
        currency = Currency.USD.value
        if 'BS' in price_str or 'VES' in price_str or 'BOLIVAR' in price_str:
            currency = Currency.VES.value
        elif 'ARS' in price_str or 'PESO' in price_str:
            currency = Currency.ARS.value
        elif 'EUR' in price_str or '€' in price_str:
            currency = Currency.EUR.value
        
        # Extraer número
        for pattern in cls.PRICE_PATTERNS:
            match = re.search(pattern, price_str, re.IGNORECASE)
            if match:
                price_num = match.group(1)
                # Normalizar separadores
                price_num = price_num.replace(',', '').replace('.', '')
                # Si tiene decimales, restaurarlos
                if len(price_num) > 2:
                    try:
                        return float(price_num), currency
                    except ValueError:
                        continue
        
        # Intentar extraer cualquier número
        numbers = re.findall(r'[\d,\.]+', price_str)
        for num in numbers:
            clean_num = num.replace(',', '').replace('.', '')
            if clean_num:
                try:
                    return float(clean_num), currency
                except ValueError:
                    continue
        
        return None, currency
    
    @classmethod
    def normalize_property_type(cls, text: str) -> str:
        """
        Detecta el tipo de inmueble basándose en palabras clave.
        
        Args:
            text: Texto que puede contener el tipo de inmueble
            
        Returns:
            Tipo de inmueble normalizado
        """
        if not text:
            return PropertyType.OTRO.value
        
        text_lower = text.lower()
        
        for prop_type, keywords in cls.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return prop_type.value
        
        return PropertyType.OTRO.value
    
    @classmethod
    def normalize_location(cls, location: str, default_label: str = "Maracaibo") -> str:
        """
        Normaliza la ubicación, asegurando que incluya el contexto geográfico.
        """
        if not location:
            return default_label or "Sin ubicación"

        location = location.strip()
        location = re.sub(r'\s+', ' ', location)

        if default_label and default_label.lower() not in location.lower():
            location = f"{location}, {default_label}"

        return location

    @classmethod
    def normalize_operation(cls, operation: str) -> str:
        """Normaliza tipo de operación a venta o alquiler."""
        op = (operation or "venta").lower().strip()
        if op in ("alquiler", "rent", "renta", "arriendo", "alquileres", "rental"):
            return "alquiler"
        return "venta"
    
    @classmethod
    def extract_number(cls, text: str) -> Optional[int]:
        """Extrae el primer número entero de una cadena."""
        if not text:
            return None
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else None
    
    @classmethod
    def extract_area(cls, text: str) -> Optional[float]:
        """Extrae el área en metros cuadrados de una cadena."""
        if not text:
            return None
        
        # Patrones comunes para área
        patterns = [
            r'([\d,\.]+)\s*m[²2]',
            r'([\d,\.]+)\s*mts?',
            r'([\d,\.]+)\s*metros',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                area_str = match.group(1).replace(',', '.')
                try:
                    return float(area_str)
                except ValueError:
                    continue
        
        return None
    
    @classmethod
    def clean_text(cls, text: str) -> str:
        """Limpia y normaliza texto."""
        if not text:
            return ""
        
        # Remover HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text)
        # Strip
        text = text.strip()
        
        return text
    
    @classmethod
    def generate_id(cls, source: str, *args) -> str:
        """
        Genera un ID único para una propiedad.
        
        Args:
            source: Nombre del portal
            *args: Componentes adicionales para el ID
            
        Returns:
            ID único de la propiedad
        """
        components = [source] + [str(arg) for arg in args if arg]
        return "_".join(components)
    
    @classmethod
    def validate_property(cls, prop: Property) -> tuple[bool, List[str]]:
        """
        Valida que una propiedad tenga los campos requeridos.
        
        Args:
            prop: Propiedad a validar
            
        Returns:
            Tupla (es_valida, lista_de_errores)
        """
        errors = []
        
        if not prop.id_externo:
            errors.append("id_externo es requerido")
        
        if not prop.source:
            errors.append("source es requerido")
        
        if not prop.titulo:
            errors.append("titulo es requerido")
        
        if prop.precio is None or prop.precio <= 0:
            errors.append("precio debe ser mayor a 0")
        
        if not prop.url:
            errors.append("url es requerida")
        
        return len(errors) == 0, errors



