'''
Entradas

- interim/eventos.parquet    
- interim/partidos.parquet  
- interim/team_match_stats.parquet
- interim/player_match_stats.parquet

Salidas

- interim/validacion_conteos_equipo.csv
- interim/validacion_conteos_jugadores.csv
- TERMINAL: dos tablas detalladas en texto para verificar si las diferencias de conteo son cero.
'''

import pandas as pd

# Cargamos tablas limpias de interim
df_ev = pd.read_parquet('data/interim/eventos.parquet')
df_partidos = pd.read_parquet('data/interim/partidos.parquet')
df_tms = pd.read_parquet('data/interim/team_match_stats.parquet')
df_pms = pd.read_parquet('data/interim/player_match_stats.parquet')

# Elegimos 3 partidos de muestra y filtramos al Club América (team_id == 1229)
AMERICA_ID = 1229
muestra_matches = df_partidos['match_id'].head(3).tolist()

# Detectamos nombres exactos de columnas en interim/eventos.parquet
col_team = 'team_id' if 'team_id' in df_ev.columns else 'team.id'
col_type = 'type_name' if 'type_name' in df_ev.columns else 'type.name'
col_shot_type = 'shot_type_name' if 'shot_type_name' in df_ev.columns else 'shot.type.name'
col_xg = 'shot_statsbomb_xg' if 'shot_statsbomb_xg' in df_ev.columns else 'shot.statsbomb_xg'
col_pass_out = 'pass_outcome_name' if 'pass_outcome_name' in df_ev.columns else 'pass.outcome.name'

# 1. CONTEOS PROPIOS POR EQUIPO (América en esos 3 partidos, excluyendo tanda de penales period < 5)
ev_3p = df_ev[(df_ev['match_id'].isin(muestra_matches)) & (df_ev[col_team] == AMERICA_ID) & (df_ev['period'] < 5)].copy()

comparacion_equipo = []
for mid in muestra_matches:
    sub = ev_3p[ev_3p['match_id'] == mid]
    
    # Tiros sin penales (np_shots) y xG sin penales (np_xg)
    tiros_np = sub[(sub[col_type] == 'Shot') & (sub[col_shot_type] != 'Penalty')]
    propio_np_shots = len(tiros_np)
    propio_np_xg = round(tiros_np[col_xg].sum(), 4)
    
    # Datos oficiales en team_match_stats
    oficial = df_tms[(df_tms['match_id'] == mid) & (df_tms['team_id'] == AMERICA_ID)].iloc[0]
    
    comparacion_equipo.append({
        'match_id': mid,
        'propio_np_shots': propio_np_shots,
        'statsbomb_np_shots': int(oficial['team_match_np_shots']),
        'diff_shots': propio_np_shots - int(oficial['team_match_np_shots']),
        'propio_np_xg': propio_np_xg,
        'statsbomb_np_xg': round(float(oficial['team_match_np_xg']), 4),
        'diff_xg': round(propio_np_xg - float(oficial['team_match_np_xg']), 4)
    })

df_comp_eq = pd.DataFrame(comparacion_equipo)
print("=== CONTROL DE CALIDAD: EQUIPO (eventos vs team_match_stats) ===")
print(df_comp_eq.to_string(index=False))

# 2. CONTEOS PROPIOS POR JUGADOR (Top jugadores del primer partido)
mid_1 = muestra_matches[0]
sub_j = ev_3p[ev_3p['match_id'] == mid_1]
col_player = 'player_id' if 'player_id' in df_ev.columns else 'player.id'

pases_j = sub_j[sub_j[col_type] == 'Pass'].groupby(col_player).agg(
    propio_passes=('id', 'count'),
    propio_successful_passes=(col_pass_out, lambda s: s.isna().sum())
).reset_index().rename(columns={col_player: 'player_id'})

tiros_j = sub_j[(sub_j[col_type] == 'Shot') & (sub_j[col_shot_type] != 'Penalty')].groupby(col_player).agg(
    propio_np_shots=('id', 'count'),
    propio_np_xg=(col_xg, 'sum')
).reset_index().rename(columns={col_player: 'player_id'})

oficial_j = df_pms[(df_pms['match_id'] == mid_1) & (df_pms['team_id'] == AMERICA_ID)][
    ['player_id', 'player_name', 'player_match_passes', 'player_match_successful_passes', 'player_match_np_shots', 'player_match_np_xg']
]

df_comp_jug = oficial_j.merge(pases_j, on='player_id', how='left').merge(tiros_j, on='player_id', how='left').fillna(0)
print(f"\n=== CONTROL DE CALIDAD: JUGADORES (match_id={mid_1}) ===")
print(df_comp_jug.head(10).to_string(index=False))

# Guardamos los CSVs en interim/
df_comp_eq.to_csv('data/interim/validacion_conteos_equipo.csv', index=False)
df_comp_jug.to_csv('data/interim/validacion_conteos_jugadores.csv', index=False)
