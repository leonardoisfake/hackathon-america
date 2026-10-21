# Spec 03: presión y defensa (scripts/03_defensa.py)

Estado: v0.2, 20-oct-2026. Dueño: Pablo. Referencia: plan de trabajo, sección 14.5 (a Pablo le tocan defensa y balón parado); especificación de métricas de Lee, fichas B5 y D1 a D5 (sección 7) y P1 y P2 (sección 9), convenciones de la sección 1, umbrales de la sección 2 y validaciones de la sección 12; framework de Pato (`01_definiciones_y_supuestos.md`); contrato v0.2; `docs/spec_03_contexto.md`.

## Problema

La narrativa necesita describir cómo defiende el América de Jardine y cómo le va a balón parado. En defensa: qué tan arriba presiona, cuánto deja jugar al rival, qué pasa cuando pierde el balón, a qué altura defiende y qué ocurre en los primeros segundos de cada transición. En balón parado: cuántas jugadas tiene a favor y en contra, cuántas terminan en tiro y desde dónde se remata.

`03_defensa.py` calcula las fichas B5, D1 a D5, P1 y P2 desde `data/interim/` y deja las tablas en `data/processed/`. Va después de `03_contexto.py`, porque toma de ahí tres tablas y no recalcula nada de lo que ya hace Yordi:

- `contexto_eventos`, para el contexto por evento.
- `contexto_partidos`, para `is_home`, `stage` y `rival_strength_tercil` del partido.
- `contexto_posesiones`, para comprobar que las posesiones son las mismas que usa ataque.

Valida contra `team_match_stats`. Sigue el mismo estilo que `03_contexto.py`: mensajes `[OK]` y `AVISO:`, errores a stderr, categorías fijas y el mismo esquema de escritura.

## Salidas

| Tabla | Una fila por | Llave | Fichas |
| :--- | :--- | :--- | :--- |
| `defensa_partidos` | partido (91) | `match_id` | D1 a D5 y B5 resumidos, más las columnas `*_sb` de StatsBomb |
| `defensa_periodos` | partido y periodo 1 a 4 (184) | `match_id`, `period` | D1, D2 y D4 (las fichas piden partido y periodo) |
| `defensa_fases_presion` | fase de presión (3,942) | `match_id`, `variante`, `fase_id` | B5, variantes `intentos` y `solo_pressure` |
| `defensa_perdidas` | pérdida del EQ en juego abierto (3,923) | `match_id`, `index` | D3 |
| `defensa_transiciones` | cambio de posesión en juego abierto (10,908) | `match_id`, `index` | D5, `tipo` = defensiva u ofensiva |
| `defensa_zonas` | partido, acción y `cell_6x5` (8,678) | `match_id`, `accion`, `cell_6x5` | Apoyo para mapas; usa la celda de E1 |
| `defensa_liga` | equipo y torneo (144) | `team_id`, `torneo` | Apoyo: promedios de StatsBomb en fase regular de los 8 torneos de la línea base, con `rank_*` dentro del torneo, `es_america` y `es_jardine` |
| `balon_parado_posesiones` | posesión con `play_pattern` 2, 3 o 4, de los dos equipos (7,381) | `match_id`, `possession` | P1: tipo, lado, saque, tiros, xG y goles |
| `balon_parado_tiros` | tiro sin penal y con ubicación, de los dos equipos (2,241) | `match_id`, `index` | P2: origen, tipo, zona de remate, `cell_6x5`, xG y gol |
| `balon_parado_partidos` | partido, lado y tipo (728 = 91 × 2 × 4) | `match_id`, `lado`, `set_piece_type` | P1 y P2 por partido: corner, tiro libre, saque de banda y juego abierto, con la referencia de StatsBomb |

- `defensa_partidos` guarda numeradores y denominadores (`ppda_pases_rival`, `ppda_acciones`, `perdidas`, `perdidas_regain_5s`...), así que cualquier agregado por torneo o por contexto se recalcula sumando y no promediando tasas.
- Las tablas por evento (`defensa_fases_presion`, `defensa_perdidas` y `defensa_transiciones`) traen `index` del evento de referencia (primer intento, evento de la pérdida o primer evento de la posesión nueva) y, en ese evento, `score_state`, `numerical_state_cat`, `minute_bin`, `rival_strength_tercil` y `stage` de `contexto_eventos`. Para más contexto se hace un `merge` por (`match_id`, `index`).
- `defensa_partidos` trae además `stage` y `rival_strength_tercil` del partido.

## Reglas por ficha

