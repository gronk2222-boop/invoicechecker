--- glavobsnab_system/app.py (原始)


+++ glavobsnab_system/app.py (修改后)
"""
app.py - Главное приложение Streamlit
Система интеллектуального сравнения счетов для "Главоблснаб"
"""

import streamlit as st
import pandas as pd
import os
import tempfile
from datetime import datetime
from typing import List, Dict
import folium
from streamlit_folium import st_folium

# Импорт локальных модулей
from database import (
    init_database, get_or_create_client, get_or_create_supplier,
    create_document, create_item, get_items_by_document,
    get_items_for_comparison, add_price_history, get_price_statistics,
    log_processing, get_all_suppliers
)
from parsers import parse_file, extract_items_as_dict, ParsedDocument
from ai_engine import (
    search_product_characteristics, check_compatibility,
    estimate_volume_and_weight, select_transport_type,
    calculate_delivery_cost, get_coordinates_by_address,
    calculate_distance, analyze_supplier_locations
)


# === Конфигурация страницы ===
st.set_page_config(
    page_title="Главоблснаб - Сравнение счетов",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === CSS стили ===
st.markdown("""
<style>
    .main {
        background-color: #0b132b;
    }
    .stButton>button {
        background-color: #1c2541;
        color: #87ceeb;
        border: 1px solid #87ceeb;
    }
    .stButton>button:hover {
        background-color: #87ceeb;
        color: #0b132b;
    }
    .metric-card {
        background-color: #1c2541;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #87ceeb;
        margin: 10px 0;
    }
    .status-exact { color: #4CAF50; }
    .status-warning { color: #FFC107; }
    .status-error { color: #F44336; }
    .status-info { color: #2196F3; }

    h1, h2, h3 {
        color: #87ceeb !important;
    }
    label, p, div {
        color: #e0e0e0 !important;
    }
</style>
""", unsafe_allow_html=True)

# === Инициализация БД ===
init_database()

# === Session State ===
if 'request_data' not in st.session_state:
    st.session_state.request_data = None
if 'invoices_data' not in st.session_state:
    st.session_state.invoices_data = []
if 'comparison_results' not in st.session_state:
    st.session_state.comparison_results = None
if 'current_step' not in st.session_state:
    st.session_state.current_step = 1


# === Вспомогательные функции ===

def save_uploaded_file(uploaded_file) -> str:
    """Сохранение загруженного файла во временную директорию"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


def process_request(file_path: str, client_name: str, delivery_address: str) -> Dict:
    """Обработка заявки клиента"""
    parsed_doc = parse_file(file_path)

    if not parsed_doc or not parsed_doc.items:
        return {'error': 'Не удалось распарсить заявку'}

    # Создаем клиента
    client_id = get_or_create_client(client_name)

    # Создаем документ
    doc_id = create_document(
        doc_type='request',
        client_id=client_id,
        filename=os.path.basename(file_path),
        delivery_address=delivery_address
    )

    # Сохраняем позиции
    items = extract_items_as_dict(parsed_doc)
    for item_data in items:
        item_id = create_item(document_id=doc_id, **item_data)
        # Добавляем в историю цен
        if item_data.get('price_per_unit'):
            add_price_history(
                item_name=item_data['name'],
                supplier_id=None,
                price_per_unit=item_data['price_per_unit'],
                quantity=item_data['quantity'],
                document_id=doc_id
            )

    log_processing(doc_id, 'success', f'Заявка обработана: {len(items)} позиций')

    return {
        'doc_id': doc_id,
        'client_name': client_name,
        'delivery_address': delivery_address,
        'items': items,
        'total_amount': sum(item.get('total_price', 0) or item.get('quantity', 0) * item.get('price_per_unit', 0) for item in items)
    }


def process_invoice(file_path: str, delivery_address: str) -> Dict:
    """Обработка счета поставщика"""
    parsed_doc = parse_file(file_path)

    if not parsed_doc or not parsed_doc.items:
        return {'error': 'Не удалось распарсить счет'}

    # Определяем поставщика
    supplier_name = parsed_doc.supplier_name or os.path.basename(file_path)
    supplier_id = get_or_create_supplier(
        name=supplier_name,
        address=parsed_doc.supplier_address,
        free_delivery=parsed_doc.free_delivery
    )

    # Создаем документ
    doc_id = create_document(
        doc_type='invoice',
        supplier_id=supplier_id,
        filename=os.path.basename(file_path),
        delivery_address=delivery_address,
        total_amount=parsed_doc.total_amount
    )

    # Сохраняем позиции
    items = extract_items_as_dict(parsed_doc)
    for item_data in items:
        item_id = create_item(document_id=doc_id, **item_data)
        # Добавляем в историю цен
        if item_data.get('price_per_unit'):
            add_price_history(
                item_name=item_data['name'],
                supplier_id=supplier_id,
                price_per_unit=item_data['price_per_unit'],
                quantity=item_data['quantity'],
                document_id=doc_id
            )

    log_processing(doc_id, 'success', f'Счет обработан: {len(items)} позиций')

    return {
        'doc_id': doc_id,
        'supplier_name': supplier_name,
        'supplier_address': parsed_doc.supplier_address,
        'items': items,
        'total_amount': parsed_doc.total_amount,
        'delivery_cost': parsed_doc.delivery_cost,
        'free_delivery': parsed_doc.free_delivery
    }


def compare_request_with_invoices(request_items: List[Dict], invoices: List[Dict]) -> List[Dict]:
    """Сравнение заявки со счетами"""
    results = []

    for idx, invoice in enumerate(invoices):
        comparison = get_items_for_comparison(request_items, invoice['items'])

        # Рассчитываем логистику
        total_volume, total_weight = estimate_volume_and_weight(invoice['items'])
        transport_info = select_transport_type(total_volume, total_weight)

        # Получаем координаты для расчета доставки
        supplier_coords = get_coordinates_by_address(invoice.get('supplier_address', ''))
        delivery_coords = get_coordinates_by_address(st.session_state.request_data.get('delivery_address', ''))
        distance = calculate_distance(supplier_coords, delivery_coords)

        # Расчет доставки
        delivery_cost = calculate_delivery_cost(
            distance_km=distance,
            transport_info=transport_info,
            free_delivery=invoice.get('free_delivery', False),
            delivery_included=invoice.get('delivery_cost')
        )

        # Проверка совместимости
        compatibility_warnings = check_compatibility(invoice['items'])

        # Анализ истории цен
        price_analysis = []
        for item in invoice['items']:
            stats = get_price_statistics(item['name'])
            if stats.get('avg_price') and item.get('price_per_unit'):
                diff_percent = ((item['price_per_unit'] - stats['avg_price']) / stats['avg_price']) * 100
                price_analysis.append({
                    'item_name': item['name'],
                    'current_price': item['price_per_unit'],
                    'avg_price': stats['avg_price'],
                    'diff_percent': diff_percent,
                    'trend': stats['trend']
                })

        # Итоговая сумма с доставкой
        invoice_total = invoice.get('total_amount', 0) or sum(
            item.get('total_price', 0) or item.get('quantity', 0) * item.get('price_per_unit', 0)
            for item in invoice['items']
        )
        grand_total = invoice_total + delivery_cost

        results.append({
            'invoice_idx': idx,
            'supplier_name': invoice['supplier_name'],
            'items_comparison': comparison,
            'invoice_total': invoice_total,
            'delivery_cost': delivery_cost,
            'grand_total': grand_total,
            'total_volume_m3': total_volume,
            'total_weight_kg': total_weight,
            'transport_type': transport_info['recommended']['type'],
            'distance_km': distance,
            'compatibility_warnings': compatibility_warnings,
            'price_analysis': price_analysis,
            'free_delivery': invoice.get('free_delivery', False)
        })

    return results


def render_status_badge(status: str) -> str:
    """Рендеринг бейджа статуса"""
    badges = {
        'exact_match': '<span class="status-exact">✅ Точное совпадение</span>',
        'quantity_diff': '<span class="status-warning">⚠️ Разница в количестве</span>',
        'price_increase': '<span class="status-error">📈 Цена выше</span>',
        'price_decrease': '<span class="status-info">📉 Цена ниже</span>',
        'missing': '<span class="status-error">❌ Отсутствует</span>',
        'extra': '<span class="status-info">🆕 Лишняя позиция</span>'
    }
    return badges.get(status, status)


# === Основной интерфейс ===

st.title("🏗️ Главоблснаб - Система сравнения счетов")
st.markdown("---")

# Прогресс-бар шагов
progress_col1, progress_col2, progress_col3 = st.columns(3)
with progress_col1:
    if st.session_state.current_step >= 1:
        st.success("**Шаг 1:** Заявка")
    else:
        st.info("Шаг 1: Заявка")
with progress_col2:
    if st.session_state.current_step >= 2:
        st.success("**Шаг 2:** Счета")
    else:
        st.info("Шаг 2: Счета")
with progress_col3:
    if st.session_state.current_step >= 3:
        st.success("**Шаг 3:** Результат")
    else:
        st.info("Шаг 3: Результат")

st.markdown("---")

# === ШАГ 1: Загрузка заявки ===
st.header("📋 Шаг 1: Заявка клиента")

col1, col2 = st.columns([2, 1])

with col1:
    request_file = st.file_uploader(
        "Загрузите файл заявки (PDF, XLSX, DOCX, CSV, TXT)",
        type=['pdf', 'xlsx', 'xls', 'docx', 'doc', 'csv', 'txt'],
        key='request_uploader'
    )

with col2:
    client_name = st.text_input("Имя клиента *", placeholder="ООО 'СтройМонтаж'")
    delivery_address = st.text_area("Адрес доставки *", placeholder="г. Москва, ул. Примерная, д. 10")

if st.button("Обработать заявку", disabled=not (request_file and client_name and delivery_address)):
    with st.spinner("Обработка заявки..."):
        try:
            file_path = save_uploaded_file(request_file)
            result = process_request(file_path, client_name, delivery_address)

            if 'error' in result:
                st.error(f"Ошибка: {result['error']}")
            else:
                st.session_state.request_data = result
                st.session_state.current_step = 2
                st.success(f"✅ Заявка обработана! Найдено позиций: {len(result['items'])}")
                os.unlink(file_path)
                st.rerun()
        except Exception as e:
            st.error(f"Ошибка обработки: {str(e)}")

# Отображение данных заявки если обработана
if st.session_state.request_
    st.subheader("📦 Позиции заявки")
    req_df = pd.DataFrame(st.session_state.request_data['items'])
    if not req_df.empty:
        st.dataframe(
            req_df[['name', 'quantity', 'unit', 'price_per_unit', 'total_price']],
            use_container_width=True
        )

    st.metric("Общая сумма заявки", f"{st.session_state.request_data['total_amount']:,.2f} ₽")

# === ШАГ 2: Загрузка счетов ===
if st.session_state.request_
    st.markdown("---")
    st.header("📄 Шаг 2: Счета от поставщиков")

    invoice_files = st.file_uploader(
        "Загрузите один или несколько счетов",
        type=['pdf', 'xlsx', 'xls', 'docx', 'doc', 'csv', 'txt'],
        accept_multiple_files=True,
        key='invoice_uploader'
    )

    if st.button("Обработать счета и сравнить", disabled=not invoice_files):
        with st.spinner("Обработка счетов..."):
            try:
                invoices = []
                for inv_file in invoice_files:
                    file_path = save_uploaded_file(inv_file)
                    result = process_invoice(file_path, st.session_state.request_data['delivery_address'])

                    if 'error' not in result:
                        invoices.append(result)
                        st.success(f"✅ Счет от {result['supplier_name']} обработан")
                    else:
                        st.warning(f"⚠️ Счет не обработан: {result.get('error')}")

                    os.unlink(file_path)

                if invoices:
                    st.session_state.invoices_data = invoices

                    # Запуск сравнения
                    with st.spinner("Сравнение и анализ..."):
                        comparison = compare_request_with_invoices(
                            st.session_state.request_data['items'],
                            invoices
                        )
                        st.session_state.comparison_results = comparison
                        st.session_state.current_step = 3
                        st.rerun()

            except Exception as e:
                st.error(f"Ошибка: {str(e)}")

# === ШАГ 3: Результаты ===
if st.session_state.comparison_results:
    st.markdown("---")
    st.header("📊 Шаг 3: Результаты сравнения")

    results = st.session_state.comparison_results

    # Карточки с итогами по каждому счету
    st.subheader("💰 Сводка по поставщикам")

    cols = st.columns(len(results))

    # Находим лучший вариант
    best_idx = min(range(len(results)), key=lambda i: results[i]['grand_total'])

    for idx, col in enumerate(cols):
        with col:
            result = results[idx]
            is_best = idx == best_idx

            card_color = "#2d4a22" if is_best else "#1c2541"

            st.markdown(f"""
            <div class="metric-card" style="background-color: {card_color}; border-left-color: {'#4CAF50' if is_best else '#87ceeb'};">
                <h4>{result['supplier_name'][:20]}{'...' if len(result['supplier_name']) > 20 else ''}</h4>
                <p>Товары: {result['invoice_total']:,.0f} ₽</p>
                <p>Доставка: {result['delivery_cost']:,.0f} ₽</p>
                <h3 style="color: {'#4CAF50' if is_best else '#87ceeb'};">Итого: {result['grand_total']:,.0f} ₽</h3>
                {'🏆 Лучший выбор!' if is_best else ''}
            </div>
            """, unsafe_allow_html=True)

    # Детальная таблица сравнения
    st.subheader("📋 Детальное сравнение позиций")

    # Выбор поставщика для детального просмотра
    supplier_options = [r['supplier_name'] for r in results]
    selected_supplier = st.selectbox("Выберите поставщика для просмотра", supplier_options)

    selected_result = next(r for r in results if r['supplier_name'] == selected_supplier)

    # Таблица сравнения
    comparison_data = []
    for item_comp in selected_result['items_comparison']:
        comparison_data.append({
            'Позиция': item_comp['item_name'],
            'Статус': render_status_badge(item_comp['status']),
            'Заявка (кол-во)': item_comp['request_qty'],
            'Счет (кол-во)': item_comp['invoice_qty'],
            'Δ кол-во': f"{item_comp['delta_qty']:+.2f}" if item_comp['delta_qty'] else '-',
            'Заявка (цена)': f"{item_comp['request_price']:,.2f}" if item_comp['request_price'] else '-',
            'Счет (цена)': f"{item_comp['invoice_price']:,.2f}" if item_comp['invoice_price'] else '-',
            'Δ цены': f"{item_comp['delta_price']:+.2f}" if item_comp['delta_price'] else '-'
        })

    comp_df = pd.DataFrame(comparison_data)
    st.markdown(comp_df.to_html(escape=False), unsafe_allow_html=True)

    # Логистика и доставка
    st.subheader("🚚 Логистика")

    log_col1, log_col2, log_col3 = st.columns(3)

    with log_col1:
        st.metric("Объем груза", f"{selected_result['total_volume_m3']:.2f} м³")
    with log_col2:
        st.metric("Вес груза", f"{selected_result['total_weight_kg']:.0f} кг")
    with log_col3:
        st.metric("Тип транспорта", selected_result['transport_type'])

    st.info(f"📍 Расстояние до поставщика: {selected_result['distance_km']:.1f} км")

    # Предупреждения о совместимости
    if selected_result['compatibility_warnings']:
        st.subheader("⚠️ Проверка совместимости")
        for warning in selected_result['compatibility_warnings']:
            if warning['type'] == 'missing_related':
                st.warning(warning['message'])
            elif warning['type'] == 'potential_conflict':
                st.error(warning['message'])

    # Анализ цен
    if selected_result['price_analysis']:
        st.subheader("📈 Анализ истории цен")

        price_changes = [p for p in selected_result['price_analysis'] if abs(p['diff_percent']) > 5]

        if price_changes:
            for pc in price_changes[:5]:  # Показываем топ-5 изменений
                color = "red" if pc['diff_percent'] > 0 else "green"
                st.markdown(
                    f"- **{pc['item_name'][:40]}**: {pc['current_price']:,.2f} ₽ "
                    f"<span style='color: {color}'>({pc['diff_percent']:+.1f}%)</span>",
                    unsafe_allow_html=True
                )

    # Карта
    st.subheader("🗺️ Карта поставщиков")

    delivery_addr = st.session_state.request_data['delivery_address']
    delivery_coords = get_coordinates_by_address(delivery_addr)

    m = folium.Map(location=delivery_coords, zoom_start=10)

    # Маркер доставки
    folium.Marker(
        delivery_coords,
        popup=f"📍 Доставка: {delivery_addr}",
        icon=folium.Icon(color='red', icon='home')
    ).add_to(m)

    # Маркеры поставщиков
    for result in results:
        supplier_coords = get_coordinates_by_address(
            next((inv['supplier_address'] for inv in st.session_state.invoices_data
                  if inv['supplier_name'] == result['supplier_name']), '')
        )

        color = 'green' if results.index(result) == best_idx else 'blue'

        folium.Marker(
            supplier_coords,
            popup=f"🏭 {result['supplier_name']}<br>Итого: {result['grand_total']:,.0f} ₽",
            icon=folium.Icon(color=color, icon='building')
        ).add_to(m)

    st_folium(m, width=800, height=400)

    # Экспорт результатов
    st.subheader("💾 Экспорт")

    export_col1, export_col2 = st.columns(2)

    with export_col1:
        # CSV экспорт
        csv_data = pd.DataFrame([{
            'Поставщик': r['supplier_name'],
            'Сумма товаров': r['invoice_total'],
            'Доставка': r['delivery_cost'],
            'Итого': r['grand_total'],
            'Объем (м³)': r['total_volume_m3'],
            'Вес (кг)': r['total_weight_kg'],
            'Транспорт': r['transport_type']
        } for r in results])

        st.download_button(
            label="📥 Скачать сводку (CSV)",
            data=csv_data.to_csv(index=False, sep=';').encode('utf-8-sig'),
            file_name=f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

    with export_col2:
        # Excel экспорт деталей
        detail_data = []
        for result in results:
            for item_comp in result['items_comparison']:
                detail_data.append({
                    'Поставщик': result['supplier_name'],
                    'Позиция': item_comp['item_name'],
                    'Статус': item_comp['status'],
                    'Заявка_кол': item_comp['request_qty'],
                    'Счет_кол': item_comp['invoice_qty'],
                    'Заявка_цена': item_comp['request_price'],
                    'Счет_цена': item_comp['invoice_price']
                })

        if detail_
            excel_df = pd.DataFrame(detail_data)

            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False, sheet_name='Сравнение')

            st.download_button(
                label="📥 Скачать детали (Excel)",
                data=output.getvalue(),
                file_name=f"comparison_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# === Сайдбар ===
with st.sidebar:
    st.image("https://via.placeholder.com/300x100/0b132b/87ceeb?text=Главоблснаб", use_column_width=True)
    st.markdown("### 🛠️ Инструменты")

    if st.button("🔄 Начать заново"):
        st.session_state.request_data = None
        st.session_state.invoices_data = []
        st.session_state.comparison_results = None
        st.session_state.current_step = 1
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ О системе")
    st.markdown("""
    Система автоматического сравнения
    счетов от поставщиков с заявкой клиента.

    **Возможности:**
    - Парсинг PDF, Excel, Word
    - Сравнение позиций
    - Расчет логистики
    - Проверка совместимости
    - История цен
    """)

    # Статистика из БД
    suppliers = get_all_suppliers()
    st.markdown(f"**Поставщиков в базе:** {len(suppliers)}")