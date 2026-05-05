import pandas as pd
import io
import re

def parse_file(content, filename):
    """
    Универсальный парсер файлов.
    content: байты файла
    filename: имя файла для определения типа
    """
    filename_lower = filename.lower()
    
    try:
        if filename_lower.endswith('.csv'):
            df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        
        elif filename_lower.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(content))
            
        elif filename_lower.endswith('.txt'):
            # Простой парсинг TXT (предполагаем разделители табуляцией или запятой)
            text = content.decode('utf-8')
            lines = text.split('\n')
            data = []
            for line in lines:
                if ',' in line:
                    parts = line.split(',')
                elif '\t' in line:
                    parts = line.split('\t')
                else:
                    continue
                if len(parts) >= 3:
                    data.append(parts[:3]) # Берем первые 3 колонки
            
            df = pd.DataFrame(data, columns=['name', 'quantity', 'price'])
            
        elif filename_lower.endswith('.pdf'):
            # Упрощенный парсинг PDF (требует pdfplumber, который есть в requirements)
            try:
                import pdfplumber
                tables = []
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    for page in pdf.pages:
                        table = page.extract_table()
                        if table:
                            tables.extend(table)
                
                if tables:
                    df = pd.DataFrame(tables)
                    # Попытка очистить заголовки, если они попали в данные
                    if len(df) > 0:
                        # Простая эвристика: если первая строка содержит слова "Наименование", "Цена" и т.д., пропускаем её
                        first_row_str = str(df.iloc[0]).lower()
                        if 'наименование' in first_row_str or 'цена' in first_row_str or 'count' in first_row_str:
                            df = df[1:]
                else:
                    df = pd.DataFrame()
            except Exception as e:
                print(f"PDF parse error: {e}")
                df = pd.DataFrame()
                
        elif filename_lower.endswith('.docx'):
            try:
                from docx import Document
                doc = Document(io.BytesIO(content))
                data = []
                for table in doc.tables:
                    for row in table.rows:
                        cells = [cell.text for cell in row.cells]
                        if len(cells) >= 3:
                            data.append(cells)
                df = pd.DataFrame(data)
            except Exception as e:
                print(f"DOCX parse error: {e}")
                df = pd.DataFrame()
        else:
            df = pd.DataFrame()
            
    except Exception as e:
        raise Exception(f"Ошибка чтения файла {filename}: {str(e)}")

    if df.empty:
        return df

    # Нормализация колонок
    # Переименовываем колонки в стандартные: 'name', 'quantity', 'price'
    # Предполагаем порядок: Название, Кол-во, Цена (или похожий)
    cols = df.columns.tolist()
    
    # Маппинг возможных имен колонок
    name_keywords = ['наименование', 'товар', 'продукция', 'description', 'name', 'позиция']
    qty_keywords = ['кол', 'количество', 'qty', 'count', 'шт', 'объем']
    price_keywords = ['цена', 'price', 'cost', 'сумма', 'руб']
    
    new_cols = {}
    
    # Пытаемся найти колонки по ключевым словам в заголовках (если они есть)
    # Если заголовков нет (числа 0, 1, 2), полагаемся на порядок
    
    has_headers = any(any(kw in str(c).lower() for kw in name_keywords + qty_keywords + price_keywords) for c in cols)
    
    if has_headers:
        # Логика переименования по заголовкам
        final_cols = []
        for col in cols:
            col_str = str(col).lower()
            if any(kw in col_str for kw in name_keywords):
                final_cols.append('name')
            elif any(kw in col_str for kw in qty_keywords):
                final_cols.append('quantity')
            elif any(kw in col_str for kw in price_keywords):
                final_cols.append('price')
            else:
                final_cols.append(col)
        df.columns = final_cols
        
        # Оставляем только нужные
        keep = [c for c in ['name', 'quantity', 'price'] if c in df.columns]
        if not keep:
             # Если не нашли по именам, берем первые три
             df.columns = ['name', 'quantity', 'price'] + [f'extra_{i}' for i in range(len(df.columns)-3)]
             keep = ['name', 'quantity', 'price']
        df = df[keep]
    else:
        # Нет заголовков, предполагаем порядок: Имя, Кол-во, Цена
        df_cols = []
        if len(df.columns) >= 1: df_cols.append('name')
        if len(df.columns) >= 2: df_cols.append('quantity')
        if len(df.columns) >= 3: df_cols.append('price')
        for i in range(3, len(df.columns)):
            df_cols.append(f'extra_{i}')
        
        df.columns = df_cols[:len(df.columns)]
        if 'name' not in df.columns or 'quantity' not in df.columns or 'price' not in df.columns:
             # Принудительное создание, если колонок мало
             if len(df.columns) == 1: df.columns = ['name']
             elif len(df.columns) == 2: df.columns = ['name', 'quantity']

    # Очистка данных
    if 'quantity' in df.columns:
        df['quantity'] = pd.to_numeric(df['quantity'].astype(str).str.replace(',', '.').str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
    
    if 'price' in df.columns:
        df['price'] = pd.to_numeric(df['price'].astype(str).str.replace(',', '.').str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)
        
    if 'name' in df.columns:
        df['name'] = df['name'].astype(str).str.strip()

    return df