- **D1.** `press_height` es la x media de los `Pressure` del EQ. Una presión alta tiene x ≥ 80 (40 yardas, como lo tomó Lee). `presiones_altas_40m` usa x ≥ 76.26 (40 metros, como dice el framework de Pato). `presiones_mitad_rival` (x ≥ 60) es la referencia de StatsBomb.
- **D2.** Los pases del rival cuentan con x ≤ 72 en sus coordenadas. Las acciones son `Duel` Tackle, `Interception` y `Foul Committed` del EQ con x ≥ 48. `ppda` usa todos los pases (versión 1 de la ficha) y `ppda_juego_abierto` solo los de `play_pattern` 1, 5, 6, 7 u 8 (versión 2).
- **D3.**
  - Pérdida: `Dispossessed`, `Miscontrol`, `Pass` con `pass_outcome_name` o `Dribble` Incomplete del EQ, en posesión del EQ y en juego abierto.
  - `regain_5s`: el EQ abre una posesión en el mismo periodo a 5 s o menos de la pérdida, medidos con `timestamp`.
  - `con_contrapresion`: algún evento del EQ con `counterpress` en esos 5 s.
  - `segundos_a_recuperar`: el tiempo hasta la siguiente posesión del EQ en el periodo; es nulo si no la hay.
- **D4.**
  - Acciones: `Duel` Tackle, `Interception`, `Block`, `Clearance` y `Ball Recovery` del EQ.
  - Se excluyen el portero (`position_id` 1), el balón parado (`play_pattern` 2, 3 y 4) y `Pressure`.
  - Se reporta en yardas y en escala 0 a 100 (`_100`). La variante `_defensas` usa solo `position_id` 2 a 8.
- **B5.**
  - Intento: `Pressure`, `Ball Recovery`, `Duel` Tackle o `Interception` del EQ, ordenados por (`match_id`, `period`, `timestamp`).
  - Una fase es un grupo de al menos 3 intentos con menos de 10 s entre cada uno y el anterior.
  - `recupera`: el EQ abre una posesión desde el primer intento hasta 5 s después del último.
  - La variante `solo_pressure` es la de sensibilidad de la ficha.
- **D5.**
  - Cambio de posesión: una posesión no administrativa cuyo equipo difiere del de la anterior, en el mismo periodo, y cuyo `play_pattern` es de juego abierto.
  - Ventana: los eventos no administrativos desde el primero de la posesión nueva hasta 5 s después, cortada en el fin del periodo. No se corta si la posesión vuelve a cambiar dentro de los 5 s.
  - En la ventana se miden eventos, tiros y xG sin penales de los dos equipos, `obv_total_net` del EQ, avance del equipo que gana el balón (x máxima menos x inicial, en su perspectiva), contrapresión del EQ y la proporción de `is_transition`.
  - `x_eq_inicio` ubica el cambio en la perspectiva del EQ.
- **P1.**
  - `set_piece_type` sale del `play_pattern_id` del primer evento no administrativo de la posesión: 2 = Corner, 3 = Free Kick y 4 = Throw In.
  - El saque es un `Pass` con `pass_type_name` Corner, Free Kick o Throw-in, o un `Shot` con `shot_type_name` Free Kick (tiro libre directo, `es_directo`).
  - `lado` es `a_favor` si la posesión es del EQ y `en_contra` si es del rival.
  - Cada posesión trae tiros, xG y goles de balón parado del equipo con la posesión (regla de P2), `tiros_posesion` (todos sus tiros sin penal) y `set_piece_phase_max` tal cual.
  - `con_saque` es False si el equipo no ejecutó un saque en la posesión.
- **P2.**
  - Se toman los tiros sin penal y con ubicación de los dos equipos.
  - `origen` es `balon_parado` si el tiro trae `set_piece_phase` o es tiro libre directo; si no, `juego_abierto`. El tipo sale del `play_pattern_id` del tiro.
  - `zona_remate`: `area_chica` (x ≥ 114 y 30 ≤ y ≤ 50), `area_grande` (x ≥ 102 y 18 ≤ y ≤ 62, sin el área chica) o `fuera_del_area`, en la perspectiva del que remata. Además trae `cell_6x5` de E1.
  - `balon_parado_partidos` suma por partido, lado y tipo, y agrega la fila `Juego abierto` para comparar.

## Desviaciones de las fichas

