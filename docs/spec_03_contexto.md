# Spec 03: contexto y espacio por evento (scripts/03_contexto.py)

Estado: v0.4, 19-oct-2026 (paso 4: tablas por posesión y por partido, con los ajustes de B1 que decidió el usuario y las correcciones de la revisión doble). Dueño: Yordi. Referencia: especificación de métricas de Lee, fichas B1 (`01_objetos_base.md`), C1 a C5 (`02_contexto.md`) y E1 a E2 (`03_espacio.md`); contrato v0.2; `propuesta_nombres_fase3.md` (nombres aprobados por el equipo el 19-oct).

## Problema

Las métricas de la fase 3 (ataque, defensa, jugadores) necesitan segmentar cada evento por su contexto: minuto, marcador, localía, rival, fuerza del rival y superioridad numérica, y ubicarlo en la cancha (tercio, celda, zona 14, distancia y ángulo a la portería). Hoy cada script tendría que recalcularlo por su cuenta y podrían divergir. `03_contexto.py` calcula esas columnas una sola vez desde `data/interim/`, las valida contra los marcadores, las tarjetas y las alineaciones, y las deja en `data/processed/` para unirlas a `eventos` por (`match_id`, `index`). Cada ficha es una función que devuelve su propio frame. Con esas funciones se arman además una tabla por posesión (contexto al inicio, conteos y la posesión válida de B1) y una por partido (contexto, goles, expulsiones y minutos por marcador).

## Salidas (nombres aprobados el 19-oct, en constantes al inicio del script)

- `data/processed/contexto_eventos.parquet`: una fila por evento de `eventos`, llave (`match_id`, `index`), solo la llave y las columnas nuevas. No repite `torneo` porque ya está en `eventos`.
- `data/processed/rival_strength.parquet`: una fila por (`team_id`, `torneo`) de toda la liga, sin el equipo analizado (EQ, `team_id` 1229).
- `data/processed/contexto_posesiones.parquet`: una fila por posesión de StatsBomb de los periodos 1 a 4, llave (`match_id`, `possession`). No se funden filas.
- `data/processed/contexto_partidos.parquet`: una fila por partido, llave `match_id`, 91 filas.
- `data/processed/control_posesiones_fundidas.csv`: muestra fija de hasta 10 posesiones fundidas para revisarlas a mano (validación de B1). Se escribe siempre, aunque sea solo con el encabezado, para que no quede el archivo de una corrida anterior.

| Ficha | Columnas en `contexto_eventos` |
| :--- | :--- |
| C1 | `match_clock`, `minute_bin` |
| C2 | `goal_diff`, `goal_diff_clip`, `score_state` |
| C3 | `is_home`, `rival_id`, `stage`, `match_week` |
| C4 | `rival_strength`, `rival_strength_tercil`, `rival_ppg` |
| C5 | `numerical_state`, `numerical_state_cat` |
| E1 | `third`, `cell_6x5`, `zona14` |
| E2 | `dist_goal`, `angle_goal` |

`contexto_posesiones`:

| Columnas | Regla |
| :--- | :--- |
| `possession_team_id`, `es_eq` | Equipo con el balón; `es_eq` si es 1229. |
| `period`, `index_inicio`, `index_fin` | Periodo del primer evento y primer y último `index` de la posesión. |
| `segundo_inicio`, `duracion` | `match_second` del primer evento; `timestamp` del último menos el del primero, en segundos (nulo si cruzan de periodo, lo que solo pasa en posesiones administrativas del medio tiempo). |
| `play_pattern_name`, `es_balon_parado` | Del primer evento no administrativo (si no hay, del primero); `es_balon_parado` = `play_pattern_id` en {2, 3, 4}. |
| `x_inicio`, `y_inicio`, `third_inicio` | Primer evento con ubicación y `team_id == possession_team_id`, en su perspectiva; `third_inicio` con la regla de E1. |
| `n_eventos`, `n_pases`, `n_tiros`, `xg` | Todos los eventos; `Pass` y `Shot` del equipo con la posesión (los tiros incluyen penales); suma de `shot_statsbomb_xg` de sus tiros sin penales. |
| `score_state`, `numerical_state`, `minute_bin`, `stage`, `rival_strength_tercil` | De `contexto_eventos` en `index_inicio`. `score_state`, `numerical_state` y `rival_strength_tercil` se ven siempre desde el EQ, también en las posesiones del rival (por ejemplo, `ganando` quiere decir que el EQ va ganando). |
| `posesion_fundida_id`, `is_valid_possession` | B1, regla de abajo. |
| `es_administrativa` | True si todos los eventos de la posesión tienen `es_administrativo` (el criterio de `ADMINISTRATIVOS` de `contrato.py`, tomado de `eventos`). Las filas no se borran. Va al final de la tabla. |

