# Contrato de datos v0.2

Estado: v0.2, 2026-10-18. Dueño: Yordi.

## Para qué sirve

Es el acuerdo entre quien limpia los datos y quien los usa. Lee (métricas) y Pablo (gráficas) programan contra los nombres, tipos y llaves de las tablas limpias que producen `scripts/02_limpieza.py` y `scripts/02_auxiliares.py`. Los tipos salen de los parquet completos de los 91 partidos de Jardine con América. Este contrato no trae el % de nulos por columna; ese reporte lo entrega Lee.

La versión ejecutable es `contrato_datos.csv`, que lee `scripts/contrato.py` para crear DataFrames vacíos y validar las tablas. Además de `tabla`, `columna`, `tipo`, `origen` y `regla`, trae `relleno` (con qué se llenan los ausentes; hoy solo False en las banderas) y `puede_faltar`. `puede_faltar` es True cuando la columna no existe en el parquet crudo de ninguno de los 91 partidos; la limpieza la crea igual, con su `relleno` o nula.

## Cómo se genera

Todo lo de esta carpeta sale de `python scripts/gen_contrato.py`; no se edita a mano. Para cambiar una regla o una decisión se modifica el script y se vuelve a correr. `cambios.md` sale de `HISTORIAL`, la lista de versiones ya publicadas que vive en el script. Si `VERSION` ya está en `HISTORIAL`, el script corre sin argumento y, antes de escribir, compara lo generado contra el `contrato_datos.csv` que ya está en esta carpeta: si cambian tablas, columnas o tipos, se detiene y pide subir `VERSION` y `FECHA`. Los cambios solo de texto de las reglas pasan.

## Cómo se publica una versión nueva

1. Antes de correr nada, copia el csv publicado fuera de la carpeta, por ejemplo con `git show HEAD:docs/contrato/contrato_datos.csv > %TEMP%\contrato_anterior.csv`. La corrida sobrescribe `docs/contrato/contrato_datos.csv`, y el script se detiene si le pasas ese archivo con una versión nueva.
2. Sube `VERSION` y `FECHA` en `scripts/gen_contrato.py`. Si el contrato anterior que le pasas ya es `VERSION`, el script se detiene y pide subirlas.
3. Corre `python scripts/gen_contrato.py <la copia del csv publicado>`. La versión anterior se lee del `README.md` que está junto al csv; si no está, pásala con `--version-anterior`.
4. Como la versión nueva todavía no está en `HISTORIAL`, el script calcula su entrada (cambios de tipo, columnas nuevas o quitadas y las notas de `NOTAS_VERSION`) y la imprime como literal de Python.
5. Al publicar, pega esa entrada al principio de `HISTORIAL` y vacía `NOTAS_VERSION`. Desde ahí la entrada queda fija y no depende del csv anterior.

## Fuentes

`data/diccionario.json`, `data/raw/parquet/*.parquet` (salida de `scripts/01_descarga.py`) y `Plan_de_trabajo_Kpumas.md`, secciones 7.1 a 7.3.

## Convenciones

