[Volver al índice](README.md)

# 12. Validaciones cruzadas contra StatsBomb

## Resumen general

Una tabla de 17 filas que dice con qué columna de los endpoints de estadísticas se compara cada métrica y a qué nivel.

Resumen de con qué columna de los endpoints de estadísticas se compara cada métrica. Salvo que se indique otra cosa, la regla es coincidencia exacta en conteos simples y diferencias pequeñas y explicadas en las métricas continuas.

| Métrica | Se compara con | Nivel |
| :--- | :--- | :--- |
| `score_state` ([C2](02_contexto.md#c2-score_state)) | `matches`: `home_score`, `away_score` | Partido |
| Posesiones ([B1](01_objetos_base.md#b1-posesión-válida)) | `team_match_possessions` | Partido |
| xG ([B2](01_objetos_base.md#b2-secuencia-ofensiva), [V1](06_ocasiones_y_valor.md#v1-xg-y-uplift-de-ejecución), [P2](07_balon_parado.md#p2-zona-de-remate-y-xg-de-balón-parado-contra-juego-abierto)) | `team_match_np_xg`, `team_match_op_xg`, `team_match_sp_xg` | Partido |
| xA ([V2](06_ocasiones_y_valor.md#v2-xa)) | `player_match_stats`: `xa`, `op_xa`, `sp_xa` | Jugador y partido |
| OBV ([V3](06_ocasiones_y_valor.md#v3-obv-neto)) | `team_match_obv`, `obv_pass`, `obv_shot`, `obv_defensive_action`, `obv_dribble_carry`, `obv_gk` | Partido |
| Pases ([B4](01_objetos_base.md#b4-fase-de-construcción)) | `team_match_op_passes`, `passes`, `successful_passes` | Partido |
| Presiones ([B5](01_objetos_base.md#b5-fase-de-presión), [D1](05_presion_y_defensa.md#d1-press_height-y-high_press)) | `team_match_pressures`, `fhalf_pressures` | Partido |
| Contrapresión ([D3](05_presion_y_defensa.md#d3-counterpress-y-regain_5s)) | `team_match_counterpressures`, `counterpressure_regains`, `pressure_regains` | Partido |
| PPDA ([D2](05_presion_y_defensa.md#d2-ppda)) | `team_match_ppda` | Partido |
| Transición ([D5](05_presion_y_defensa.md#d5-transition)) | `team_match_transition_xg`, `time_in_transition` (solo el orden) | Partido |
| Progresiones profundas ([V4](06_ocasiones_y_valor.md#v4-deep_progressions-y-deep_completions)) | `team_match_deep_progressions`, `deep_completions` | Partido |
| Balón parado ([P1](07_balon_parado.md#p1-set_piece_type-y-set_piece_phase), [P2](07_balon_parado.md#p2-zona-de-remate-y-xg-de-balón-parado-contra-juego-abierto)) | `team_match_corners`, `free_kicks`, `throw_ins`, `corner_xg`, `free_kick_xg`, `throw_in_xg`, `shots_from_*` | Partido |
| Expulsiones ([C5](02_contexto.md#c5-numerical_state)) | `team_match_red_cards`, `second_yellow_cards` | Partido |
| Pase que rompe líneas ([I3](04_inicio_y_construccion.md#i3-line_breaking_pass-statsbomb-360)) | `player_match_stats`: `lbp`, `lbp_completed` | Jugador y partido |
| Pases progresivos ([I6](04_inicio_y_construccion.md#i6-progressive_pass-y-carry_progress)) | `player_match_stats`: `forward_passes` (cota superior) | Jugador y partido |
| `xGChain` y `xGBuildup` ([V5](06_ocasiones_y_valor.md#v5-xgchain-y-xgbuildup)) | `player_match_stats`: `xgchain`, `op_xgchain`, `xgbuildup`, `op_xgbuildup` | Jugador y partido |
| Minutos ([J1](08_jugadores.md#j1-role_group-y-minutos)) | `player_match_stats`: `minutes` | Jugador y partido |
