[Volver al índice](README.md)

# 7. Presión y defensa

## Resumen general

Cinco fichas sobre qué hace el EQ sin balón: altura de la presión, PPDA, contrapresión y recuperación a los 5 s, altura de la línea defensiva y comportamiento en las transiciones.

## D1. press_height y high_press

- **Qué mide.** Qué tan arriba presiona el EQ y qué parte de sus presiones ocurre en la zona alta.
- **Entrada.** `events`: `type.name = Pressure`, `team.id`, `location`, `counterpress`, `period`.
- **Cálculo.** `press_height` = x media de las presiones del EQ por partido (0 a 120). `high_press` = presión con x ≥ 80. Se reportan presiones totales, presiones altas y % de presiones altas. Para comparar con StatsBomb se calcula también el conteo en la mitad rival (x ≥ 60).
- **Unidad y nivel.** Yardas; conteo y porcentaje por partido.
- **Umbrales.** x ≥ 80 (los últimos 40 de la cancha rival; ver [punto por confirmar 1](09_puntos_por_confirmar.md)). Si fueran metros reales, x ≥ 76.26.
- **No se considera.** `period` = 5.
- **Validación.** Las presiones totales deben coincidir con `team_match_pressures` y las que tienen x ≥ 60 con `team_match_fhalf_pressures`.

## D2. PPDA

- **Qué mide.** Cuántos pases deja hacer el EQ al rival por cada acción defensiva en la zona de ataque. Un valor bajo significa más presión.
- **Entrada.** `events`: `type.name` (`Pass`, `Duel`, `Interception`, `Foul Committed`), `duel.type.name`, `team.id`, `location`, `period`.
- **Cálculo.** La zona de ataque del EQ empieza al 40% del largo de la cancha: x ≥ 48 en coordenadas del EQ. Pases del rival = `Pass` de R cuya `location` espejada cae en esa zona (120 − x ≥ 48, es decir, x ≤ 72 en coordenadas del rival). Acciones defensivas del EQ = `Duel` con `duel.type.name = Tackle`, `Interception` y `Foul Committed` con x ≥ 48. `PPDA = pases del rival / acciones defensivas del EQ`, por partido y por periodo.
- **Unidad y nivel.** Razón (pases por acción).
- **Umbrales.** 40% del largo de la cancha (48 yardas). Acciones defensivas: entrada, intercepción y falta (glosario).
- **No se considera.** `period` = 5. La primera versión incluye todos los pases del rival; la segunda, solo los de juego abierto.
- **Validación.** Se compara con `team_match_ppda` en al menos 3 partidos. Si no coincide, se prueban las variantes (con o sin balón parado, con o sin faltas) y se declara en el framework la que cuadre.

## D3. counterpress y regain_5s

- **Qué mide.** Cuántas veces el EQ presiona tras perder el balón y cuántas veces lo recupera en 5 s.
- **Entrada.** `events`: `counterpress`, `type.name` (`Pressure`, `Dispossessed`, `Miscontrol`, `Pass`, `Dribble`), `pass.outcome.name`, `dribble.outcome.name`, `team.id`, `possession_team.id`, `timestamp`, `period`.
- **Cálculo.** Pérdida del EQ en juego abierto = `Dispossessed`, `Miscontrol`, `Pass` con `pass.outcome.name` presente o `Dribble` con `dribble.outcome.name = Incomplete`. Contrapresiones = eventos del EQ con `counterpress` en `True` (en particular los `Pressure`). `regain_5s = 1` si, dentro de 5 s después de la pérdida (mismo `period`), el EQ vuelve a tener la posesión (aparece un evento del EQ con `possession_team.id = EQ`). Tasa = pérdidas con recuperación / pérdidas. Segunda tasa: solo para pérdidas con contrapresión.
- **Unidad y nivel.** Conteo, porcentaje y segundos; por partido.
- **Umbrales.** 5 s.
- **No se considera.** Balón parado y `period` = 5. Las ventanas que cruzan el fin del periodo se cortan.
- **Validación.** Los `Pressure` con `counterpress` en `True` deben coincidir con `team_match_counterpressures`; las recuperaciones tras contrapresión con `team_match_counterpressure_regains` y las de presión con `team_match_pressure_regains`.

## D4. defensive_line_height

- **Qué mide.** La altura media de las acciones defensivas del EQ, es decir, qué tan adelantada juega su línea defensiva.
- **Entrada.** `events`: `type.name` (`Duel` con `Tackle`, `Interception`, `Block`, `Clearance`, `Ball Recovery`), `location`, `position.id`, `team.id`, `play_pattern.id`, `period`.
- **Cálculo.** x media de las acciones defensivas del EQ por partido y por periodo, en yardas y en escala 0 a 100 (x / 120 × 100) para alinearse con el glosario (`average_x_`). Variante: solo acciones de defensas (`position.id` 2 a 8).
- **Unidad y nivel.** Yardas (0 a 120) y escala 0 a 100; por partido y periodo.
- **Umbrales.** Ninguno.
- **No se considera.** Portero, acciones de balón parado (`play_pattern` 2, 3 y 4), `Pressure` (se mide en [D1](05_presion_y_defensa.md#d1-press_height-y-high_press)) y `period` = 5.
- **Validación.** No se encontró una columna a nivel equipo en `team_match_stats` para compararla. Se valida con un mapa de las acciones defensivas y comprobando que los partidos con más `press_height` tengan una línea más alta.

## D5. transition

- **Qué mide.** Qué hace el EQ en los primeros 5 s tras perder o ganar el balón.
- **Entrada.** `events`: `possession_team.id`, `team.id`, `timestamp`, `period`, `type.name`, `location`, `obv_total_net`, `shot.statsbomb_xg`, `play_pattern.id`, `is_transition`, `control_degree`.
- **Cálculo.** Cambio de posesión = evento en que `possession_team.id` pasa de un equipo al otro, en juego abierto. Transición defensiva del EQ = ventana de 5 s después de perder la posesión; ofensiva = ventana de 5 s después de ganarla. En cada ventana: n de eventos del EQ, tiros y xG a favor y en contra, suma de `obv_total_net` del EQ, avance (x máxima − x inicial) y si hubo contrapresión ([D3](05_presion_y_defensa.md#d3-counterpress-y-regain_5s)). Como referencia se reporta también `is_transition` de StatsBomb (juego aún no asentado, `control_degree` < 1).
- **Unidad y nivel.** Segundos, conteos y xG por ventana; por partido.
- **Umbrales.** 5 s.
- **No se considera.** Cambios de posesión por balón parado y `period` = 5. Las ventanas que cruzan el fin del periodo se cortan.
- **Validación.** La proporción de eventos con `is_transition` en `True` debe ser alta dentro de las ventanas de 5 s y baja fuera de ellas. Se compara también el orden entre partidos con `team_match_transition_xg` y `team_match_time_in_transition`.
