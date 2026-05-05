--- glavobsnab_system/ai_engine.py (原始)


+++ glavobsnab_system/ai_engine.py (修改后)
"""
ai_engine.py - Модуль ИИ-поиска и анализа
Поиск характеристик товаров, проверка совместимости, анализ истории цен
"""

import re
import json
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ProductCharacteristics:
    """Характеристики товара"""
    weight_kg: float = None
    volume_m3: float = None
    dimensions: str = None  # Д x Ш x В
    material: str = None
    standard: str = None  # ГОСТ, DIN, ISO
    compatibility_notes: List[str] = None


# База знаний для типичных строительных материалов
MATERIALS_KNOWLEDGE_BASE = {
    # Бетон и смеси
    'бетон': {'density_kg_m3': 2400, 'volume_per_ton': 0.42},
    'раствор': {'density_kg_m3': 2000, 'volume_per_ton': 0.5},
    'цемент': {'density_kg_m3': 1500, 'bag_weight_kg': 50},
    'песок': {'density_kg_m3': 1600, 'volume_per_ton': 0.625},
    'щебень': {'density_kg_m3': 1400, 'volume_per_ton': 0.71},

    # Металлопрокат
    'арматура': {'density_kg_m3': 7850, 'standard_lengths': [6, 9, 11.7]},
    'труба': {'density_kg_m3': 7850},
    'балка': {'density_kg_m3': 7850},
    'швеллер': {'density_kg_m3': 7850},

    # Кирпич и блоки
    'кирпич': {'weight_per_piece': 2.5, 'pieces_per_m3': 513},
    'блок': {'weight_per_piece': 20, 'pieces_per_m3': 50},
    'газоблок': {'density_kg_m3': 600},
    'пеноблок': {'density_kg_m3': 500},

    # Изоляция
    'утеплитель': {'density_kg_m3': 35},
    'минвата': {'density_kg_m3': 40},
    'пенопласт': {'density_kg_m3': 25},
    'пеноплекс': {'density_kg_m3': 35},

    # Кабели
    'кабель': {'weight_per_100m': 50},  # Средний вес
    'провод': {'weight_per_100m': 10},

    # Лакокрасочные
    'краска': {'volume_per_kg': 0.0012},
    'грунтовка': {'volume_per_kg': 0.001},
}

# Правила совместимости
COMPATIBILITY_RULES = {
    'бетон': ['добав', 'пластификатор', 'арматур'],
    'кабель': ['автомат', 'щит', 'розетк', 'выключатель'],
    'труба': ['фитинг', 'кран', 'вентил', 'задвижк'],
    'кирпич': ['раствор', 'кладочн', 'смес'],
    'утеплитель': ['клей', 'дюбель', 'сетк', 'штукатур'],
}


