[Volver al índice](README.md)

# 13. Columnas ambiguas del diccionario: aclaración y decisión

## Resumen general

Las 45 columnas que el diccionario marca como `[ambiguo]`, cada una con su duda, su aclaración y su decisión: 5 se usan con una prueba previa, 21 se reemplazan por un cálculo propio y 19 se descartan. Cierra con los 6 pasos para confirmarlo con datos reales.

El diccionario marca 45 columnas con `[ambiguo]`. Significa que el PDF oficial de StatsBomb es confuso, se contradice o no coincide con lo que devuelve la API. Aquí cada una se aclara con la evidencia que trae el propio diccionario (ejemplos, tipos, columnas vecinas y glosario) y se decide si se usa. Límite importante: desde este análisis no se puede consultar la API, así que cada aclaración es una hipótesis con evidencia, no una confirmación; por eso cada decisión trae una prueba para hacer con los datos descargados. Las columnas sin documentar o ausentes (`estado_cruce`) son otro tema y se revisan al descargar los datos completos.

## 13.1 Resumen de decisiones

| Decisión | N | Cuáles |
| :--- | :--- | :--- |
| Se usan, con una prueba previa | 5 | `frames_360`: `event_uuid`, `ball_receipt_in_space`. `lineups`: `positions.to`. `matches`: `metadata.shot_fidelity_version`. `events`: `pass.cut_back` |
| Se reemplazan por un cálculo propio | 21 | `player_match_stats`: 9 columnas `ball_receipts_in_space`. `player_season_stats`: `xgchain`, `op_xgchain`, `xgbuildup`, `op_xgbuildup` y 5 `padj_*`. `team_match_stats`: `yellow_cards` y `defensive_distance_ppda`. `team_season_stats`: `defensive_distance_ppda` |
| Se descartan | 19 | `lineups` `skills.HOPS`; `frames_360` `point_id`; `player_match_stats` `np_xg`, `np_xg_per_shot` y `possession`; `player_season_stats` `np_psxg_faced_90`; `team_match_stats` `account_id` y 6 campos de tiro libre directo; `team_season_stats` `possessions` y `minutes`; `competitions` `match_available_360`; `matches` `stadium.country.id`; `player_mapping` `competition_id` y `player_preferred_foot` |

## 13.2 Se usan, con una prueba previa (5)