- Nombres en snake_case con `_` en lugar de `.` (`pass.length` -> `pass_length`, `shot.statsbomb_xg` -> `shot_statsbomb_xg`). La columna **origen** conserva la ruta con punto del diccionario para trazabilidad.
- En `partidos` se quita el prefijo repetido (`home_team.home_team_id` -> `home_team_id`); `50_50.*` pasa a `fifty_fifty_*` (un nombre no puede empezar con dígito).
- Tipos pandas: `Int64` (entero con nulos), `float64`, `boolean` (con nulos), `string`, `category`, `datetime64[us]`. Ningún id queda como float. Las fechas van sin zona horaria en `datetime64[us]`, la resolución que da pandas 3 al convertir texto, y `validar()` exige ese dtype exacto.
- Llaves: eventos (`match_id`, `index`); frames_360 (`match_id`, `event_uuid`, `jugador_idx`); frames_360_evento (`match_id`, `event_uuid`); partidos `match_id`. `id` y `event_uuid` son UUID de texto y solo sirven como llave.
- Unidad: yardas, cancha 120 x 80, ataque hacia x = 120. Las coordenadas vienen en la perspectiva del equipo que ejecuta el evento (también en 360).
- **Perspectiva del equipo analizado.** `x`, `y`, `end_x`, `end_y` están en la perspectiva de `team_id` (el equipo del evento). Para comparar al equipo analizado contra sus rivales en una misma cancha, usar `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`: igual que `x`/`y` si `es_equipo_analizado`; `120 - x` y `80 - y` si el evento es del rival.
- **Orden.** Ordenar siempre por (`match_id`, `index`). `match_second` no es único entre periodos: sirve para agrupar por tiempo dentro de (`match_id`, `period`).
- **Texto.** Todo texto (string y category) pasa por strip. En una columna de texto, "Sin cambios." quiere decir "solo strip".
- **Categorías.** Las categorías de una columna category salen de los valores de cada corrida, así que dos corridas (o dos tablas) pueden traer categorías distintas. Antes de concatenarlas hay que alinearlas con `pandas.api.types.union_categoricals` o pasar la columna a string.
- Nulo legítimo no se imputa; las banderas que solo aparecen si son verdaderas se rellenan con False (plan 7.3).
- `fase` vale `regular` (competition_stage.id en {1, 42, 44}) o `liguilla`; `es_play_in` marca el stage id 2 y `es_final` los dos partidos de la final. `torneo` sale de la fecha: julio a diciembre = Apertura, enero a junio = Clausura.
- Los parquet limpios se guardan en `data/interim/` con el nombre de la tabla (`data/interim/eventos.parquet`); la muestra de un partido en `data/interim/muestra/`.
- Las columnas documentadas que faltan en un partido se crean igual (False o nulo) para que el esquema no cambie entre corridas. `puede_faltar = True` marca solo las que no existen en el parquet crudo de ninguno de los 91 partidos, y su regla lo dice.
- **Alcance (C18).** Los partidos que no pasan los filtros de calidad (plan 7.1) los anota la limpieza en `data/interim/partidos_excluidos.csv`, con las columnas `match_id`, `campo` y `valor` y una fila por partido y por filtro que falla. Los valores posibles de `campo` son los cuatro filtros: `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py`, salvo `team_match_stats_liga`, traen solo los `match_id` que quedan en `partidos`; las 4 de `02_auxiliares.py` deben salir de `data/interim/eventos.parquet`, y no de los crudos, para cumplirlo.

### Salidas de control de `02_limpieza.py`

Además de los parquet, `02_limpieza.py` escribe tres CSV de control en la misma carpeta (`data/interim/`, o `data/interim/muestra/` con `--solo-partido`):

- `partidos_excluidos.csv`: `match_id`, `campo` y `valor`, con una fila por partido y por filtro de 7.1 que falla. Los partidos que no pasan esos filtros se excluyen de todas las tablas salvo `team_match_stats_liga`, se reportan aquí y no detienen la corrida.
- `calidad_limpieza.csv`: una fila por tabla con `tabla`, `filas_crudas`, `filas`, `filas_descartadas`, `columnas`, `llave`, `llaves_duplicadas`, `padre`, `huerfanos`, `huerfanos_por_padre` y `columnas_creadas_vacias`. En `partidos`, `filas_crudas` cuenta todas las filas leídas; en las tablas hijas cuenta solo las filas de los partidos que pasaron 7.1 y, en las que salen de explotar una lista, las filas ya explotadas. Las exclusiones de C18 (C18) se ven solo en `partidos`, así que `filas_descartadas` en las hijas es 0 por construcción. `padre` y `huerfanos_por_padre` listan las tablas padre en el mismo orden; `huerfanos` cuenta las filas que faltan en al menos uno de sus padres.
- `cobertura_360_por_partido.csv`: una fila por partido con `match_id`, `eventos`, `eventos_con_frame`, `pct_con_frame`, `eventos_tacticos`, `pct_tacticos_con_frame`, `eventos_equipo_analizado`, `pct_equipo_con_frame`, `frames_sin_conteo` y `frames_umbral_provisional`. Los tácticos son los eventos con `es_administrativo = False`, y los del equipo analizado, los que tienen `es_equipo_analizado = True`. `frames_umbral_provisional` cuenta los frames que cumplen la regla provisional de Lee (actor visible y al menos 10 jugadores visibles, C19); es solo informativo y ninguna tabla se filtra con él.

La corrida se detiene con código 1, sin escribir nada, cuando:

- alguna tabla no pasa `contrato.validar()`;
- a un partido le falta cobertura: debe tener filas en `eventos`, `frames_360`, `frames_360_evento` y `player_match_stats`; `home_team_id`, `away_team_id` y `equipo_id` no nulos; `equipo_id` igual al local o al visitante; exactamente el local y el visitante en `alineaciones` y `team_match_stats`; y al menos un evento con `es_equipo_analizado` no nulo. Un hueco detiene toda la corrida y no excluye el partido;
- alguna tabla tiene llaves duplicadas o huérfanos;
- ningún partido pasa los filtros de calidad;
- falta una columna cruda que el contrato no marca con `puede_faltar`;
- una conversión de tipo deja nulo un valor que no lo era;
- un evento tiene más de un destino no nulo entre `pass`, `carry`, `shot` y `goalkeeper`;
- llega un valor de tipo inesperado: un booleano donde va un número, una fecha numérica o con zona horaria, o un JSON inválido o de otro tipo;
- al unir con 360 hay eventos repetidos en (`match_id`, `id`);
- `match_id` aparece repetido en `partidos`;
- falla la preparación o la escritura de la carpeta temporal;
- algún archivo de destino está bloqueado (por ejemplo, abierto en Excel).

Si el reemplazo falla a medias después de esa revisión, también sale con 1, y el mensaje dice qué archivos ya se reemplazaron y en qué carpeta temporal quedaron los que faltan. Con `--solo-partido`, si el partido pedido no está en `partidos.parquet` o no pasa los filtros, solo imprime el motivo y sale con código 2, sin escribir nada.

## Resumen de tablas

Las filas se cuentan sobre los parquet crudos. Cada tabla tiene su propio archivo con el resumen y todas sus columnas.