def search_product_characteristics(item_name: str) -> ProductCharacteristics:
    """
    Поиск характеристик товара по названию
    Использует локальную базу знаний и эвристический анализ
    """
    characteristics = ProductCharacteristics(compatibility_notes=[])
    name_lower = item_name.lower()

    # Определяем категорию товара
    category = None
    for keyword, data in MATERIALS_KNOWLEDGE_BASE.items():
        if keyword in name_lower:
            category = keyword
            break

    if category:
        kb_data = MATERIALS_KNOWLEDGE_BASE[category]

        # Извлекаем плотность если есть
        if 'density_kg_m3' in kb_
            # Пытаемся найти объем или вес в названии
            volume_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(м3|куб|м³)', name_lower)
            weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(кг|kg|тонн?|т\b)', name_lower)

            if volume_match:
                volume = float(volume_match.group(1).replace(',', '.'))
                characteristics.volume_m3 = volume
                characteristics.weight_kg = volume * kb_data['density_kg_m3']
            elif weight_match:
                weight = float(weight_match.group(1).replace(',', '.'))
                if 'тонн' in name_lower or 'т ' in name_lower:
                    weight *= 1000
                characteristics.weight_kg = weight
                characteristics.volume_m3 = weight / kb_data['density_kg_m3']

        # Для штучных товаров
        if 'weight_per_piece' in kb_
            qty_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(шт|piece)', name_lower)
            if qty_match:
                qty = float(qty_match.group(1))
                characteristics.weight_kg = qty * kb_data['weight_per_piece']

    # Парсим размеры из названия
    size_match = re.search(
        r'(\d+(?:[.,]\d+)?)\s*[xх*×]\s*(\d+(?:[.,]\d+)?)\s*[xх*×]\s*(\d+(?:[.,]\d+)?)',
        name_lower
    )
    if size_match:
        l = float(size_match.group(1).replace(',', '.'))
        w = float(size_match.group(2).replace(',', '.'))
        h = float(size_match.group(3).replace(',', '.'))

        # Предполагаем что размеры в мм если не указано иное
        if 'мм' not in name_lower and 'см' not in name_lower and 'м ' not in name_lower:
            # Конвертируем мм в метры для объема
            if l > 10 or w > 10 or h > 10:
                l /= 1000
                w /= 1000
                h /= 1000

        characteristics.dimensions = f"{l}x{w}x{h} м"
        if not characteristics.volume_m3:
            characteristics.volume_m3 = l * w * h

    # Ищем стандарты (ГОСТ, DIN, ISO)
    gost_match = re.search(r'(гост\s*\d+\.?\d*|din\s*\d+|iso\s*\d+)', name_lower)
    if gost_match:
        characteristics.standard = gost_match.group(1).upper()

    return characteristics


def check_compatibility(items: List[Dict]) -> List[Dict]:
    """
    Проверка совместимости позиций между собой
    Возвращает список предупреждений о несовместимости
    """
    compatibility_warnings = []

    # Группируем товары по категориям
    categories = {}
    for item in items:
        name_lower = item.get('name', '').lower()

        for category, related_keywords in COMPATIBILITY_RULES.items():
            if category in name_lower:
                if category not in categories:
                    categories[category] = []
                categories[category].append(item)
                break

    # Проверяем наличие сопутствующих товаров
    for category, related_keywords in COMPATIBILITY_RULES.items():
        if category in categories:
            has_related = False

            for keyword in related_keywords:
                for item in items:
                    if keyword in item.get('name', '').lower():
                        has_related = True
                        break
                if has_related:
                    break

            if not has_related:
                compatibility_warnings.append({
                    'type': 'missing_related',
                    'category': category,
                    'message': f"Для '{category}' не найдены сопутствующие товары ({', '.join(related_keywords[:3])})"
                })

    # Проверяем потенциальные конфликты
    conflicts = check_potential_conflicts(items)
    compatibility_warnings.extend(conflicts)

    return compatibility_warnings


def check_potential_conflicts(items: List[Dict]) -> List[Dict]:
    """Проверка потенциальных конфликтов между товарами"""
    warnings = []
    names = [item.get('name', '').lower() for item in items]

    # Примеры проверок конфликтов
    conflict_pairs = [
        ('бетон м', 'дерево'),  # Бетон и дерево требуют особой обработки
        ('кислот', 'щелоч'),  # Кислоты и щелочи
        ('алюмин', 'медн'),  # Алюминий и медь (электрохимическая коррозия)
    ]

    for word1, word2 in conflict_pairs:
        has_word1 = any(word1 in name for name in names)
        has_word2 = any(word2 in name for name in names)

        if has_word1 and has_word2:
            warnings.append({
                'type': 'potential_conflict',
                'items': [word1, word2],
                'message': f"Возможная несовместимость: {word1} и {word2}. Требуется консультация специалиста."
            })

    return warnings