- **`frames_360.event_uuid`.** Duda: el PDF no dice con qué campo de `events` se une. Aclaración: es un UUID con el mismo formato que el `id` de `events` y un frame corresponde a un evento; en `events` el UUID se llama `id`. Decisión: se usa (fichas [I3](04_inicio_y_construccion.md#i3-line_breaking_pass-statsbomb-360) e [I5](04_inicio_y_construccion.md#i5-ball_receipt_in_space-360)). Prueba: al unir, todos los frames deben encontrar su evento y no debe haber dos frames con el mismo `event_uuid`; si queda alguno sin pareja, se reporta.
- **`frames_360.ball_receipt_in_space`.** Duda: el resumen de cambios del PDF lo llama `ball_receipt_space`. Aclaración: la muestra de la API trae `ball_receipt_in_space` completo (100% no nulo); el otro nombre es del resumen del PDF. Decisión: se usa (ficha [I5](04_inicio_y_construccion.md#i5-ball_receipt_in_space-360)). Prueba: confirmar al descargar que la columna existe con ese nombre; si solo existe la otra, se renombra.
- **`lineups.lineup[].positions[].to`.** Duda: no dice qué viene si el jugador siguió hasta el final. Aclaración: solo el 45% trae valor y el ejemplo (`01:10:58.114` con `to_period = 2`) tiene formato `horas:minutos:segundos` y pasa de 45 minutos en el segundo tiempo. Eso parece un reloj corrido del partido y no un reloj reiniciado por periodo, aunque la descripción diga «reloj del periodo». Vacío significa que el jugador siguió hasta el final, lo que cuadra con que más de la mitad de los tramos no tengan salida. Decisión: se usa (ficha [J1](08_jugadores.md#j1-role_group-y-minutos)) con la regla vacío = fin del partido. Prueba: los minutos por jugador deben coincidir con `minutes` de `player_match_stats` y la suma de minutos del EQ debe ser cerca de 11 veces la duración del partido. Ojo: este reloj no se puede cruzar directamente con el `timestamp` de `events`, que sí se reinicia en cada tiempo.
- **`matches.metadata.shot_fidelity_version`.** Duda: solo aparece en el apéndice de historial; si falta, equivale a la versión 1. Aclaración: es la versión del detalle con que se capturaron los tiros. No cambia ninguna fórmula, pero es razonable suponer que afecta qué tan comparable es el xG entre partidos capturados con versiones distintas. Decisión: se usa como variable de control, no como métrica. Prueba: contar la versión en los 91 partidos (tratando la etiqueta ausente como 1). Si hay más de una, el xG se compara dentro de la misma versión o se declara como limitación.
- **`events.pass.cut_back`.** Duda: el PDF lo escribe «cut-back» y la ruta se escribe `cut_back`. Aclaración: solo cambia el nombre; la muestra trae el campo con guion bajo (0.04% de los eventos, solo en pases). Decisión: se usa tal cual si se quiere contar cut-backs (balón raso hacia atrás dentro del área rival). Ninguna ficha lo usa por ahora. Prueba: ninguna.

## 13.3 Se reemplazan por un cálculo propio (21)

- **`player_match_stats.ball_receipts_in_space_2`, `_5`, `_10` y sus versiones `fhalf_` y `f3_` (9 columnas).** Duda: el PDF dice «porcentaje de recepciones», pero el campo es entero. Aclaración: casi seguro son conteos. Los ejemplos bajan al subir el umbral (24, 18 y 6) y bajan al estrechar la zona (total 24, mitad rival 13, último tercio 3), que es justo el patrón de conteos anidados; un porcentaje no tendría por qué cumplirlo y se guardaría como decimal. Queda además otra diferencia: estas columnas hablan de metros y la bandera de `frames_360` de yardas (radio de 2). Decisión: no se usan; [I5](04_inicio_y_construccion.md#i5-ball_receipt_in_space-360) calcula las recepciones en espacio desde `frames_360`. Prueba: en 3 partidos, el conteo propio con radio de 2 yardas debe parecerse a `_2`; una diferencia pequeña se explica por metros contra yardas.
- **`player_season_stats.xgchain`, `op_xgchain`, `xgbuildup` y `op_xgbuildup` (4).** Duda: no llevan sufijo `_90` ni `per_possession`, así que no se sabe si son total o promedio. Aclaración: el ejemplo (cerca de 1) es del orden de un solo partido y no de un total de temporada, lo que sugiere un promedio; pero depende de un solo ejemplo y no es concluyente. Además estas tablas juntan Apertura y Clausura, así que no sirven para separar torneos. El glosario tampoco aclara si el xG se «reparte» dividido o completo entre los participantes. Decisión: no se usan. [V5](06_ocasiones_y_valor.md#v5-xgchain-y-xgbuildup) las calcula desde `events` y se valida con las versiones por partido de `player_match_stats` (`xgchain`, `op_xgchain`, `xgbuildup`), que no están marcadas como ambiguas, probando las dos variantes (completo o dividido).
- **`player_season_stats.padj_tackles_90`, `padj_interceptions_90`, `padj_tackles_and_interceptions_90`, `padj_clearances_90` y `padj_pressures_90` (5).** Duda: no se aclara si el ajuste por posesión usa la posesión del equipo del jugador o la del rival. Aclaración: el glosario repite la misma duda y el diccionario no da más pistas; además son cifras de temporada de jugador. Decisión: no se usan. Si se necesita comparar el volumen defensivo entre partidos con posesiones distintas, se usa una normalización propia y explícita: acciones defensivas por cada 100 pases del rival en juego abierto (el mismo tipo de ajuste que usa el PPDA), declarada en el framework.
- **`team_match_stats.yellow_cards` (1).** Duda: la descripción del PDF dice «segunda amarilla». Aclaración: lo más probable es un error de copiado del campo vecino `second_yellow_cards`, que ya tiene esa descripción; el nombre y el ejemplo (1 contra 0) apuntan a amarillas simples. Decisión: ninguna ficha lo usa. Si hace falta, se cuentan las amarillas desde `events` (`foul_committed.card.name` y `bad_behaviour.card.name = Yellow Card`). Prueba: comparar ese conteo con este campo en 3 partidos; si coinciden, el campo se puede usar.
- **`team_match_stats.defensive_distance_ppda` y `team_season_stats.defensive_distance_ppda` (2).** Duda: la descripción copia la de `defensive_distance` y le añade «(passes per defensive action)», que es la unidad del PPDA y no de una distancia. Aclaración: no puede ser una distancia desde la portería propia. Las acciones del PPDA ocurren desde x ≥ 48 yardas (el 40% del largo), así que su promedio no bajaría de 48 (o de 40 en la escala 0 a 100 del glosario), y los ejemplos son 8.6 (partido) y 3.9 (temporada). Parece que mide otra cosa o que el PDF la describe mal. Decisión: no se usa. [D2](05_presion_y_defensa.md#d2-ppda) calcula el PPDA con una zona explícita, [D4](05_presion_y_defensa.md#d4-defensive_line_height) calcula la altura de la línea defensiva con x, y el PPDA estándar se toma de `team_match_ppda`, que no es ambiguo.

## 13.4 Se descartan (19)

| Columna | Duda | Por qué se descarta |
| :--- | :--- | :--- |
| `lineups` `skills.HOPS` | El PDF no explica la sigla | En `events`, `duel.hops_rating` describe una calificación HOPS aplicada a un duelo aéreo, así que parece una calificación aérea del jugador. Ninguna ficha la necesita |
| `frames_360` `distances_from_edge_of_visible_area[].point_id` | No dice cómo se relaciona con `freeze_frame` | La cobertura se filtra con `visible_player_counts`. Si se quisiera usar, la prueba es ver si la lista tiene el mismo largo que `freeze_frame` y coincide por orden |
| `player_match_stats` `np_xg` y `np_xg_per_shot` | El PDF los describe como xG asistido | Parece un error de copiado (el xG asistido ya está en `xa`). A nivel jugador se evitan; el xG se valida con `team_match_np_xg` y sumando `shot.statsbomb_xg` por jugador desde `events` |
| `player_match_stats` `possession` | No explica cómo se calcula la posesión de un jugador | Su ejemplo (0.6213) coincide con el de `team_match_possession`, lo que sugiere que repite la posesión del equipo en el partido. Se usa la del equipo o la propia de [B1](01_objetos_base.md#b1-posesión-válida) |
| `player_season_stats` `np_psxg_faced_90` | Casi idéntica a `npot_psxg_faced_90`; no aclara si solo cuenta tiros a puerta | Es una métrica de portero y no se evalúa a porteros |
| `team_match_stats` `account_id` | El PDF no la describe | Es el id de la cuenta con licencia, no una estadística de juego |
| `team_match_stats`: `xg_per_direct_free_kick`, `direct_free_kick_goal_ratio` y `direct_free_kick_shot_ratio` (y sus versiones `_conceded`, 6 en total) | La API real no las devuelve | No existen en los datos. [P1](07_balon_parado.md#p1-set_piece_type-y-set_piece_phase) calcula esos cocientes desde `events` o con los campos que sí existen (`direct_free_kicks`, `direct_free_kick_goals`, `shots_from_direct_free_kicks`, `direct_free_kick_xg`) |
| `team_season_stats` `possessions` | No indica si es total o promedio por partido | El ejemplo (198) es del orden de un partido (159 en el ejemplo de `team_match_possessions`), así que casi seguro es un promedio por partido. [B1](01_objetos_base.md#b1-posesión-válida) cuenta las posesiones desde `events` |
| `team_season_stats` `minutes` | La API real no lo devuelve | No se necesita |
| `competitions` `match_available_360` | No dice qué valor aparece si la competencia no tiene 360 | Se filtra con `matches.match_status_360 = available`, que sí está documentado |
| `matches` `stadium.country.id` | El PDF lo da como texto y la API como objeto | No se usa el estadio |
| `player_mapping` `competition_id` y `player_preferred_foot` | Typos del PDF (`competiton_id`, `player_perferred_foot`) | No se usa `player_mapping`; si se usara, se toman los nombres que devuelve la API |

## 13.5 Cómo confirmarlo con datos reales

Responsable sugerido: Lee, que según el plan revisa las definiciones ambiguas, con Yordi para la descarga. Se hace primero con un partido y luego con 3:

1. Confirmar los nombres de columna (`event_uuid`, `ball_receipt_in_space`, `pass.cut_back`).
2. Probar la unión de `frames_360` con `events`: todos los frames deben encontrar su evento, sin duplicados.
3. Revisar el reloj de `lineups` y la regla de `to` vacío contra los minutos de `player_match_stats`.
4. Contar `shot_fidelity_version` en los 91 partidos.
5. Comparar el conteo propio de recepciones en espacio ([I5](04_inicio_y_construccion.md#i5-ball_receipt_in_space-360)) con `ball_receipts_in_space_2` en 3 partidos.
6. Opcional: comparar las amarillas contadas en `events` con `yellow_cards`.

Cada resultado se anota en una tabla (columna, resultado, decisión final). Esa tabla va a la metodología del HTML.