- **D3, qué es una pérdida.** La ficha no dice qué hacer si el EQ conserva el balón después de un pase incompleto o un `Miscontrol` (StatsBomb no cambia la posesión). Una pérdida cuenta solo si es el último evento de pérdida de su posesión y la posesión siguiente es del rival. Si no, `regain_5s` saldría verdadero sin haber perdido nada.
- **D3, `regain_5s`.** Se mide hasta el inicio de la siguiente posesión del EQ y no con "cualquier evento con `possession_team` = EQ": dentro de la posesión de la pérdida todos los eventos ya tienen `possession_team` = EQ.
- **D3, validación de contrapresiones.** No hay coincidencia exacta con `team_match_counterpressures`: los `Pressure` con `counterpress` del EQ cuadran en 37 de 91 partidos, con 1.7 de más en promedio (rango −4 a +12). Se probaron los periodos 1 y 2, el juego abierto, solo posesión del rival y sin `off_camera`, y ninguna variante cuadra mejor. StatsBomb no documenta su regla, así que va como aviso y no detiene la corrida. Las presiones totales sí cuadran exactas (validación dura).
- **D2, variante declarada.** La que más se acerca a `team_match_ppda` es la versión 2 de la ficha (pases de juego abierto con entrada, intercepción y falta): correlación 0.944, razón mediana 0.94 y error medio 1.99. La versión 1 (todos los pases) correlaciona 0.964 pero queda 46% arriba. Las dos van en la tabla; para comparar con StatsBomb se usa `ppda_juego_abierto`.
- **D4.** No hay columna de StatsBomb para validar. Se valida con la correlación con `press_height` por partido, que es 0.772.
- **D5, validación.** Dentro de las ventanas, el 88.8% de los eventos tiene `is_transition`; fuera, el 17.0%. Eso confirma la ventana. Contra `team_match_transition_xg_conceded` el Spearman es 0.336: StatsBomb define la transición con `control_degree` y no con una ventana fija, así que solo se esperaba el mismo orden aproximado.
- **P2 y V1, origen del tiro (importa para Lee).** Ninguna de las dos reglas de V1 reproduce a StatsBomb. La regla A (`shot_type_name`) coincide en 13 de 182 equipo-partido en `sp_xg` y la B (`play_pattern_id`) en 35. La regla que cuadra es otra: un tiro es de balón parado si trae `set_piece_phase` o es un tiro libre directo.
  - Con ella, los tiros de corner, de tiro libre y de saque de banda cuadran exactos con `team_match_shots_from_*` en los 182, de los dos lados, y `team_match_sp_shots` también.
  - El xG cuadra con ±0.011 en 169 (corner), 174 (tiro libre) y 181 (saque de banda) de 182. Las diferencias que quedan son de hasta 0.27 en partidos sueltos.
  - Con `play_pattern_id` se cuentan de más los tiros de jugadas que siguen después del saque. Por ejemplo, en saques de banda salen 1.5 tiros de más por partido.
  - Conviene que Lee use esta misma regla para `op_xg` y `sp_xg` en V1, para que ataque y balón parado no se contradigan.
- **P1, posesiones que heredan el patrón.** 875 de las 7,381 posesiones con `play_pattern` 2, 3 o 4 no tienen un saque del equipo con el balón. Son posesiones que heredan el patrón de la jugada, por ejemplo el rival que recupera tras un corner. Quedan en la tabla con `con_saque` = False y no cuentan como jugada en `balon_parado_partidos`. Con eso, las posesiones por partido son exactamente los saques. Traen 11 tiros de segunda jugada (ejemplo: 3889681, el América recupera tras su corner y remata con `set_piece_phase` 1). Esos tiros sí cuentan, porque los tiros se suman por evento, como StatsBomb.
- **P2, juego abierto.** La fila `Juego abierto` es todo tiro sin penal que no es de balón parado. Contra `team_match_op_xg` cuadra en 105 de 182 (diferencia máxima 0.68), así que va solo como aviso; StatsBomb no documenta qué deja fuera de su `op_xg`.
- **`defensa_liga` y `defensa_zonas`** no son fichas. Se agregan como apoyo para la comparación con la liga y para los mapas de calor. La liga se toma solo en fase regular para que todos los equipos tengan 17 partidos.

## Criterios de aceptación