def estimate_volume_and_weight(items: List[Dict]) -> Tuple[float, float]:
    """
    Оценка общего объема (м³) и веса (кг) груза
    """
    total_volume = 0.0
    total_weight = 0.0

    for item in items:
        characteristics = search_product_characteristics(item.get('name', ''))

        qty = item.get('quantity', 1)

        # Если характеристики уже рассчитаны
        if item.get('volume_m3'):
            vol = item['volume_m3']
        elif characteristics.volume_m3:
            vol = characteristics.volume_m3
        else:
            # Эвристическая оценка по категории
            name_lower = item.get('name', '').lower()
            vol = estimate_volume_by_category(name_lower, qty, item.get('unit'))

        if item.get('weight_kg'):
            wt = item['weight_kg']
        elif characteristics.weight_kg:
            wt = characteristics.weight_kg
        else:
            # Эвристическая оценка веса
            name_lower = item.get('name', '').lower()
            wt = estimate_weight_by_category(name_lower, qty, item.get('unit'))

        total_volume += vol
        total_weight += wt

    return total_volume, total_weight


def estimate_volume_by_category(name: str, quantity: float, unit: str) -> float:
    """Оценка объема по категории товара"""
    name_lower = name.lower()

    # Стандартные объемы для различных категорий
    if 'бетон' in name_lower or 'раствор' in name_lower:
        return quantity * 1.0 if unit in ['м3', 'куб'] else quantity * 0.5
    elif 'кирпич' in name_lower:
        return quantity * 0.00195  # Объем одного кирпича
    elif 'блок' in name_lower:
        return quantity * 0.02  # Объем одного блока
    elif 'мешок' in name_lower or 'упак' in name_lower:
        return quantity * 0.05  # Объем мешка
    elif 'шт' in (unit or ''):
        return quantity * 0.01  # Средний объем штучного товара
    elif 'кг' in (unit or ''):
        return quantity * 0.001  # Примерно 1 кг = 0.001 м³
    else:
        return quantity * 0.1  # Дефолтная оценка


def estimate_weight_by_category(name: str, quantity: float, unit: str) -> float:
    """Оценка веса по категории товара"""
    name_lower = name.lower()

    if 'бетон' in name_lower or 'раствор' in name_lower:
        return quantity * 2400 if unit in ['м3', 'куб'] else quantity * 25
    elif 'металл' in name_lower or 'арматур' in name_lower:
        return quantity * 7850 if unit in ['м3', 'куб'] else quantity * 2
    elif 'кирпич' in name_lower:
        return quantity * 2.5
    elif 'блок' in name_lower:
        return quantity * 20
    elif 'цемент' in name_lower or 'смес' in name_lower:
        return quantity * 25 if 'мешок' in name_lower or 'упак' in name_lower else quantity
    elif 'шт' in (unit or ''):
        return quantity * 1  # Средний вес штучного товара
    elif 'м3' in (unit or '') or 'куб' in name_lower:
        return quantity * 500  # Средняя плотность
    else:
        return quantity * 1  # Дефолтная оценка


def select_transport_type(total_volume: float, total_weight: float) -> Dict:
    """
    Подбор типа транспорта по объему и весу
    Тарифы для Москвы и МО
    """
    transport_options = [
        {
            'type': 'Газель',
            'max_weight_kg': 1500,
            'max_volume_m3': 9,
            'base_price_rub': 2500,
            'price_per_km': 50
        },
        {
            'type': 'Газель удлиненная',
            'max_weight_kg': 1500,
            'max_volume_m3': 16,
            'base_price_rub': 3500,
            'price_per_km': 60
        },
        {
            'type': '5-тонник',
            'max_weight_kg': 5000,
            'max_volume_m3': 36,
            'base_price_rub': 7000,
            'price_per_km': 75
        },
        {
            'type': '10-тонник',
            'max_weight_kg': 10000,
            'max_volume_m3': 56,
            'base_price_rub': 12000,
            'price_per_km': 85
        },
        {
            'type': '20-тонник',
            'max_weight_kg': 20000,
            'max_volume_m3': 86,
            'base_price_rub': 18000,
            'price_per_km': 95
        },
        {
            'type': 'Манипулятор 10т',
            'max_weight_kg': 10000,
            'max_volume_m3': 40,
            'base_price_rub': 15000,
            'price_per_km': 100
        }
    ]

    # Находим подходящий транспорт
    suitable = []
    for option in transport_options:
        if total_weight <= option['max_weight_kg'] and total_volume <= option['max_volume_m3']:
            suitable.append(option)

    if not suitable:
        # Если груз слишком большой, рекомендуем самый крупный транспорт
        return {
            'recommended': transport_options[-1],
            'note': 'Груз превышает стандартные лимиты. Требуется спецтранспорт.',
            'multiple_trips': total_weight / transport_options[-1]['max_weight_kg']
        }

    # Выбираем минимально подходящий по цене
    recommended = min(suitable, key=lambda x: x['base_price_rub'])

    return {
        'recommended': recommended,
        'note': None,
        'multiple_trips': 1
    }


