# Contrato de datos v0.1

Estado: v0.1, 2026-10-17. Dueño: Yordi. Es el contrato para que Lee (métricas) y Pablo (gráficas) programen contra los nombres y tipos de las tablas limpias que produce `scripts/02_limpieza.py`. Los tipos y % de nulos salen de los parquet completos de los 91 partidos de Jardine. La versión ejecutable está en `docs/contrato_datos.csv` y `scripts/contrato.py`.

Este archivo se genera con `python scripts/gen_contrato.py`; no se edita a mano.

Fuentes: `data/diccionario.json`, `data/raw/parquet/*.parquet` (salida de `scripts/01_descarga.py`) y `Plan_de_trabajo_Kpumas.md` secciones 7.1 a 7.3.

## Convenciones

- Nombres en snake_case con `_` en lugar de `.` (`pass.length` -> `pass_length`, `shot.statsbomb_xg` -> `shot_statsbomb_xg`). La columna **origen** conserva la ruta con punto del diccionario para trazabilidad.
- En `partidos` se quita el prefijo repetido (`home_team.home_team_id` -> `home_team_id`); `50_50.*` pasa a `fifty_fifty_*` (un nombre no puede empezar con dígito).
- Tipos pandas: `Int64` (entero con nulos), `float64`, `boolean` (con nulos), `string`, `category`, `datetime64[ns]`. Ningún id queda como float.
- Llaves: eventos (`match_id`, `index`); frames_360 (`match_id`, `event_uuid`, `jugador_idx`); frames_360_evento (`match_id`, `event_uuid`); partidos `match_id`. `id` y `event_uuid` son UUID de texto y solo sirven como llave.
- Unidad: yardas, cancha 120 x 80, ataque hacia x = 120. Las coordenadas vienen en la perspectiva del equipo que ejecuta el evento (también en 360).
- **Perspectiva del equipo analizado.** `x`, `y`, `end_x`, `end_y` están en la perspectiva de `team_id` (el equipo del evento). Para comparar al equipo analizado contra sus rivales en una misma cancha, usar `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`: igual que `x`/`y` si `es_equipo_analizado`; `120 - x` y `80 - y` si el evento es del rival.
- **Orden.** `match_second` no es único entre periodos; ordenar siempre por (`match_id`, `index`) o por (`period`, `match_second`).
- Nulo legítimo no se imputa; las banderas que solo aparecen si son verdaderas se rellenan con False (plan 7.3).
- `fase` vale `regular` (competition_stage.id en {1, 42, 44}) o `liguilla`; `es_play_in` marca el stage id 2 y `es_final` los dos partidos de la final.
- Los parquet limpios se guardan en `data/interim/` con el nombre de la tabla (`data/interim/eventos.parquet`); la muestra de un partido en `data/interim/muestra/`.
- Las columnas que no aparecen en algún partido se crean igual (False o nulo) para que el esquema no cambie entre corridas.

## Resumen de tablas