- AC1: `defensa_partidos` trae exactamente los 91 `match_id` de `partidos`, filtrados por `entrenador_id` y `equipo_id`. Ninguna otra tabla trae un `match_id` fuera de esos 91. `defensa_periodos` trae los 91 en los periodos 1 y 2.
- AC2: las diez tablas tienen llave única.
- AC2b: las 18,784 posesiones no administrativas que usa el script coinciden con las de `contexto_posesiones` en llave, equipo, periodo y `play_pattern`. Así defensa y ataque cuentan las mismas posesiones. La única diferencia es el evento de inicio en 6 posesiones: aquí se toma el primero no administrativo, porque mide cuándo empieza el juego.
- AC3: las presiones del EQ cuadran exactamente con `team_match_pressures` en los 91 partidos.
- AC4: todo `index` de las tablas por evento existe en `contexto_eventos` y su `score_state` no es nulo.
- AC5: las alturas están en [0, 120] y las tasas en [0, 1]. `ppda`, `press_height` y `defensive_line_height` no son nulos en ningún partido.
- AC6: cada fase tiene al menos 3 intentos, sin huecos de 10 s o más y con duración no negativa. Ninguna ventana de D5 pasa de 5 s. `segundos_a_recuperar` no es negativo.
- AC7: `defensa_liga` trae un renglón del América por cada torneo de Jardine.
- AC7b (P1 y P2):
  - `balon_parado_partidos` tiene 728 filas.
  - Los saques y los tiros de corner, tiro libre y saque de banda cuadran exactos con `team_match_corners`, `free_kicks`, `throw_ins` y `shots_from_*`, a favor y en contra.
  - Los saques de las posesiones con saque suman los saques del partido.
  - Ningún tiro queda sin xG y `zona_remate` está en el catálogo.
- AC8: si falla una validación dura no se escribe nada y el código es 1. Si falta un archivo de entrada, también 1, y el mensaje dice qué script correr antes. La escritura sigue el esquema de `03_contexto.py`:
  - Todo va primero a una carpeta temporal `data/processed/.tmp_defensa_*`.
  - Antes de reemplazar, revisa que ningún destino esté bloqueado (por ejemplo, abierto en Excel).
  - Reemplaza archivo por archivo. Si se queda a medias, el mensaje dice qué se reemplazó y dónde quedó la carpeta, que no se borra.
  - Al terminar borra los temporales de corridas anteriores.
- Informativas (avisos): presiones en x ≥ 60, contrapresiones y regains contra StatsBomb, variantes de PPDA, `is_transition` dentro y fuera de las ventanas, Spearman de D5 y correlación de D4 con D1.

## Resultado de la primera corrida (20-oct)

Código 0, unos 10 s.

- **D1:** 13,265 presiones (iguales a StatsBomb en los 91 partidos), 23.7% altas, `press_height` medio de 57.3 yd. Las de x ≥ 60 cuadran en 84 partidos, con diferencia máxima de 1.
- **D2:** PPDA de 18.2 con todos los pases y 11.3 en juego abierto.
- **D3:** 3,923 pérdidas, 6.2% con `regain_5s` y 30.6% con contrapresión; de esas, 14.6% recupera en 5 s.
- **D4:** 47.4 yd con todas las acciones y 35.4 yd solo defensas.
- **B5:** 2,532 fases, de las que el 58.6% recupera; 1,410 en la variante `solo_pressure`.
- **D5:** 5,432 transiciones defensivas (xG del rival 5.3) y 5,476 ofensivas (xG del EQ 6.3).
- **D1 con 40 m:** 26.9% de presiones altas, contra 23.7% con 40 yardas.
- **P1 y P2 a favor:**
  - 455 corners: 154 con tiro, 177 tiros, xG 17.4, 15 goles.
  - 1,169 tiros libres: 108 tiros, xG 8.9, 8 goles.
  - 1,752 saques de banda: 16 tiros, xG 1.2, 1 gol.
- **P1 y P2 en contra:**
  - 440 corners: 169 con tiro, 193 tiros, xG 15.0, 9 goles.
  - 1,007 tiros libres: 102 tiros, xG 6.5, 5 goles.
  - 1,683 saques de banda: 20 tiros, xG 1.3, 0 goles.

Pruebas:

- Dos corridas seguidas dan tablas idénticas (`assert_frame_equal`).
- Sin `contexto_eventos` sale con código 1.
- Con un `Pass` del EQ cambiado a `Pressure` falla AC3, sale con código 1 y `data/processed/` no cambia.
- Con un corner del EQ cambiado a tiro libre fallan las dos validaciones de AC7b y sale con código 1.
- Sin `contexto_posesiones` sale con código 1 y pide correr antes `03_contexto.py`.
- Con el equipo de una posesión no administrativa cambiado en `contexto_posesiones` falla AC2b y sale con código 1.
- Revisión manual de una pérdida: 3889637, `index` 576. `Dispossessed` en 11:13.674, contrapresión en 11:14.228 y `Ball Recovery` del EQ en 11:16.188, así que `regain_5s` en 2.5 s.

## Fuera de alcance

- Agregados por torneo, fase o contexto. Se arman al integrar sumando numeradores y denominadores de `defensa_partidos` o filtrando las tablas por evento.
- B6 (contragolpe), que es de ataque.
- La altura de la línea con 360. Ninguna ficha la pide; D4 usa eventos.
- El grupo de contraste (Ortiz y Solari) fuera de `defensa_liga`.
