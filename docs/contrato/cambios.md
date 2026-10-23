[Volver al índice](README.md)

# Cambios del contrato

## v0.2 (2026-10-18), cambios desde v0.1

- Respecto a v0.1: 23 cambios de tipo (tabla abajo), 0 columnas nuevas y 0 columnas quitadas. Las 13 tablas suman 938 columnas.
- C12: 18 columnas de nombre de equipos y catálogos (los `*_name` y `partidos.rival_nombre`) pasan de string a category. Los nombres de personas siguen como string.
- 5 columnas de fecha pasan de datetime64[ns] a datetime64[us]: `partidos.match_date`, `partidos.last_updated`, `partidos.last_updated_360`, `alineaciones.birth_date` y `team_match_stats_liga.match_date`.
- datetime64[us] es la resolución que da pandas 3 al convertir texto y la que ya produce la limpieza. `validar()` ahora exige el dtype exacto y rechaza otra resolución y las fechas con zona horaria.
- El csv agrega las columnas `relleno` y `puede_faltar`. `relleno` dice con qué se llenan los ausentes: hoy es False en 64 banderas, justo las que tienen una regla que empieza con "Ausente = False". `puede_faltar` es True en 8 columnas, las banderas de C10, que no existen en el parquet crudo de ninguno de los 91 partidos. Estas dos columnas permiten dejar de interpretar el texto de la regla; la limpieza lo adopta en su propio PR.
- `scripts/contrato.py` carga las dos columnas nuevas, rechaza un csv con tipos fuera de `TIPOS_VALIDOS` y expone `ADMINISTRATIVOS`, la lista de los tipos de evento administrativos. `cargar()` solo acepta True o False en `puede_faltar` (0 y 1 dan error), y en `relleno` solo vacío o False, únicamente en columnas boolean. Por eso ya no lee un csv de la v0.1, que no trae `relleno` ni `puede_faltar`.
- `validar()` también marca como falla una columna con `relleno` que trae nulos y una category cuyas categorías no son texto.
- `ADMINISTRATIVOS` agrega Camera On, como en la especificación de Lee; tiene 0 filas en los 91 partidos.
- La regla de `posiciones.to` ahora es definitiva: el nulo significa que el jugador siguió hasta el silbatazo final (1,976 de 4,150 tramos, 47.6%). Sustituye al "~55%, verificar" de la v0.1.
- El diccionario dice que `posiciones.from` y `posiciones.to` usan el reloj del periodo, pero los datos traen el reloj corrido del partido: con `from_period` = 2 el mínimo de `from` es 00:45:00.000 y el máximo de `to` es 02:01:11.394. `to − from` es la duración del tramo solo si `from_period` = `to_period`; si cruza de periodo, la duración se suma por periodo (ver la regla de `posiciones.to`). El generador lo comprueba en cada corrida.
- El contrato pasa de un solo md a la carpeta `docs/contrato/`: README, un md por tabla, `cambios.md` y `contrato_datos.csv`. `scripts/contrato.py` lee el csv desde ahí.
- Resueltas el 18 de octubre: C5 (los eventos administrativos se conservan), C8 (se cierra sin tablas nuevas), C9 (nulo en `to`), y C10, C12, C16 con el default vigente.
- Resueltas por Lee en su especificación de métricas: C6 (`match_clock` y `minute_bin` no van en la tabla limpia; se calculan en la fase 3, `scripts/03_contexto.py`) y C13 (los penales se conservan con `period = 5` y todas las fichas los excluyen).
- Resueltas por Pablo: C14 (los eventos con `x`/`y` nulos no entran a las gráficas) y C15 (en `frames_360` usa `es_equipo_analizado` y no toma los nulos).
- Decisiones nuevas: C17 (`posiciones` la produce `02_limpieza.py`), C18 (los partidos que no pasan los filtros del plan 7.1 se excluyen de todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga`, y se reportan), C19 (el umbral de jugadores visibles lo aplica cada métrica y lo define Lee; valor provisional: actor visible y al menos 10 jugadores visibles), C20 (`managers` se queda resumido en `partidos`; abierta, la confirma Lee) y C21 (los conteos 360 vacíos quedan nulos; resuelta).
- C10 se amplía: las 8 banderas que no salen en ningún partido se conservan en False. C11 anota que `out` y `off_camera` ya se rellenan con False. C19 reemplaza el punto 7 de la sección 11 del plan.
- Siguen abiertas con su default: C4, C7, C11 y C20 (Lee), vigente por defecto; confirmar antes del lun 19. Las decisiones resueltas pasan de 3 a 17.
- Correcciones de texto: el orden es siempre (`match_id`, `index`) y `match_second` sirve para agrupar dentro de (`match_id`, `period`); `timestamp` queda verificado; "Escala 0 a 1" solo aparece en las proporciones conocidas por nombre cuyo rango observado cabe en [0, 1], y `directness` ya no la lleva; `player_match_long_balls` dice pases largos intentados; los % de nulos de `alineaciones` se recalculan y se documenta la banca que no entró; `partidos.md` explica `partidos_excluidos.csv` y los errores de video; la línea base aclara qué filtros no se le aplican; se quita la etiqueta "D1:" del grano de `partidos`.
- Convenciones nuevas en el README: todo texto pasa por strip, las categorías salen de cada corrida (hay que alinearlas antes de concatenar), el csv tiene `relleno` y `puede_faltar`, y el alcance de C18 lista los cuatro filtros. `eventos` aclara que también trae `es_play_in` y `es_final` desde `partidos`.
- `cambios.md` sale de una lista fija de versiones publicadas en el script, así que regenerar ya no borra la historia. El README explica cómo se publica una versión nueva.
- Se documentan las salidas de control de `02_limpieza.py` y se precisan las reglas de `pass_completed`, `receipt_ok` y `n_visibles_*`.

Tipos que cambian, calculados contra el `contrato_datos.csv` de v0.1:

| tabla | columna | v0.1 | v0.2 |
|---|---|---|---|
| `partidos` | `match_date` | datetime64[ns] | datetime64[us] |
| `partidos` | `last_updated` | datetime64[ns] | datetime64[us] |
| `partidos` | `last_updated_360` | datetime64[ns] | datetime64[us] |
| `partidos` | `home_team_name` | string | category |
| `partidos` | `home_team_country_name` | string | category |
| `partidos` | `away_team_name` | string | category |
| `partidos` | `away_team_country_name` | string | category |
| `partidos` | `stadium_name` | string | category |
| `partidos` | `stadium_country_name` | string | category |
| `partidos` | `referee_country_name` | string | category |
| `partidos` | `rival_nombre` | string | category |
| `alineaciones` | `team_name` | string | category |
| `alineaciones` | `birth_date` | datetime64[ns] | datetime64[us] |
| `team_match_stats` | `team_name` | string | category |
| `team_match_stats` | `opposition_name` | string | category |
| `team_match_stats` | `competition_name` | string | category |
| `team_match_stats` | `season_name` | string | category |
| `player_match_stats` | `team_name` | string | category |
| `team_match_stats_liga` | `team_name` | string | category |
| `team_match_stats_liga` | `opposition_name` | string | category |
| `team_match_stats_liga` | `competition_name` | string | category |
| `team_match_stats_liga` | `season_name` | string | category |
| `team_match_stats_liga` | `match_date` | datetime64[ns] | datetime64[us] |

## v0.1 (2026-10-17), cambios desde v0

- `fase` pasa de `regular`/`final` a `regular`/`liguilla`; nueva columna `es_play_in` (stage id 2).
- `partidos` agrega `entrenador_id`, `equipo_id`, `entrenador_rival_id` y `rival_coentrenador`; se quita la decisión abierta sobre ellos.
- Los tipos y los % de nulos se recalcularon con los parquet completos (91 partidos, 317,849 eventos) en lugar de la muestra de 3 a 5 partidos.
- `eventos` tiene 180 columnas de origen con los 91 partidos (170 en la muestra de 5). De las 17 banderas documentadas que no salieron en la muestra, 9 sí aparecen con los datos completos y 8 siguen sin aparecer (se crean con False).
- Las 6 columnas de `team_match_stats` que la API no devolvía en la muestra (tiros libres directos) sí aparecen con los datos completos.
- Nueva tabla `team_match_stats_liga` (línea base de la liga).
- Perspectiva del equipo analizado: `es_equipo_analizado`, `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq` en `eventos`; `es_equipo_analizado` en `frames_360`.
- `match_second` aclara que no es único entre periodos; se ordena por (`period`, `match_second`).
- Columna 'produce' en el resumen: `02_limpieza.py` (Yordi) y `02_auxiliares.py` (Lee).
- Las decisiones abiertas pasan a tabla con default, responsable y fecha límite; 3 quedan resueltas.
- Se corrigen descripciones cortadas y vacías.

Tipos que cambiaron al recalcular con los datos completos:

| tabla | columna | v0 | v0.1 |
|---|---|---|---|
| `team_match_stats` | `team_match_direct_free_kick_xg` | Int64 | float64 |
| `team_match_stats` | `team_match_direct_free_kick_xg_conceded` | Int64 | float64 |

Columnas nuevas respecto a v0 (por tabla):

- `partidos` (3): `es_play_in`, `entrenador_rival_id`, `rival_coentrenador`
- `eventos` (6): `es_play_in`, `es_equipo_analizado`, `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`
- `frames_360` (1): `es_equipo_analizado`

## v0 (2026-10-17)

- Primera versión, calculada con la muestra de 3 a 5 partidos.