def calculate_delivery_cost(distance_km: float, transport_info: Dict,
                           free_delivery: bool = False,
                           delivery_included: float = None) -> float:
    """
    Расчет стоимости доставки
    """
    if free_delivery:
        return 0.0

    if delivery_included is not None and delivery_included > 0:
        return delivery_included

    transport = transport_info.get('recommended', {})
    base_price = transport.get('base_price_rub', 5000)
    price_per_km = transport.get('price_per_km', 50)

    # Минимальная доставка
    if distance_km < 5:
        distance_km = 5

    total_cost = base_price + (distance_km * price_per_km)

    # Учитываем количество рейсов
    multiple_trips = transport_info.get('multiple_trips', 1)
    if multiple_trips > 1:
        total_cost *= multiple_trips

    return total_cost


def get_coordinates_by_address(address: str) -> Tuple[float, float]:
    """
    Получение координат по адресу (упрощенная версия)
    В production использовать API Яндекс.Карт или Google Maps
    """
    # Упрощенная геокодировка для Москвы
    moscow_coords = (55.7558, 37.6173)

    if not address:
        return moscow_coords

    address_lower = address.lower()

    # Примеры координат для районов Москвы
    districts = {
        'центр': (55.7558, 37.6173),
        'север': (55.8328, 37.5908),
        'юг': (55.6413, 37.6173),
        'восток': (55.7558, 37.7558),
        'запад': (55.7558, 37.4790),
        'зеленоград': (55.9833, 37.1833),
        'новомосковск': (55.5583, 37.4167),
        'троицк': (55.4833, 37.3167),
    }

    for district, coords in districts.items():
        if district in address_lower:
            return coords

    return moscow_coords


def calculate_distance(coords1: Tuple[float, float], coords2: Tuple[float, float]) -> float:
    """
    Расчет расстояния между двумя точками (формула гаверсинуса)
    Возвращает расстояние в км
    """
    import math

    R = 6371  # Радиус Земли в км

    lat1, lon1 = map(math.radians, coords1)
    lat2, lon2 = map(math.radians, coords2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def analyze_supplier_locations(supplier_addresses: List[str], delivery_address: str) -> Dict:
    """
    Анализ точек загрузки поставщиков относительно адреса доставки
    Рекомендации по оптимизации маршрута
    """
    delivery_coords = get_coordinates_by_address(delivery_address)

    supplier_points = []
    for addr in supplier_addresses:
        coords = get_coordinates_by_address(addr)
        distance = calculate_distance(coords, delivery_coords)
        supplier_points.append({
            'address': addr,
            'coords': coords,
            'distance_km': distance
        })

    # Сортируем по расстоянию
    supplier_points.sort(key=lambda x: x['distance_km'])

    # Анализируем是否需要 разделение на рейсы
    total_distance = sum(p['distance_km'] for p in supplier_points)

    recommendation = {
        'points': supplier_points,
        'total_suppliers': len(supplier_points),
        'nearest_supplier': supplier_points[0] if supplier_points else None,
        'farthest_supplier': supplier_points[-1] if supplier_points else None,
        'multi_point_route': len(supplier_points) > 2,
        'recommendation': None
    }

    if len(supplier_points) > 2:
        recommendation['recommendation'] = (
            "Рекомендуется разделить доставку на 2 рейса или выбрать поставщиков с ближайшими складами. "
            "Мульти-точечный маршрут может быть дороже."
        )

    return recommendation