| tabla | columnas | produce | grano |
|---|---|---|---|
| `partidos` | 60 | 02_limpieza.py (Yordi) | D1: un partido por fila (91 filas). Se descartan attendance, home_team_group y away_team_group (0% de datos) y las listas de managers (se resumen en entrenador_*). |
| `eventos` | 197 | 02_limpieza.py (Yordi) | Una fila por evento. Llave (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`). |
| `frames_360` | 9 | 02_limpieza.py (Yordi) | Una fila por jugador visible en cada frame. Solo incluye a quienes ve la cámara. |
| `frames_360_evento` | 12 | 02_limpieza.py (Yordi) | Una fila por evento con frame (área visible y métricas 360 a nivel evento). |
| `alineaciones` | 21 | 02_limpieza.py (Yordi) | Una fila por (partido, equipo, jugador) de la cédula (titulares y banca). |
| `posiciones` | 14 | 02_limpieza.py (Yordi) | Una fila por tramo de posición de cada jugador (explode de `lineup[].positions`). |
| `team_match_stats` | 206 | 02_limpieza.py (Yordi) | Una fila por (partido, equipo). Se descarta account_id. |
| `player_match_stats` | 177 | 02_limpieza.py (Yordi) | Una fila por (partido, jugador). Se descarta account_id. |
| `team_match_stats_liga` | 212 | 02_limpieza.py (Yordi) | Línea base: una fila por (partido, equipo) de los 1,364 partidos de las 4 temporadas (available, Complete, Normal). Sirve para comparar al equipo contra la liga. |
| `related_events` | 5 | 02_auxiliares.py (Lee) | Una fila por (evento, evento relacionado). |
| `tactics_lineup` | 9 | 02_auxiliares.py (Lee) | Una fila por jugador en cada evento Starting XI / Tactical Shift. |
| `defensive_responsibility` | 6 | 02_auxiliares.py (Lee) | Una fila por (evento, jugador). `probability_sum` y `categories` quedan en `eventos`. |
| `shot_freeze_frame` | 10 | 02_auxiliares.py (Lee) | Adición propuesta (no estaba en la lista de tareas): el plan 7.3.7 pide explotar `shot.freeze_frame`. |

## `partidos` (60 columnas)

D1: un partido por fila (91 filas). Se descartan attendance, home_team_group y away_team_group (0% de datos) y las listas de managers (se resumen en entrenador_*).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Número único del partido. | `match_id` | Sin cambios. |
| `match_date` | datetime64[ns] | Fecha en que se juega el partido (formato año-mes-día). | `match_date` | Texto -> fecha. |
| `kick_off` | string | Hora del silbatazo inicial. | `kick_off` | Sin cambios. |
| `home_score` | Int64 | Goles finales del local. | `home_score` | Sin cambios. |
| `away_score` | Int64 | Goles finales del visitante. | `away_score` | Sin cambios. |
| `behind_closed_doors` | boolean | Verdadero si el partido fue a puerta cerrada, sin público. | `behind_closed_doors` | Sin cambios. |
| `neutral_ground` | boolean | Verdadero si se jugó en cancha neutral (ninguno de los dos es local de verdad). | `neutral_ground` | Sin cambios. |
| `collection_status` | category | Avance de la captura de datos de este partido: 'Complete' significa terminado; los demás indican proceso, validación o problema (ver valores). | `collection_status` | Sin cambios. |
| `play_status` | category | Si el partido se jugó o se jugará normal, o si fue pospuesto, cancelado, suspendido o dado por perdido. | `play_status` | Sin cambios. |
| `match_status` | category | Indica si ya hay datos de EVENTOS descargables. | `match_status` | Sin cambios. |
| `match_status_360` | category | Indica si hay datos 360 de ese partido. | `match_status_360` | Sin cambios. |
| `last_updated` | datetime64[ns] | Última vez que se modificó la información del partido. | `last_updated` | Texto ISO -> fecha y hora. |
| `last_updated_360` | datetime64[ns] | Última actualización de los datos 360. | `last_updated_360` | Texto ISO -> fecha y hora. |
| `match_week` | Int64 | Número de jornada/semana del torneo en que cae el partido. | `match_week` | Sin cambios. |
| `competition_id` | Int64 | Id de la competencia (ej. Liga MX). | `competition.competition_id` | Sin cambios. |
| `competition_country_name` | category | País de la competencia. | `competition.country_name` | Sin cambios. |
| `competition_name` | category | Nombre de la competencia. | `competition.competition_name` | Sin cambios. |
| `season_id` | Int64 | Id de la temporada. | `season.season_id` | Sin cambios. |
| `season_name` | category | Nombre de la temporada (ej. '2017/2018'). | `season.season_name` | Sin cambios. |
| `home_team_id` | Int64 | Id del equipo local. | `home_team.home_team_id` | Sin cambios. |
| `home_team_name` | string | Nombre del equipo local. | `home_team.home_team_name` | Sin cambios. |
| `home_team_gender` | category | Si el equipo local es varonil o femenil. | `home_team.home_team_gender` | Sin cambios. |
| `home_team_youth` | boolean | Verdadero si el equipo local es de categoría juvenil. | `home_team.home_team_youth` | Sin cambios. |
| `home_team_country_id` | Int64 | Id del país del equipo local. | `home_team.country.id` | Sin cambios. |
| `home_team_country_name` | string | Nombre del país del equipo local. | `home_team.country.name` | Sin cambios. |
| `away_team_id` | Int64 | Id del equipo visitante. | `away_team.away_team_id` | Sin cambios. |
| `away_team_name` | string | Nombre del equipo visitante. | `away_team.away_team_name` | Sin cambios. |
| `away_team_gender` | category | Si el equipo visitante es varonil o femenil. | `away_team.away_team_gender` | Sin cambios. |
| `away_team_youth` | boolean | Verdadero si el equipo visitante es de categoría juvenil. | `away_team.away_team_youth` | Sin cambios. |
| `away_team_country_id` | Int64 | Id del país del equipo visitante. | `away_team.country.id` | Sin cambios. |
| `away_team_country_name` | string | Nombre del país del equipo visitante. | `away_team.country.name` | Sin cambios. |
| `metadata_data_version` | category | Versión del método de captura de los eventos (ej. 1.1.0). | `metadata.data_version` | Sin cambios. |
| `metadata_shot_fidelity_version` | category | Versión de fidelidad con la que se capturaron los tiros. | `metadata.shot_fidelity_version` | Sin cambios. |
| `metadata_xy_fidelity_version` | category | Versión de fidelidad con la que se capturaron las coordenadas (sin documentar en el PDF). | `metadata.xy_fidelity_version` | Sin cambios. |
| `competition_stage_id` | Int64 | Id de la fase del torneo (1 = temporada regular; ver tabla de valores). | `competition_stage.id` | Sin cambios. |
| `competition_stage_name` | category | Nombre de la fase: temporada regular, liguilla (Play-offs), final, etc. | `competition_stage.name` | Sin cambios. |
| `stadium_id` | Int64 | Id del estadio. | `stadium.id` | Sin cambios. |
| `stadium_name` | string | Nombre del estadio (ej. Estadio Azteca). | `stadium.name` | Sin cambios. |
| `stadium_country_id` | Int64 | Id del país donde está el estadio. | `stadium.country.id` | Sin cambios. |
| `stadium_country_name` | string | País donde está el estadio. | `stadium.country.name` | Sin cambios. |
| `referee_id` | Int64 | Id del árbitro central. | `referee.id` | Sin cambios. |
| `referee_name` | string | Nombre del árbitro central. | `referee.name` | Sin cambios. |
| `referee_country_id` | Int64 | Id del país del árbitro. | `referee.country.id` | Sin cambios. |
| `referee_country_name` | string | País de origen del árbitro. | `referee.country.name` | Sin cambios. |
| `torneo` | category | Torneo derivado de la fecha (por ejemplo 'Apertura 2023'). | `partidos.parquet` (derivada) | Derivada de match_date: julio a diciembre = Apertura, enero a junio = Clausura. |
| `fase` | category | regular o liguilla. | `partidos.parquet` (derivada) | regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso. |
| `es_play_in` | boolean | El partido es de la ronda Play-In. | `partidos.parquet` (derivada) | competition_stage.id = 2. |
| `es_final` | boolean | Uno de los dos partidos de la final del torneo. | `partidos.parquet` (derivada) | Dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos (calculado sobre toda la liga). |
| `entrenador_id` | Int64 | manager_id del entrenador analizado. | `partidos.parquet` (derivada) | Agregada en la descarga con --manager-id. |
| `equipo_id` | Int64 | team_id del equipo analizado. | `partidos.parquet` (derivada) | Agregada en la descarga con --team-id. |
| `es_local` | boolean | El equipo analizado juega de local. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `rival_id` | Int64 | team_id del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `rival_nombre` | string | Nombre del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `entrenador_rival` | string | Entrenador(es) del rival, separados por ' / '. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `entrenador_rival_id` | Int64 | manager_id del primer entrenador del rival. | `partidos.parquet` (derivada) | Derivada en la descarga; Int64. |
| `rival_coentrenador` | boolean | El rival tuvo más de un manager en el partido. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `goles_favor` | Int64 | Goles del equipo analizado. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `goles_contra` | Int64 | Goles del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `resultado` | category | G, E o P para el equipo analizado. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `coentrenador` | boolean | El equipo analizado tuvo más de un manager en el partido. | `partidos.parquet` (derivada) | Derivada en la descarga. |

## `eventos` (197 columnas)

Una fila por evento. Llave (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido al que pertenece el evento. | match_id (agregado por la descarga) | Llave junto con `index`. |
| `id` | string | Identificador único del evento (como un folio). | `id` | UUID; solo llave (no modelar). strip. |
| `index` | Int64 | Número de orden del evento dentro del partido (1, 2, 3...). | `index` | Entero. |
| `period` | Int64 | Parte del partido: 1 primer tiempo, 2 segundo tiempo, 3 y 4 tiempos extra, 5 tanda de penales. | `period` | Entero. |
| `timestamp` | string | Momento del evento medido desde el inicio del periodo (hh:mm:ss.mmm). | `timestamp` | Texto HH:MM:SS.mmm desde el inicio del periodo; verificar con groupby('period'). |
| `minute` | Int64 | Minuto del reloj del partido. | `minute` | Entero. |
| `second` | Int64 | Segundo dentro del minuto (parte de segundos del timestamp). | `second` | Entero. |
| `possession` | Int64 | Número de la posesión dentro del partido (1, 2, 3...). | `possession` | Entero. |
| `obv_for_after` | float64 | Probabilidad de que tu equipo anote en la cadena de posesión después de este evento (OBV, On-Ball Value). | `obv_for_after` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_for_before` | float64 | Probabilidad de que tu equipo anote en la cadena de posesión antes de este evento (OBV). | `obv_for_before` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_for_net` | float64 | Cuánto cambió la probabilidad de anotar por este evento (después menos antes). | `obv_for_net` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_against_after` | float64 | Probabilidad de que tu equipo reciba gol en la siguiente cadena de posesión después de este evento (OBV). | `obv_against_after` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_against_before` | float64 | Probabilidad de que tu equipo reciba gol en la siguiente cadena de posesión antes de este evento (OBV). | `obv_against_before` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_against_net` | float64 | Cuánto cambió la probabilidad de recibir gol por este evento. | `obv_against_net` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `obv_total_net` | float64 | Valor total de la acción en diferencia de goles esperada: cambio en la probabilidad de anotar menos cambio en la probabilidad de recibir gol, en las siguientes 2 cadenas de posesión. | `obv_total_net` | Nulo legítimo (OBV solo en 10 tipos de evento); no imputar. |
| `attacking_direction` | category | Hacia qué lado de la cámara ataca el equipo (left_to_right o right_to_left). | `attacking_direction` | strip; nulo fuera del tipo de evento correspondiente. |
| `duration` | float64 | Cuántos segundos duró el evento (por ejemplo una conducción, un pase o una presión). | `duration` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `type_id` | Int64 | Código numérico del tipo de evento (pase, tiro, presión, conducción, etc.). | `type.id` | Entero. |
| `type_name` | category | Nombre del tipo de evento (pase, tiro, presión, conducción, etc.). | `type.name` | strip. |
| `possession_team_id` | Int64 | Código numérico del equipo que inició la posesión con el balón. | `possession_team.id` | Entero. |
| `possession_team_name` | category | Nombre del equipo que inició la posesión con el balón. | `possession_team.name` | strip. |
| `play_pattern_id` | Int64 | Código numérico de cómo se originó la jugada (juego regular, tiro de esquina, tiro libre, saque de banda, contragolpe, saque de meta, etc.). | `play_pattern.id` | Entero. |
| `play_pattern_name` | category | Nombre de cómo se originó la jugada (juego regular, tiro de esquina, tiro libre, saque de banda, contragolpe, saque de meta, etc.). | `play_pattern.name` | strip. |
| `team_id` | Int64 | Código numérico del equipo al que pertenece el evento. | `team.id` | Entero. |
| `team_name` | category | Nombre del equipo al que pertenece el evento. | `team.name` | strip. |
| `tactics_formation` | Int64 | Formación del equipo (por ejemplo 442 o 343). | `tactics.formation` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `control_degree` | float64 | Qué tan estable es la posesión del equipo: sube hacia 1.0 conforme controla el balón; 1.0 = posesión establecida. | `control_degree` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `is_transition` | boolean | TRUE si la jugada ocurre en transición, es decir, con el juego aún no asentado (control_degree menor a 1), como tras una recuperación o pérdida. | `is_transition` | Nulo legítimo (solo juego abierto); no imputar. |
| `is_controlled_possession` | boolean | TRUE si en algún momento de esa posesión el equipo llegó a controlar el balón (control_degree llegó a 1). | `is_controlled_possession` | Nulo legítimo (solo juego abierto); no imputar. |
| `possession_directness` | float64 | Qué tan directa es la posesión, de 0 a 1: cerca de 1 avanza de forma sostenida hacia la portería rival (juego vertical); cerca de 0 circula el balón o lo recicla. | `possession_directness` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `player_possession_directness` | float64 | Cuánto avanza (positivo) o retrocede (negativo) el balón hacia la portería mientras lo tiene el jugador. | `player_possession_directness` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `location_bucket` | category | Tercio de la cancha donde empieza el evento según hacia dónde ataca el equipo con balón: defensive_third (propio), midfield_third (medio), final_third (rival). | `location_bucket` | strip; nulo fuera del tipo de evento correspondiente. |
| `off_camera` | boolean | Vale TRUE si la jugada ocurrió fuera de cámara; los datos son inferidos y pueden ser menos precisos. | `off_camera` | Ausente = False (rellenar con False). |
| `x` | float64 | Coordenada x del evento (yardas, cancha 120x80, ataque hacia x=120). | `location` | Lista JSON [x, y] -> columnas; sin ubicación queda nulo (no imputar, excluir de mapas). |
| `y` | float64 | Coordenada y del evento (yardas, cancha 120x80, ataque hacia x=120). | `location` | Lista JSON [x, y] -> columnas; sin ubicación queda nulo (no imputar, excluir de mapas). |
| `defensive_responsibility_categories` | string | Lista con el tipo de respuesta defensiva esperada: pressure_like (tipo presión), interception_like (tipo intercepción) o ambas. | `defensive_responsibility.categories` | Lista guardada como texto JSON. |
| `defensive_responsibility_probability_sum` | float64 | Suma de las probabilidades individuales de los defensores: qué tan probable es que alguien del rival responda defensivamente a esta jugada. | `defensive_responsibility.probability_sum` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `player_id` | Int64 | Código numérico del jugador que realiza el evento. | `player.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `player_name` | string | Nombre del jugador que realiza el evento. | `player.name` | strip. |
| `position_id` | Int64 | Código numérico de la posición del jugador al momento del evento (portero, lateral, mediocampista, delantero...). | `position.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `position_name` | category | Nombre de la posición del jugador al momento del evento (portero, lateral, mediocampista, delantero...). | `position.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_recipient_id` | Int64 | Código numérico del jugador que recibe el pase (o a quien iba dirigido si fue incompleto). | `pass.recipient.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_recipient_name` | string | Nombre del jugador que recibe el pase (o a quien iba dirigido si fue incompleto). | `pass.recipient.name` | strip. |
| `pass_length` | float64 | Distancia del pase en yardas, del punto de origen al destino. | `pass.length` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_angle` | float64 | Dirección del pase en radianes: 0 es hacia adelante, π es hacia atrás; positivo es en sentido de las manecillas del reloj y negativo al contrario. | `pass.angle` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_height_id` | Int64 | Código numérico de la altura del pase (a ras de piso, bajo o alto). | `pass.height.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_height_name` | category | Nombre de la altura del pase (a ras de piso, bajo o alto). | `pass.height.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `end_x` | float64 | Coordenada x del destino del evento (pase, conducción, tiro o portero), en yardas. | `pass.end_location`; `carry.end_location`; `shot.end_location`; `goalkeeper.end_location` | Se separa [x, y(, z)]; un solo juego de columnas end_* para pass, carry, shot y goalkeeper (cada evento tiene a lo sumo uno; se interpreta con `type_name`). Nulo si no hay destino. |
| `end_y` | float64 | Coordenada y del destino del evento (pase, conducción, tiro o portero), en yardas. | `pass.end_location`; `carry.end_location`; `shot.end_location`; `goalkeeper.end_location` | Se separa [x, y(, z)]; un solo juego de columnas end_* para pass, carry, shot y goalkeeper (cada evento tiene a lo sumo uno; se interpreta con `type_name`). Nulo si no hay destino. |
| `pass_pass_success_probability` | float64 | Probabilidad estimada de que el pase se complete, según dónde y cómo se intenta y hacia dónde va. | `pass.pass_success_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_body_part_id` | Int64 | Código numérico de la parte del cuerpo con que se dio el pase (pie derecho, izquierdo, cabeza, etc.). | `pass.body_part.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_body_part_name` | category | Nombre de la parte del cuerpo con que se dio el pase (pie derecho, izquierdo, cabeza, etc.). | `pass.body_part.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_type_id` | Int64 | Código numérico del tipo de pase por situación: tiro de esquina, tiro libre, saque de meta, saque de banda, saque inicial, etc. Si no viene, es pase en juego abierto. | `pass.type.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_type_name` | category | Nombre del tipo de pase por situación: tiro de esquina, tiro libre, saque de meta, saque de banda, saque inicial, etc. Si no viene, es pase en juego abierto. | `pass.type.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_pass_cluster_id` | Int64 | Número (0 a 59) del grupo (cluster) de tipos de pase al que más se parece este pase. | `pass.pass_cluster_id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_pass_cluster_label` | category | Descripción en texto del cluster del pase (tercio, lado, dirección, largo y altura). | `pass.pass_cluster_label` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_pass_cluster_probability` | float64 | Probabilidad (0 a 1) de que el pase pertenezca a ese cluster. | `pass.pass_cluster_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_switch` | boolean | TRUE si fue un cambio de frente: pase que cruza más de 40 yardas a lo ancho de la cancha. | `pass.switch` | Ausente = False (rellenar con False). |
| `under_pressure` | boolean | Vale TRUE si el jugador hizo la acción con un rival presionándolo; si no, el campo no aparece. | `under_pressure` | Ausente = False (rellenar con False). |
| `pass_assisted_shot_id` | string | Id del tiro que originó este pase (asistencia); se une con el id de ese evento de tiro. | `pass.assisted_shot_id` | UUID que apunta a `id` de otro evento; strip. |
| `pass_shot_assist` | boolean | TRUE si el pase dio origen a un tiro que no fue gol (pase clave). | `pass.shot_assist` | Ausente = False (rellenar con False). |
| `shot_statsbomb_xg` | float64 | Goles esperados (xG) del tiro: probabilidad (0 a 1) de que ese tiro sea gol según la situación (posición, portero y bloqueadores), sin contar qué tan bien se ejecutó. | `shot.statsbomb_xg` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `shot_shot_execution_xg` | float64 | Probabilidad de gol ya contando la ejecución del tiro (colocación y velocidad), además de lo que considera statsbomb_xg. | `shot.shot_execution_xg` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `shot_shot_execution_xg_uplift` | float64 | Cuánto mejoró (o empeoró) la ejecución del tiro la probabilidad de gol: shot_execution_xg menos statsbomb_xg. | `shot.shot_execution_xg_uplift` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `shot_gk_positioning_xg_suppression` | float64 | Peligro de gol que el portero evitó por su colocación, comparado con un portero promedio. | `shot.gk_positioning_xg_suppression` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `end_z` | float64 | Coordenada z del destino del evento (pase, conducción, tiro o portero), en yardas. | `shot.end_location` | Se separa [x, y(, z)]; un solo juego de columnas end_* para pass, carry, shot y goalkeeper (cada evento tiene a lo sumo uno; se interpreta con `type_name`). Nulo si no hay destino. |
| `shot_key_pass_id` | string | Id del pase clave que originó el tiro; se une con el id de ese evento de pase. | `shot.key_pass_id` | UUID que apunta a `id` de otro evento; strip. |
| `shot_type_id` | Int64 | Código numérico del tipo de tiro (juego abierto, tiro libre, tiro de esquina, penal, saque inicial). | `shot.type.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `shot_type_name` | category | Nombre del tipo de tiro (juego abierto, tiro libre, tiro de esquina, penal, saque inicial). | `shot.type.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `shot_technique_id` | Int64 | Código numérico de la técnica del tiro (normal, volea, media volea, chilena, globito, taconazo, cabezazo en palomita). | `shot.technique.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `shot_technique_name` | category | Nombre de la técnica del tiro (normal, volea, media volea, chilena, globito, taconazo, cabezazo en palomita). | `shot.technique.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `shot_outcome_id` | Int64 | Código numérico del resultado del tiro (gol, atajado, bloqueado, desviado, poste, etc.). | `shot.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `shot_outcome_name` | category | Nombre del resultado del tiro (gol, atajado, bloqueado, desviado, poste, etc.). | `shot.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `shot_body_part_id` | Int64 | Código numérico de la parte del cuerpo con que se tiró (cabeza, pie izquierdo, pie derecho, otra). | `shot.body_part.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `shot_body_part_name` | category | Nombre de la parte del cuerpo con que se tiró (cabeza, pie izquierdo, pie derecho, otra). | `shot.body_part.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `shot_first_time` | boolean | TRUE si el tiro fue de primera, sin controlar el balón. | `shot.first_time` | Ausente = False (rellenar con False). |
| `goalkeeper_type_id` | Int64 | Código numérico del tipo de acción del portero (atajada, gol recibido, salida, despeje, etc.). | `goalkeeper.type.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_type_name` | category | Nombre del tipo de acción del portero (atajada, gol recibido, salida, despeje, etc.). | `goalkeeper.type.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_position_id` | Int64 | Código numérico de la posición del portero antes del tiro (en movimiento, tirado, quieto). | `goalkeeper.position.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_position_name` | category | Nombre de la posición del portero antes del tiro (en movimiento, tirado, quieto). | `goalkeeper.position.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_outcome_id` | Int64 | Código numérico del resultado del pase. | `pass.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_outcome_name` | category | Nombre del resultado del pase. | `pass.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `ball_receipt_outcome_id` | Int64 | Código del resultado de la recepción. | `ball_receipt.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `ball_receipt_outcome_name` | category | Resultado de la recepción; el PDF solo documenta Incomplete (el jugador no alcanzó a recibir el pase). | `ball_receipt.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `counterpress` | boolean | Vale TRUE si es una presión (o acción defensiva) dentro de los 5 segundos posteriores a perder el balón en juego abierto, es decir, presión tras pérdida (contrapresión). | `counterpress` | Ausente = False (rellenar con False). |
| `interception_outcome_id` | Int64 | Código del resultado de la intercepción. | `interception.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `interception_outcome_name` | category | Resultado de la intercepción (ganada, balón queda en juego, balón fuera, etc.). | `interception.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `clearance_body_part_id` | Int64 | Código numérico de la parte del cuerpo con que se despejó (cabeza, pie izquierdo, pie derecho, otra). | `clearance.body_part.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `clearance_body_part_name` | category | Nombre de la parte del cuerpo con que se despejó (cabeza, pie izquierdo, pie derecho, otra). | `clearance.body_part.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `clearance_head` | boolean | TRUE: Despeje de cabeza. | `clearance.head` | Ausente = False (rellenar con False). |
| `shot_gk_save_difficulty_xg` | float64 | Probabilidad de que el portero reciba gol considerando colocación, velocidad y posición del portero. | `shot.gk_save_difficulty_xg` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `shot_gk_shot_stopping_xg_suppression` | float64 | Goles evitados por el portero por encima de lo esperado, según el resultado y qué tan difícil era detener el tiro. | `shot.gk_shot_stopping_xg_suppression` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `goalkeeper_body_part_id` | Int64 | Código numérico de la parte del cuerpo con la que el portero hizo la acción. | `goalkeeper.body_part.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_body_part_name` | category | Nombre de la parte del cuerpo con la que el portero hizo la acción. | `goalkeeper.body_part.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_outcome_id` | Int64 | Código numérico del resultado de la acción del portero. | `goalkeeper.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_outcome_name` | category | Nombre del resultado de la acción del portero. | `goalkeeper.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_technique_id` | Int64 | Código numérico de la técnica del portero (lanzándose o de pie). | `goalkeeper.technique.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `goalkeeper_technique_name` | category | Nombre de la técnica del portero (lanzándose o de pie). | `goalkeeper.technique.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `dribble_outcome_id` | Int64 | Código del resultado del regate. | `dribble.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `dribble_outcome_name` | category | Resultado del regate: Complete (superó al rival) o Incomplete (no lo logró). | `dribble.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `out` | boolean | Vale TRUE si la acción terminó con el balón fuera de la cancha. | `out` | Ausente = False (rellenar con False). |
| `set_piece_phase` | float64 | Fase de la jugada a balón parado (1 o 2) a la que pertenece el evento. | `set_piece_phase` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_cross` | boolean | TRUE si el pase fue un centro al área. | `pass.cross` | Ausente = False (rellenar con False). |
| `duel_type_id` | Int64 | Código del tipo de duelo. | `duel.type.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `duel_type_name` | category | Tipo de duelo: Aerial Lost (disputa aérea perdida) o Tackle (barrida o quite de balón). | `duel.type.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `duel_duel_win_probability` | float64 | Probabilidad estimada (0 a 1) de ganar el duelo aéreo, según la métrica HOPS. | `duel.duel_win_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `duel_hops_rating` | float64 | Calificación HOPS normalizada (0 a 1) del jugador. | `duel.hops_rating` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `duel_hops_raw_rating` | float64 | Calificación HOPS cruda del jugador en el duelo aéreo. | `duel.hops_raw_rating` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `duel_hops_opponent_rating` | float64 | Calificación HOPS normalizada (0 a 1) del rival. | `duel.hops_opponent_rating` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `duel_hops_opponent_raw_rating` | float64 | Calificación HOPS cruda del rival en el duelo. | `duel.hops_opponent_raw_rating` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `clearance_aerial_won` | boolean | TRUE si el despeje fue además un duelo aéreo ganado. | `clearance.aerial_won` | Ausente = False (rellenar con False). |
| `clearance_duel_win_probability` | float64 | Probabilidad estimada (0 a 1) de ganar el duelo aéreo en este despeje, según la métrica HOPS. | `clearance.duel_win_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `shot_follows_dribble` | boolean | TRUE si el tiro llegó justo después de un regate exitoso del mismo jugador. | `shot.follows_dribble` | Ausente = False (rellenar con False). |
| `clearance_other` | boolean | TRUE: Despeje con otra parte del cuerpo (rodilla, pecho, etc.). | `clearance.other` | Ausente = False (rellenar con False). |
| `clearance_right_foot` | boolean | TRUE: Despeje con pie derecho. | `clearance.right_foot` | Ausente = False (rellenar con False). |
| `pass_xclaim` | float64 | Probabilidad (0 a 1) de que el portero se quede con el balón (por ejemplo en un centro). | `pass.xclaim` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `clearance_left_foot` | boolean | TRUE: Despeje con pie izquierdo. | `clearance.left_foot` | Ausente = False (rellenar con False). |
| `foul_committed_advantage` | boolean | TRUE si el árbitro dejó seguir la jugada (ley de la ventaja). | `foul_committed.advantage` | Ausente = False (rellenar con False). |
| `foul_won_advantage` | boolean | TRUE si se recibió falta pero el árbitro aplicó ventaja. | `foul_won.advantage` | Ausente = False (rellenar con False). |
| `duel_outcome_id` | Int64 | Código del resultado del duelo. | `duel.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `duel_outcome_name` | category | Resultado del duelo: ganado, perdido con balón en juego o fuera, etc. | `duel.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `injury_stoppage_in_chain` | boolean | TRUE si el equipo del lesionado tenía el balón antes de la pausa por lesión. | `injury_stoppage.in_chain` | Ausente = False (rellenar con False). |
| `foul_won_defensive` | boolean | TRUE si la falta se ganó sin tener el balón (falta a favor en defensa). | `foul_won.defensive` | Ausente = False (rellenar con False). |
| `fifty_fifty_outcome_id` | Int64 | Código del resultado del balón dividido (50/50). | `50_50.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `fifty_fifty_outcome_name` | category | Resultado del balón dividido (50/50): ganado, perdido, etc. | `50_50.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `pass_inswinging` | boolean | TRUE: tiro de esquina con efecto hacia la portería (cerrado). | `pass.inswinging` | Ausente = False (rellenar con False). |
| `pass_technique_id` | Int64 | Código numérico de la técnica del pase (con efecto hacia dentro, hacia fuera, recto o pase filtrado). | `pass.technique.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `pass_technique_name` | category | Nombre de la técnica del pase (con efecto hacia dentro, hacia fuera, recto o pase filtrado). | `pass.technique.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `ball_recovery_recovery_failure` | boolean | TRUE si la recuperación falló: se perdió el balón al intentar recuperar un balón suelto. | `ball_recovery.recovery_failure` | Ausente = False (rellenar con False). |
| `pass_aerial_won` | boolean | TRUE si el pase fue una disputa aérea ganada. | `pass.aerial_won` | Ausente = False (rellenar con False). |
| `pass_duel_win_probability` | float64 | Probabilidad estimada (0 a 1) de ganar el duelo aéreo en este pase, según HOPS. | `pass.duel_win_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_cut_back` | boolean | TRUE si fue un pase de cut-back: balón raso hacia atrás dentro del área rival (Apéndice 5). | `pass.cut_back` | Ausente = False (rellenar con False). |
| `pass_through_ball` | boolean | TRUE: pase filtrado que rompe la última línea defensiva. | `pass.through_ball` | Ausente = False (rellenar con False). |
| `dribble_nutmeg` | boolean | TRUE si el regate fue un túnel (el balón pasó entre las piernas del rival). | `dribble.nutmeg` | Ausente = False (rellenar con False). |
| `foul_committed_card_id` | Int64 | Código de la tarjeta. | `foul_committed.card.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `foul_committed_card_name` | category | Tarjeta mostrada por la falta (amarilla, segunda amarilla, roja). | `foul_committed.card.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `foul_committed_offensive` | boolean | TRUE si la falta se cometió con el balón en posesión (falta en ataque). | `foul_committed.offensive` | Ausente = False (rellenar con False). |
| `foul_committed_type_id` | Int64 | Código del tipo de falta. | `foul_committed.type.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `foul_committed_type_name` | category | Tipo de falta cometida (juego peligroso, mano, simulación, etc.). | `foul_committed.type.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `ball_recovery_offensive` | boolean | TRUE si fue una recuperación ofensiva: se recupera un balón que perdió un compañero por mal control o regate. | `ball_recovery.offensive` | Ausente = False (rellenar con False). |
| `substitution_outcome_id` | Int64 | Código numérico del tipo de cambio (por lesión o táctico). | `substitution.outcome.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `substitution_outcome_name` | category | Nombre del tipo de cambio (por lesión o táctico). | `substitution.outcome.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `substitution_replacement_id` | Int64 | Código numérico del jugador que entra. | `substitution.replacement.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `substitution_replacement_name` | string | Nombre del jugador que entra. | `substitution.replacement.name` | strip. |
| `pass_no_touch` | boolean | TRUE: el jugador dejó pasar el balón a propósito para que lo tomara un compañero atrás (dejada o "dummy"). | `pass.no_touch` | Ausente = False (rellenar con False). |
| `pass_goal_assist` | boolean | TRUE si el pase fue asistencia de gol. | `pass.goal_assist` | Ausente = False (rellenar con False). |
| `pass_outswinging` | boolean | TRUE: tiro de esquina con efecto que se aleja de la portería (abierto). | `pass.outswinging` | Ausente = False (rellenar con False). |
| `pass_miscommunication` | boolean | TRUE si hubo falta de entendimiento: pase bien dado pero el receptor lo leyó mal, o el pasador lo mandó a donde estaba antes el receptor. | `pass.miscommunication` | Ausente = False (rellenar con False). |
| `miscontrol_aerial_won` | boolean | TRUE si el mal control ocurrió en una disputa aérea ganada. | `miscontrol.aerial_won` | Ausente = False (rellenar con False). |
| `miscontrol_duel_win_probability` | float64 | Probabilidad estimada (0 a 1) de ganar el duelo aéreo asociado al mal control, según HOPS. | `miscontrol.duel_win_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `block_deflection` | boolean | TRUE si el bloqueo solo desvió el balón sin cambiar mucho su trayectoria. | `block.deflection` | Ausente = False (rellenar con False). |
| `shot_aerial_won` | boolean | TRUE si el tiro vino de un duelo aéreo ganado. | `shot.aerial_won` | Ausente = False (rellenar con False). |
| `shot_duel_win_probability` | float64 | Probabilidad estimada (0 a 1) de ganar el duelo aéreo del tiro, según HOPS. | `shot.duel_win_probability` | Nulo fuera del tipo de evento correspondiente; no imputar. |
| `pass_straight` | boolean | TRUE: tiro de esquina sin efecto marcado. | `pass.straight` | Ausente = False (rellenar con False). |
| `shot_one_on_one` | boolean | TRUE si fue un mano a mano contra el portero. | `shot.one_on_one` | Ausente = False (rellenar con False). |
| `shot_open_goal` | boolean | TRUE si el tiro fue con la portería vacía. | `shot.open_goal` | Ausente = False (rellenar con False). |
| `pass_deflected` | boolean | TRUE si el pase se desvió en el camino (puede ser completo o incompleto). | `pass.deflected` | Ausente = False (rellenar con False). |
| `bad_behaviour_card_id` | Int64 | Código de la tarjeta mostrada por conducta fuera del juego. | `bad_behaviour.card.id` | Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente. |
| `bad_behaviour_card_name` | category | Tarjeta mostrada (amarilla, segunda amarilla, roja). | `bad_behaviour.card.name` | strip; nulo fuera del tipo de evento correspondiente. |
| `shot_shot_goal_assist` | boolean | TRUE si este tiro generó un gol de otro jugador (por ejemplo un rebote). | `shot.shot_goal_assist` | Ausente = False (rellenar con False). |
| `block_offensive` | boolean | TRUE si el bloqueo fue ofensivo. | `block.offensive` | Ausente = False (rellenar con False). |
| `shot_redirect` | boolean | TRUE si el tiro fue un desvío/remate de otro jugador. | `shot.redirect` | Ausente = False (rellenar con False). |
| `dribble_overrun` | boolean | TRUE si el regate pasó al defensor original pero el balón quedó en poder de otro jugador. | `dribble.overrun` | Ausente = False (rellenar con False). |
| `shot_saved_to_post` | boolean | TRUE si el portero atajó y el balón rebotó en el poste. | `shot.saved_to_post` | Ausente = False (rellenar con False). |
| `goalkeeper_shot_saved_to_post` | boolean | TRUE si el portero atajó y el balón pegó en el poste. | `goalkeeper.shot_saved_to_post` | Ausente = False (rellenar con False). |
| `shot_shot_shot_assist` | boolean | TRUE si este tiro generó otro tiro (por ejemplo un rebote) que no fue gol. | `shot.shot_shot_assist` | Ausente = False (rellenar con False). |
| `goalkeeper_punched_out` | boolean | TRUE si el portero despejó con los puños y el balón salió. | `goalkeeper.punched_out` | Ausente = False (rellenar con False). |
| `block_save_block` | boolean | TRUE si un jugador de campo bloqueó un tiro que iba directo a portería (como una atajada hecha por un jugador de campo). | `block.save_block` | Ausente = False (rellenar con False). |
| `dribble_no_touch` | boolean | TRUE si el jugador intentó el regate dejando pasar el balón al rival sin tocarlo. | `dribble.no_touch` | Ausente = False (rellenar con False). |
| `foul_committed_penalty` | boolean | TRUE si la falta terminó en penal. | `foul_committed.penalty` | Ausente = False (rellenar con False). |
| `foul_won_penalty` | boolean | TRUE si la falta recibida terminó en penal a favor. | `foul_won.penalty` | Ausente = False (rellenar con False). |
| `shot_deflected` | boolean | TRUE si el tiro se desvió por el toque de otro jugador. | `shot.deflected` | Ausente = False (rellenar con False). |
| `shot_saved_off_target` | boolean | TRUE si el portero atajó un tiro que iba fuera. | `shot.saved_off_target` | Ausente = False (rellenar con False). |
| `goalkeeper_shot_saved_off_target` | boolean | TRUE si el portero atajó un tiro que iba fuera. | `goalkeeper.shot_saved_off_target` | Ausente = False (rellenar con False). |
| `player_off_permanent` | boolean | TRUE si el jugador salió definitivamente (por ejemplo lesión sin cambios disponibles). | `player_off.permanent` | Ausente = False (rellenar con False). |
| `goalkeeper_success_in_play` | boolean | TRUE si el portero salió a quitar el balón y lo dejó en un compañero. | `goalkeeper.success_in_play` | Ausente = False (rellenar con False). |
| `goalkeeper_lost_out` | boolean | TRUE si el portero salió a quitar el balón (smother) y lo mandó fuera a favor del rival. | `goalkeeper.lost_out` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `goalkeeper_success_out` | boolean | TRUE si el portero salió a quitar el balón y lo mandó fuera a favor de su equipo. | `goalkeeper.success_out` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `half_end_early_video_end` | boolean | TRUE si el video del partido terminó antes del silbatazo final del periodo (datos incompletos al final). | `half_end.early_video_end` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `half_end_match_suspended` | boolean | TRUE si el árbitro suspendió o pospuso el partido. | `half_end.match_suspended` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `half_start_late_video_start` | boolean | TRUE si el video empezó después del saque inicial (faltan los primeros eventos). | `half_start.late_video_start` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `pass_backheel` | boolean | TRUE si el pase fue de taconazo. | `pass.backheel` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `offside_advantage` | boolean | TRUE si el árbitro dejó seguir la jugada (ventaja) pese al fuera de lugar. | `offside.advantage` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `shot_kick_off` | boolean | TRUE si el tiro fue directo de saque inicial. | `shot.kick_off` | Ausente = False (rellenar con False). No apareció en los 91 partidos; se crea con False. |
| `pass_completed` | boolean | Pase completado (True) o fallido (False); nulo si el evento no es Pass. | `pass.outcome.name` | Resultado vacío = éxito: True si type_name = Pass y pass_outcome_name es nulo. |
| `receipt_ok` | boolean | Recepción buena (True) o mala (False); nulo si el evento no es Ball Receipt*. | `ball_receipt.outcome.name` | Resultado vacío = éxito: True si type_name = 'Ball Receipt*' y el resultado es nulo. |
| `match_second` | Int64 | Segundo del partido desde el inicio. | `minute`, `second` | minute * 60 + second. NO es único entre periodos (el 2o tiempo arranca en 2700 pero el 1o puede pasar de 2700): ordenar siempre por (`period`, `match_second`). |
| `es_administrativo` | boolean | Evento que no entra al análisis táctico. | `type.name` | True para Half Start/End, Starting XI, Tactical Shift, Substitution, Player On/Off, Injury Stoppage y Referee Ball-Drop; se conservan en la tabla. |
| `torneo` | category | Torneo del partido (por ejemplo 'Apertura 2023'). | `partidos.torneo` | Unión con partidos por match_id; julio a diciembre = Apertura, enero a junio = Clausura. |
| `fase` | category | regular o liguilla. | `partidos.fase` | regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso. |
| `es_play_in` | boolean | El partido es de la ronda Play-In. | `partidos.es_play_in` | competition_stage.id = 2. |
| `es_final` | boolean | El partido es uno de los dos de la final del torneo. | `partidos.es_final` | Dos últimos partidos de eliminación directa entre el mismo par de equipos. |
| `es_equipo_analizado` | boolean | El evento lo ejecuta el equipo analizado (América). | `team.id`, `partidos.equipo_id` | team_id == equipo_id del partido. |
| `x_eq` | float64 | Coordenada x en la perspectiva del equipo analizado. | `x`, `es_equipo_analizado` | x si es del equipo analizado; 120 - x si es del rival (así el equipo analizado siempre ataca hacia x = 120). |
| `y_eq` | float64 | Coordenada y en la perspectiva del equipo analizado. | `y`, `es_equipo_analizado` | y si es del equipo analizado; 80 - y si es del rival. |
| `end_x_eq` | float64 | Coordenada x de destino en la perspectiva del equipo analizado. | `end_x`, `es_equipo_analizado` | end_x si es del equipo analizado; 120 - end_x si es del rival. |
| `end_y_eq` | float64 | Coordenada y de destino en la perspectiva del equipo analizado. | `end_y`, `es_equipo_analizado` | end_y si es del equipo analizado; 80 - end_y si es del rival. |

## `frames_360` (9 columnas)

Una fila por jugador visible en cada frame. Solo incluye a quienes ve la cámara.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `event_uuid` | string | Evento al que pertenece el frame; se une con `eventos.id`. | `event_uuid` | strip. Llave junto con jugador_idx. |
| `jugador_idx` | Int64 | Orden del jugador dentro del freeze frame. | posición en la lista `freeze_frame` | explode con contador desde 0; el freeze frame no trae ids de jugador. |
| `teammate` | boolean | El jugador visible es compañero de quien ejecuta el evento. | `freeze_frame[].teammate` | Sin cambios. |
| `actor` | boolean | El jugador visible es quien ejecuta el evento. | `freeze_frame[].actor` | Sin cambios. |
| `keeper` | boolean | El jugador visible es portero. | `freeze_frame[].keeper` | Sin cambios. |
| `x` | float64 | Coordenada x del jugador visible (yardas, perspectiva del equipo que ejecuta el evento). | `freeze_frame[].location` | Se separa [x, y]. |
| `y` | float64 | Coordenada y del jugador visible (yardas, perspectiva del equipo que ejecuta el evento). | `freeze_frame[].location` | Se separa [x, y]. |
| `es_equipo_analizado` | boolean | El jugador visible pertenece al equipo analizado. | `freeze_frame[].teammate`, `eventos.team_id`, `partidos.equipo_id` | Si el equipo del evento es el analizado: teammate; si no: not teammate. |

## `frames_360_evento` (12 columnas)

Una fila por evento con frame (área visible y métricas 360 a nivel evento).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `event_uuid` | string | Evento (unión con `eventos.id`). Llave junto con match_id. | `event_uuid` | strip. |
| `visible_area` | string | Polígono de la cancha que alcanzaba a ver la cámara de la transmisión en ese momento. | `visible_area` | Polígono [x1, y1, x2, y2, ...] guardado como texto JSON. |
| `visible_area_yd2` | float64 | Área del polígono visible en yardas cuadradas. | `visible_area` | Fórmula del polígono (shoelace) sobre los puntos. |
| `n_visibles_equipo` | Int64 | Jugadores visibles del equipo que ejecuta el evento. | `visible_player_counts[].count` | count del team_id igual al `eventos.team_id` del evento. |
| `n_visibles_rival` | Int64 | Jugadores visibles del equipo rival. | `visible_player_counts[].count` | count del team_id distinto al del evento. |
| `line_breaking_pass` | boolean | Verdadero si fue un pase que rompió una línea de defensas (pase filtrado entre líneas) y avanzó bien hacia el centro de la portería. | `line_breaking_pass` | Ausente = False. |
| `ball_receipt_in_space` | boolean | Verdadero si recibió el balón con espacio libre de rivales (radio de al menos 2 yardas). | `ball_receipt_in_space` | Ausente = False. |
| `num_defenders_on_goal_side_of_actor` | float64 | Cuántos rivales visibles están entre el que juega el balón y la portería (más cerca del arco que él). | `num_defenders_on_goal_side_of_actor` | Nulo legítimo; no imputar. |
| `distance_to_nearest_defender` | float64 | Distancia del jugador con balón al rival visible más cercano (en unidades de cancha de 120 x 80). | `distance_to_nearest_defender` | Nulo legítimo; filtrar por `n_visibles_rival` antes de usarlo. |
| `ball_receipt_exceeds_distance` | float64 | Qué tan grande era el espacio libre al recibir: 2, 5 o 10 yardas de radio sin rivales. | `ball_receipt_exceeds_distance` | Nulo legítimo; no imputar. |
| `distances_from_edge_of_visible_area` | string | Lista con la distancia de cada jugador al borde de lo que ve la cámara (indica qué tan confiable es su posición). | `distances_from_edge_of_visible_area` | Lista de {point_id, distance} guardada como texto JSON. |

## `alineaciones` (21 columnas)

Una fila por (partido, equipo, jugador) de la cédula (titulares y banca).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `team_id` | Int64 | Equipo. | `team_id` | Llave junto con player_id. |
| `team_name` | string | Nombre del equipo. | `team_name` | strip. |
| `player_id` | Int64 | Id del jugador. | `lineup[].player_id` | explode de `lineup`. |
| `player_name` | string | Nombre del jugador. | `lineup[].player_name` | strip. |
| `player_nickname` | string | Apodo o nombre corto del jugador. | `lineup[].player_nickname` | strip; nulo en ~2% de los casos. |
| `birth_date` | datetime64[ns] | Fecha de nacimiento. | `lineup[].birth_date` | Texto -> fecha. |
| `player_gender` | category | Género del jugador. | `lineup[].player_gender` | Sin cambios. |
| `player_height` | float64 | Estatura en centímetros. | `lineup[].player_height` | Sin cambios (cm). |
| `player_weight` | float64 | Peso en kilos. | `lineup[].player_weight` | Sin cambios (kg). |
| `jersey_number` | Int64 | Número de camiseta en ese partido. | `lineup[].jersey_number` | Int64. |
| `country_id` | Int64 | Id del país del jugador (nacionalidad). | `lineup[].country.id` | Int64. |
| `country_name` | category | Nacionalidad del jugador. | `lineup[].country.name` | strip. |
| `stats_goals` | Int64 | Goles del jugador en el partido. | `lineup[].stats.goals` | Vacío en ~24% de las filas; se recalcula desde eventos, no se usa como fuente. |
| `stats_assists` | Int64 | Asistencias. | `lineup[].stats.assists` | Ídem. |
| `stats_own_goals` | Int64 | Autogoles. | `lineup[].stats.own_goals` | Ídem. |
| `stats_penalties_scored` | Int64 | Penales anotados. | `lineup[].stats.penalties_scored` | Ídem. |
| `stats_penalties_missed` | Int64 | Penales fallados. | `lineup[].stats.penalties_missed` | Ídem. |
| `stats_penalties_saved` | Int64 | Penales atajados (portero). | `lineup[].stats.penalties_saved` | Ídem. |
| `skills_hops_rating` | float64 | Calificación del jugador normalizada entre 0 y 1 (más cerca de 1 = mejor). | `lineup[].skills.HOPS.rating` | Nulo legítimo (~10%); no imputar. |
| `skills_hops_raw_rating` | float64 | Calificación cruda del modelo, sin normalizar. | `lineup[].skills.HOPS.raw_rating` | Nulo legítimo; no imputar. |

## `posiciones` (14 columnas)

Una fila por tramo de posición de cada jugador (explode de `lineup[].positions`).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `team_id` | Int64 | Equipo. | `team_id` | Llave. |
| `player_id` | Int64 | Jugador. | `lineup[].player_id` | Llave. |
| `posicion_idx` | Int64 | Orden del tramo del jugador en el partido. | posición en `lineup[].positions` | explode con contador desde 0. |
| `position_id` | Int64 | Número de la posición (1 a 25; ver tabla de valores). | `lineup[].positions[].position_id` | Int64. |
| `position` | category | Nombre de la posición (portero, lateral, mediocampista, delantero, etc.). | `lineup[].positions[].position` | strip. |
| `from` | string | Minuto (reloj del periodo) en que empezó a jugar en esa posición. | `lineup[].positions[].from` | Texto HH:MM:SS.mmm. |
| `to` | string | Minuto (reloj del periodo) en que dejó esa posición. | `lineup[].positions[].to` | Nulo en ~55%: probablemente siguió hasta el final; verificar antes de calcular minutos. |
| `from_period` | Int64 | Tiempo del partido en que empezó en esa posición (1 = primer tiempo, 2 = segundo, 3 y 4 = tiempos extra, 5 = penales). | `lineup[].positions[].from_period` | Int64. |
| `to_period` | Int64 | Tiempo del partido en que terminó en esa posición. | `lineup[].positions[].to_period` | Float con vacíos -> Int64. |
| `start_reason` | category | Por qué empezó en esa posición: once inicial, cambio, ajuste táctico, etc. | `lineup[].positions[].start_reason` | strip. |
| `end_reason` | category | Por qué terminó: silbatazo final, cambio, tarjeta roja, ajuste táctico, etc. | `lineup[].positions[].end_reason` | strip; sirve para detectar rojas. |
| `counterpart_id` | Int64 | En un cambio, id del jugador que entró o salió en su lugar. | `lineup[].positions[].counterpart_id` | Float con vacíos -> Int64. |
| `counterpart_name` | string | En un cambio, nombre del jugador que entró o salió en su lugar. | `lineup[].positions[].counterpart_name` | strip. |

## `team_match_stats` (206 columnas)

Una fila por (partido, equipo). Se descarta account_id.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Identificador numérico del partido. | `match_id` | Int64. |
| `team_id` | Int64 | Identificador numérico del equipo en la API. | `team_id` | Int64. |
| `team_name` | string | Nombre completo del equipo. | `team_name` | strip. |
| `opposition_id` | Int64 | Identificador numérico del equipo rival. | `opposition_id` | Int64. |
| `opposition_name` | string | Nombre completo del equipo rival. | `opposition_name` | strip. |
| `competition_id` | Int64 | Identificador numérico de la competencia. | `competition_id` | Int64. |
| `competition_name` | string | Nombre completo de la competencia (por ejemplo, la liga). | `competition_name` | strip. |
| `season_id` | Int64 | Identificador numérico de la temporada. | `season_id` | Int64. |
| `season_name` | string | Descripción de la temporada (por ejemplo, 2020/2021). | `season_name` | strip. |
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
| `team_match_possession` | float64 | Porcentaje de posesión del balón del equipo en el partido. | `team_match_possession` | Sin cambios. Escala 0 a 1. |
| `team_match_directness` | float64 | Qué tan directo ataca el equipo en el partido: distancia que avanzó hacia la portería rival desde el inicio de cada posesión que terminó en tiro, dividida entre la distancia total recorrida en esa construcción. | `team_match_directness` | Sin cambios. |
| `team_match_pace_towards_goal` | float64 | Velocidad promedio (m/s) de la construcción en posesiones que acaban en tiro, del inicio al disparo. | `team_match_pace_towards_goal` | Sin cambios. |
| `team_match_gk_pass_distance` | float64 | Longitud promedio del pase del portero al sacar jugando desde atrás. | `team_match_gk_pass_distance` | Sin cambios. |
| `team_match_gk_long_pass_ratio` | float64 | Porcentaje de pases largos del portero que llegan completos. | `team_match_gk_long_pass_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_box_cross_ratio` | float64 | De los pases al área, qué porcentaje son centros. | `team_match_box_cross_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_passes_inside_box` | Int64 | Pases completos del equipo dentro del área rival en el partido. | `team_match_passes_inside_box` | Sin cambios. |
| `team_match_defensive_distance` | float64 | Distancia promedio, medida desde la portería propia, a la que el equipo hace sus acciones defensivas en el partido (el PDF no indica la unidad). | `team_match_defensive_distance` | Sin cambios. |
| `team_match_ppda` | float64 | PPDA: pases que el equipo deja hacer al rival antes de una acción defensiva (entrada, intercepción o falta), contando solo la zona de ataque, del 40% del largo de la cancha (desde la portería propia) hacia adelante, en el partido. | `team_match_ppda` | Sin cambios. |
| `team_match_defensive_distance_ppda` | float64 | Ambiguo en el PDF: distancia promedio, medida desde la portería propia, de las acciones defensivas que entran en el cálculo del PPDA, en el partido. | `team_match_defensive_distance_ppda` | Sin cambios. |
| `team_match_opp_passing_ratio` | float64 | Porcentaje de pases completos del rival (contra este equipo). | `team_match_opp_passing_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_opp_final_third_pass_ratio` | float64 | Porcentaje de pases completos del rival en su último tercio (contra este equipo). | `team_match_opp_final_third_pass_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_corner_shot_ratio` | float64 | Tiros por cada tiro de esquina del equipo (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_corner_goal_ratio` | float64 | Goles por cada tiro de esquina del equipo (efectividad). | `team_match_corner_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_goal_ratio` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del equipo en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_shot_ratio` | float64 | Tiros por cada saque de banda del equipo (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_goal_ratio` | float64 | Goles por cada saque de banda del equipo (efectividad). | `team_match_throw_in_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_corner_conceded` | float64 | Goles esperados (xG) promedio por cada tiro de esquina del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_corner_conceded` | Sin cambios. |
| `team_match_corner_shot_ratio_conceded` | float64 | Tiros por cada tiro de esquina del rival (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_corner_goal_ratio_conceded` | float64 | Goles por cada tiro de esquina del rival (efectividad). | `team_match_corner_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_free_kick_conceded` | Sin cambios. |
| `team_match_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_throw_in_conceded` | float64 | Goles esperados (xG) promedio por cada saque de banda del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_throw_in_conceded` | Sin cambios. |
| `team_match_throw_in_shot_ratio_conceded` | float64 | Tiros por cada saque de banda del rival (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_goal_ratio_conceded` | float64 | Goles por cada saque de banda del rival (efectividad). | `team_match_throw_in_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_shot_ratio` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del equipo en el partido. | `team_match_direct_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_sp` | Int64 | Número de jugadas de balón parado del equipo. | `team_match_sp` | Sin cambios. |
| `team_match_xg_per_sp` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del equipo en el partido. | `team_match_xg_per_sp` | Sin cambios. |
| `team_match_sp_shot_ratio` | float64 | Tiros por cada jugada de balón parado del equipo. | `team_match_sp_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_goals` | Int64 | Goles del equipo de balón parado. | `team_match_sp_goals` | Sin cambios. |
| `team_match_sp_goal_ratio` | float64 | Goles por cada jugada de balón parado del equipo. | `team_match_sp_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_conceded` | Int64 | Número de jugadas de balón parado del rival. | `team_match_sp_conceded` | Sin cambios. |
| `team_match_xg_per_sp_conceded` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del rival en el partido. | `team_match_xg_per_sp_conceded` | Sin cambios. |
| `team_match_sp_shot_ratio_conceded` | float64 | Tiros por cada jugada de balón parado del rival. | `team_match_sp_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_goals_conceded` | Int64 | Goles del rival de balón parado. | `team_match_sp_goals_conceded` | Sin cambios. |
| `team_match_sp_goal_ratio_conceded` | float64 | Goles por cada jugada de balón parado del rival. | `team_match_sp_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_penalties_won` | Int64 | Penales que el equipo provocó a su favor en el partido. | `team_match_penalties_won` | Sin cambios. |
| `team_match_penalties_conceded` | Int64 | Penales que el equipo cometió y se señalaron a favor del rival en el partido. | `team_match_penalties_conceded` | Sin cambios. |
| `team_match_completed_dribbles` | Int64 | Regates completados por el equipo. | `team_match_completed_dribbles` | Sin cambios. |
| `team_match_failed_dribbles` | Int64 | Regates intentados que fallaron. | `team_match_failed_dribbles` | Sin cambios. |
| `team_match_total_dribbles` | Int64 | Total de intentos de regate (completados más fallados). | `team_match_total_dribbles` | Sin cambios. |
| `team_match_dribble_ratio` | float64 | Porcentaje de regates completados. | `team_match_dribble_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_completed_dribbles_conceded` | Int64 | Regates completados por el rival. | `team_match_completed_dribbles_conceded` | Sin cambios. |
| `team_match_failed_dribbles_conceded` | Int64 | Regates del rival que fallaron. | `team_match_failed_dribbles_conceded` | Sin cambios. |
| `team_match_total_dribbles_conceded` | Int64 | Total de intentos de regate del rival. | `team_match_total_dribbles_conceded` | Sin cambios. |
| `team_match_opposition_dribble_ratio` | float64 | Porcentaje de regates completados por el rival. | `team_match_opposition_dribble_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_high_press_shots_conceded` | Int64 | Tiros que el equipo concedió en posesiones que perdió en los 5 segundos siguientes a una acción defensiva del rival (presión, entrada, intercepción o pase bloqueado) en la mitad del propio equipo, en el partido. | `team_match_high_press_shots_conceded` | Sin cambios. |
| `team_match_np_gd` | Int64 | Diferencia de goles sin contar penales. | `team_match_np_gd` | Sin cambios. |
| `team_match_np_xgd` | float64 | Diferencia de goles esperados (xG) sin contar penales en el partido: el xG a favor del equipo menos el xG en contra. | `team_match_np_xgd` | Sin cambios. |
| `team_match_deep_completions` | Int64 | Pases completos del equipo a menos de 20 metros de la portería rival en el partido. | `team_match_deep_completions` | Sin cambios. |
| `team_match_passing_ratio` | float64 | Porcentaje de pases completos del equipo. | `team_match_passing_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_fhalf_pressures_ratio` | float64 | Porcentaje de las presiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_pressures_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_fhalf_counterpressures_ratio` | float64 | Porcentaje de las contrapresiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_counterpressures_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_crosses_into_box` | Int64 | Centros al área. | `team_match_crosses_into_box` | Sin cambios. |
| `team_match_successful_crosses_into_box` | Int64 | Centros al área que resultaron exitosos. | `team_match_successful_crosses_into_box` | Sin cambios. |
| `team_match_successful_box_cross_ratio` | float64 | De los pases completos al área, qué porcentaje son centros. | `team_match_successful_box_cross_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_indirect_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_indirect_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_indirect_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_indirect_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_indirect_free_kick_conceded` | Sin cambios. |
| `team_match_indirect_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_indirect_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_indirect_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_aerial_duel_difficulty` | float64 | Porcentaje promedio de duelos aéreos ganados estimado con las calificaciones HOPS de los jugadores; qué tan difícil es ganar por aire. | `team_match_aerial_duel_difficulty` | Sin cambios. |
| `team_match_aerial_team_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 11 jugadores en cancha, ponderada por tiempo. | `team_match_aerial_team_rating` | Sin cambios. |
| `team_match_aerial_unit_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 5 mejores jugadores aéreos en cancha, ponderada por tiempo. | `team_match_aerial_unit_rating` | Sin cambios. |
| `team_match_transition_possession_rate` | float64 | Proporción, de 0 a 1, de las posesiones del equipo que se quedan en transición y nunca llegan a la posesión asentada (control_degree = 1), en el partido. | `team_match_transition_possession_rate` | Sin cambios. Escala 0 a 1. |
| `team_match_time_in_transition` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas en fase de transición, es decir, con la posesión aún sin asentar (control_degree menor a 1), en el partido. | `team_match_time_in_transition` | Sin cambios. |
| `team_match_time_in_control` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas con la posesión asentada (control_degree = 1), en el partido. | `team_match_time_in_control` | Sin cambios. |
| `team_match_transition_xg` | float64 | Goles esperados (xG) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón, antes de que control_degree llegue a 1), en el partido. | `team_match_transition_xg` | Sin cambios. |
| `team_match_transition_xg_conceded` | float64 | Goles esperados (xG) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_xg_conceded` | Sin cambios. |
| `team_match_transition_obv` | float64 | OBV (valor de la acción con balón) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón), en el partido. | `team_match_transition_obv` | Sin cambios. |
| `team_match_transition_obv_conceded` | float64 | OBV (valor de la acción con balón) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_obv_conceded` | Sin cambios. |
| `team_match_avg_team_possession_directness` | float64 | Directness promedio de todas las posesiones del equipo en el partido, en una escala de 0 a 1: cerca de 1 es progresión sostenida hacia la portería rival y cerca de 0 es circulación del balón. | `team_match_avg_team_possession_directness` | Sin cambios. Escala 0 a 1. |
| `team_match_avg_team_possession_directness_in_control` | float64 | Directness promedio (escala de 0 a 1) de las posesiones asentadas del equipo (control_degree = 1) en el partido. | `team_match_avg_team_possession_directness_in_control` | Sin cambios. Escala 0 a 1. |
| `team_match_avg_team_possession_directness_in_transition` | float64 | Directness promedio (escala de 0 a 1) de las posesiones del equipo que siguen en transición, sin asentarse, en el partido. | `team_match_avg_team_possession_directness_in_transition` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_shot_distance_conceded` | float64 | Distancia promedio a portería de los tiros del rival de balón parado. | `team_match_sp_shot_distance_conceded` | Sin cambios. |
| `team_match_xg_per_direct_free_kick_conceded` | float64 | Ambiguo en el PDF: goles esperados (xG) promedio por cada tiro libre directo del rival en el partido. | `team_match_xg_per_direct_free_kick_conceded` | Sin cambios. |
| `team_match_direct_free_kick_goal_ratio_conceded` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del rival en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_shot_ratio_conceded` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del rival en el partido. | `team_match_direct_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |

## `player_match_stats` (177 columnas)

Una fila por (partido, jugador). Se descarta account_id.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Identificador numérico del partido. | `match_id` | Int64. |
| `team_id` | Int64 | Identificador numérico del equipo en la API. | `team_id` | Int64. |
| `team_name` | string | Nombre del equipo del jugador. | `team_name` | strip. |
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
| `player_match_possession` | float64 | Ambiguo en el PDF: porcentaje de posesión asociado al jugador en el partido. | `player_match_possession` | Sin cambios. Escala 0 a 1. |
| `player_match_dribbled_past` | Int64 | Veces que lo regatean (pierde el duelo y lo dejan atrás). | `player_match_dribbled_past` | Sin cambios. |
| `player_match_dribbles_faced` | Int64 | Regates que enfrenta (rivales que intentan pasarlo). | `player_match_dribbles_faced` | Sin cambios. |
| `player_match_dribbles` | Int64 | Regates exitosos (deja atrás al rival con el balón). | `player_match_dribbles` | Sin cambios. |
| `player_match_challenge_ratio` | float64 | Porcentaje de veces que el jugador logra la entrada cuando va al duelo, frente a las veces que lo regatean. | `player_match_challenge_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_fouls` | Int64 | Faltas cometidas. | `player_match_fouls` | Sin cambios. |
| `player_match_dispossessions` | Int64 | Veces que le quitan el balón en una entrada. | `player_match_dispossessions` | Sin cambios. |
| `player_match_long_balls` | Int64 | Pases largos completos. | `player_match_long_balls` | Sin cambios. |
| `player_match_successful_long_balls` | Int64 | Pases largos completos. | `player_match_successful_long_balls` | Sin cambios. |
| `player_match_long_ball_ratio` | float64 | Porcentaje de pases largos intentados que se completan. | `player_match_long_ball_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_shots_blocked` | Int64 | Tiros suyos bloqueados. | `player_match_shots_blocked` | Sin cambios. |
| `player_match_clearances` | Int64 | Despejes. | `player_match_clearances` | Sin cambios. |
| `player_match_aerials` | Int64 | Duelos aéreos que disputó. | `player_match_aerials` | Sin cambios. |
| `player_match_successful_aerials` | Int64 | Duelos aéreos que ganó. | `player_match_successful_aerials` | Sin cambios. |
| `player_match_passes` | Int64 | Pases intentados. | `player_match_passes` | Sin cambios. |
| `player_match_successful_passes` | Int64 | Pases completos. | `player_match_successful_passes` | Sin cambios. |
| `player_match_passing_ratio` | float64 | Porcentaje de pases intentados que se completan. | `player_match_passing_ratio` | Sin cambios. Escala 0 a 1. |
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
| `player_match_crossing_ratio` | float64 | Porcentaje de centros intentados que llegan a un compañero. | `player_match_crossing_ratio` | Sin cambios. Escala 0 a 1. |
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
| `player_match_box_cross_ratio` | float64 | De los pases completos al área, qué porcentaje son centros. | `player_match_box_cross_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_deep_progressions` | Int64 | Pases, regates y conducciones del jugador que meten el balón al último tercio rival. | `player_match_deep_progressions` | Sin cambios. |
| `player_match_shot_touch_ratio` | float64 | Tiros como proporción de sus toques de balón (qué tanto tira en vez de solo tocar). | `player_match_shot_touch_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_fouls_won` | Int64 | Faltas recibidas. | `player_match_fouls_won` | Sin cambios. |
| `player_match_xgchain` | float64 | xGChain: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión, incluidos quien tiró y quien asistió. | `player_match_xgchain` | Sin cambios. |
| `player_match_op_xgchain` | float64 | xGChain del jugador en jugada abierta: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión. | `player_match_op_xgchain` | Sin cambios. |
| `player_match_xgbuildup` | float64 | xGBuildup: reparte el xG del tiro final entre todos los jugadores que participaron en la posesión, sin contar a quien tiró ni a quien dio el pase del tiro. | `player_match_xgbuildup` | Sin cambios. |
| `player_match_op_xgbuildup` | float64 | xGBuildup del jugador en jugada abierta: reparte el xG del tiro final entre quienes participaron en la posesión, sin contar a quien tiró ni a quien dio el pase del tiro. | `player_match_op_xgbuildup` | Sin cambios. |
| `player_match_xgchain_per_possession` | float64 | xGChain del jugador expresado por posesión, no como total del partido. | `player_match_xgchain_per_possession` | Sin cambios. Escala 0 a 1. |
| `player_match_op_xgchain_per_possession` | float64 | xGChain del jugador en jugada abierta, expresado por posesión, no como total del partido. | `player_match_op_xgchain_per_possession` | Sin cambios. Escala 0 a 1. |
| `player_match_xgbuildup_per_possession` | float64 | xGBuildup del jugador expresado por posesión, no como total del partido. | `player_match_xgbuildup_per_possession` | Sin cambios. Escala 0 a 1. |
| `player_match_op_xgbuildup_per_possession` | float64 | xGBuildup del jugador en jugada abierta, expresado por posesión, no como total del partido. | `player_match_op_xgbuildup_per_possession` | Sin cambios. Escala 0 a 1. |
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
| `player_match_save_ratio` | float64 | Portero: porcentaje de tiros a puerta que ataja. | `player_match_save_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_npot_shots_faced` | Int64 | Portero: tiros a puerta sin penales enfrentados. | `player_match_npot_shots_faced` | Sin cambios. |
| `player_match_defensive_responsibility_actions` | Int64 | Acciones defensivas que hizo como respuesta a jugadas de ataque rival. | `player_match_defensive_responsibility_actions` | Sin cambios. |
| `player_match_expected_defensive_actions` | float64 | Acciones defensivas esperadas según las situaciones que enfrentó (mide la carga o la oportunidad de defender). | `player_match_expected_defensive_actions` | Sin cambios. |
| `player_match_defensive_actions_above_expectation` | float64 | Acciones defensivas reales menos las esperadas. | `player_match_defensive_actions_above_expectation` | Sin cambios. |
| `player_match_obv_conceded_responsibility_weighted` | float64 | OBV (valor de la acción con balón) que concede el jugador, ponderado por su probabilidad de responsabilidad defensiva ante las jugadas de ataque rival. | `player_match_obv_conceded_responsibility_weighted` | Sin cambios. |
| `player_match_predicted_headers` | float64 | Duelos de cabeza que se esperaría que ganara según la dificultad de cada duelo. | `player_match_predicted_headers` | Sin cambios. |
| `player_match_transition_possession_rate` | float64 | Proporción, de 0 a 1, de las posesiones del jugador que se quedan en fase de transición y no llegan a la posesión asentada (control_degree = 1). | `player_match_transition_possession_rate` | Sin cambios. Escala 0 a 1. |
| `player_match_transition_xg` | float64 | Goles esperados (xG) que genera el jugador mientras la posesión aún no se asienta (fase de transición con balón). | `player_match_transition_xg` | Sin cambios. |
| `player_match_transition_obv` | float64 | OBV (valor de la acción con balón) que genera el jugador mientras la posesión aún no se asienta (fase de transición con balón). | `player_match_transition_obv` | Sin cambios. |
| `player_match_avg_player_possession_directness` | float64 | Directness promedio del jugador en sus acciones con balón, ponderado por el número de acciones, en el partido. | `player_match_avg_player_possession_directness` | Sin cambios. Escala 0 a 1. |
| `player_match_avg_player_possession_directness_in_control` | float64 | Directness promedio del jugador en las acciones con balón en que la posesión ya está asentada (control_degree = 1), en el partido. | `player_match_avg_player_possession_directness_in_control` | Sin cambios. Escala 0 a 1. |
| `player_match_avg_player_possession_directness_in_transition` | float64 | Directness promedio del jugador en las acciones con balón durante la transición, con la posesión aún sin asentar, en el partido. | `player_match_avg_player_possession_directness_in_transition` | Sin cambios. Escala 0 a 1. |
| `player_match_counterpressure_duration_total` | float64 | Duración total de las contrapresiones del jugador (presiones en los 5 segundos siguientes a perder el balón) en el partido. | `player_match_counterpressure_duration_total` | Sin cambios. |
| `player_match_counterpressure_duration_avg` | float64 | Duración promedio de las contrapresiones del jugador (presiones en los 5 segundos siguientes a perder el balón) en el partido. | `player_match_counterpressure_duration_avg` | Sin cambios. |
| `player_match_f3_average_lbp_to_space_received_distance` | float64 | Espacio libre promedio con el que el jugador recibió sus pases que rompen líneas en el último tercio, en el partido. | `player_match_f3_average_lbp_to_space_received_distance` | Sin cambios. |
| `player_match_aerial_ratio` | float64 | Porcentaje de duelos aéreos (balones por arriba, cabezazos) que el jugador gana. | `player_match_aerial_ratio` | Sin cambios. Escala 0 a 1. |
| `player_match_fhalf_average_lbp_to_space_distance` | float64 | Espacio libre promedio del receptor en los pases del jugador que rompen líneas y se completaron en la mitad rival, en el partido. | `player_match_fhalf_average_lbp_to_space_distance` | Sin cambios. |
| `player_match_f3_average_lbp_to_space_distance` | float64 | Espacio libre promedio del receptor en los pases del jugador que rompen líneas y se completaron en el último tercio, en el partido. | `player_match_f3_average_lbp_to_space_distance` | Sin cambios. |
| `player_match_obv_gk` | float64 | OBV (valor de la acción con balón) neto de las acciones del jugador como portero. | `player_match_obv_gk` | Sin cambios. |
| `player_match_claim_success` | float64 | Portero: porcentaje de intentos de atrapar el balón (centros/pases) que le salen bien. | `player_match_claim_success` | Sin cambios. |
| `player_match_gk_positioning_error` | float64 | Portero: qué tan lejos está en promedio de la posición ideal para enfrentar un tiro (menos es mejor). | `player_match_gk_positioning_error` | Sin cambios. |
| `player_match_gsaa_ratio` | float64 | Portero: goles evitados sobre lo esperado, como porcentaje de los tiros enfrentados. | `player_match_gsaa_ratio` | Sin cambios. Escala 0 a 1. |

## `team_match_stats_liga` (212 columnas)

Línea base: una fila por (partido, equipo) de los 1,364 partidos de las 4 temporadas (available, Complete, Normal). Sirve para comparar al equipo contra la liga.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Identificador numérico del partido. | `match_id` | Int64. |
| `team_id` | Int64 | Identificador numérico del equipo en la API. | `team_id` | Int64. |
| `team_name` | string | Nombre completo del equipo. | `team_name` | strip. |
| `opposition_id` | Int64 | Identificador numérico del equipo rival. | `opposition_id` | Int64. |
| `opposition_name` | string | Nombre completo del equipo rival. | `opposition_name` | strip. |
| `competition_id` | Int64 | Identificador numérico de la competencia. | `competition_id` | Int64. |
| `competition_name` | string | Nombre completo de la competencia (por ejemplo, la liga). | `competition_name` | strip. |
| `season_id` | Int64 | Identificador numérico de la temporada. | `season_id` | Int64. |
| `season_name` | string | Descripción de la temporada (por ejemplo, 2020/2021). | `season_name` | strip. |
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
| `team_match_possession` | float64 | Porcentaje de posesión del balón del equipo en el partido. | `team_match_possession` | Sin cambios. Escala 0 a 1. |
| `team_match_directness` | float64 | Qué tan directo ataca el equipo en el partido: distancia que avanzó hacia la portería rival desde el inicio de cada posesión que terminó en tiro, dividida entre la distancia total recorrida en esa construcción. | `team_match_directness` | Sin cambios. |
| `team_match_pace_towards_goal` | float64 | Velocidad promedio (m/s) de la construcción en posesiones que acaban en tiro, del inicio al disparo. | `team_match_pace_towards_goal` | Sin cambios. |
| `team_match_gk_pass_distance` | float64 | Longitud promedio del pase del portero al sacar jugando desde atrás. | `team_match_gk_pass_distance` | Sin cambios. |
| `team_match_gk_long_pass_ratio` | float64 | Porcentaje de pases largos del portero que llegan completos. | `team_match_gk_long_pass_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_box_cross_ratio` | float64 | De los pases al área, qué porcentaje son centros. | `team_match_box_cross_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_passes_inside_box` | Int64 | Pases completos del equipo dentro del área rival en el partido. | `team_match_passes_inside_box` | Sin cambios. |
| `team_match_defensive_distance` | float64 | Distancia promedio, medida desde la portería propia, a la que el equipo hace sus acciones defensivas en el partido (el PDF no indica la unidad). | `team_match_defensive_distance` | Sin cambios. |
| `team_match_ppda` | float64 | PPDA: pases que el equipo deja hacer al rival antes de una acción defensiva (entrada, intercepción o falta), contando solo la zona de ataque, del 40% del largo de la cancha (desde la portería propia) hacia adelante, en el partido. | `team_match_ppda` | Sin cambios. |
| `team_match_defensive_distance_ppda` | float64 | Ambiguo en el PDF: distancia promedio, medida desde la portería propia, de las acciones defensivas que entran en el cálculo del PPDA, en el partido. | `team_match_defensive_distance_ppda` | Sin cambios. |
| `team_match_opp_passing_ratio` | float64 | Porcentaje de pases completos del rival (contra este equipo). | `team_match_opp_passing_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_opp_final_third_pass_ratio` | float64 | Porcentaje de pases completos del rival en su último tercio (contra este equipo). | `team_match_opp_final_third_pass_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_sp_shot_distance_conceded` | float64 | Distancia promedio a portería de los tiros del rival de balón parado. | `team_match_sp_shot_distance_conceded` | Sin cambios. |
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
| `team_match_corner_shot_ratio` | float64 | Tiros por cada tiro de esquina del equipo (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_corner_goal_ratio` | float64 | Goles por cada tiro de esquina del equipo (efectividad). | `team_match_corner_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_goal_ratio` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del equipo en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_shot_ratio` | float64 | Tiros por cada saque de banda del equipo (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_goal_ratio` | float64 | Goles por cada saque de banda del equipo (efectividad). | `team_match_throw_in_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_corner_conceded` | float64 | Goles esperados (xG) promedio por cada tiro de esquina del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_corner_conceded` | Sin cambios. |
| `team_match_corner_shot_ratio_conceded` | float64 | Tiros por cada tiro de esquina del rival (qué tanto se convierte en disparo). | `team_match_corner_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_corner_goal_ratio_conceded` | float64 | Goles por cada tiro de esquina del rival (efectividad). | `team_match_corner_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_free_kick_conceded` | Sin cambios. |
| `team_match_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_direct_free_kick_conceded` | float64 | Ambiguo en el PDF: goles esperados (xG) promedio por cada tiro libre directo del rival en el partido. | `team_match_xg_per_direct_free_kick_conceded` | Sin cambios. |
| `team_match_direct_free_kick_goal_ratio_conceded` | float64 | Ambiguo en el PDF: goles por cada tiro libre directo del rival en el partido; mide su efectividad. | `team_match_direct_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_throw_in_conceded` | float64 | Goles esperados (xG) promedio por cada saque de banda del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_throw_in_conceded` | Sin cambios. |
| `team_match_throw_in_shot_ratio_conceded` | float64 | Tiros por cada saque de banda del rival (qué tanto se convierte en disparo). | `team_match_throw_in_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_throw_in_goal_ratio_conceded` | float64 | Goles por cada saque de banda del rival (efectividad). | `team_match_throw_in_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_shot_ratio` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del equipo en el partido. | `team_match_direct_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_direct_free_kick_shot_ratio_conceded` | float64 | Ambiguo en el PDF: tiros por cada tiro libre directo del rival en el partido. | `team_match_direct_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_sp` | Int64 | Número de jugadas de balón parado del equipo. | `team_match_sp` | Sin cambios. |
| `team_match_xg_per_sp` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del equipo en el partido. | `team_match_xg_per_sp` | Sin cambios. |
| `team_match_sp_shot_ratio` | float64 | Tiros por cada jugada de balón parado del equipo. | `team_match_sp_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_goals` | Int64 | Goles del equipo de balón parado. | `team_match_sp_goals` | Sin cambios. |
| `team_match_sp_goal_ratio` | float64 | Goles por cada jugada de balón parado del equipo. | `team_match_sp_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_conceded` | Int64 | Número de jugadas de balón parado del rival. | `team_match_sp_conceded` | Sin cambios. |
| `team_match_xg_per_sp_conceded` | float64 | Goles esperados (xG) promedio por cada jugada de balón parado del rival en el partido. | `team_match_xg_per_sp_conceded` | Sin cambios. |
| `team_match_sp_shot_ratio_conceded` | float64 | Tiros por cada jugada de balón parado del rival. | `team_match_sp_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_sp_goals_conceded` | Int64 | Goles del rival de balón parado. | `team_match_sp_goals_conceded` | Sin cambios. |
| `team_match_sp_goal_ratio_conceded` | float64 | Goles por cada jugada de balón parado del rival. | `team_match_sp_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_penalties_won` | Int64 | Penales que el equipo provocó a su favor en el partido. | `team_match_penalties_won` | Sin cambios. |
| `team_match_penalties_conceded` | Int64 | Penales que el equipo cometió y se señalaron a favor del rival en el partido. | `team_match_penalties_conceded` | Sin cambios. |
| `team_match_completed_dribbles` | Int64 | Regates completados por el equipo. | `team_match_completed_dribbles` | Sin cambios. |
| `team_match_failed_dribbles` | Int64 | Regates intentados que fallaron. | `team_match_failed_dribbles` | Sin cambios. |
| `team_match_total_dribbles` | Int64 | Total de intentos de regate (completados más fallados). | `team_match_total_dribbles` | Sin cambios. |
| `team_match_dribble_ratio` | float64 | Porcentaje de regates completados. | `team_match_dribble_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_completed_dribbles_conceded` | Int64 | Regates completados por el rival. | `team_match_completed_dribbles_conceded` | Sin cambios. |
| `team_match_failed_dribbles_conceded` | Int64 | Regates del rival que fallaron. | `team_match_failed_dribbles_conceded` | Sin cambios. |
| `team_match_total_dribbles_conceded` | Int64 | Total de intentos de regate del rival. | `team_match_total_dribbles_conceded` | Sin cambios. |
| `team_match_opposition_dribble_ratio` | float64 | Porcentaje de regates completados por el rival. | `team_match_opposition_dribble_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_high_press_shots_conceded` | Int64 | Tiros que el equipo concedió en posesiones que perdió en los 5 segundos siguientes a una acción defensiva del rival (presión, entrada, intercepción o pase bloqueado) en la mitad del propio equipo, en el partido. | `team_match_high_press_shots_conceded` | Sin cambios. |
| `team_match_np_gd` | Int64 | Diferencia de goles sin contar penales. | `team_match_np_gd` | Sin cambios. |
| `team_match_np_xgd` | float64 | Diferencia de goles esperados (xG) sin contar penales en el partido: el xG a favor del equipo menos el xG en contra. | `team_match_np_xgd` | Sin cambios. |
| `team_match_deep_completions` | Int64 | Pases completos del equipo a menos de 20 metros de la portería rival en el partido. | `team_match_deep_completions` | Sin cambios. |
| `team_match_passing_ratio` | float64 | Porcentaje de pases completos del equipo. | `team_match_passing_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_fhalf_pressures_ratio` | float64 | Porcentaje de las presiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_pressures_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_fhalf_counterpressures_ratio` | float64 | Porcentaje de las contrapresiones del equipo que ocurren en la mitad rival en el partido. | `team_match_fhalf_counterpressures_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_crosses_into_box` | Int64 | Centros al área. | `team_match_crosses_into_box` | Sin cambios. |
| `team_match_successful_crosses_into_box` | Int64 | Centros al área que resultaron exitosos. | `team_match_successful_crosses_into_box` | Sin cambios. |
| `team_match_successful_box_cross_ratio` | float64 | De los pases completos al área, qué porcentaje son centros. | `team_match_successful_box_cross_ratio` | Sin cambios. Escala 0 a 1. |
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
| `team_match_indirect_free_kick_shot_ratio` | float64 | Tiros por cada tiro libre indirecto del equipo (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_indirect_free_kick_goal_ratio` | float64 | Goles por cada tiro libre indirecto del equipo (efectividad). | `team_match_indirect_free_kick_goal_ratio` | Sin cambios. Escala 0 a 1. |
| `team_match_xg_per_indirect_free_kick_conceded` | float64 | Goles esperados (xG) promedio por cada tiro libre indirecto del rival en el partido; indica qué tan peligroso es cada uno. | `team_match_xg_per_indirect_free_kick_conceded` | Sin cambios. |
| `team_match_indirect_free_kick_shot_ratio_conceded` | float64 | Tiros por cada tiro libre indirecto del rival (qué tanto se convierte en disparo). | `team_match_indirect_free_kick_shot_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_indirect_free_kick_goal_ratio_conceded` | float64 | Goles por cada tiro libre indirecto del rival (efectividad). | `team_match_indirect_free_kick_goal_ratio_conceded` | Sin cambios. Escala 0 a 1. |
| `team_match_aerial_duel_difficulty` | float64 | Porcentaje promedio de duelos aéreos ganados estimado con las calificaciones HOPS de los jugadores; qué tan difícil es ganar por aire. | `team_match_aerial_duel_difficulty` | Sin cambios. |
| `team_match_aerial_team_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 11 jugadores en cancha, ponderada por tiempo. | `team_match_aerial_team_rating` | Sin cambios. |
| `team_match_aerial_unit_rating` | float64 | Calificación HOPS normalizada (0 a 1) de los 5 mejores jugadores aéreos en cancha, ponderada por tiempo. | `team_match_aerial_unit_rating` | Sin cambios. |
| `team_match_transition_possession_rate` | float64 | Proporción, de 0 a 1, de las posesiones del equipo que se quedan en transición y nunca llegan a la posesión asentada (control_degree = 1), en el partido. | `team_match_transition_possession_rate` | Sin cambios. Escala 0 a 1. |
| `team_match_time_in_transition` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas en fase de transición, es decir, con la posesión aún sin asentar (control_degree menor a 1), en el partido. | `team_match_time_in_transition` | Sin cambios. |
| `team_match_time_in_control` | float64 | Duración total, en milisegundos, de las acciones con balón del equipo (pases, tiros y conducciones) realizadas con la posesión asentada (control_degree = 1), en el partido. | `team_match_time_in_control` | Sin cambios. |
| `team_match_transition_xg` | float64 | Goles esperados (xG) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón, antes de que control_degree llegue a 1), en el partido. | `team_match_transition_xg` | Sin cambios. |
| `team_match_transition_xg_conceded` | float64 | Goles esperados (xG) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_xg_conceded` | Sin cambios. |
| `team_match_transition_obv` | float64 | OBV (valor de la acción con balón) que genera el equipo mientras su posesión aún no se asienta (fase de transición con balón), en el partido. | `team_match_transition_obv` | Sin cambios. |
| `team_match_transition_obv_conceded` | float64 | OBV (valor de la acción con balón) que el equipo concede durante su propia transición sin balón, la fase posterior a perder el balón, en el partido. | `team_match_transition_obv_conceded` | Sin cambios. |
| `team_match_avg_team_possession_directness` | float64 | Directness promedio de todas las posesiones del equipo en el partido, en una escala de 0 a 1: cerca de 1 es progresión sostenida hacia la portería rival y cerca de 0 es circulación del balón. | `team_match_avg_team_possession_directness` | Sin cambios. Escala 0 a 1. |
| `team_match_avg_team_possession_directness_in_control` | float64 | Directness promedio (escala de 0 a 1) de las posesiones asentadas del equipo (control_degree = 1) en el partido. | `team_match_avg_team_possession_directness_in_control` | Sin cambios. Escala 0 a 1. |
| `team_match_avg_team_possession_directness_in_transition` | float64 | Directness promedio (escala de 0 a 1) de las posesiones del equipo que siguen en transición, sin asentarse, en el partido. | `team_match_avg_team_possession_directness_in_transition` | Sin cambios. Escala 0 a 1. |
| `torneo` | category | Torneo del partido (derivado de la fecha). | `team_match_stats_liga.parquet` | julio a diciembre = Apertura, enero a junio = Clausura. |
| `fase` | category | regular o liguilla. | `team_match_stats_liga.parquet` | regular si competition_stage.id en {1, 42, 44}. |
| `es_play_in` | boolean | El partido es de la ronda Play-In. | `team_match_stats_liga.parquet` | competition_stage.id = 2. |
| `es_final` | boolean | Uno de los dos partidos de la final del torneo. | `team_match_stats_liga.parquet` | Calculado sobre toda la liga. |
| `match_date` | datetime64[ns] | Fecha del partido. | `team_match_stats_liga.parquet` | Texto -> fecha. |
| `match_week` | Int64 | Jornada. | `team_match_stats_liga.parquet` | Int64. |

## `related_events` (5 columnas)

Una fila por (evento, evento relacionado).

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento que declara la relación. | `index` del evento | Llave junto con match_id. |
| `id` | string | UUID del evento que declara la relación. | `id` | strip. |
| `related_id` | string | UUID del evento relacionado. | `related_events` | explode de la lista JSON; una fila por relación. |
| `related_index` | Int64 | Índice del evento relacionado en el mismo partido. | `related_events` + `id` | Join de related_id contra id dentro del partido; nulo si no se encuentra. |

## `tactics_lineup` (9 columnas)

Una fila por jugador en cada evento Starting XI / Tactical Shift.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento Starting XI o Tactical Shift. | `index` | Llave junto con match_id. |
| `team_id` | Int64 | Equipo del evento táctico. | `team.id` | Int64. |
| `tactics_formation` | Int64 | Formación (por ejemplo 4231). | `tactics.formation` | Float por los vacíos -> Int64. |
| `jersey_number` | Int64 | Dorsal. | `tactics.lineup[].jersey_number` | explode de la lista JSON. |
| `player_id` | Int64 | Jugador. | `tactics.lineup[].player.id` | explode. |
| `player_name` | string | Nombre del jugador. | `tactics.lineup[].player.name` | strip. |
| `position_id` | Int64 | Posición (1 a 25). | `tactics.lineup[].position.id` | Int64. |
| `position_name` | category | Nombre de la posición. | `tactics.lineup[].position.name` | strip. |

## `defensive_responsibility` (6 columnas)

Una fila por (evento, jugador). `probability_sum` y `categories` quedan en `eventos`.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento. | `index` | Llave junto con match_id. |
| `player_id` | Int64 | Jugador con responsabilidad defensiva. | `defensive_responsibility.players[].player_id` | explode de la lista JSON. |
| `probability` | float64 | Probabilidad de responsabilidad defensiva del jugador. | `defensive_responsibility.players[].probability` | Sin cambios. |
| `interception_like_probability` | float64 | Probabilidad de acción tipo intercepción. | `defensive_responsibility.players[].interception_like_probability` | Nulo legítimo; no imputar. |
| `pressure_like_probability` | float64 | Probabilidad de acción tipo presión. | `defensive_responsibility.players[].pressure_like_probability` | Nulo legítimo; no imputar. |

## `shot_freeze_frame` (10 columnas)

Adición propuesta (no estaba en la lista de tareas): el plan 7.3.7 pide explotar `shot.freeze_frame`.

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del tiro. | `index` | Llave junto con match_id. |
| `jugador_idx` | Int64 | Orden del jugador dentro del freeze frame. | posición en la lista | explode con contador desde 0. |
| `teammate` | boolean | El jugador es compañero del tirador. | `shot.freeze_frame[].teammate` | Sin cambios. |
| `player_id` | Int64 | Jugador. | `shot.freeze_frame[].player.id` | Int64. |
| `player_name` | string | Nombre. | `shot.freeze_frame[].player.name` | strip. |
| `position_id` | Int64 | Posición. | `shot.freeze_frame[].position.id` | Int64. |
| `position_name` | category | Nombre de la posición. | `shot.freeze_frame[].position.name` | strip. |
| `x` | float64 | Coordenada x. | `shot.freeze_frame[].location` | Se separa [x, y]. |
| `y` | float64 | Coordenada y. | `shot.freeze_frame[].location` | Se separa [x, y]. |

## Decisiones abiertas

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| 1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (usuario) | resuelta |
| 2 | Destino unificado `end_x`, `end_y`, `end_z` | Un solo juego para pass, carry, shot y goalkeeper, interpretado con `type_name` | RESUELTA (usuario) | resuelta |
| 3 | 360 en dos tablas | `frames_360` (jugador visible) y `frames_360_evento` (área y conteos) | RESUELTA (usuario) | resuelta |
| 4 | Tabla extra `shot_freeze_frame` | Se incluye; la produce `02_auxiliares.py` | Lee | sáb 17, 20:00 |
| 5 | Eventos administrativos | Se conservan en `eventos` con `es_administrativo = True` | Yordi | sáb 17, 20:00 |
| 6 | `match_clock` y `minute_bin` | No están en v0.1; solo `match_second` | Lee | sáb 17, 20:00 |
| 7 | `defensive_responsibility.categories` | Texto JSON en `eventos`; no se explota | Lee | sáb 17, 20:00 |
| 8 | Tarjetas y formaciones de lineups | Sin tabla en v0.1; propuesta `alineaciones_eventos` y `formaciones` | Yordi y Lee | sáb 17, 20:00 |
| 9 | `positions.to` nulo (~55%) | Se conserva el nulo hasta verificar si significa 'siguió hasta el final' | Yordi | sáb 17, 20:00 |
| 10 | Columnas que no aparecen siempre | Banderas ausentes se crean con False; stats ausentes, nulas | Yordi | sáb 17, 20:00 |
| 11 | Banderas con nulo legítimo | Solo `is_transition` e `is_controlled_possession`; el resto False. Validar `out` y `off_camera` | Lee | sáb 17, 20:00 |
| 12 | `category` o `string` en nombres | `*_name` es category, salvo nombres de personas (string) | Yordi | sáb 17, 20:00 |
| 13 | Penales (periodo 5) | Se conservan con `period = 5`; las métricas de juego abierto los excluyen | Lee | sáb 17, 20:00 |
| 14 | Eventos sin ubicación (~1%) | `x` e `y` nulos; se excluyen de los mapas, sin imputar | Pablo | sáb 17, 20:00 |
| 15 | Perspectiva en `frames_360` | Solo `es_equipo_analizado`; `x` e `y` quedan en la perspectiva del equipo del evento (sin `x_eq`/`y_eq`) | Pablo | sáb 17, 20:00 |
| 16 | Dónde viven los parquet limpios | `data/interim/` (limpias) y `data/processed/` (agregadas del lunes) | Yordi | sáb 17, 20:00 |

## Cambios

### v0.1 (2026-10-17), cambios desde v0

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

### v0 (2026-10-17)

- Primera versión, calculada con la muestra de 3 a 5 partidos.
