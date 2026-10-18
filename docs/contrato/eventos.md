[Volver al índice](README.md)

# `eventos`

## Resumen general

Una fila por evento de los partidos de `partidos` (91 en el crudo): pases, tiros, presiones, conducciones y el resto de tipos de StatsBomb. Trae las coordenadas, las banderas de cada evento y las columnas que ponen al equipo analizado siempre atacando hacia x = 120.

- Grano y llave: Un evento por fila. Llave: (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 197
- Filas: 317,849 en los parquet crudos
- Fuente: Endpoint `events` (`data/raw/parquet/events__<torneo>.parquet`, 4 archivos) unido con `partidos` para `torneo`, `fase`, `es_play_in`, `es_final` y `equipo_id`.

Reglas principales:

- Nombres en snake_case; `location` y los destinos se separan en `x`, `y` y un solo juego `end_x`, `end_y`, `end_z` que se interpreta con `type_name`.
- Las banderas ausentes se rellenan con False, salvo `is_transition` e `is_controlled_possession`, que conservan el nulo.
- Los eventos administrativos (Half Start, Half End, Starting XI, Tactical Shift, Substitution, Player On, Player Off, Injury Stoppage, Referee Ball-Drop y Camera On) se conservan con `es_administrativo = True`.
- `x_eq`, `y_eq`, `end_x_eq` y `end_y_eq` voltean al rival (`120 - x`, `80 - y`) para comparar ambos equipos en una misma cancha.
- Se ordena siempre por (`match_id`, `index`). `match_second` no es único entre periodos y sirve para agrupar por tiempo dentro de (`match_id`, `period`). Los penales llevan `period = 5`.
- `timestamp` se mide desde el inicio de cada periodo: el mínimo por (`match_id`, `period`) es 00:00:00.000 en los 185 periodos.
- Las listas anidadas (`tactics.lineup`, `related_events`, `defensive_responsibility.players`, `shot.freeze_frame`) salen a las tablas auxiliares. Las formaciones y las tarjetas se leen de `tactics_formation`, `foul_committed_card_*` y `bad_behaviour_card_*`.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (usuario) | resuelta |
| C2 | Destino unificado `end_x`, `end_y`, `end_z` | Un solo juego para pass, carry, shot y goalkeeper, interpretado con `type_name` | RESUELTA (usuario) | resuelta |
| C5 | Eventos administrativos | Se conservan en `eventos` con `es_administrativo = True` | RESUELTA (usuario) | resuelta |
| C6 | `match_clock` y `minute_bin` | No van en la tabla limpia. Se calculan en la fase 3 (`scripts/03_contexto.py`, Yordi) con la ficha C1 (`match_clock` y `minute_bin`) de la especificación de métricas de Lee: `match_clock = match_second / 60` y `minute_bin` en ventanas de 15 minutos por periodo | RESUELTA (Lee) | resuelta |
| C7 | `defensive_responsibility.categories` | Texto JSON en `eventos`; no se explota | Lee | vigente por defecto; confirmar antes del lun 19 |
| C8 | Tarjetas y formaciones de lineups | Se cierra sin tablas nuevas: las formaciones salen de `tactics_formation` (eventos Starting XI y Tactical Shift) y las tarjetas de `foul_committed_card_*` y `bad_behaviour_card_*`, que ya están en `eventos` | RESUELTA (usuario) | resuelta |
| C10 | Columnas que no aparecen siempre | Las banderas ausentes se crean con False y las stats ausentes, nulas. Las que no salen en ninguno de los 91 partidos se quedan en False para que el esquema no cambie entre corridas; hoy son 8 en `eventos`: `goalkeeper_lost_out`, `goalkeeper_success_out`, `half_end_early_video_end`, `half_end_match_suspended`, `half_start_late_video_start`, `pass_backheel`, `offside_advantage` y `shot_kick_off` | RESUELTA (usuario) | resuelta |
| C11 | Banderas con nulo legítimo | Solo `is_transition` e `is_controlled_possession` conservan el nulo; el resto va a False. La limpieza ya rellena `out` y `off_camera` con False; Lee confirma que así debe ser | Lee | vigente por defecto; confirmar antes del lun 19 |
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (usuario) | resuelta |
| C13 | Penales (periodo 5) | Se conservan con `period = 5`. Todas las fichas de la especificación de Lee los excluyen (exclusión global de su sección 1) | RESUELTA (Lee) | resuelta |
| C14 | Eventos sin ubicación (0.9%) | `x` e `y` nulos; se excluyen de los mapas, sin imputar | Pablo | vigente por defecto; confirmar antes del lun 19 |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (usuario) | resuelta |

## Columnas (197)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido al que pertenece el evento. | match_id (agregado por la descarga) | Llave junto con `index`. |
| `id` | string | Identificador único del evento (como un folio). | `id` | UUID; solo llave (no modelar). strip. |
| `index` | Int64 | Número de orden del evento dentro del partido (1, 2, 3...). | `index` | Entero. |
| `period` | Int64 | Parte del partido: 1 primer tiempo, 2 segundo tiempo, 3 y 4 tiempos extra, 5 tanda de penales. | `period` | Entero. |
| `timestamp` | string | Momento del evento medido desde el inicio del periodo (hh:mm:ss.mmm). | `timestamp` | Texto HH:MM:SS.mmm desde el inicio del periodo. Verificado: el mínimo por (match_id, period) es 00:00:00.000 en los 185 periodos de los 91 partidos. |
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
| `goalkeeper_lost_out` | boolean | TRUE si el portero salió a quitar el balón (smother) y lo mandó fuera a favor del rival. | `goalkeeper.lost_out` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `goalkeeper_success_out` | boolean | TRUE si el portero salió a quitar el balón y lo mandó fuera a favor de su equipo. | `goalkeeper.success_out` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `half_end_early_video_end` | boolean | TRUE si el video del partido terminó antes del silbatazo final del periodo (datos incompletos al final). | `half_end.early_video_end` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `half_end_match_suspended` | boolean | TRUE si el árbitro suspendió o pospuso el partido. | `half_end.match_suspended` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `half_start_late_video_start` | boolean | TRUE si el video empezó después del saque inicial (faltan los primeros eventos). | `half_start.late_video_start` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `pass_backheel` | boolean | TRUE si el pase fue de taconazo. | `pass.backheel` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `offside_advantage` | boolean | TRUE si el árbitro dejó seguir la jugada (ventaja) pese al fuera de lugar. | `offside.advantage` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `shot_kick_off` | boolean | TRUE si el tiro fue directo de saque inicial. | `shot.kick_off` | Ausente = False (rellenar con False). No existe en el parquet crudo de ninguno de los 91 partidos; se crea con False. |
| `pass_completed` | boolean | Pase completado (True) o fallido (False); nulo si el evento no es Pass. | `pass.outcome.name` | Resultado vacío = éxito: True si type_name = Pass y pass_outcome_name es nulo. |
| `receipt_ok` | boolean | Recepción buena (True) o mala (False); nulo si el evento no es Ball Receipt*. | `ball_receipt.outcome.name` | Resultado vacío = éxito: True si type_name = 'Ball Receipt*' y el resultado es nulo. |
| `match_second` | Int64 | Segundo del partido desde el inicio. | `minute`, `second` | minute * 60 + second. NO es único entre periodos (el 2o tiempo arranca en 2700 pero el 1o puede pasar de 2700): ordenar siempre por (`match_id`, `index`); `match_second` sirve para agrupar por tiempo dentro de (`match_id`, `period`). |
| `es_administrativo` | boolean | Evento que no entra al análisis táctico. | `type.name` | True para Half Start, Half End, Starting XI, Tactical Shift, Substitution, Player On, Player Off, Injury Stoppage, Referee Ball-Drop y Camera On (`contrato.ADMINISTRATIVOS`); se conservan en la tabla. `Camera On` no tiene filas en los 91 partidos; está en la lista porque la especificación de Lee lo cuenta como administrativo. |
| `torneo` | category | Torneo del partido, derivado de la fecha (por ejemplo 'Apertura 2023'). | `partidos.torneo` | Unión con partidos por match_id; julio a diciembre = Apertura, enero a junio = Clausura. |
| `fase` | category | regular o liguilla. | `partidos.fase` | regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso. |
| `es_play_in` | boolean | El partido es de la ronda Play-In. | `partidos.es_play_in` | competition_stage.id = 2. |
| `es_final` | boolean | Uno de los dos partidos de la final del torneo. | `partidos.es_final` | Dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos (calculado sobre toda la liga). |
| `es_equipo_analizado` | boolean | El evento lo ejecuta el equipo analizado (América). | `team.id`, `partidos.equipo_id` | team_id == equipo_id del partido. |
| `x_eq` | float64 | Coordenada x en la perspectiva del equipo analizado. | `x`, `es_equipo_analizado` | x si es del equipo analizado; 120 - x si es del rival (así el equipo analizado siempre ataca hacia x = 120). |
| `y_eq` | float64 | Coordenada y en la perspectiva del equipo analizado. | `y`, `es_equipo_analizado` | y si es del equipo analizado; 80 - y si es del rival. |
| `end_x_eq` | float64 | Coordenada x de destino en la perspectiva del equipo analizado. | `end_x`, `es_equipo_analizado` | end_x si es del equipo analizado; 120 - end_x si es del rival. |
| `end_y_eq` | float64 | Coordenada y de destino en la perspectiva del equipo analizado. | `end_y`, `es_equipo_analizado` | end_y si es del equipo analizado; 80 - end_y si es del rival. |