`contexto_partidos`: `torneo`, `match_week`, `stage`, `es_final`, `is_home`, `rival_id`, `rival_nombre`, `rival_strength`, `rival_strength_tercil`, `rival_ppg`, `goles_eq`, `goles_rival`, `expulsiones_eq`, `expulsiones_rival`, `minutos_ganando`, `minutos_empatando` y `minutos_perdiendo`. Los tres nombres de minutos no estaban fijados en la propuesta.

Las categorías tienen listas fijas en el script, así que no cambian entre corridas.

### Regla de B1 (posesión fundida y válida)

- Dos posesiones consecutivas `p` y `q` (la siguiente en la numeración de StatsBomb) se funden si son del mismo `possession_team_id`, del mismo periodo, las dos tienen al menos un evento propio no administrativo, los eventos no administrativos del rival "entre ellas" son al menos uno y todos toques sin dirección (`Block`, `Clearance`, `Miscontrol` o `Ball Recovery` con `ball_recovery_recovery_failure = True`), y `q` no empieza con una reanudación. "Entre ellas" son los eventos del rival en `p` después del último evento propio de `p`, más los de `q` antes del primer evento propio de `q`.
- Reanudación: el `play_pattern_name` de `q` (el de su primer evento no administrativo) es `From Corner`, `From Free Kick`, `From Throw In`, `From Goal Kick` o `From Kick Off`. Por el paso 1 de la ficha, una reanudación abre una posesión nueva aunque la ejecute el mismo equipo, así que no se funde (decisión del usuario, 19-oct).
- Las cadenas se funden completas (`p`, `q`, `r`, ...); `posesion_fundida_id` es el `possession` de la primera. Una posesión que no se funde tiene su propio número.
- `is_valid_possession` = (al menos 3 pases o al menos 1 tiro sin penal en la posesión fundida) y no `es_balon_parado`. Las sumas del grupo solo cuentan las filas que no son de balón parado, para que una `p` de córner o tiro libre no vuelva válida a una `q` de juego abierto si algún día hay fusiones (hoy no cambia nada). Los penales no cuentan como tiro para la validez (decisión del usuario, 19-oct); `n_tiros` sí los incluye. Las filas de balón parado quedan en False; quien analiza balón parado filtra por `es_balon_parado`.
- Solo está implementada la regla de frontera (cola de `p` y cabeza de `q`, con `q` la posesión siguiente). Una posesión intermedia `r` hecha solo de toques del rival, o una posesión administrativa entre `p` y `q`, no se funde: `p` y `q` dejan de ser consecutivas.
- Por qué la fusión literal no aplica: StatsBomb ya deja el toque sin dirección del rival dentro de la posesión del equipo con el balón. Solo 9 posesiones están hechas únicamente de esos toques y ninguna queda entre dos posesiones del mismo equipo, así que la regla literal (con `r` intermedia) tampoco fundiría nada. Los pares consecutivos del mismo equipo con un toque así en la frontera son 1,400, y todos empiezan con una reanudación (973 saques de banda, 400 córners y 27 saques de meta), que se excluyen por el paso 1. Resultado: 0 fusiones, y `posesion_fundida_id` es igual a `possession` en todas las filas. La columna se queda porque el equipo la aprobó y porque la regla sigue en el código por si cambian los datos.

