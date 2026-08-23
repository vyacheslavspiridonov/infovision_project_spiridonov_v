import os
import datetime
import pandas as pd

PATH_SOURCE = os.curdir
PATH_TRANS = PATH_SOURCE + '/invent_trans/'
PATH_STOCK = PATH_SOURCE + '/stock/'


def main() -> None:
    # -----------------------------------------------------------------------------
    # ## Открытие файлов:
    
    # ### Остатки:
    # Имена файлов
    stock_file_names = os.listdir(PATH_STOCK)
    
    # Пути к файлам (Путь к директории + Имя файла)
    stock_file_paths = [PATH_STOCK + x for x in stock_file_names if x.endswith('.csv')]
    
    stock_file_paths
    
    
    # Проверка количества файлов с остатками:
    
    if len(stock_file_paths) > 1:
        raise Exception('Обнаружено более 1 файла с остатками')
    else:
        stock_df = pd.read_csv(stock_file_paths[0], sep=';')
    
    stock_df['trans_date'] = stock_df['trans_date'].astype('datetime64[ns]')
    
    
    # Проверка дубликатов в остатках:
    
    # Количество дубликатов по ключевым полям
    stock_duplicates = stock_df.duplicated(subset=['item_id', 'location_id']).sum()
    
    if stock_duplicates != 0:
        raise Exception('Необходима корректировка остатков. Найдены дубликаты по ключевым полям item_id и location_id')
    
    
    # ### Движения
    # Имена файлов
    movements_file_names = os.listdir(PATH_TRANS)
    
    
    # Пути к файлам (Путь к директории + Имя файла)
    movements_file_paths = [PATH_TRANS + x for x in movements_file_names if x.endswith('.csv')]
    
    
    # Переменная, ограничивающая количество файлов для конкатенации
    file_max = 5
    
    # Инициализация Датафрейма
    movements_df = pd.DataFrame()
    
    # Конкатенация файлов 
    if len(movements_file_paths) < file_max:
        movements_df = pd.concat(
            [pd.read_csv(x, sep=';') for x in movements_file_paths]
        )
    
    # Проверка конкатенации
    if len(movements_df) == 0:
        raise Exception('Ошибка конкатенации') 
    
    movements_df['trans_date'] = movements_df['trans_date'].astype('datetime64[ns]')
    
    # Дубликаты строк:
    
    # Количество всех строк, которые имеют повторы
    int(movements_df.duplicated(keep=False).sum())
    
    
    # Количество повторов 
    int(movements_df.duplicated(keep='first').sum())
    
    
    # Первые десять
    movements_df[movements_df.duplicated(keep=False)].sort_values(
        by=list(movements_df.columns)
    ).head(10)
    
    # Распределение дубликатов:

    movements_df['month'] = movements_df['trans_date'].dt.month
    
    # Распределение повторов по месяцам
    movements_df[movements_df.duplicated(keep='first')]\
        .groupby('month').trans_date.count()
    
    movements_df.drop(['month'],axis=1, inplace=True)

    # ### Календарь наличия
    # Справочник вида локация-товар
    item_locateion_dim = pd.concat([movements_df[['location_id','item_id']], stock_df[['location_id','item_id']]]).drop_duplicates()
    
    # Объявлеие начала и конца необходимого периода
    start_day = '2025-04-30'
    end_day = '2025-07-31'
    
    # Генерация дней
    date_index = pd.date_range(start=start_day, end=end_day, freq='D')
    
    date_dim = pd.DataFrame(date_index, columns=['stock_date'])
    
    # Матрица вида: `Календарный день`-`Локация`-`Товар`
    
    item_location_matrix = date_dim.merge(
        item_locateion_dim,
        how='cross'
    )
    
    print('Файлы открыты; Переход к агрегации.')
    
    # -----------------------------------------------------------------------------
    # ## Агрегация данных
    # Расчёт дневных итогов для каждого товара с учётом локации:
    
    movements_df_total = movements_df.groupby(
        ['location_id','item_id','trans_date']
    ).agg(
        {'qty':'sum',
         'cost_amount':'sum'}
    ).reset_index()
    
    # Объединение данных остатков и транзакций:
    
    df_history = pd.concat([stock_df, movements_df_total]).sort_values(by=['location_id','item_id','trans_date'])
    
    # Матрица остатков:
    
    df_matrix = item_location_matrix.merge(
        df_history,
        how='left',
        left_on=['item_id','location_id','stock_date'],
        right_on=['item_id','location_id','trans_date'])
    
    # Сортировка массива данных для корректного заполнения пропусков:
    
    
    df_matrix.sort_values(
        by=['location_id','item_id','stock_date'], inplace=True
    )
    
    
    # Заполнение пропусков в столбцах факта
    df_matrix.fillna(
        {'qty':0, 
         'cost_amount':0,
         'trans_date':df_matrix['stock_date']}, 
        inplace=True
    )
    
    
    # Расчёт остатков по дням (кумулятивная сумма от начальной даты):
    # Остаток по `qty`:
    df_matrix['stock_qty'] = df_matrix.groupby(
        ['location_id','item_id']
    )['qty'].cumsum()
    
    # Остаток по `cost_amount`:
    df_matrix['stock_cost_amount'] = df_matrix.groupby(
        ['location_id','item_id']
    )['cost_amount'].cumsum()

    print('Агрегация данных завершена; Переход к сохранению.')
    # -----------------------------------------------------------------------------
    # # Сохранение результатов подсчёта:
    
    # Сортировка значений даты:
    date_values = sorted(date_dim.stock_date.dt.date.unique())
    
    # Перебор факта остатков по дням:
    for d_value in date_values:
        
        # Фильтр по дню остатка
        filter_mask = ( df_matrix['trans_date'] == d_value.strftime('%Y-%m-%d') )
    
        # Преобразование для сохранения
        # Фильтрация
        day_stock_df = df_matrix[filter_mask][ 
            # Выбираем нужные столбы
            ['item_id','location_id','trans_date','stock_qty','stock_cost_amount']
                ].rename(
                    # Переименование столбцов
                    columns={'stock_qty':'qty','stock_cost_amount':'cost_amount'}
                        )
        # Форматирование даты
        d_str_value = d_value.strftime('%Y_%m_%d')
    
        # Сохранение в CSV-файл
        day_stock_df.to_csv(f'{os.curdir}/stock/counted_stock/stock_{d_str_value}.csv', index=False, sep=';')

    print('Сохранение файлов завершено.')


if __name__ == "__main__":

    try:
        main()
    except Exception:
        print('Oops... Something wrong!')