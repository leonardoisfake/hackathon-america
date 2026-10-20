[Volver al índice](README.md)

# `team_match_stats`

## Resumen general

Las estadísticas de cada equipo en cada partido, tal como las entrega la API de StatsBomb.

- Grano y llave: Un equipo por partido. Llave: (`match_id`, `team_id`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 206
- Filas: 182 en los parquet crudos
- Fuente: Endpoint `team_match_stats` (`data/raw/parquet/team_match_stats.parquet`).

Reglas principales:

- Se descarta `account_id`.
- Las proporciones que se reconocen por el nombre (`*_ratio`, `*_ratio_conceded`, `*_rate` y `*possession`, sin contar `*_per_possession`) llevan una etiqueta según su rango observado: "Proporción; rango observado dentro de [0, 1]" si cabe en [0, 1] (es una observación de estos datos, no una garantía de StatsBomb); "Razón que puede pasar de 1" con el máximo observado si lo pasa; "No es una escala 0 a 1" con el rango si baja de 0; "Un solo valor observado" si el mínimo y el máximo coinciden, y "Sin datos observados" si no hay valores. `directness` no es una proporción; su regla da el rango observado. Los infinitos se descartan antes de calcular el rango.
- Las columnas que el diccionario documenta y la API no devolvió se marcan con `puede_faltar = True`. Si otra columna deja de llegar, sale del contrato y la protección de versión lo detecta como cambio.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C10 | Columnas que no aparecen siempre | Las banderas ausentes se crean con False y las stats ausentes, nulas. Las que no salen en ninguno de los 91 partidos se quedan en False para que el esquema no cambie entre corridas; hoy son 8 en `eventos`: `goalkeeper_lost_out`, `goalkeeper_success_out`, `half_end_early_video_end`, `half_end_match_suspended`, `half_start_late_video_start`, `pass_backheel`, `offside_advantage` y `shot_kick_off` | RESUELTA (Yordi) | resuelta |
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) salen de los eventos crudos (`data/raw/parquet/events__*.parquet`) porque `data/interim/eventos.parquet` no trae sus listas; se filtran a los `match_id` de `data/interim/partidos.parquet` y se unen a `eventos` por (`match_id`, `index`) | RESUELTA (Yordi) | resuelta |