## Criterios de aceptación

- AC1 (C1): `match_clock = match_second / 60` reusa la columna de `eventos`. `minute_bin` sale de `minute`: periodo 1 en `0-15`, `15-30`, `30-45` y `45+`; periodo 2 en `45-60`, `60-75`, `75-90` y `90+`; periodos 3 y 4 en `ET`; periodo 5 nulo. La corrida falla si el mínimo de `timestamp` no es cero en algún periodo o si algún bin queda vacío en el agregado.
- AC2 (C2): un gol es un `Shot` con `shot_outcome_name = Goal` (periodos 1 a 4) o un `Own Goal For`, del equipo del evento. Se acumula por (`match_id`, `index`) y se desplaza un evento, así que `goal_diff` (goles EQ menos goles del rival) es el estado antes del evento. `goal_diff_clip` lo recorta a ±2 y `score_state` vale ganando, empatando o perdiendo. Periodo 5 nulo. La corrida falla si los goles finales no cuadran con `home_score` y `away_score` en los 91 partidos con ninguno de los dos criterios de autogol (directo e invertido); el script imprime cuál funcionó.
- AC3 (C3): `is_home = home_team_id == 1229`; `rival_id` viene de `partidos` y debe ser el otro equipo; `stage` es `regular` si `competition_stage_id` está en {1, 42, 44} y `fase final` si no; `match_week` y `torneo` vienen de `partidos`. La corrida falla si no hay 91 partidos, 66 regulares y 25 de fase final, o si `rival_id` no es el otro equipo. También falla si los huecos de jornada en fase regular (contra 1 a la jornada máxima de la liga en ese torneo) no son exactamente los de `HUECOS_PERMITIDOS` = {`Clausura 2025`: {1, 2}} (partidos de Diego Cervantes), o si hay jornadas repetidas en la fase regular.
- AC4 (C4): desde `team_match_stats_liga` con `fase = regular`, para cada (`team_id`, `torneo`) sin contar sus partidos contra 1229: `rival_strength` = promedio de `team_match_np_xgd`; `rival_strength_tercil` = débil, medio o fuerte por terciles dentro del torneo, sobre el rango con empate al primero (`rank(method="first")`, que desempata por `team_id`); con 17 equipos quedan 6 débiles, 5 medios y 6 fuertes, verificado en los 8 torneos; `rival_ppg` = puntos por partido (3/1/0 con `team_match_goals` contra `team_match_goals_conceded`). La corrida falla si algún rival de los 91 partidos no tiene valor en su torneo o si alguna fila `es_play_in` tiene `fase = regular`. Imprime dónde caen las filas `es_play_in` (y "ninguna entra en fase regular" solo si hay filas), el reparto de terciles, los 3 primeros y los 3 últimos de cada torneo de Jardine y la correlación de Spearman entre `rival_strength` y `rival_ppg`.
- AC5 (C5): una expulsión es `Red Card` o `Second Yellow` en `foul_committed_card_name` o `bad_behaviour_card_name`, y solo cuenta si el jugador estaba en la cancha (regla de abajo). `numerical_state` = expulsiones del rival menos expulsiones del EQ acumuladas en orden (`match_id`, `index`), incluyendo el propio evento de la tarjeta (vigente desde la tarjeta, como dice la ficha). `numerical_state_cat` = igualdad, superioridad o inferioridad. Periodo 5 nulo. La corrida falla si las expulsiones en cancha no son exactamente los tramos de `posiciones` con `end_reason` `Red Card` o `Second Yellow Card`, o si todas las expulsiones de eventos no cuadran por (partido, equipo) con `team_match_red_cards + team_match_second_yellow_cards`, o si algún par (`match_id`, `team_id`) con expulsiones en eventos no está en `team_match_stats`. Imprime cada partido donde el conteo en cancha difiere de `team_match_stats` y el rango de `numerical_state` sin recortar.
- AC6 (E1): `third` vale `defensive_third` (x < 40), `midfield_third` (40 a 80) o `final_third` (x ≥ 80), con las etiquetas de `location_bucket`. `cell_6x5 = fila * 6 + columna`, con columna = min(⌊x/20⌋, 5) y fila = min(⌊y/16⌋, 4): id 0 en la esquina x < 20, y < 16, recorre x primero y llega a 29 en x ≥ 100, y ≥ 64. `zona14` = 80 ≤ x < 102 y 26.7 ≤ y ≤ 53.3. Sin `x` todo queda nulo. La corrida falla si algún x está fuera de [0, 120] o algún y fuera de [0, 80], o si el acuerdo de `third` con `location_bucket` en juego abierto (`play_pattern_id` 1 o 6) baja de 99.5%. Hoy es 99.74% (163,965 eventos); los 427 desacuerdos tienen x exactamente 40 u 80, donde `location_bucket` pone el borde en el tercio de abajo.
- AC7 (E2): `dist_goal = √((120 − x)² + (40 − y)²)` y `angle_goal = |atan2(44 − y, 120 − x) − atan2(36 − y, 120 − x)|` en grados, con `x` e `y` sin espejar. La corrida falla si algún tiro con `shot_type_name = Penalty`, de cualquiera de los dos equipos, no da 12 yardas. Imprime el xG medio por bins de distancia en los tiros que no son penal (periodos 1 a 4) y avisa si no baja.
- AC8: si falla cualquier validación dura no se escribe nada y el código de salida es 1; si todo pasa se escriben las cuatro tablas y el CSV de control, y el código es 0. La escritura sigue el esquema de `02_limpieza.py`: todo va a una carpeta temporal `data/processed/.tmp_contexto_*`; los errores de escritura (`OSError`, `ValueError`, `TypeError`, `ArrowException`) no reemplazan nada; antes de reemplazar se revisa que ningún destino esté bloqueado (por ejemplo, el CSV abierto en Excel); después se reemplaza archivo por archivo y, si falla a la mitad, sale con 1 y el mensaje dice qué se reemplazó y dónde quedó la carpeta temporal, que no se borra. Al final se borran los `.tmp_contexto_*` y `.<salida>.tmp` de corridas anteriores. Con `--sin-escribir` corre todo, también la muestra de control, y no escribe. La revisión de bloqueo es heurística, como en `02_limpieza.py`: un proceso que deja leer y escribir pero no borrar no se detecta antes y cae en el caso de reemplazo a medias.
- AC9 (B1): `contexto_posesiones` tiene una fila por (`match_id`, `possession`) de los periodos 1 a 4 con las columnas de arriba. La corrida falla si una posesión fundida mezcla equipos o periodos, si algún `posesion_fundida_id` es mayor que su `possession`, si el número de fusiones no es filas menos grupos o si algún `index_inicio` no existe en `eventos` (aparte, la llave única se revisa con las demás salidas). Imprime, por (partido, equipo), la razón entre las posesiones de StatsBomb antes de fundir y `team_match_possessions` (media, mínimo y máximo), cuántas posesiones se fundieron (y de qué tipo), cuántos pares se excluyen por reanudación, cuántas válidas cambian por la fusión y cuántas posesiones son administrativas, y escribe `control_posesiones_fundidas.csv` con una columna `tipo`: hasta 10 posesiones fundidas (`fundida`) y hasta 10 pares (`p`, `q`) descartados porque `q` empieza con reanudación (`descartada_reanudacion`), las dos muestras con semilla 0. Se eligió un solo CSV con `tipo` para no agregar otro archivo; con 0 fusiones trae solo los 10 descartados.
- AC10 (partidos): `contexto_partidos` tiene 91 filas con llave única. `goles_eq` y `goles_rival` salen de C2 (periodos 1 a 4) y la corrida falla si no cuadran con `goles_favor` y `goles_contra` de `partidos`. `expulsiones_eq` y `expulsiones_rival` cuentan solo las expulsiones en cancha de C5 y la corrida falla si no cuadran por (partido, equipo) con los tramos de `posiciones` con `end_reason` de tarjeta. Los minutos ganando, empatando y perdiendo se ponderan por tiempo: cada evento aporta la diferencia de `match_second` hasta el siguiente dentro de (`match_id`, `period`), sin periodo 5, y ese tramo se asigna al marcador vigente después del evento (el `score_state` del evento siguiente). Imprime la suma de minutos por partido contra la duración por `timestamp` (máximo de `timestamp` por periodo, sumado).
- AC11: en `contexto_eventos`, `contexto_posesiones` y `contexto_partidos` el conjunto de `match_id` es exactamente el de los 91 partidos de `partidos`; si aparece otro (por ejemplo, los 2 de Diego Cervantes del Clausura 2025) o falta alguno, la corrida falla sin escribir nada.

