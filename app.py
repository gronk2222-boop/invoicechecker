import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime
import folium
from streamlit_folium import folium_static
import requests
from bs4 import BeautifulSoup
import re

# Импорт локальных модулей (убедитесь, что они лежат рядом с app.py)
try:
    from database import init_db, save_invoice, get_price_history, get_supplier_info
    from parsers import parse_file
    from ai_engine import analyze_compatibility, search_product_info, calculate_logistics
except ImportError:
    # Заглушки для случаев, если модули еще не загружены или имена изменены
    st.error("Ошибка импорта модулей. Убедитесь, что database.py, parsers.py и ai_engine.py находятся в той же папке.")
    def init_db(): pass
    def save_invoice(*args): pass
    def get_price_history(*args): return []
    def get_supplier_info(*args): return {}
    def parse_file(*args): return pd.DataFrame()
    def analyze_compatibility(*args): return []
    def search_product_info(*args): return {}
    def calculate_logistics(*args): return {}

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(
    page_title="Главоблснаб: Умное сравнение счетов",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- СТИЛИ (CSS) ---
st.markdown("""
<style>
    /* Основной фон */
    .stApp {
        background-color: #0b132b;
        color: #ffffff;
    }
    
    /* Заголовки */
    h1, h2, h3 {
        color: #87ceeb !important;
        font-family: 'Segoe UI', sans-serif;
    }
    
    /* Карточки и контейнеры */
    .css-1r6slb0, .css-1d391kg {
        background-color: #1c2541;
        border-radius: 10px;
        padding: 20px;
    }
    
    /* Кнопки */
    .stButton>button {
        background-color: #3a506b;
        color: white;
        border: 1px solid #87ceeb;
        border-radius: 5px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #87ceeb;
        color: #0b132b;
    }
    
    /* Таблицы */
    table {
        color: white;
    }
    th {
        background-color: #3a506b !important;
        color: #87ceeb !important;
    }
    
    /* Статусы */
    .status-ok { color: #4caf50; font-weight: bold; }
    .status-warn { color: #ff9800; font-weight: bold; }
    .status-err { color: #f44336; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ БД ---
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect('invoices.db', check_same_thread=False)
    init_db(conn)
    return conn

conn = get_db_connection()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def reset_session():
    keys = ['request_data', 'invoices_data', 'client_name', 'delivery_address', 'analysis_done']
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]

def format_currency(val):
    try:
        return f"{val:,.2f} ₽"
    except:
        return str(val)

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---

st.title("🏗️ Система интеллектуального сравнения счетов")
st.markdown("### Для ООО «Главоблснаб»")

# Боковая панель
with st.sidebar:
    st.header("Меню")
    option = st.radio("Навигация", ["Загрузка данных", "Анализ и Результаты", "История закупок"])
    
    if st.button("🗑️ Сбросить всё"):
        reset_session()
        st.rerun()
    
    st.info("💡 **Совет:** Загружайте файлы в форматах PDF, XLSX, DOCX или CSV.")

# --- ШАГ 1: ЗАГРУЗКА ДАННЫХ ---
if option == "Загрузка данных":
    st.header("1. Параметры заявки")
    
    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input("Имя клиента", value=st.session_state.get('client_name', ''), placeholder="Например: ЖК 'Северный'")
    with col2:
        delivery_address = st.text_input("Адрес доставки", value=st.session_state.get('delivery_address', ''), placeholder="Москва, ул. Строителей, д. 5")
    
    if client_name:
        st.session_state['client_name'] = client_name
    if delivery_address:
        st.session_state['delivery_address'] = delivery_address

    st.divider()
    
    st.header("2. Загрузка Заявки (Эталон)")
    req_file = st.file_uploader("Загрузить файл заявки", type=['pdf', 'xlsx', 'xls', 'docx', 'csv', 'txt'], key="req_uploader")
    
    if req_file and ('request_data' not in st.session_state or st.session_state.get('req_file_name') != req_file.name):
        with st.spinner("Обработка заявки..."):
            try:
                content = req_file.read()
                df_req = parse_file(content, req_file.name)
                if not df_req.empty:
                    st.session_state['request_data'] = df_req
                    st.session_state['req_file_name'] = req_file.name
                    st.success(f"Заявка обработана! Найдено позиций: {len(df_req)}")
                else:
                    st.error("Не удалось извлечь данные из файла заявки.")
            except Exception as e:
                st.error(f"Ошибка парсинга заявки: {str(e)}")

    if 'request_data' in st.session_state:
        with st.expander("Просмотр заявки"):
            st.dataframe(st.session_state['request_data'], use_container_width=True)

    st.divider()
    
    st.header("3. Загрузка счетов поставщиков")
    st.markdown("Можно загрузить несколько файлов одновременно.")
    inv_files = st.file_uploader("Файлы счетов", type=['pdf', 'xlsx', 'xls', 'docx', 'csv', 'txt'], accept_multiple_files=True, key="inv_uploader")
    
    if inv_files:
        invoices = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(inv_files):
            try:
                content = file.read()
                df_inv = parse_file(content, file.name)
                if not df_inv.empty:
                    df_inv['source_file'] = file.name
                    invoices.append(df_inv)
                progress_bar.progress((i + 1) / len(inv_files))
            except Exception as e:
                st.warning(f"Ошибка в файле {file.name}: {str(e)}")
        
        if invoices:
            st.session_state['invoices_data'] = invoices
            st.success(f"Загружено счетов: {len(invoices)}")
            
            with st.expander("Просмотр загруженных счетов"):
                all_inv_df = pd.concat(invoices, ignore_index=True)
                st.dataframe(all_inv_df, use_container_width=True)

    # Кнопка перехода
    col_left, col_right, _ = st.columns([1, 1, 3])
    with col_right:
        if st.button("Перейти к анализу ➡️", disabled=('request_data' not in st.session_state or 'invoices_data' not in st.session_state)):
            st.session_state['page'] = "analysis"
            st.rerun()

# --- ШАГ 2: АНАЛИЗ И РЕЗУЛЬТАТЫ ---
elif option == "Анализ и Результаты" or st.session_state.get('page') == "analysis":
    if 'request_data' not in st.session_state or 'invoices_data' not in st.session_state:
        st.warning("Сначала загрузите заявку и счета на вкладке 'Загрузка данных'.")
        st.stop()

    st.header("Результаты сравнения")
    
    with st.spinner("ИИ анализирует совместимость, ищет характеристики и считает логистику..."):
        # 1. Объединение данных для анализа
        req_df = st.session_state['request_data']
        inv_list = st.session_state['invoices_data']
        
        results = []
        
        # Простой алгоритм сравнения (в реальном проекте вынести в ai_engine)
        for inv_df in inv_list:
            supplier_name = inv_df['source_file'].iloc[0] if 'source_file' in inv_df.columns else "Неизвестно"
            
            # Попытка найти поставщика в названии файла или реквизитах
            # Здесь упрощенно берем имя файла
            
            total_score = 0
            matched_items = 0
            
            for idx, row in req_df.iterrows():
                req_item = str(row.get('name', '')).lower()
                req_qty = float(row.get('quantity', 0))
                
                # Поиск похожей позиции в счете
                found = False
                best_match = None
                best_ratio = 0
                
                for _, inv_row in inv_df.iterrows():
                    inv_item = str(inv_row.get('name', '')).lower()
                    # Простое сравнение строк (можно улучшить через fuzzy matching)
                    if req_item in inv_item or inv_item in req_item or req_item.split()[0] == inv_item.split()[0]:
                        ratio = len(set(req_item.split()) & set(inv_item.split())) / len(set(req_item.split()) | set(inv_item.split()))
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_match = inv_row
                
                status = "❌ Нет в счете"
                price_diff = 0
                qty_diff = 0
                
                if best_match and best_ratio > 0.4:
                    found = True
                    matched_items += 1
                    inv_qty = float(best_match.get('quantity', 0))
                    inv_price = float(best_match.get('price', 0))
                    req_price_est = float(row.get('price', 0)) if 'price' in row else 0
                    
                    qty_diff = inv_qty - req_qty
                    if req_price_est > 0:
                        price_diff = ((inv_price - req_price_est) / req_price_est) * 100
                    
                    if abs(qty_diff) < 0.1 and abs(price_diff) < 5:
                        status = "✅ Точное совпадение"
                        total_score += 10
                    elif abs(qty_diff) < 1.0:
                        status = "⚠️ Аналог/Расхождение"
                        total_score += 5
                    else:
                        status = "⚠️ Сильное расхождение"
                
                results.append({
                    "Поставщик": supplier_name,
                    "Товар": row.get('name'),
                    "Статус": status,
                    "Цена в счете": best_match.get('price', 0) if found else 0,
                    "Дельта цены %": round(price_diff, 2),
                    "Кол-во (план/факт)": f"{req_qty} / {best_match.get('quantity', 0) if found else 0}"
                })

        res_df = pd.DataFrame(results)
        
        # 2. Расчет логистики (имитация для примера)
        logistics_info = calculate_logistics(req_df, st.session_state.get('delivery_address', 'Москва'))
        
        # 3. Проверка совместимости
        compatibility_warnings = analyze_compatibility(req_df)

    st.subheader("📊 Сводная таблица")
    
    # Фильтры
    status_filter = st.multiselect("Фильтр по статусу", res_df["Статус"].unique(), default=res_df["Статус"].unique())
    filtered_df = res_df[res_df["Статус"].isin(status_filter)]
    
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🚚 Логистика и Доставка")
        if logistics_info:
            st.json(logistics_info) # Вывод в формате JSON для наглядности
            st.info(f"Рекомендуемый транспорт: **{logistics_info.get('vehicle', 'Не определен')}**")
        else:
            st.write("Нет данных для расчета логистики.")

    with col2:
        st.subheader("⚠️ Совместимость материалов")
        if compatibility_warnings:
            for warn in compatibility_warnings:
                st.error(warn)
        else:
            st.success("Конфликтов совместимости не выявлено.")

    st.divider()
    
    st.subheader("🗺️ Карта доставки")
    # Простая карта с центром в Москве (можно улучшить геокодированием адреса)
    m = folium.Map(location=[55.7558, 37.6173], zoom_start=10, tiles="CartoDB dark_matter")
    
    if st.session_state.get('delivery_address'):
        folium.Marker(
            [55.7558, 37.6173], # Координаты нужно получать через геокодер
            popup=st.session_state['delivery_address'],
            icon=folium.Icon(color='red', icon='home')
        ).add_to(m)
    
    # Точки поставщиков (случайные для демо)
    for i, inv in enumerate(inv_list):
        lat = 55.7558 + (i * 0.05)
        lon = 37.6173 + (i * 0.05)
        folium.Marker(
            [lat, lon],
            popup=f"Поставщик: {inv['source_file'].iloc[0]}",
            icon=folium.Icon(color='green', icon='truck')
        ).add_to(m)

    folium_static(m, width=800, height=400)
    
    # Экспорт
    csv = res_df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Скачать отчет (CSV)", csv, "report.csv", "text/csv")

# --- ШАГ 3: ИСТОРИЯ ---
elif option == "История закупок":
    st.header("Архив закупок и цен")
    
    query = st.text_input("Поиск по товару или поставщику")
    
    # Получение данных из БД
    # В реальном приложении здесь был бы сложный SQL запрос
    try:
        df_hist = pd.read_sql_query("SELECT * FROM invoices ORDER BY date DESC LIMIT 100", conn)
        if not df_hist.empty:
            if query:
                mask = df_hist.apply(lambda row: row.astype(str).str.contains(query, case=False).any(), axis=1)
                df_hist = df_hist[mask]
            st.dataframe(df_hist, use_container_width=True)
            
            # График динамики цен (если есть данные)
            if 'price' in df_hist.columns and 'name' in df_hist.columns:
                st.subheader("Динамика цен (последние 10 позиций)")
                # Группировка для примера
                chart_data = df_hist.groupby('name')['price'].mean().tail(10)
                st.bar_chart(chart_data)
        else:
            st.info("История пуста. Обработанные счета появятся здесь.")
    except Exception as e:
        st.error(f"Ошибка чтения истории: {e}")

# Футер
st.markdown("---")
st.caption("Система разработана для ООО «Главоблснаб». Версия 1.0")
