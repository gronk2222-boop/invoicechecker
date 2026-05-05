import random

def search_product_info(item_name):
    """
    Имитация поиска информации о товаре.
    В реальной системе здесь был бы запрос к LLM или API.
    Возвращает вес (кг) и объем (м3) для единицы товара.
    """
    # Словарь заглушек для демонстрации
    defaults = {'weight': 1.0, 'volume': 0.001, 'density': 1000}
    
    name_lower = item_name.lower()
    
    if 'бетон' in name_lower:
        return {'weight': 2400, 'volume': 0.001, 'density': 2400} # 1 литр ~ 2.4 кг
    if 'кирпич' in name_lower:
        return {'weight': 3.5, 'volume': 0.002, 'density': 1750}
    if 'цемент' in name_lower:
        return {'weight': 50, 'volume': 0.04, 'density': 1250} # Мешок
    if 'труба' in name_lower:
        return {'weight': 15, 'volume': 0.01, 'density': 1500}
    if 'краска' in name_lower:
        return {'weight': 1.2, 'volume': 0.001, 'density': 1200}
    if 'арматура' in name_lower:
        return {'weight': 20, 'volume': 0.002, 'density': 7800}
    
    # Случайные значения для неизвестных товаров, чтобы логистика считалась
    return {
        'weight': round(random.uniform(0.5, 10), 2),
        'volume': round(random.uniform(0.001, 0.05), 3),
        'density': round(random.uniform(500, 2000), 0)
    }

def analyze_compatibility(items_df):
    """
    Проверка совместимости товаров.
    Возвращает список предупреждений.
    """
    warnings = []
    if items_df is None or items_df.empty:
        return warnings
        
    names = [str(n).lower() for n in items_df.get('name', [])]
    
    # Примеры правил совместимости
    has_concrete = any('бетон' in n for n in names)
    has_water_proof = any('гидроизо' in n for n in names) or any('добавк' in n for n in names)
    
    has_cable = any('кабель' in n for n in names)
    has_high_voltage = any('10 кв' in n or '0.4 кв' in n for n in names)
    
    if has_concrete and not has_water_proof:
        # Это скорее рекомендация, чем ошибка, но для примера выведем
        pass # Можно добавить warning: "Рекомендуется добавить пластификаторы"
    
    # Проверка на явные конфликты (выдуманная логика для примера)
    if any('растворитель' in n for n in names) and any('краска' in n for n in names):
        warnings.append("⚠️ Внимание: Растворители и краски требуют раздельного хранения при транспортировке!")
        
    return warnings

def calculate_logistics(items_df, address):
    """
    Расчет логистики.
    Возвращает словарь с данными о транспорте и стоимости.
    """
    if items_df is None or items_df.empty:
        return {}
    
    total_weight = 0
    total_volume = 0
    
    for _, row in items_df.iterrows():
        qty = float(row.get('quantity', 0))
        info = search_product_info(str(row.get('name', '')))
        
        total_weight += qty * info['weight']
        total_volume += qty * info['volume']
    
    # Подбор транспорта
    vehicle = "Газель (1.5т)"
    rate = 0
    
    if total_weight > 1.5 or total_volume > 9:
        vehicle = "5-тонник"
        rate = 1.2
    if total_weight > 5 or total_volume > 30:
        vehicle = "10-тонник"
        rate = 1.5
    if total_weight > 10 or total_volume > 60:
        vehicle = "20-тонник (Фура)"
        rate = 1.8
    if total_weight > 20:
        vehicle = "Спецтранспорт / Конвой"
        rate = 2.5
        
    # Базовая стоимость по Москве (условно 5000 руб старт + км)
    base_cost = 5000
    estimated_cost = base_cost + (total_weight * rate * 10) # Очень грубая формула
    
    return {
        "total_weight_kg": round(total_weight, 2),
        "total_volume_m3": round(total_volume, 2),
        "vehicle": vehicle,
        "estimated_cost": round(estimated_cost, 2),
        "items_count": len(items_df)
    }