## Desviaciones de las fichas

- C1: `match_second` ya existe en `eventos` y no se recalcula. El máximo de `minute` por periodo no cuadra en todos los partidos: en 3972074 el primer tiempo llega al minuto 79 por una pausa de unos 23 minutos tras el 36:40 (`Injury Stoppage`), y en 3970308 el segundo tiempo llega al 105. El reloj no se corrige; esos eventos caen en `45+` y `90+`. El script avisa cuando el primer tiempo llega al minuto 60 o el segundo al 105.
- C3: en el Clausura 2025 faltan las jornadas 1 y 2 de fase regular. No es un hueco de datos: esos dos partidos (3972016 y 3972023) los dirigió Diego Cervantes y la descarga los excluye como "otro manager" (`docs/inventario_descarga.md`). Los otros tres torneos tienen las 17 jornadas.
- C3: `torneo` sale de la columna `torneo` de `partidos` (misma regla de fecha, ya calculada en la descarga), no se deriva otra vez de `match_date`.
- C4: la ficha filtra por `competition_stage.id`, pero `team_match_stats_liga` no lo tiene; se usa `fase = regular` (la misma regla {1, 42, 44} aplicada en la descarga). Las 6 filas `es_play_in` tienen `fase = liguilla`, así que quedan fuera. El EQ no entra en la tabla ni en los terciles: nunca es rival y su promedio no excluiría nada.
- C5, expulsiones de banca: los eventos traen 27 expulsiones (21 rojas y 6 segundas amarillas) y `posiciones` 25. Las 2 de más son de jugadores que no estaban en la cancha: Héctor Moreno (3918991, `team_id` 1222), roja en el 91:12 después de salir de cambio en el 57:00, y José Santiago Hernández (3972118, `team_id` 1296), portero suplente que no jugó, roja en el 73:53. `team_match_stats` cuenta las 27. Regla: una expulsión cuenta para `numerical_state` solo si el jugador tiene un tramo en `posiciones` que cubre el momento de la tarjeta, comparando (periodo, segundo) del evento con (`from_period`, `from`) y (`to_period`, `to`) del tramo; un `to` nulo llega al silbatazo final. El reloj de `posiciones` en tiempo extra no está documentado en el contrato; en estos datos el cruce exacto de las 25 expulsiones en cancha con `end_reason` lo respalda.
- B1, periodo 5: la tanda queda fuera de `contexto_posesiones`, como dice la ficha.
- B1, balón parado: la ficha dice que el balón parado "se marca aparte y no se filtra por número de pases" y que "no se considera". Se marca con `es_balon_parado` y su `is_valid_possession` queda en False.
- B1, fusión: la regla literal no funde nada en estos datos, y la de frontera solo encuentra pares que empiezan con una reanudación, que se excluyen (ver la regla de B1). Hay 0 fusiones; la validez se cuenta por posesión de StatsBomb.
- B1, posesiones administrativas: 269 posesiones de los periodos 1 a 4 solo tienen eventos administrativos (`Starting XI`, `Half End`/`Half Start`, cambios). Se conservan, porque la tabla tiene una fila por posesión de StatsBomb, y se marcan con `es_administrativa`; quedan con `n_pases = 0` y no válidas. Las del medio tiempo cruzan de periodo y llevan `duracion` nula.
- B1, `play_pattern`: 487 posesiones traen más de un `play_pattern_id` entre sus eventos no administrativos; se toma el del primero.
- C5, rango: la ficha dice −2 a +2, pero en 3918375 el rival (1300) tuvo 3 expulsiones en cancha (79:12, 94:37 en el periodo 3 y 121:11 en el periodo 4), así que `numerical_state` llega a +3. No se recorta; el script lo imprime como aviso.
- Validaciones informativas: el xG medio por distancia (E2) y la correlación de Spearman de C4 se imprimen pero no detienen la corrida, igual que los avisos de C1 y de los minutos por partido.
- E2: la ficha pide espejar los eventos del rival, pero `x` e `y` ya vienen en la dirección de ataque del equipo del evento (contrato v0.2). Espejarlos mediría hacia su propia portería, así que no se espejan. Los penales del rival dan 12 yardas, igual que los del EQ, y eso lo confirma.

