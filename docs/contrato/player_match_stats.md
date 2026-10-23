[Volver al índice](README.md)

# `player_match_stats`

## Resumen general

Las estadísticas de cada jugador en cada partido, tal como las entrega la API de StatsBomb.

- Grano y llave: Un jugador por partido. Llave: (`match_id`, `team_id`, `player_id`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 177
- Filas: 2,817 en los parquet crudos
- Fuente: Endpoint `player_match_stats` (`data/raw/parquet/player_match_stats.parquet`).

Reglas principales:

- Se descarta `account_id`.
- Las proporciones que se reconocen por el nombre (`*_ratio`, `*_ratio_conceded`, `*_rate` y `*possession`, sin contar `*_per_possession`) llevan una etiqueta según su rango observado: "Proporción; rango observado dentro de [0, 1]" si cabe en [0, 1] (es una observación de estos datos, no una garantía de StatsBomb); "Razón que puede pasar de 1" con el máximo observado si lo pasa; "No es una escala 0 a 1" con el rango si baja de 0; "Un solo valor observado" si el mínimo y el máximo coinciden, y "Sin datos observados" si no hay valores. `directness` no es una proporción; su regla da el rango observado. Los infinitos se descartan antes de calcular el rango.
- Las columnas que el diccionario documenta y la API no devolvió se marcan con `puede_faltar = True`. Si otra columna deja de llegar, sale del contrato y la protección de versión lo detecta como cambio.
- Solo trae a los jugadores que entraron al campo; la banca que no jugó está en `alineaciones` y no aquí.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) salen de los eventos crudos (`data/raw/parquet/events__*.parquet`) porque `data/interim/eventos.parquet` no trae sus listas; se filtran a los `match_id` de `data/interim/partidos.parquet` y se unen a `eventos` por (`match_id`, `index`) | RESUELTA (Yordi) | resuelta |