## Columnas (206)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Identificador numérico del partido. | `match_id` | Int64. |
| `team_id` | Int64 | Identificador numérico del equipo en la API. | `team_id` | Int64. |
| `team_name` | category | Nombre completo del equipo. | `team_name` | strip. |
| `opposition_id` | Int64 | Identificador numérico del equipo rival. | `opposition_id` | Int64. |
| `opposition_name` | category | Nombre completo del equipo rival. | `opposition_name` | strip. |
| `competition_id` | Int64 | Identificador numérico de la competencia. | `competition_id` | Int64. |
| `competition_name` | category | Nombre completo de la competencia (por ejemplo, la liga). | `competition_name` | strip. |
| `season_id` | Int64 | Identificador numérico de la temporada. | `season_id` | Int64. |
| `season_name` | category | Descripción de la temporada (por ejemplo, 2020/2021). | `season_name` | strip. |
| `team_female` | boolean | Indica si es un equipo femenil (verdadero/falso). | `team_female` | Sin cambios. |
| `team_match_gd` | Int64 | Diferencia de goles: goles a favor menos goles en contra. | `team_match_gd` | Sin cambios. |
| `team_match_xgd` | float64 | Diferencia de goles esperados (xG) en el partido: el xG que generó el equipo menos el xG que concedió. | `team_match_xgd` | Sin cambios. |
| `team_match_np_shots` | Int64 | Tiros sin contar penales. | `team_match_np_shots` | Sin cambios. |
| `team_match_op_shots` | Int64 | Tiros en jugada abierta (sin balón parado). | `team_match_op_shots` | Sin cambios. |
| `team_match_op_shots_outside_box` | Int64 | Tiros de media o larga distancia (fuera del área) en jugada abierta. | `team_match_op_shots_outside_box` | Sin cambios. |
| `team_match_sp_shots` | Int64 | Tiros del equipo que nacen de balón parado. | `team_match_sp_shots` | Sin cambios. |
| `team_match_np_xg` | float64 | Goles esperados (xG) acumulados por todos los tiros sin penal del equipo en el partido; resume la calidad de las ocasiones que creó. | `team_match_np_xg` | Sin cambios. |
| `team_match_op_xg` | float64 | Goles esperados (xG) acumulados por los tiros del equipo en jugada abierta (sin balón parado) en el partido. | `team_match_op_xg` | Sin cambios. |
| `team_match_sp_xg` | float64 | Goles esperados (xG) acumulados por los tiros del equipo de balón parado en el partido. | `team_match_sp_xg` | Sin cambios. |
| `team_match_np_xg_per_shot` | float64 | Goles esperados (xG) promedio por tiro sin penal del equipo en el partido. | `team_match_np_xg_per_shot` | Sin cambios. |
| `team_match_np_shot_distance` | float64 | Distancia promedio a portería de los tiros sin penal del equipo. | `team_match_np_shot_distance` | Sin cambios. |
| `team_match_op_shot_distance` | float64 | Distancia promedio a portería de los tiros en jugada abierta. | `team_match_op_shot_distance` | Sin cambios. |
| `team_match_sp_shot_distance` | float64 | Distancia promedio a portería de los tiros del equipo de balón parado. | `team_match_sp_shot_distance` | Sin cambios. |
| `team_match_possessions` | Int64 | Número de posesiones del equipo en el partido; una posesión es una secuencia de acciones con balón. | `team_match_possessions` | Sin cambios. |
| `team_match_possession` | float64 | Porcentaje de posesión del balón del equipo en el partido. | `team_match_possession` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_directness` | float64 | Qué tan directo ataca el equipo en el partido: distancia que avanzó hacia la portería rival desde el inicio de cada posesión que terminó en tiro, dividida entre la distancia total recorrida en esa construcción. | `team_match_directness` | Sin cambios. No es una proporción: rango observado de 0.39 a 0.99. |
| `team_match_pace_towards_goal` | float64 | Velocidad promedio (m/s) de la construcción en posesiones que acaban en tiro, del inicio al disparo. | `team_match_pace_towards_goal` | Sin cambios. |
| `team_match_gk_pass_distance` | float64 | Longitud promedio del pase del portero al sacar jugando desde atrás. | `team_match_gk_pass_distance` | Sin cambios. |
| `team_match_gk_long_pass_ratio` | float64 | Porcentaje de pases largos del portero que llegan completos. | `team_match_gk_long_pass_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_box_cross_ratio` | float64 | De los pases al área, qué porcentaje son centros. | `team_match_box_cross_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_passes_inside_box` | Int64 | Pases completos del equipo dentro del área rival en el partido. | `team_match_passes_inside_box` | Sin cambios. |
| `team_match_defensive_distance` | float64 | Distancia promedio, medida desde la portería propia, a la que el equipo hace sus acciones defensivas en el partido (el PDF no indica la unidad). | `team_match_defensive_distance` | Sin cambios. |
| `team_match_ppda` | float64 | PPDA: pases que el equipo deja hacer al rival antes de una acción defensiva (entrada, intercepción o falta), contando solo la zona de ataque, del 40% del largo de la cancha (desde la portería propia) hacia adelante, en el partido. | `team_match_ppda` | Sin cambios. |
| `team_match_defensive_distance_ppda` | float64 | Ambiguo en el PDF: distancia promedio, medida desde la portería propia, de las acciones defensivas que entran en el cálculo del PPDA, en el partido. | `team_match_defensive_distance_ppda` | Sin cambios. |
| `team_match_opp_passing_ratio` | float64 | Porcentaje de pases completos del rival (contra este equipo). | `team_match_opp_passing_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_opp_final_third_pass_ratio` | float64 | Porcentaje de pases completos del rival en su último tercio (contra este equipo). | `team_match_opp_final_third_pass_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_np_shots_conceded` | Int64 | Tiros sin penal que el equipo permitió al rival. | `team_match_np_shots_conceded` | Sin cambios. |
| `team_match_op_shots_conceded` | Int64 | Tiros del rival en jugada abierta que el equipo permitió. | `team_match_op_shots_conceded` | Sin cambios. |
| `team_match_op_shots_conceded_outside_box` | Int64 | Tiros del rival desde fuera del área en jugada abierta. | `team_match_op_shots_conceded_outside_box` | Sin cambios. |
| `team_match_sp_shots_conceded` | Int64 | Tiros del rival que nacen de balón parado. | `team_match_sp_shots_conceded` | Sin cambios. |
| `team_match_np_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros sin penal que el equipo concedió al rival en el partido; resume la calidad de las ocasiones que permitió. | `team_match_np_xg_conceded` | Sin cambios. |
| `team_match_op_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros del rival en jugada abierta que el equipo concedió en el partido. | `team_match_op_xg_conceded` | Sin cambios. |
| `team_match_sp_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros del rival de balón parado que el equipo concedió en el partido. | `team_match_sp_xg_conceded` | Sin cambios. |
| `team_match_np_xg_per_shot_conceded` | float64 | Goles esperados (xG) promedio por tiro sin penal que el equipo concedió al rival en el partido. | `team_match_np_xg_per_shot_conceded` | Sin cambios. |
| `team_match_np_shot_distance_conceded` | float64 | Distancia promedio a portería de los tiros sin penal del rival. | `team_match_np_shot_distance_conceded` | Sin cambios. |
| `team_match_op_shot_distance_conceded` | float64 | Distancia promedio a portería de los tiros del rival en jugada abierta. | `team_match_op_shot_distance_conceded` | Sin cambios. |
| `team_match_deep_completions_conceded` | Int64 | Pases completos del rival a menos de 20 metros de la portería del equipo en el partido; son los que el equipo permitió. | `team_match_deep_completions_conceded` | Sin cambios. |
| `team_match_passes_inside_box_conceded` | Int64 | Pases completos del rival dentro del área del equipo en el partido; son los que el equipo permitió. | `team_match_passes_inside_box_conceded` | Sin cambios. |
| `team_match_corners` | Int64 | Número de tiros de esquina a favor del equipo. | `team_match_corners` | Sin cambios. |
| `team_match_corner_xg` | float64 | Goles esperados (xG) acumulados por los tiros que generó el equipo a partir de tiros de esquina en el partido. | `team_match_corner_xg` | Sin cambios. |
| `team_match_xg_per_corner` | float64 | Goles esperados (xG) promedio por cada tiro de esquina del equipo en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_corner` | Sin cambios. |
| `team_match_free_kicks` | Int64 | Número de tiros libres indirectos a favor del equipo. | `team_match_free_kicks` | Sin cambios. |
| `team_match_free_kick_xg` | float64 | Goles esperados (xG) acumulados por los tiros que generó el equipo a partir de tiros libres indirectos en el partido. | `team_match_free_kick_xg` | Sin cambios. |
| `team_match_xg_per_free_kick` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del equipo en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_free_kick` | Sin cambios. |
| `team_match_direct_free_kicks` | Int64 | Número de tiros libres directos (incluye rebotes rápidos) a favor del equipo. | `team_match_direct_free_kicks` | Sin cambios. |
| `team_match_direct_free_kick_xg` | float64 | Goles esperados (xG) acumulados por los tiros que generó el equipo a partir de tiros libres directos en el partido (incluye rebotes rápidos). | `team_match_direct_free_kick_xg` | Sin cambios. |
| `team_match_xg_per_direct_free_kick` | float64 | Ambiguo en el PDF: goles esperados (xG) promedio por cada tiro libre directo del equipo en el partido. | `team_match_xg_per_direct_free_kick` | Sin cambios. |
| `team_match_throw_ins` | Int64 | Número de saques de banda a favor del equipo. | `team_match_throw_ins` | Sin cambios. |
| `team_match_throw_in_xg` | float64 | Goles esperados (xG) acumulados por los tiros que generó el equipo a partir de saques de banda en el partido. | `team_match_throw_in_xg` | Sin cambios. |
| `team_match_xg_per_throw_in` | float64 | Goles esperados (xG) promedio por cada saque de banda del equipo en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_throw_in` | Sin cambios. |
| `team_match_ball_in_play_time` | float64 | Tiempo real de reloj con el balón en juego. | `team_match_ball_in_play_time` | Sin cambios. |
| `team_match_counter_attacking_shots` | Int64 | Tiros dentro de los 15 segundos posteriores a una posesión iniciada en su propia mitad (contragolpe). | `team_match_counter_attacking_shots` | Sin cambios. |
| `team_match_high_press_shots` | Int64 | Tiros del equipo en posesiones que recuperó en los 5 segundos siguientes a una acción defensiva (presión, entrada, intercepción o pase bloqueado) en la mitad rival, en el partido. | `team_match_high_press_shots` | Sin cambios. |
| `team_match_shots_in_clear` | Int64 | Tiros en los que solo el portero rival estaba entre el tirador y la portería (ocasión clara). | `team_match_shots_in_clear` | Sin cambios. |
| `team_match_counter_attacking_shots_conceded` | Int64 | Tiros del rival en contragolpe: dentro de 15 segundos de una posesión iniciada en la mitad del rival. | `team_match_counter_attacking_shots_conceded` | Sin cambios. |
| `team_match_shots_in_clear_conceded` | Int64 | Tiros del rival en los que solo el portero del equipo estaba entre el tirador y la portería. | `team_match_shots_in_clear_conceded` | Sin cambios. |
| `team_match_aggressive_actions` | Int64 | Entradas, presiones y faltas del equipo en los 2 segundos posteriores a que el rival recibe el balón, en el partido. | `team_match_aggressive_actions` | Sin cambios. |
| `team_match_aggression` | float64 | Proporción de recepciones de pase del rival que el equipo frena con una entrada, una falta o una presión en los 2 segundos siguientes, en el partido. | `team_match_aggression` | Sin cambios. |
| `team_match_goals` | Int64 | Goles anotados por el equipo en el partido. | `team_match_goals` | Sin cambios. |
| `team_match_own_goals` | Int64 | Autogoles del propio equipo. | `team_match_own_goals` | Sin cambios. |
| `team_match_penalty_goals` | Int64 | Goles de penal anotados. | `team_match_penalty_goals` | Sin cambios. |
| `team_match_goals_conceded` | Int64 | Goles que recibió el equipo en el partido. | `team_match_goals_conceded` | Sin cambios. |
| `team_match_opposition_own_goals` | Int64 | Autogoles del rival (a favor del equipo). | `team_match_opposition_own_goals` | Sin cambios. |
| `team_match_penalty_goals_conceded` | Int64 | Goles de penal que recibió el equipo en el partido. | `team_match_penalty_goals_conceded` | Sin cambios. |
| `team_match_shots_from_corners` | Int64 | Tiros que hizo el equipo después de tiros de esquina. | `team_match_shots_from_corners` | Sin cambios. |
| `team_match_goals_from_corners` | Int64 | Goles que metió el equipo después de tiros de esquina. | `team_match_goals_from_corners` | Sin cambios. |
| `team_match_shots_from_free_kicks` | Int64 | Tiros que hizo el equipo después de tiros libres indirectos. | `team_match_shots_from_free_kicks` | Sin cambios. |
| `team_match_goals_from_free_kicks` | Int64 | Goles que metió el equipo después de tiros libres indirectos. | `team_match_goals_from_free_kicks` | Sin cambios. |
| `team_match_direct_free_kick_goals` | Int64 | Goles del equipo de tiros libres directos (incluye rebotes rápidos). | `team_match_direct_free_kick_goals` | Sin cambios. |
| `team_match_shots_from_direct_free_kicks` | Int64 | Tiros que hizo el equipo después de tiros libres directos (incluye rebotes rápidos). | `team_match_shots_from_direct_free_kicks` | Sin cambios. |
| `team_match_shots_from_throw_ins` | Int64 | Tiros que hizo el equipo después de saques de banda. | `team_match_shots_from_throw_ins` | Sin cambios. |
| `team_match_goals_from_throw_ins` | Int64 | Goles que metió el equipo después de saques de banda. | `team_match_goals_from_throw_ins` | Sin cambios. |
| `team_match_direct_free_kick_goals_conceded` | Int64 | Goles del rival de tiros libres directos (incluye rebotes rápidos). | `team_match_direct_free_kick_goals_conceded` | Sin cambios. |
| `team_match_shots_from_direct_free_kicks_conceded` | Int64 | Tiros que hizo el rival después de tiros libres directos (incluye rebotes rápidos). | `team_match_shots_from_direct_free_kicks_conceded` | Sin cambios. |
| `team_match_corners_conceded` | Int64 | Número de tiros de esquina del rival (los que el equipo concede). | `team_match_corners_conceded` | Sin cambios. |
| `team_match_corner_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros que generó el rival a partir de tiros de esquina en el partido. | `team_match_corner_xg_conceded` | Sin cambios. |
| `team_match_shots_from_corners_conceded` | Int64 | Tiros que hizo el rival después de tiros de esquina. | `team_match_shots_from_corners_conceded` | Sin cambios. |
| `team_match_goals_from_corners_conceded` | Int64 | Goles que metió el rival después de tiros de esquina. | `team_match_goals_from_corners_conceded` | Sin cambios. |
| `team_match_free_kicks_conceded` | Int64 | Número de tiros libres indirectos concedidos: los que el equipo le regala o permite al rival. | `team_match_free_kicks_conceded` | Sin cambios. |
| `team_match_free_kick_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros que generó el rival a partir de tiros libres indirectos en el partido. | `team_match_free_kick_xg_conceded` | Sin cambios. |
| `team_match_shots_from_free_kicks_conceded` | Int64 | Tiros que hizo el rival después de tiros libres indirectos. | `team_match_shots_from_free_kicks_conceded` | Sin cambios. |
| `team_match_goals_from_free_kicks_conceded` | Int64 | Goles que metió el rival después de tiros libres indirectos. | `team_match_goals_from_free_kicks_conceded` | Sin cambios. |
| `team_match_direct_free_kicks_conceded` | Int64 | Número de tiros libres directos (incluye rebotes rápidos) concedidos: los que el equipo le regala o permite al rival. | `team_match_direct_free_kicks_conceded` | Sin cambios. |
| `team_match_direct_free_kick_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros que generó el rival a partir de tiros libres directos en el partido (incluye rebotes rápidos). | `team_match_direct_free_kick_xg_conceded` | Sin cambios. |
| `team_match_throw_ins_conceded` | Int64 | Número de saques de banda del rival (los que el equipo concede). | `team_match_throw_ins_conceded` | Sin cambios. |
| `team_match_throw_in_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros que generó el rival a partir de saques de banda en el partido. | `team_match_throw_in_xg_conceded` | Sin cambios. |
| `team_match_shots_from_throw_ins_conceded` | Int64 | Tiros que hizo el rival después de saques de banda. | `team_match_shots_from_throw_ins_conceded` | Sin cambios. |
| `team_match_goals_from_throw_ins_conceded` | Int64 | Goles que metió el rival después de saques de banda. | `team_match_goals_from_throw_ins_conceded` | Sin cambios. |
| `team_match_corner_shot_ratio` | float64 | Tiros por cada tiro de esquina del equipo (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio` | Sin cambios. Razón que puede pasar de 1 (máximo observado 2). |
| `team_match_corner_goal_ratio` | float64 | Goles por cada tiro de esquina del equipo (efectividad). | `team_match_corner_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_free_kick_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_direct_free_kick_goal_ratio` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del equipo en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_throw_in_shot_ratio` | float64 | Tiros por cada saque de banda del equipo (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_throw_in_goal_ratio` | float64 | Goles por cada saque de banda del equipo (efectividad). | `team_match_throw_in_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_xg_per_corner_conceded` | float64 | Goles esperados (xG) promedio por cada tiro de esquina del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_corner_conceded` | Sin cambios. |
| `team_match_corner_shot_ratio_conceded` | float64 | Tiros por cada tiro de esquina del rival (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio_conceded` | Sin cambios. Razón que puede pasar de 1 (máximo observado 2). |
| `team_match_corner_goal_ratio_conceded` | float64 | Goles por cada tiro de esquina del rival (efectividad). | `team_match_corner_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_xg_per_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_free_kick_conceded` | Sin cambios. |
| `team_match_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_free_kick_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_xg_per_throw_in_conceded` | float64 | Goles esperados (xG) promedio por cada saque de banda del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_throw_in_conceded` | Sin cambios. |
| `team_match_throw_in_shot_ratio_conceded` | float64 | Tiros por cada saque de banda del rival (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_throw_in_goal_ratio_conceded` | float64 | Goles por cada saque de banda del rival (efectividad). | `team_match_throw_in_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_direct_free_kick_shot_ratio` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del equipo en el partido. | `team_match_direct_free_kick_shot_ratio` | Sin cambios. Razón que puede pasar de 1 (máximo observado 2). |
| `team_match_sp` | Int64 | Número de jugadas de balón parado del equipo. | `team_match_sp` | Sin cambios. |
| `team_match_xg_per_sp` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del equipo en el partido. | `team_match_xg_per_sp` | Sin cambios. |
| `team_match_sp_shot_ratio` | float64 | Tiros por cada jugada de balón parado del equipo. | `team_match_sp_shot_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_sp_goals` | Int64 | Goles del equipo de balón parado. | `team_match_sp_goals` | Sin cambios. |
| `team_match_sp_goal_ratio` | float64 | Goles por cada jugada de balón parado del equipo. | `team_match_sp_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_sp_conceded` | Int64 | Número de jugadas de balón parado del rival. | `team_match_sp_conceded` | Sin cambios. |
| `team_match_xg_per_sp_conceded` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del rival en el partido. | `team_match_xg_per_sp_conceded` | Sin cambios. |
| `team_match_sp_shot_ratio_conceded` | float64 | Tiros por cada jugada de balón parado del rival. | `team_match_sp_shot_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_sp_goals_conceded` | Int64 | Goles del rival de balón parado. | `team_match_sp_goals_conceded` | Sin cambios. |
| `team_match_sp_goal_ratio_conceded` | float64 | Goles por cada jugada de balón parado del rival. | `team_match_sp_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_penalties_won` | Int64 | Penales que el equipo provocó a su favor en el partido. | `team_match_penalties_won` | Sin cambios. |
| `team_match_penalties_conceded` | Int64 | Penales que el equipo cometió y se señalaron a favor del rival en el partido. | `team_match_penalties_conceded` | Sin cambios. |
| `team_match_completed_dribbles` | Int64 | Regates completados por el equipo. | `team_match_completed_dribbles` | Sin cambios. |
| `team_match_failed_dribbles` | Int64 | Regates intentados que fallaron. | `team_match_failed_dribbles` | Sin cambios. |
| `team_match_total_dribbles` | Int64 | Total de intentos de regate (completados más fallados). | `team_match_total_dribbles` | Sin cambios. |
| `team_match_dribble_ratio` | float64 | Porcentaje de regates completados. | `team_match_dribble_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_completed_dribbles_conceded` | Int64 | Regates completados por el rival. | `team_match_completed_dribbles_conceded` | Sin cambios. |
| `team_match_failed_dribbles_conceded` | Int64 | Regates del rival que fallaron. | `team_match_failed_dribbles_conceded` | Sin cambios. |
| `team_match_total_dribbles_conceded` | Int64 | Total de intentos de regate del rival. | `team_match_total_dribbles_conceded` | Sin cambios. |
| `team_match_opposition_dribble_ratio` | float64 | Porcentaje de regates completados por el rival. | `team_match_opposition_dribble_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_high_press_shots_conceded` | Int64 | Tiros que el equipo concedió en posesiones que perdió en los 5 segundos siguientes a una acción defensiva del rival (presión, entrada, intercepción o pase bloqueado) en la mitad del propio equipo, en el partido. | `team_match_high_press_shots_conceded` | Sin cambios. |
| `team_match_np_gd` | Int64 | Diferencia de goles sin contar penales. | `team_match_np_gd` | Sin cambios. |
| `team_match_np_xgd` | float64 | Diferencia de goles esperados (xG) sin contar penales en el partido: el xG a favor del equipo menos el xG en contra. | `team_match_np_xgd` | Sin cambios. |
| `team_match_deep_completions` | Int64 | Pases completos del equipo a menos de 20 metros de la portería rival en el partido. | `team_match_deep_completions` | Sin cambios. |
| `team_match_passing_ratio` | float64 | Porcentaje de pases completos del equipo. | `team_match_passing_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_pressures` | Int64 | Número de presiones del equipo sobre el rival en el partido. | `team_match_pressures` | Sin cambios. |
| `team_match_counterpressures` | Int64 | Contrapresiones del equipo en el partido: presiones hechas en los 5 segundos siguientes a perder el balón. | `team_match_counterpressures` | Sin cambios. |
| `team_match_pressure_regains` | Int64 | Veces que el equipo recuperó el balón en los 5 segundos siguientes a una presión de uno de sus jugadores, en el partido. | `team_match_pressure_regains` | Sin cambios. |
| `team_match_counterpressure_regains` | Int64 | Veces que el equipo recuperó el balón en los 5 segundos siguientes a una contrapresión de uno de sus jugadores, en el partido. | `team_match_counterpressure_regains` | Sin cambios. |
| `team_match_defensive_action_regains` | Int64 | Veces que el equipo recuperó el balón en los 5 segundos siguientes a una acción defensiva de uno de sus jugadores, en el partido. | `team_match_defensive_action_regains` | Sin cambios. |
| `team_match_yellow_cards` | Int64 | Ambiguo en el PDF: tarjetas amarillas del equipo en el partido, según el nombre del campo. | `team_match_yellow_cards` | Sin cambios. |
| `team_match_second_yellow_cards` | Int64 | Veces que un jugador del equipo recibe segunda amarilla (expulsión por acumulación). | `team_match_second_yellow_cards` | Sin cambios. |
| `team_match_red_cards` | Int64 | Tarjetas rojas del equipo. | `team_match_red_cards` | Sin cambios. |
| `team_match_fhalf_pressures` | Int64 | Presiones del equipo en la mitad rival (presión alta) en el partido. | `team_match_fhalf_pressures` | Sin cambios. |
| `team_match_fhalf_counterpressures` | Int64 | Contrapresiones del equipo en la mitad rival en el partido. | `team_match_fhalf_counterpressures` | Sin cambios. |
| `team_match_fhalf_pressures_ratio` | float64 | Porcentaje de las presiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_pressures_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_fhalf_counterpressures_ratio` | float64 | Porcentaje de las contrapresiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_counterpressures_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_crosses_into_box` | Int64 | Centros al área. | `team_match_crosses_into_box` | Sin cambios. |
| `team_match_successful_crosses_into_box` | Int64 | Centros al área que resultaron exitosos. | `team_match_successful_crosses_into_box` | Sin cambios. |
| `team_match_successful_box_cross_ratio` | float64 | De los pases completos al área, qué porcentaje son centros. | `team_match_successful_box_cross_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_deep_progressions` | Int64 | Pases, regates y conducciones del equipo que llegan al último tercio rival en el partido. | `team_match_deep_progressions` | Sin cambios. |
| `team_match_deep_progressions_conceded` | Int64 | Pases, regates y conducciones del rival que llegan al tercio más cercano a la portería del equipo en el partido; es el avance que el equipo permitió. | `team_match_deep_progressions_conceded` | Sin cambios. |
| `team_match_obv` | float64 | Valor de la acción con balón (OBV) neto total del equipo en el partido, sumando todos los tipos de acción. | `team_match_obv` | Sin cambios. |
| `team_match_obv_pass` | float64 | OBV (valor de la acción con balón) neto de los pases del equipo en el partido. | `team_match_obv_pass` | Sin cambios. |
| `team_match_obv_shot` | float64 | OBV (valor de la acción con balón) neto de los tiros del equipo en el partido. | `team_match_obv_shot` | Sin cambios. |
| `team_match_obv_defensive_action` | float64 | OBV (valor de la acción con balón) neto de las acciones defensivas del equipo en el partido. | `team_match_obv_defensive_action` | Sin cambios. |
| `team_match_obv_dribble_carry` | float64 | OBV (valor de la acción con balón) neto de los regates y conducciones del equipo en el partido. | `team_match_obv_dribble_carry` | Sin cambios. |
| `team_match_obv_gk` | float64 | OBV (valor de la acción con balón) neto de las acciones del portero del equipo en el partido. | `team_match_obv_gk` | Sin cambios. |
| `team_match_obv_conceded` | float64 | OBV (valor de la acción con balón) neto total del rival en el partido, sumando todos los tipos de acción; es el valor que el equipo le permitió generar. | `team_match_obv_conceded` | Sin cambios. |
| `team_match_obv_pass_conceded` | float64 | OBV (valor de la acción con balón) neto de los pases del rival en el partido. | `team_match_obv_pass_conceded` | Sin cambios. |
| `team_match_obv_shot_nconceded` | float64 | OBV (valor de la acción con balón) neto de los tiros del rival en el partido. | `team_match_obv_shot_nconceded` | Sin cambios. |
| `team_match_obv_defensive_action_conceded` | float64 | OBV (valor de la acción con balón) neto de las acciones defensivas del rival en el partido. | `team_match_obv_defensive_action_conceded` | Sin cambios. |
| `team_match_obv_dribble_carry_conceded` | float64 | OBV (valor de la acción con balón) neto de los regates y conducciones del rival en el partido. | `team_match_obv_dribble_carry_conceded` | Sin cambios. |
| `team_match_obv_gk_conceded` | float64 | OBV (valor de la acción con balón) neto de las acciones del portero rival en el partido. | `team_match_obv_gk_conceded` | Sin cambios. |
| `team_match_passes` | Int64 | Pases intentados. | `team_match_passes` | Sin cambios. |
| `team_match_successful_passes` | Int64 | Pases completos. | `team_match_successful_passes` | Sin cambios. |
| `team_match_passes_conceded` | Int64 | Pases intentados por el rival. | `team_match_passes_conceded` | Sin cambios. |
| `team_match_successful_passes_conceded` | Int64 | Pases completos del rival. | `team_match_successful_passes_conceded` | Sin cambios. |
| `team_match_op_passes` | Int64 | Pases intentados en jugada abierta. | `team_match_op_passes` | Sin cambios. |
| `team_match_op_passes_conceded` | Int64 | Pases intentados por el rival en jugada abierta contra el equipo. | `team_match_op_passes_conceded` | Sin cambios. |
| `team_match_indirect_free_kicks` | Int64 | Número de tiros libres indirectos a favor del equipo. | `team_match_indirect_free_kicks` | Sin cambios. |
| `team_match_indirect_free_kick_xg` | float64 | Goles esperados (xG) acumulados por los tiros que generó el equipo a partir de tiros libres indirectos en el partido. | `team_match_indirect_free_kick_xg` | Sin cambios. |
| `team_match_xg_per_indirect_free_kick` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del equipo en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_indirect_free_kick` | Sin cambios. |
| `team_match_shots_from_indirect_free_kicks` | Int64 | Tiros que hizo el equipo después de tiros libres indirectos. | `team_match_shots_from_indirect_free_kicks` | Sin cambios. |
| `team_match_goals_from_indirect_free_kicks` | Int64 | Goles que metió el equipo después de tiros libres indirectos. | `team_match_goals_from_indirect_free_kicks` | Sin cambios. |
| `team_match_shots_from_indirect_free_kicks_conceded` | Int64 | Tiros que hizo el rival después de tiros libres indirectos. | `team_match_shots_from_indirect_free_kicks_conceded` | Sin cambios. |
| `team_match_goals_from_indirect_free_kicks_conceded` | Int64 | Goles que metió el rival después de tiros libres indirectos. | `team_match_goals_from_indirect_free_kicks_conceded` | Sin cambios. |
| `team_match_indirect_free_kicks_conceded` | Int64 | Número de tiros libres indirectos concedidos: los que el equipo le regala o permite al rival. | `team_match_indirect_free_kicks_conceded` | Sin cambios. |
| `team_match_indirect_free_kick_xg_conceded` | float64 | Goles esperados (xG) acumulados por los tiros que generó el rival a partir de tiros libres indirectos en el partido. | `team_match_indirect_free_kick_xg_conceded` | Sin cambios. |
| `team_match_indirect_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_indirect_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_indirect_free_kick_goal_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_xg_per_indirect_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_indirect_free_kick_conceded` | Sin cambios. |
| `team_match_indirect_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_indirect_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_indirect_free_kick_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_aerial_duel_difficulty` | float64 | Porcentaje promedio de duelos aéreos ganados estimado con las calificaciones HOPS de los jugadores; qué tan difícil es ganar por aire. | `team_match_aerial_duel_difficulty` | Sin cambios. |
| `team_match_aerial_team_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 11 jugadores en cancha, ponderada por tiempo. | `team_match_aerial_team_rating` | Sin cambios. |
| `team_match_aerial_unit_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 5 mejores jugadores aéreos en cancha, ponderada por tiempo. | `team_match_aerial_unit_rating` | Sin cambios. |
| `team_match_transition_possession_rate` | float64 | Proporción, de 0 a 1, de las posesiones del equipo que se quedan en transición y nunca llegan a la posesión asentada (control_degree = 1), en el partido. | `team_match_transition_possession_rate` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_time_in_transition` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas en fase de transición, es decir, con la posesión aún sin asentar (control_degree menor a 1), en el partido. | `team_match_time_in_transition` | Sin cambios. |
| `team_match_time_in_control` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas con la posesión asentada (control_degree = 1), en el partido. | `team_match_time_in_control` | Sin cambios. |
| `team_match_transition_xg` | float64 | Goles esperados (xG) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón, antes de que control_degree llegue a 1), en el partido. | `team_match_transition_xg` | Sin cambios. |
| `team_match_transition_xg_conceded` | float64 | Goles esperados (xG) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_xg_conceded` | Sin cambios. |
| `team_match_transition_obv` | float64 | OBV (valor de la acción con balón) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón), en el partido. | `team_match_transition_obv` | Sin cambios. |
| `team_match_transition_obv_conceded` | float64 | OBV (valor de la acción con balón) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_obv_conceded` | Sin cambios. |
| `team_match_avg_team_possession_directness` | float64 | Directness promedio de todas las posesiones del equipo en el partido, en una escala de 0 a 1: cerca de 1 es progresión sostenida hacia la portería rival y cerca de 0 es circulación del balón. | `team_match_avg_team_possession_directness` | Sin cambios. No es una proporción: rango observado de 0.36 a 0.68. |
| `team_match_avg_team_possession_directness_in_control` | float64 | Directness promedio (escala de 0 a 1) de las posesiones asentadas del equipo (control_degree = 1) en el partido. | `team_match_avg_team_possession_directness_in_control` | Sin cambios. No es una proporción: rango observado de 0.33 a 0.71. |
| `team_match_avg_team_possession_directness_in_transition` | float64 | Directness promedio (escala de 0 a 1) de las posesiones del equipo que siguen en transición, sin asentarse, en el partido. | `team_match_avg_team_possession_directness_in_transition` | Sin cambios. No es una proporción: rango observado de 0.34 a 0.97. |
| `team_match_sp_shot_distance_conceded` | float64 | Distancia promedio a portería de los tiros del rival de balón parado. | `team_match_sp_shot_distance_conceded` | Sin cambios. |
| `team_match_xg_per_direct_free_kick_conceded` | float64 | Ambiguo en el PDF: goles esperados (xG) promedio por cada tiro libre directo del rival en el partido. | `team_match_xg_per_direct_free_kick_conceded` | Sin cambios. |
| `team_match_direct_free_kick_goal_ratio_conceded` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del rival en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio_conceded` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `team_match_direct_free_kick_shot_ratio_conceded` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del rival en el partido. | `team_match_direct_free_kick_shot_ratio_conceded` | Sin cambios. Razón que puede pasar de 1 (máximo observado 2). |