## Fuera de alcance

- Métricas por posesión o por partido de cada quien (inicio, presión, contragolpe, secuencia ofensiva) — se agregan al integrar; aquí solo va el contexto y la posesión válida de B1.
- Fundir filas en `contexto_posesiones` — la llave sigue siendo la de StatsBomb; la fusión es solo el id `posesion_fundida_id`.
- Métricas de ataque, defensa y jugadores — son `03_ataque.py`, `03_defensa.py` y `03_jugadores.py`.
- Contexto del grupo de contraste (Ortiz y Solari) — el script es solo para el EQ 1229, igual que `data/interim/`.
- Columnas en el contrato de datos — `data/processed/` no tiene contrato todavía; los nombres quedaron aprobados en `propuesta_nombres_fase3.md`.
- Corregir el reloj por pausas largas (3972074) — se reporta y no se toca.
- Cambiar `02_limpieza.py`, `contrato.py`, `gen_contrato.py` o `docs/contrato/`.

## Plan de pruebas

No hay tests ni linter: se verifica corriendo `python scripts/03_contexto.py` y leyendo la salida.

- AC1 → manual: la salida imprime el mínimo de `timestamp` por periodo y el conteo por bin.
- AC2 → manual: la salida dice qué criterio de autogol cuadró los 91 partidos.
- AC3 → manual: la salida imprime 91 / 66 / 25 y los huecos de jornada por torneo.
- AC4 → manual: la salida imprime dónde caen los play-in, el top y el fondo por torneo y la correlación de Spearman.
- AC5 → manual: la salida imprime las expulsiones totales y en cancha, los cruces con `posiciones` y `team_match_stats`, las 2 de banca y el rango.
- AC6 → manual: la salida imprime el rango de x e y y el acuerdo con `location_bucket` en juego abierto y en total.
- AC7 → manual: la salida imprime los penales y el xG por distancia.
- AC8 → manual: correr con `--sin-escribir` y confirmar que `data/processed/` no cambia; leer los parquet escritos y comprobar llaves únicas, 317,849 filas y una fila por (`team_id`, `torneo`). Forzar fallas duras cargando el módulo con `leer` envuelto (un partido extra, un `timestamp` de periodo 2 que no empieza en 0) y con el CSV bloqueado desde otro proceso, y comprobar código 1 y archivos sin cambios.
- AC9 → manual: la salida imprime la razón contra `team_match_possessions`, las fusiones, los pares excluidos por reanudación y las administrativas; `control_posesiones_fundidas.csv` existe aunque no haya fusiones.
- AC10 → manual: la salida confirma goles y expulsiones e imprime minutos contra duración.
- AC11 → manual: cargar el módulo con `leer` envuelto para agregar a `eventos` un partido que no está en `partidos` y comprobar código 1 sin escribir.