| tabla | columnas | filas | produce | grano |
|---|---|---|---|---|
| [`partidos`](partidos.md) | 60 | 91 | 02_limpieza.py (Yordi) | Un partido por fila (91 filas en el crudo; menos si C18 excluye partidos). Se descartan attendance, home_team_group y away_team_group (0% de datos) y las listas de managers (se resumen en entrenador_*). |
| [`eventos`](eventos.md) | 197 | 317,849 | 02_limpieza.py (Yordi) | Una fila por evento. Llave (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`). |
| [`frames_360`](frames_360.md) | 9 | 3,848,340 | 02_limpieza.py (Yordi) | Una fila por jugador visible en cada frame. Solo incluye a quienes ve la cámara. |
| [`frames_360_evento`](frames_360_evento.md) | 12 | 283,700 | 02_limpieza.py (Yordi) | Una fila por evento con frame (área visible y métricas 360 a nivel evento). |
| [`alineaciones`](alineaciones.md) | 21 | 3,820 | 02_limpieza.py (Yordi) | Una fila por (partido, equipo, jugador) de la cédula (titulares y banca). |
| [`posiciones`](posiciones.md) | 14 | 4,150 | 02_limpieza.py (Yordi), con acuerdo de Lee | Una fila por tramo de posición de cada jugador (explode de `lineup[].positions`). |
| [`team_match_stats`](team_match_stats.md) | 206 | 182 | 02_limpieza.py (Yordi) | Una fila por (partido, equipo). Se descarta account_id. |
| [`player_match_stats`](player_match_stats.md) | 177 | 2,817 | 02_limpieza.py (Yordi) | Una fila por (partido, jugador). Se descarta account_id. |
| [`team_match_stats_liga`](team_match_stats_liga.md) | 212 | 2,728 | 02_limpieza.py (Yordi) | Línea base: una fila por (partido, equipo) de los 1,364 partidos de las 4 temporadas (available, Complete, Normal). Sirve para comparar al equipo contra la liga. |
| [`related_events`](related_events.md) | 5 | 606,902 | 02_auxiliares.py (Lee) | Una fila por (evento, evento relacionado). |
| [`tactics_lineup`](tactics_lineup.md) | 9 | 5,714 | 02_auxiliares.py (Lee) | Una fila por jugador en cada evento Starting XI / Tactical Shift. |
| [`defensive_responsibility`](defensive_responsibility.md) | 6 | 1,794,080 | 02_auxiliares.py (Lee) | Una fila por (evento, jugador). `probability_sum` y `categories` quedan en `eventos`. |
| [`shot_freeze_frame`](shot_freeze_frame.md) | 10 | 30,057 | 02_auxiliares.py (Lee) | Una fila por jugador en el freeze frame de cada tiro. Llave (`match_id`, `index`, `jugador_idx`). |

## Decisiones

Las resueltas llevan `RESUELTA (Yordi)`, `RESUELTA (Lee)` o `RESUELTA (Pablo)`. Las demás tienen un default vigente, un responsable y una fecha límite.

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (Yordi) | resuelta |
| C2 | Destino unificado `end_x`, `end_y`, `end_z` | Un solo juego para pass, carry, shot y goalkeeper, interpretado con `type_name` | RESUELTA (Yordi) | resuelta |
| C3 | 360 en dos tablas | `frames_360` (jugador visible) y `frames_360_evento` (área y conteos) | RESUELTA (Yordi) | resuelta |
| C4 | Tabla extra `shot_freeze_frame` | Se incluye; la produce `02_auxiliares.py` | Lee | vigente por defecto; confirmar antes del lun 19 |
| C5 | Eventos administrativos | Se conservan en `eventos` con `es_administrativo = True` | RESUELTA (Yordi) | resuelta |
| C6 | `match_clock` y `minute_bin` | No van en la tabla limpia. Se calculan en la fase 3 (`scripts/03_contexto.py`, Yordi) con la ficha C1 (`match_clock` y `minute_bin`) de la especificación de métricas de Lee: `match_clock = match_second / 60` y `minute_bin` en ventanas de 15 minutos por periodo | RESUELTA (Lee) | resuelta |
| C7 | `defensive_responsibility.categories` | Texto JSON en `eventos`; no se explota | Lee | vigente por defecto; confirmar antes del lun 19 |
| C8 | Tarjetas y formaciones de lineups | Se cierra sin tablas nuevas: las formaciones salen de `tactics_formation` (eventos Starting XI y Tactical Shift) y las tarjetas de `foul_committed_card_*` y `bad_behaviour_card_*`, que ya están en `eventos` | RESUELTA (Yordi) | resuelta |
| C9 | `posiciones.to` nulo (47.6%) | El nulo significa que el jugador siguió hasta el silbatazo final; no se imputa un minuto. Verificado con los 91 partidos: 1,976 de 4,150 tramos tienen `to` nulo, todos con `end_reason` = Final Whistle y último tramo del jugador | RESUELTA (Yordi) | resuelta |
| C10 | Columnas que no aparecen siempre | Las banderas ausentes se crean con False y las stats ausentes, nulas. Las que no salen en ninguno de los 91 partidos se quedan en False para que el esquema no cambie entre corridas; hoy son 8 en `eventos`: `goalkeeper_lost_out`, `goalkeeper_success_out`, `half_end_early_video_end`, `half_end_match_suspended`, `half_start_late_video_start`, `pass_backheel`, `offside_advantage` y `shot_kick_off` | RESUELTA (Yordi) | resuelta |
| C11 | Banderas con nulo legítimo | Solo `is_transition` e `is_controlled_possession` conservan el nulo; el resto va a False. La limpieza ya rellena `out` y `off_camera` con False; Lee confirma que así debe ser | Lee | vigente por defecto; confirmar antes del lun 19 |
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (Yordi) | resuelta |
| C13 | Penales (periodo 5) | Se conservan con `period = 5`. Todas las fichas de la especificación de Lee los excluyen (exclusión global de su sección 1) | RESUELTA (Lee) | resuelta |
| C14 | Eventos sin ubicación (0.9%) | `x` e `y` nulos; se excluyen de los mapas, sin imputar | RESUELTA (Pablo) | resuelta |
| C15 | Perspectiva en `frames_360` | Solo `es_equipo_analizado`; `x` e `y` quedan en la perspectiva del equipo del evento (sin `x_eq`/`y_eq`) | RESUELTA (Pablo) | resuelta |
| C16 | Dónde viven los parquet limpios | `data/interim/` (limpias) y `data/processed/` (agregadas del lunes) | RESUELTA (Yordi) | resuelta |
| C17 | Quién produce `posiciones` | `02_limpieza.py` (Yordi), con acuerdo de Lee | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (Yordi) | resuelta |
| C19 | Umbral de jugadores visibles del 360 | No se fija en la tabla limpia: `frames_360_evento` entrega `n_visibles_equipo` y `n_visibles_rival`, y cada métrica aplica su propio filtro. Lee define el umbral en la especificación de métricas; su valor provisional es actor visible y al menos 10 jugadores visibles, por calibrar con la distribución real de `visible_player_counts`. Esta decisión reemplaza el punto 7 de la sección 11 del plan | RESUELTA (Yordi) | resuelta |
| C20 | Listas de managers | `managers` no se explota: queda resumido en `entrenador_id`, `entrenador_rival`, `entrenador_rival_id`, `rival_coentrenador` y `coentrenador` de `partidos` | Lee | vigente por defecto; confirmar antes del lun 19 |
| C21 | Conteos 360 sin `visible_player_counts` | `n_visibles_equipo` y `n_visibles_rival` quedan nulos cuando `visible_player_counts` viene vacío (2,253 frames, 0.8%). El nulo quiere decir que no hay conteo y no equivale a cero | RESUELTA (Yordi) | resuelta |

## Historial

Las versiones anteriores y lo que cambió en cada una están en [`cambios.md`](cambios.md).