## Columnas (177)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Identificador numérico del partido. | `match_id` | Int64. |
| `team_id` | Int64 | Identificador numérico del equipo en la API. | `team_id` | Int64. |
| `team_name` | category | Nombre del equipo del jugador. | `team_name` | strip. |
| `player_id` | Int64 | Identificador numérico del jugador en la API. | `player_id` | Int64. |
| `player_name` | string | Nombre completo del jugador. | `player_name` | strip. |
| `player_match_minutes` | float64 | Minutos jugados. | `player_match_minutes` | Sin cambios. |
| `player_match_np_xg_per_shot` | float64 | Ambiguo en el PDF: se asume que es el xG promedio por tiro sin penales del jugador, como indica el nombre. | `player_match_np_xg_per_shot` | Sin cambios. |
| `player_match_np_xg` | float64 | Ambiguo en el PDF: se asume que son los goles esperados (xG) sin penales de los tiros del propio jugador. | `player_match_np_xg` | Sin cambios. |
| `player_match_np_shots` | Int64 | Tiros sin penales. | `player_match_np_shots` | Sin cambios. |
| `player_match_goals` | Int64 | Goles anotados, incluidos penales. | `player_match_goals` | Sin cambios. |
| `player_match_np_goals` | Int64 | Goles anotados sin contar penales. | `player_match_np_goals` | Sin cambios. |
| `player_match_xa` | float64 | Asistencias esperadas (xA): suma del xG de los tiros que se generan a partir de los pases del jugador. | `player_match_xa` | Sin cambios. |
| `player_match_key_passes` | Int64 | Pases clave: pases que terminan en tiro de un compañero (también llamados asistencias de tiro o ocasiones creadas). | `player_match_key_passes` | Sin cambios. |
| `player_match_op_key_passes` | Int64 | Pases clave en jugada abierta (sin balón parado). | `player_match_op_key_passes` | Sin cambios. |
| `player_match_assists` | Int64 | Asistencias (pase que termina en gol de un compañero). | `player_match_assists` | Sin cambios. |
| `player_match_through_balls` | Int64 | Pases filtrados completos (rompen la defensa para que un compañero corra al espacio). | `player_match_through_balls` | Sin cambios. |
| `player_match_passes_into_box` | Int64 | Pases completos al área desde fuera del área. | `player_match_passes_into_box` | Sin cambios. |
| `player_match_op_passes_into_box` | Int64 | Pases completos al área desde fuera, en jugada abierta. | `player_match_op_passes_into_box` | Sin cambios. |
| `player_match_touches_inside_box` | Int64 | Toques con el pie dentro del área (incluye tiros). | `player_match_touches_inside_box` | Sin cambios. |
| `player_match_tackles` | Int64 | Entradas exitosas. | `player_match_tackles` | Sin cambios. |
| `player_match_interceptions` | Int64 | Intercepciones (corta pases del rival). | `player_match_interceptions` | Sin cambios. |
| `player_match_possession` | float64 | Ambiguo en el PDF: porcentaje de posesión asociado al jugador en el partido. | `player_match_possession` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_dribbled_past` | Int64 | Veces que lo regatean (pierde el duelo y lo dejan atrás). | `player_match_dribbled_past` | Sin cambios. |
| `player_match_dribbles_faced` | Int64 | Regates que enfrenta (rivales que intentan pasarlo). | `player_match_dribbles_faced` | Sin cambios. |
| `player_match_dribbles` | Int64 | Regates exitosos (deja atrás al rival con el balón). | `player_match_dribbles` | Sin cambios. |
| `player_match_challenge_ratio` | float64 | Porcentaje de veces que el jugador logra la entrada cuando va al duelo, frente a las veces que lo regatean. | `player_match_challenge_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_fouls` | Int64 | Faltas cometidas. | `player_match_fouls` | Sin cambios. |
| `player_match_dispossessions` | Int64 | Veces que le quitan el balón en una entrada. | `player_match_dispossessions` | Sin cambios. |
| `player_match_long_balls` | Int64 | Pases largos intentados. | `player_match_long_balls` | Sin cambios. |
| `player_match_successful_long_balls` | Int64 | Pases largos completos. | `player_match_successful_long_balls` | Sin cambios. |
| `player_match_long_ball_ratio` | float64 | Porcentaje de pases largos intentados que se completan. | `player_match_long_ball_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_shots_blocked` | Int64 | Tiros suyos bloqueados. | `player_match_shots_blocked` | Sin cambios. |
| `player_match_clearances` | Int64 | Despejes. | `player_match_clearances` | Sin cambios. |
| `player_match_aerials` | Int64 | Duelos aéreos que disputó. | `player_match_aerials` | Sin cambios. |
| `player_match_successful_aerials` | Int64 | Duelos aéreos que ganó. | `player_match_successful_aerials` | Sin cambios. |
| `player_match_passes` | Int64 | Pases intentados. | `player_match_passes` | Sin cambios. |
| `player_match_successful_passes` | Int64 | Pases completos. | `player_match_successful_passes` | Sin cambios. |
| `player_match_passing_ratio` | float64 | Porcentaje de pases intentados que se completan. | `player_match_passing_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_op_passes` | Int64 | Pases intentados en jugada abierta (sin balón parado). | `player_match_op_passes` | Sin cambios. |
| `player_match_forward_passes` | Int64 | Pases hacia adelante. | `player_match_forward_passes` | Sin cambios. |
| `player_match_backward_passes` | Int64 | Pases hacia atrás. | `player_match_backward_passes` | Sin cambios. |
| `player_match_sideways_passes` | Int64 | Pases laterales. | `player_match_sideways_passes` | Sin cambios. |
| `player_match_op_f3_passes` | Int64 | Pases del jugador en el último tercio, en jugada abierta. | `player_match_op_f3_passes` | Sin cambios. |
| `player_match_op_f3_forward_passes` | Int64 | Pases hacia adelante del jugador en el último tercio, en jugada abierta. | `player_match_op_f3_forward_passes` | Sin cambios. |
| `player_match_op_f3_backward_passes` | Int64 | Pases hacia atrás del jugador en el último tercio, en jugada abierta. | `player_match_op_f3_backward_passes` | Sin cambios. |
| `player_match_op_f3_sideways_passes` | Int64 | Pases laterales del jugador en el último tercio, en jugada abierta. | `player_match_op_f3_sideways_passes` | Sin cambios. |
| `player_match_np_shots_on_target` | Int64 | Tiros a puerta sin penales. | `player_match_np_shots_on_target` | Sin cambios. |
| `player_match_crosses` | Int64 | Centros completos. | `player_match_crosses` | Sin cambios. |
| `player_match_successful_crosses` | Int64 | Centros exitosos. | `player_match_successful_crosses` | Sin cambios. |
| `player_match_crossing_ratio` | float64 | Porcentaje de centros intentados que llegan a un compañero. | `player_match_crossing_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_penalties_won` | Int64 | Penales provocados. | `player_match_penalties_won` | Sin cambios. |
| `player_match_passes_inside_box` | Int64 | Pases completos que empiezan y terminan dentro del área. | `player_match_passes_inside_box` | Sin cambios. |
| `player_match_op_xa` | float64 | Asistencias esperadas (xA) del jugador en jugada abierta (sin balón parado). | `player_match_op_xa` | Sin cambios. |
| `player_match_op_assists` | Int64 | Asistencias en jugada abierta (sin balón parado). | `player_match_op_assists` | Sin cambios. |
| `player_match_pressured_long_balls` | Int64 | Despejes o pases largos hechos bajo presión. | `player_match_pressured_long_balls` | Sin cambios. |
| `player_match_unpressured_long_balls` | Int64 | Pases largos hechos sin presión. | `player_match_unpressured_long_balls` | Sin cambios. |
| `player_match_aggressive_actions` | Int64 | Acciones defensivas agresivas: entradas, presiones y faltas hechas en los 2 segundos posteriores a que el rival recibe el balón. | `player_match_aggressive_actions` | Sin cambios. |
| `player_match_turnovers` | Int64 | Pérdidas de balón por mal control o regate fallido. | `player_match_turnovers` | Sin cambios. |
| `player_match_crosses_into_box` | Int64 | Centros al área. | `player_match_crosses_into_box` | Sin cambios. |
| `player_match_sp_xa` | float64 | Asistencias esperadas (xA) del jugador en balón parado: suma del xG de los tiros que generan sus pases de balón parado. | `player_match_sp_xa` | Sin cambios. |
| `player_match_op_shots` | Int64 | Tiros en jugada abierta. | `player_match_op_shots` | Sin cambios. |
| `player_match_touches` | Int64 | Toques de balón con el pie completados. | `player_match_touches` | Sin cambios. |
| `player_match_pressure_regains` | Int64 | Veces que recuperó el balón en los 5 segundos posteriores a presionar a un rival. | `player_match_pressure_regains` | Sin cambios. |
| `player_match_box_cross_ratio` | float64 | De los pases completos al área, qué porcentaje son centros. | `player_match_box_cross_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_deep_progressions` | Int64 | Pases, regates y conducciones del jugador que meten el balón al último tercio rival. | `player_match_deep_progressions` | Sin cambios. |
| `player_match_shot_touch_ratio` | float64 | Tiros como proporción de sus toques de balón (qué tanto tira en vez de solo tocar). | `player_match_shot_touch_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_fouls_won` | Int64 | Faltas recibidas. | `player_match_fouls_won` | Sin cambios. |
| `player_match_xgchain` | float64 | xGChain: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión, incluidos quien tiró y quien asistió. | `player_match_xgchain` | Sin cambios. |
| `player_match_op_xgchain` | float64 | xGChain del jugador en jugada abierta: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión. | `player_match_op_xgchain` | Sin cambios. |
| `player_match_xgbuildup` | float64 | xGBuildup: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión, sin contar a quien tiró ni a quien dio el pase del tiro. | `player_match_xgbuildup` | Sin cambios. |
| `player_match_op_xgbuildup` | float64 | xGBuildup del jugador en jugada abierta: reparte el xG del tiro final entre quienes participaron en la posesión, sin contar a quien tiró ni a quien dio el pase del tiro. | `player_match_op_xgbuildup` | Sin cambios. |
| `player_match_xgchain_per_possession` | float64 | xGChain del jugador expresado por posesión, no como total del partido. | `player_match_xgchain_per_possession` | Sin cambios. |
| `player_match_op_xgchain_per_possession` | float64 | xGChain del jugador en jugada abierta, expresado por posesión, no como total del partido. | `player_match_op_xgchain_per_possession` | Sin cambios. |
| `player_match_xgbuildup_per_possession` | float64 | xGBuildup del jugador expresado por posesión, no como total del partido. | `player_match_xgbuildup_per_possession` | Sin cambios. |
| `player_match_op_xgbuildup_per_possession` | float64 | xGBuildup del jugador en jugada abierta, expresado por posesión, no como total del partido. | `player_match_op_xgbuildup_per_possession` | Sin cambios. |
| `player_match_pressures` | float64 | Veces que el jugador presiona a un rival. | `player_match_pressures` | Sin cambios. |
| `player_match_pressure_duration_total` | float64 | Duración total de las presiones del jugador en el partido. | `player_match_pressure_duration_total` | Sin cambios. |
| `player_match_pressure_duration_avg` | float64 | Duración promedio de las presiones del jugador en el partido. | `player_match_pressure_duration_avg` | Sin cambios. |
| `player_match_pressured_action_fails` | float64 | Veces que no recuperó el balón en los 5 segundos tras presionar a un rival. | `player_match_pressured_action_fails` | Sin cambios. |
| `player_match_counterpressures` | float64 | Contrapresiones: presiones hechas en los 5 segundos posteriores a perder el balón. | `player_match_counterpressures` | Sin cambios. |
| `player_match_counterpressured_action_fails` | float64 | Contrapresiones del jugador que fallaron, es decir, que no sirvieron para recuperar el balón. | `player_match_counterpressured_action_fails` | Sin cambios. |
| `player_match_obv` | float64 | Valor de la acción con balón (OBV) neto total del jugador, sumando todos los tipos de acción. | `player_match_obv` | Sin cambios. |
| `player_match_obv_pass` | float64 | OBV (valor de la acción con balón) neto generado por los pases del jugador. | `player_match_obv_pass` | Sin cambios. |
| `player_match_obv_shot` | float64 | OBV (valor de la acción con balón) neto generado por los tiros del jugador. | `player_match_obv_shot` | Sin cambios. |
| `player_match_obv_defensive_action` | float64 | OBV (valor de la acción con balón) neto generado por las acciones defensivas del jugador. | `player_match_obv_defensive_action` | Sin cambios. |
| `player_match_obv_dribble_carry` | float64 | OBV (valor de la acción con balón) neto generado por los regates y conducciones del jugador. | `player_match_obv_dribble_carry` | Sin cambios. |
| `player_match_deep_completions` | Int64 | Pases completos en zona profunda, cerca del área rival. | `player_match_deep_completions` | Sin cambios. |
| `player_match_ball_recoveries` | Int64 | Recuperaciones de balón. | `player_match_ball_recoveries` | Sin cambios. |
| `player_match_np_psxg` | float64 | Post-shot xG (goles esperados después del tiro) de los tiros a puerta del jugador, sin penales: mide la calidad del remate según hacia dónde fue. | `player_match_np_psxg` | Sin cambios. |
| `player_match_penalties_faced` | Int64 | Portero: penales enfrentados. | `player_match_penalties_faced` | Sin cambios. |
| `player_match_penalties_conceded` | Int64 | Portero: penales enfrentados que terminaron en gol. | `player_match_penalties_conceded` | Sin cambios. |
| `player_match_fhalf_ball_recoveries` | Int64 | Recuperaciones de balón del jugador en la mitad rival (recuperación alta). | `player_match_fhalf_ball_recoveries` | Sin cambios. |
| `player_match_average_space_received_in` | float64 | Espacio libre promedio del jugador al recibir el balón, según los datos 360, en el partido. | `player_match_average_space_received_in` | Sin cambios. |
| `player_match_average_fhalf_space_received_in` | float64 | Espacio libre promedio del jugador al recibir el balón en la mitad rival, según los datos 360, en el partido. | `player_match_average_fhalf_space_received_in` | Sin cambios. |
| `player_match_average_f3_space_received_in` | float64 | Espacio libre promedio del jugador al recibir el balón en el último tercio, según los datos 360, en el partido. | `player_match_average_f3_space_received_in` | Sin cambios. |
| `player_match_ball_receipts_in_space_10` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador con más de 10 m de espacio libre en el partido; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_ball_receipts_in_space_10` | Sin cambios. |
| `player_match_ball_receipts_in_space_2` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador con más de 2 m de espacio libre en el partido. | `player_match_ball_receipts_in_space_2` | Sin cambios. |
| `player_match_ball_receipts_in_space_5` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador con más de 5 m de espacio libre en el partido; también cuentan en la categoría de más de 2 m. | `player_match_ball_receipts_in_space_5` | Sin cambios. |
| `player_match_fhalf_ball_receipts_in_space_10` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en la mitad rival con más de 10 m de espacio libre en el partido; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_fhalf_ball_receipts_in_space_10` | Sin cambios. |
| `player_match_fhalf_ball_receipts_in_space_2` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en la mitad rival con más de 2 m de espacio libre en el partido. | `player_match_fhalf_ball_receipts_in_space_2` | Sin cambios. |
| `player_match_fhalf_ball_receipts_in_space_5` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en la mitad rival con más de 5 m de espacio libre en el partido; también cuentan en la categoría de más de 2 m. | `player_match_fhalf_ball_receipts_in_space_5` | Sin cambios. |
| `player_match_f3_ball_receipts_in_space_10` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en el último tercio con más de 10 m de espacio libre en el partido; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_f3_ball_receipts_in_space_10` | Sin cambios. |
| `player_match_f3_ball_receipts_in_space_2` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en el último tercio con más de 2 m de espacio libre en el partido. | `player_match_f3_ball_receipts_in_space_2` | Sin cambios. |
| `player_match_f3_ball_receipts_in_space_5` | Int64 | Ambiguo en el PDF: recepciones de balón del jugador en el último tercio con más de 5 m de espacio libre en el partido; también cuentan en la categoría de más de 2 m. | `player_match_f3_ball_receipts_in_space_5` | Sin cambios. |
| `player_match_lbp` | Int64 | Pases que rompen líneas (pases que superan una línea de defensores rivales) intentados por el jugador en jugada abierta. | `player_match_lbp` | Sin cambios. |
| `player_match_lbp_completed` | Int64 | Pases que rompen líneas completados por el jugador en jugada abierta. | `player_match_lbp_completed` | Sin cambios. |
| `player_match_fhalf_lbp_completed` | Int64 | Pases que rompen líneas completados por el jugador en la mitad rival, en jugada abierta. | `player_match_fhalf_lbp_completed` | Sin cambios. |
| `player_match_f3_lbp_completed` | Int64 | Pases que rompen líneas completados por el jugador en el último tercio, en jugada abierta. | `player_match_f3_lbp_completed` | Sin cambios. |
| `player_match_fhalf_lbp` | Int64 | Pases que rompen líneas intentados por el jugador en la mitad rival, en jugada abierta. | `player_match_fhalf_lbp` | Sin cambios. |
| `player_match_f3_lbp` | Int64 | Pases que rompen líneas intentados por el jugador en el último tercio, en jugada abierta. | `player_match_f3_lbp` | Sin cambios. |
| `player_match_obv_lbp` | float64 | OBV (valor de la acción con balón) de pase generado por los pases del jugador que rompen líneas. | `player_match_obv_lbp` | Sin cambios. |
| `player_match_fhalf_obv_lbp` | float64 | OBV (valor de la acción con balón) de pase generado por los pases del jugador que rompen líneas en la mitad rival. | `player_match_fhalf_obv_lbp` | Sin cambios. |
| `player_match_f3_obv_lbp` | float64 | OBV (valor de la acción con balón) de pase generado por los pases del jugador que rompen líneas en el último tercio. | `player_match_f3_obv_lbp` | Sin cambios. |
| `player_match_lbp_received` | Int64 | Pases que rompen líneas recibidos por el jugador en jugada abierta. | `player_match_lbp_received` | Sin cambios. |
| `player_match_fhalf_lbp_received` | Int64 | Pases que rompen líneas recibidos por el jugador en la mitad rival, en jugada abierta. | `player_match_fhalf_lbp_received` | Sin cambios. |
| `player_match_f3_lbp_received` | Int64 | Pases que rompen líneas recibidos por el jugador en el último tercio, en jugada abierta. | `player_match_f3_lbp_received` | Sin cambios. |
| `player_match_average_lbp_to_space_distance` | float64 | Espacio libre promedio del receptor en los pases del jugador que rompen líneas y se completaron, en el partido. | `player_match_average_lbp_to_space_distance` | Sin cambios. |
| `player_match_lbp_to_space_10_received` | Int64 | Pases que rompen líneas que el jugador recibió con más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_lbp_to_space_10_received` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_10_received` | Int64 | Pases que rompen líneas que el jugador recibió en la mitad rival con más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_fhalf_lbp_to_space_10_received` | Sin cambios. |
| `player_match_f3_lbp_to_space_10_received` | Int64 | Pases que rompen líneas que el jugador recibió en el último tercio con más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_f3_lbp_to_space_10_received` | Sin cambios. |
| `player_match_lbp_to_space_2_received` | Int64 | Pases que rompen líneas que el jugador recibió con más de 2 m de espacio libre. | `player_match_lbp_to_space_2_received` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_2_received` | Int64 | Pases que rompen líneas que el jugador recibió en la mitad rival con más de 2 m de espacio libre. | `player_match_fhalf_lbp_to_space_2_received` | Sin cambios. |
| `player_match_f3_lbp_to_space_2_received` | Int64 | Pases que rompen líneas que el jugador recibió en el último tercio con más de 2 m de espacio libre. | `player_match_f3_lbp_to_space_2_received` | Sin cambios. |
| `player_match_lbp_to_space_5_received` | Int64 | Pases que rompen líneas que el jugador recibió con más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_lbp_to_space_5_received` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_5_received` | Int64 | Pases que rompen líneas que el jugador recibió en la mitad rival con más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_fhalf_lbp_to_space_5_received` | Sin cambios. |
| `player_match_f3_lbp_to_space_5_received` | Int64 | Pases que rompen líneas que el jugador recibió en el último tercio con más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_f3_lbp_to_space_5_received` | Sin cambios. |
| `player_match_average_lbp_to_space_received_distance` | float64 | Espacio libre promedio con el que el jugador recibió sus pases que rompen líneas, en el partido. | `player_match_average_lbp_to_space_received_distance` | Sin cambios. |
| `player_match_fhalf_average_lbp_to_space_received_distance` | float64 | Espacio libre promedio con el que el jugador recibió sus pases que rompen líneas en la mitad rival, en el partido. | `player_match_fhalf_average_lbp_to_space_received_distance` | Sin cambios. |
| `player_match_lbp_to_space_10` | Int64 | Pases que rompen líneas completados por el jugador cuyo receptor tenía más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_lbp_to_space_10` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_10` | Int64 | Pases que rompen líneas completados por el jugador en la mitad rival cuyo receptor tenía más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_fhalf_lbp_to_space_10` | Sin cambios. |
| `player_match_f3_lbp_to_space_10` | Int64 | Pases que rompen líneas completados por el jugador en el último tercio cuyo receptor tenía más de 10 m de espacio libre; también cuentan en las categorías de más de 5 m y de 2 m. | `player_match_f3_lbp_to_space_10` | Sin cambios. |
| `player_match_lbp_to_space_2` | Int64 | Pases que rompen líneas completados por el jugador cuyo receptor tenía más de 2 m de espacio libre. | `player_match_lbp_to_space_2` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_2` | Int64 | Pases que rompen líneas completados por el jugador en la mitad rival cuyo receptor tenía más de 2 m de espacio libre. | `player_match_fhalf_lbp_to_space_2` | Sin cambios. |
| `player_match_f3_lbp_to_space_2` | Int64 | Pases que rompen líneas completados por el jugador en el último tercio cuyo receptor tenía más de 2 m de espacio libre. | `player_match_f3_lbp_to_space_2` | Sin cambios. |
| `player_match_lbp_to_space_5` | Int64 | Pases que rompen líneas completados por el jugador cuyo receptor tenía más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_lbp_to_space_5` | Sin cambios. |
| `player_match_fhalf_lbp_to_space_5` | Int64 | Pases que rompen líneas completados por el jugador en la mitad rival cuyo receptor tenía más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_fhalf_lbp_to_space_5` | Sin cambios. |
| `player_match_f3_lbp_to_space_5` | Int64 | Pases que rompen líneas completados por el jugador en el último tercio cuyo receptor tenía más de 5 m de espacio libre; también cuentan en la categoría de más de 2 m. | `player_match_f3_lbp_to_space_5` | Sin cambios. |
| `player_match_passes_360` | Int64 | Pases del jugador registrados con datos 360. | `player_match_passes_360` | Sin cambios. |
| `player_match_obv_passes_360` | float64 | OBV (valor de la acción con balón) de pase de los pases del jugador registrados con datos 360. | `player_match_obv_passes_360` | Sin cambios. |
| `player_match_fhalf_passes_360` | Int64 | Pases del jugador en la mitad rival registrados con datos 360. | `player_match_fhalf_passes_360` | Sin cambios. |
| `player_match_fhalf_obv_passes_360` | float64 | OBV (valor de la acción con balón) de pase de los pases del jugador en la mitad rival registrados con datos 360. | `player_match_fhalf_obv_passes_360` | Sin cambios. |
| `player_match_f3_passes_360` | Int64 | Pases del jugador en el último tercio registrados con datos 360. | `player_match_f3_passes_360` | Sin cambios. |
| `player_match_f3_obv_passes_360` | float64 | OBV (valor de la acción con balón) de pase de los pases del jugador en el último tercio registrados con datos 360. | `player_match_f3_obv_passes_360` | Sin cambios. |
| `player_match_ball_receipts_360` | Int64 | Recepciones de balón con datos 360. | `player_match_ball_receipts_360` | Sin cambios. |
| `player_match_fhalf_ball_receipts_360` | Int64 | Recepciones de balón del jugador en la mitad rival registradas con datos 360. | `player_match_fhalf_ball_receipts_360` | Sin cambios. |
| `player_match_f3_ball_receipts_360` | Int64 | Recepciones de balón del jugador en el último tercio registradas con datos 360. | `player_match_f3_ball_receipts_360` | Sin cambios. |
| `player_match_360_minutes` | float64 | Minutos jugados en partidos que tienen datos 360 (base para normalizar las métricas 360). | `player_match_360_minutes` | Sin cambios. |
| `player_match_defensive_actions` | Int64 | Acciones defensivas: entradas, presiones y faltas. | `player_match_defensive_actions` | Sin cambios. |
| `player_match_ccaa` | float64 | Portero: qué tan seguido intenta atrapar balones "atrapables" (centros, pases) comparado con el portero promedio. | `player_match_ccaa` | Sin cambios. |
| `player_match_da_aggressive_distance` | float64 | Portero: distancia promedio hacia adelante, desde su portería, a la que sale para hacer acciones defensivas, en el partido (el PDF no indica la unidad). | `player_match_da_aggressive_distance` | Sin cambios. |
| `player_match_goals_conceded` | Int64 | Portero: goles que le anotaron (sin penales ni autogoles). | `player_match_goals_conceded` | Sin cambios. |
| `player_match_gsaa` | float64 | Portero: goles evitados contra lo esperado (post-shot xG de lo que enfrentó menos goles recibidos). | `player_match_gsaa` | Sin cambios. |
| `player_match_positive_outcome_score` | float64 | Porcentaje que indica con qué frecuencia el jugador participa, mientras está en la cancha, en secuencias que terminan en tiro, tiro libre en la mitad rival o tiro de esquina. | `player_match_positive_outcome_score` | Sin cambios. |
| `player_match_npot_psxg_faced` | float64 | Portero: post-shot xG (goles esperados después del tiro) de los tiros a puerta sin penal que enfrentó. | `player_match_npot_psxg_faced` | Sin cambios. |
| `player_match_save_ratio` | float64 | Portero: porcentaje de tiros a puerta que ataja. | `player_match_save_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_npot_shots_faced` | Int64 | Portero: tiros a puerta sin penales enfrentados. | `player_match_npot_shots_faced` | Sin cambios. |
| `player_match_defensive_responsibility_actions` | Int64 | Acciones defensivas que hizo como respuesta a jugadas de ataque rival. | `player_match_defensive_responsibility_actions` | Sin cambios. |
| `player_match_expected_defensive_actions` | float64 | Acciones defensivas esperadas según las situaciones que enfrentó (mide la carga o la oportunidad de defender). | `player_match_expected_defensive_actions` | Sin cambios. |
| `player_match_defensive_actions_above_expectation` | float64 | Acciones defensivas reales menos las esperadas. | `player_match_defensive_actions_above_expectation` | Sin cambios. |
| `player_match_obv_conceded_responsibility_weighted` | float64 | OBV (valor de la acción con balón) que concede el jugador, ponderado por su probabilidad de responsabilidad defensiva ante las jugadas de ataque rival. | `player_match_obv_conceded_responsibility_weighted` | Sin cambios. |
| `player_match_predicted_headers` | float64 | Duelos de cabeza que se esperaría que ganara según la dificultad de cada duelo. | `player_match_predicted_headers` | Sin cambios. |
| `player_match_transition_possession_rate` | float64 | Proporción, de 0 a 1, de las posesiones del jugador que se quedan en fase de transición y no llegan a la posesión asentada (control_degree = 1). | `player_match_transition_possession_rate` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_transition_xg` | float64 | Goles esperados (xG) que genera el jugador mientras la posesión aún no se asienta (fase de transición con balón). | `player_match_transition_xg` | Sin cambios. |
| `player_match_transition_obv` | float64 | OBV (valor de la acción con balón) que genera el jugador mientras la posesión aún no se asienta (fase de transición con balón). | `player_match_transition_obv` | Sin cambios. |
| `player_match_avg_player_possession_directness` | float64 | Directness promedio del jugador en sus acciones con balón, ponderado por el número de acciones, en el partido. | `player_match_avg_player_possession_directness` | Sin cambios. No es una proporción: rango observado de -0.81 a 1.64. |
| `player_match_avg_player_possession_directness_in_control` | float64 | Directness promedio del jugador en las acciones con balón en que la posesión ya está asentada (control_degree = 1), en el partido. | `player_match_avg_player_possession_directness_in_control` | Sin cambios. No es una proporción: rango observado de -0.71 a 1.79. |
| `player_match_avg_player_possession_directness_in_transition` | float64 | Directness promedio del jugador en las acciones con balón durante la transición, con la posesión aún sin asentar, en el partido. | `player_match_avg_player_possession_directness_in_transition` | Sin cambios. No es una proporción: rango observado de -1.07 a 3.70. |
| `player_match_counterpressure_duration_total` | float64 | Duración total de las contrapresiones del jugador (presiones en los 5 segundos siguientes a perder el balón) en el partido. | `player_match_counterpressure_duration_total` | Sin cambios. |
| `player_match_counterpressure_duration_avg` | float64 | Duración promedio de las contrapresiones del jugador (presiones en los 5 segundos siguientes a perder el balón) en el partido. | `player_match_counterpressure_duration_avg` | Sin cambios. |
| `player_match_f3_average_lbp_to_space_received_distance` | float64 | Espacio libre promedio con el que el jugador recibió sus pases que rompen líneas en el último tercio, en el partido. | `player_match_f3_average_lbp_to_space_received_distance` | Sin cambios. |
| `player_match_aerial_ratio` | float64 | Porcentaje de duelos aéreos (balones por arriba, cabezazos) que el jugador gana. | `player_match_aerial_ratio` | Sin cambios. Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb). |
| `player_match_fhalf_average_lbp_to_space_distance` | float64 | Espacio libre promedio del receptor en los pases del jugador que rompen líneas y se completaron en la mitad rival, en el partido. | `player_match_fhalf_average_lbp_to_space_distance` | Sin cambios. |
| `player_match_f3_average_lbp_to_space_distance` | float64 | Espacio libre promedio del receptor en los pases del jugador que rompen líneas y se completaron en el último tercio, en el partido. | `player_match_f3_average_lbp_to_space_distance` | Sin cambios. |
| `player_match_obv_gk` | float64 | OBV (valor de la acción con balón) neto de las acciones del jugador como portero. | `player_match_obv_gk` | Sin cambios. |
| `player_match_claim_success` | float64 | Portero: porcentaje de intentos de atrapar el balón (centros/pases) que le salen bien. | `player_match_claim_success` | Sin cambios. |
| `player_match_gk_positioning_error` | float64 | Portero: qué tan lejos está en promedio de la posición ideal para enfrentar un tiro (menos es mejor). | `player_match_gk_positioning_error` | Sin cambios. |
| `player_match_gsaa_ratio` | float64 | Portero: goles evitados sobre lo esperado, como porcentaje de los tiros enfrentados. | `player_match_gsaa_ratio` | Sin cambios. No es una escala 0 a 1: rango observado de -0.88 a 0.48. |