## Resultado de la primera corrida (19-oct)

Código 0, unos 2 s. Cumple AC1 a AC8: 317,849 eventos con llave única y 21 columnas; `rival_strength` con 136 filas (17 equipos por 8 torneos, 16 partidos regulares cada uno). Autogol con el criterio directo. Spearman entre `rival_strength` y `rival_ppg`: 0.612. Acuerdo de `third` con `location_bucket`: 99.77%. Expulsiones: 27 en eventos y en `team_match_stats`, 25 en cancha y en `posiciones`. `numerical_state` va de −1 a +3. Los 30 penales (20 del EQ, 10 del rival, 10 de ellos en la tanda) dan 12 yardas y el xG medio baja de 0.467 (0 a 6 yardas) a 0.014 (más de 30).

## Resultado de la corrida del paso 4 (19-oct)

Código 0, unos 4 s. `contexto_eventos` y `rival_strength` no cambian. `contexto_posesiones`: 19,053 posesiones con llave única; 0 fusiones (los 1,400 pares candidatos empiezan con reanudación); 6,510 válidas (3,402 del EQ); 7,381 de balón parado en False; 269 administrativas. Antes del ajuste de reanudaciones había 1,400 fusiones y 6,751 válidas; la diferencia son las 241 filas de juego abierto que solo eran válidas por los pases de la reanudación siguiente. `contexto_partidos`: 91 filas; goles 161 a favor y 75 en contra, que cuadran con `partidos`; expulsiones en cancha 6 del EQ y 19 del rival, que cuadran con `posiciones`; la suma de minutos queda a menos de 0.05 min de la duración por `timestamp`, de 95.0 a 135.9 min por partido (el máximo es el de tiempo extra y 3972074 incluye la pausa de 23 min). Las tres salidas por partido o evento traen exactamente los 91 `match_id`; con un partido extra forzado en `eventos` o en `partidos` la corrida sale con código 1 y no escribe.

