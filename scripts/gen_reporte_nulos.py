'''
Entradas:

- interim/eventos.parquet
- diccionario_endpoints.xlsx

Salidas:

- interim/reporte_nulos_reales_91_partidos.csv
- TERMINAL: vista previa en formato tabular con las primeras 15 filas del reporte comparativo de nulos
'''

import pandas as pd

df_ev = pd.read_parquet('data/interim/eventos.parquet')

# Calculamos nulos en los 91 partidos (sobre raw para ver nulos legítimos originales y sobre interim para ver post-limpieza)
nulos_interim = pd.DataFrame({
    'columna_python': df_ev.columns,
    'tipo_python': df_ev.dtypes.astype(str).values,
    'nulos_conteo_91p': df_ev.isna().sum().values,
    'pct_nulos_91p': (df_ev.isna().mean().values * 100).round(2),
    'pct_no_nulos_91p': ((1 - df_ev.isna().mean().values) * 100).round(2)
})

# Cargamos la hoja events del diccionario para cruzar (convirtiendo puntos a guiones bajos)
dicc_ev = pd.read_excel('data/diccionario_endpoints.xlsx', sheet_name='events')
dicc_ev['columna_python_est'] = dicc_ev['columna'].str.replace('.', '_', regex=False)

reporte_comparativo = pd.merge(
    nulos_interim,
    dicc_ev[['columna', 'columna_python_est', 'pct_no_nulos', 'significado']],
    left_on='columna_python',
    right_on='columna_python_est',
    how='left'
).rename(columns={'pct_no_nulos': 'pct_no_nulos_muestra_5p'})

reporte_comparativo['diferencia_pct'] = (
    reporte_comparativo['pct_no_nulos_91p'] - reporte_comparativo['pct_no_nulos_muestra_5p']
).round(2)

reporte_comparativo.to_csv('data/interim/reporte_nulos_reales_91_partidos.csv', index=False)
print("Reporte guardado en data/interim/reporte_nulos_reales_91_partidos.csv")
print(reporte_comparativo.head(15))
