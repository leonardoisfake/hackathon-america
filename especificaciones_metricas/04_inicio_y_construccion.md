[Volver al índice](README.md)

# 6. Inicio y construcción

## Resumen general

Siete fichas sobre cómo el EQ saca el balón y lo hace avanzar: tipo de inicio de posesión, distribución del portero, pases que rompen líneas (con 360 y con eventos), recepciones en espacio, progresión y la cadena completa de construcción.

## I1. possession_start_type

- **Qué mide.** Cómo empieza cada posesión del EQ.
- **Entrada.** [B1](01_objetos_base.md#b1-posesión-válida); `events`: `play_pattern.id`, `play_pattern.name`, `team.id`, `possession_team.id`, `location`, `index`.
- **Cálculo.** En cada posesión del EQ se toma su primer evento con `team.id = EQ` (el de menor `index`). `possession_start_type = play_pattern.name` de ese evento: `Regular Play`, `From Corner`, `From Free Kick`, `From Throw In`, `From Counter`, `From Goal Kick`, `From Keeper`, `From Kick Off` u `Other`. Se guardan también `start_x`, `start_y` y `start_third` (tercio del primer evento).
- **Unidad y nivel.** Categoría por posesión; % de posesiones por tipo, por partido.
- **Umbrales.** Ninguno.
- **No se considera.** `period` = 5.
- **Validación.** La suma de posesiones por tipo debe ser igual al total de posesiones del EQ. Las de tipo `From Counter` deben coincidir con las de [B6](01_objetos_base.md#b6-contragolpe).

## I2. gk_distribution

- **Qué mide.** Cómo distribuye el portero del EQ: pase corto o largo y hacia qué tercio.
- **Entrada.** `events`: `type.name = Pass`, `position.name = Goalkeeper`, `pass.length`, `pass.end_location`, `pass.outcome.name`, `pass.type.name` (`Goal Kick`), `play_pattern.id` (7 y 8).
- **Cálculo.** Pases del EQ con `position.name = Goalkeeper`. Corto si `pass.length` < `L_corto` y largo si ≥ `L_corto`. Destino = tercio de `pass.end_location`. Se separa el saque de meta (`pass.type.name = Goal Kick`) de la distribución en juego. Métricas: % corto, % largo, % completo por categoría y % hacia cada tercio.
- **Unidad y nivel.** Yardas; porcentajes por partido.
- **Umbrales.** `L_corto` = 30 yardas (provisional; `Umbrales.pdf` no lo define). Se calibra con el histograma de `pass.length` de estos pases, que debería verse en dos grupos.
- **No se considera.** Pases del portero rival y `period` = 5. Los pases con la mano y con el pie no se separan en esta versión (se pueden separar con `pass.body_part.name`).
- **Validación.** El número de pases del portero por partido debe coincidir con `passes` de `player_match_stats` para ese jugador.

## I3. line_breaking_pass (StatsBomb 360)

- **Qué mide.** Un pase que rompe una línea de defensas rivales y avanza hacia el centro de la portería, según la definición de StatsBomb.
- **Entrada.** `frames_360`: `event_uuid`, `line_breaking_pass`, `visible_player_counts`. `events`: `id`, `type.name = Pass`, `team.id`, `pass.outcome.name`, `play_pattern.id`.
- **Cálculo.** Se une `frames_360` con `events` por `event_uuid = id`. Se filtran los pases del EQ en juego abierto con frame útil (cobertura mínima 360). `lbp = line_breaking_pass` en `True`. `lbp` completado = `lbp` sin `pass.outcome`. Tasa = pases `lbp` / pases de juego abierto con frame útil.
- **Unidad y nivel.** Conteo y porcentaje por partido.
- **Umbrales.** Cobertura mínima 360 (provisional: actor visible y al menos 10 jugadores visibles).
- **No se considera.** Balón parado, eventos sin frame, frames bajo la cobertura mínima y `period` = 5.
- **Validación.** En 3 partidos, la suma de `lbp` por jugador debe coincidir con `lbp` de `player_match_stats`.

## I4. salto_de_lineas (definición del equipo)

- **Qué mide.** Un pase acertado que cruza uno de los tres bloques (defensas, mediocampistas, delanteros) y genera un espacio que el equipo puede aprovechar.
- **Entrada.** `events`: `type.name = Pass`, `pass.outcome.name`, `location`, `pass.end_location`, `position.id`, `team.id`, `period`.
- **Cálculo (versión 1, solo con eventos; ver [punto por confirmar 3](09_puntos_por_confirmar.md)).**
  1. Cada evento se asigna a un bloque según `position.id`: defensas 2 a 8; mediocampistas 9 a 16 y 18 a 20 (mediapuntas); delanteros 17, 21 y 22 a 25 (extremos y delanteros). El portero queda fuera.
  2. Por partido y periodo se calcula la x media de los eventos con balón de cada bloque.
  3. Las fronteras son los puntos medios entre bloques consecutivos: frontera entre defensas y medios, y frontera entre medios y delanteros.
  4. Cada pase tiene un bloque de origen y uno de destino según la x de `location` y de `pass.end_location`.
  5. Salto de líneas = pase completo cuyo destino queda en un bloque más adelantado que el de origen; se guarda si cruza una o dos fronteras.
  * *Versión 2, si alcanza el tiempo:* usar los bloques del rival con el `freeze_frame` (agrupar a los rivales visibles en tres líneas por x) y compararla con [I3](04_inicio_y_construccion.md#i3-line_breaking_pass-statsbomb-360).
- **Unidad y nivel.** Conteo por partido; % de pases completos; por tercio de origen.
- **Umbrales.** Tres bloques; fronteras en el punto medio entre las x medias.
- **No se considera.** Balón parado, pases incompletos, pases hacia atrás o laterales dentro del mismo bloque y `period` = 5.
- **Validación.** Debe correlacionar con `lbp_completed` de StatsBomb, aunque no ser igual porque las definiciones difieren. Si la tasa sale cerca de 0% o de 100%, las fronteras están mal. Se revisan 20 pases en un mapa.

## I5. ball_receipt_in_space (360)

- **Qué mide.** Recepciones con espacio libre de rivales alrededor del receptor y qué tan grande era ese espacio.
- **Entrada.** `frames_360`: `event_uuid`, `ball_receipt_in_space`, `ball_receipt_exceeds_distance`, `visible_player_counts`. `events`: `id`, `type.name = Ball Receipt*`, `team.id`, `ball_receipt.outcome.name`, `location`.
- **Cálculo.** Se une por `event_uuid = id`. Se toman las recepciones del EQ que fueron buenas (`ball_receipt.outcome.name` vacío) y con frame útil. `in_space = ball_receipt_in_space`. Tamaño = `ball_receipt_exceeds_distance` (2, 5 o 10 yardas de radio sin rivales, categorías anidadas; nulo significa sin dato, no cero). Tasa = recepciones en espacio / recepciones buenas con frame útil. Se segmenta por tercio de la recepción.
- **Unidad y nivel.** Conteo y porcentaje por partido; yardas (2, 5, 10).
- **Umbrales.** Radio de al menos 2 yardas (StatsBomb) y cobertura mínima 360. El diccionario marca una duda sobre el nombre del campo; no cambia el cálculo.
- **No se considera.** Recepciones fallidas, frames bajo la cobertura mínima y `period` = 5.
- **Validación.** En un partido se revisan a mano 10 recepciones en `True` y 10 en `False` dentro del `freeze_frame`: en las `True` no debe haber rivales a menos de 2 yardas del receptor.

## I6. progressive_pass y carry_progress

- **Qué mide.** Pases y conducciones que acercan el balón a la portería rival de forma significativa.
- **Entrada.** `events`: `type.name` (`Pass`, `Carry`), `location`, `pass.end_location`, `carry.end_location`, `pass.outcome.name`, `play_pattern.id`.
- **Cálculo.** `d_ini` = distancia de `location` a [120, 40]; `d_fin` = distancia del `end_location` a [120, 40]. Es progresivo si `d_fin ≤ 0.90 × d_ini` (al menos 10% más cerca de la portería). En pases, solo si el pase fue completo. También se guarda `yardas_ganadas = d_ini − d_fin`.
- **Unidad y nivel.** Booleano por evento; conteo y yardas ganadas por partido y por 90 minutos.
- **Umbrales.** 10% (propuesta: no está en `Umbrales.pdf`; se toma del criterio de StatsBomb para el pase que rompe líneas).
- **No se considera.** Pases y conducciones de balón parado y `period` = 5.
- **Validación.** Todo pase progresivo es un pase hacia adelante, así que el conteo del EQ debe ser menor o igual a `forward_passes` de `player_match_stats` sumado por equipo. Se revisan 20 casos en un mapa.

## I7. build_up_chain

- **Qué mide.** La construcción completa: posesiones que arrancan en el primer tercio y llegan al tercio final.
- **Entrada.** [B1](01_objetos_base.md#b1-posesión-válida), [B2](01_objetos_base.md#b2-secuencia-ofensiva), [B3](01_objetos_base.md#b3-fase-de-inicio); `events`: `location`, `possession`, `shot.statsbomb_xg`.
- **Cálculo.** `build_up_chain = True` si la posesión es una fase de inicio ([B3](01_objetos_base.md#b3-fase-de-inicio)) y también una secuencia ofensiva por llegar al tercio final ([B2](01_objetos_base.md#b2-secuencia-ofensiva)). Se guardan `n_pases`, duración, si terminó en tiro y el xG de la posesión.
- **Unidad y nivel.** Por posesión; conteo y % por partido.
- **Umbrales.** Primer tercio x < 40; tercio final x ≥ 80.
- **No se considera.** Balón parado, posesiones inválidas y `period` = 5.
- **Validación.** Los conteos deben ser consistentes: `build_up_chain` ≤ secuencias ofensivas ≤ posesiones válidas. Se revisan 10 cadenas en un mapa.