Correcciones de la revisión doble: con los penales fuera de la validez, 19 posesiones dejan de ser válidas y quedan 6,491 (3,388 del EQ). `contexto_eventos`, `rival_strength` y `contexto_partidos` no cambian (`assert_frame_equal` contra la copia previa) y en `contexto_posesiones` solo cambia `is_valid_possession` en esas 19 filas. Fallas forzadas, todas con código 1: partido extra en `eventos` y `timestamp` de periodo 2 en 00:00:01 en 3889637 no escriben nada; el CSV abierto en modo exclusivo desde otro proceso se detecta antes de reemplazar y no se escribe nada; abierto sin permiso de borrar, el reemplazo queda a medias y el mensaje lista los 4 parquet reemplazados y la carpeta temporal.

`team_match_possessions` no es un conteo por equipo: vale lo mismo (±1) para los dos equipos del partido. Las posesiones de un equipo antes de fundir son 0.573 de ese valor en promedio (de 0.447 a 0.748); las del partido, sumando los dos equipos, son 1.145 veces el valor (igual antes y después de fundir, porque no hay fusiones).

## Alternativas descartadas

- Copiar las columnas de contexto dentro de `eventos` — duplicaría 197 columnas y rompería la regla de no editar las tablas del contrato; se une por (`match_id`, `index`).
- Contar como expulsión cada tramo de `posiciones` con `end_reason` de tarjeta — no da el momento exacto en eventos y mezcla dos fuentes; se usa el evento de la tarjeta y `posiciones` solo para saber si el jugador estaba en la cancha.
- Contar las 27 expulsiones de eventos — 2 son de jugadores fuera de la cancha y no cambian el número de jugadores.
- Recortar `numerical_state` a ±2 — escondería el caso real de 3918375.
- Etiquetas propias para `third` (defensivo, medio, ofensivo) — se usan las de `location_bucket` para compararlas directamente.
