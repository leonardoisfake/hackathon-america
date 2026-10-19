[Volver al índice](README.md)

# 3. Objetos base (definidos en K-Pumas/Framework.pdf)

## Resumen general

Seis objetos que define `K-Pumas/Framework.pdf` y en los que se apoyan las demás métricas: posesión válida, secuencia ofensiva, las fases de inicio, construcción y presión, y el contragolpe. Tienen su ficha aquí porque otras fichas los usan como entrada.

Varias métricas se apoyan en estos objetos, así que se especifican primero.

## B1. Posesión válida

- **Qué mide.** Un tramo de juego abierto de un equipo que cuenta para el análisis, sin rebotes.
- **Entrada.** `events`: `possession`, `possession_team.id`, `team.id`, `play_pattern.id`, `type.name`, `index`.
- **Cálculo.**
  1. Se usa `possession` de StatsBomb: cambia cuando el rival recupera el balón y también tras un saque de banda aunque lo saque el mismo equipo, igual que en `Umbrales.pdf`.
  2. Se funden dos posesiones consecutivas del mismo equipo cuando entre ellas el rival solo tiene un toque sin dirección (supuesto: `Block`, `Clearance`, `Miscontrol` o `Ball Recovery` con `recovery_failure`, sin pase ni conducción).
  3. Se cuentan los pases del equipo con la posesión (`type.name = Pass`, `team.id = possession_team.id`). La posesión es válida si tiene al menos 3 pases o al menos 1 tiro.
  4. Las posesiones de balón parado se marcan aparte y no se filtran por número de pases.
- **Unidad y nivel.** Bandera `is_valid_possession` en la tabla por posesión (una fila por posesión).
- **Umbrales.** 3 pases (`Umbrales.pdf`). Supuesto: cuentan pases intentados, completos o no.
- **No se considera.** Balón parado (`play_pattern` 2, 3 y 4) y `period` = 5.
- **Validación.** El número de posesiones por equipo antes del filtro debe parecerse a `team_match_possessions`. Se revisan a mano 10 posesiones fundidas para confirmar que fundirlas fue correcto.

## B2. Secuencia ofensiva

- **Qué mide.** Una posesión válida del EQ que llega al tercio final o termina en tiro, y qué tan efectiva fue.
- **Entrada.** [B1](01_objetos_base.md#b1-posesión-válida); `events`: `location`, `pass.end_location`, `carry.end_location`, `type.name`, `shot.statsbomb_xg`, `timestamp`.
- **Cálculo.** Sobre las posesiones válidas del EQ, es secuencia ofensiva si algún pase completo, conducción o regate completo del EQ entra al tercio final (termina en x ≥ 80) o si hay un `Shot`. Se guardan: `n_pases`, duración (diferencia de `timestamp` entre el primer y el último evento), xG de la secuencia (suma de `shot.statsbomb_xg`, sin penales) y si terminó en gol. La efectividad se mide con ese xG (`Umbrales.pdf`).
- **Unidad y nivel.** Por posesión; xG en goles esperados; duración en segundos.
- **Umbrales.** Tercio final: x ≥ 80.
- **No se considera.** Balón parado y `period` = 5. La secuencia termina cuando se pierde la posesión.
- **Validación.** La suma de xG de las secuencias de juego abierto debe parecerse a `team_match_op_xg`; las diferencias se explican con la regla de [V1](06_ocasiones_y_valor.md#v1-xg-y-uplift-de-ejecución).

## B3. Fase de inicio

- **Qué mide.** La salida del balón desde el primer tercio.
- **Entrada.** [B1](01_objetos_base.md#b1-posesión-válida); `events`: `location`, `pass.end_location`, `carry.end_location`, `type.name`, `under_pressure`, `play_pattern.id`.
- **Cálculo.** En cada posesión válida del EQ cuyo primer evento con balón ocurre en x < 40, la fase de inicio va desde ese evento hasta el primer pase completo o conducción del EQ que termina en x ≥ 40 (la salida), o hasta que se pierde la posesión. Salida lograda = el balón llega al segundo tercio sin perder la posesión. Se reporta aparte cuántas salidas ocurren con `under_pressure = True` y con `False` (lectura de «evitando presiones»; ver [punto por confirmar 2](09_puntos_por_confirmar.md)).
- **Unidad y nivel.** Por posesión; tasa de salidas logradas y % de salidas bajo presión, por partido.
- **Umbrales.** Primer tercio: x < 40.
- **No se considera.** Balón parado (`play_pattern` 2, 3 y 4) y `period` = 5.
- **Validación.** Las posesiones que empiezan en x < 40 deben coincidir con las que tienen `location_bucket = defensive_third` en su primer evento del EQ. Se revisan a mano 10 salidas en un mapa.

## B4. Fase de construcción

- **Qué mide.** Los pases del EQ desde el segundo tercio que buscan llegar a una secuencia ofensiva.
- **Entrada.** [B1](01_objetos_base.md#b1-posesión-válida) y [B2](01_objetos_base.md#b2-secuencia-ofensiva); `events`: `type.name = Pass`, `location`, `pass.outcome.name`, `team.id`.
- **Cálculo.** Pases del EQ con 40 ≤ `location.x` < 80 dentro de una posesión válida. Se marca `con_destino` cuando esa posesión llega a ser secuencia ofensiva ([B2](01_objetos_base.md#b2-secuencia-ofensiva)). Métricas: número de pases de construcción, % completos y % de posesiones con pases de construcción que llegan a secuencia ofensiva.
- **Unidad y nivel.** Conteo y porcentaje por partido.
- **Umbrales.** Segundo tercio: 40 ≤ x < 80.
- **No se considera.** Balón parado, pases de posesiones inválidas y `period` = 5.
- **Validación.** La suma de pases del EQ en juego abierto en los tres tercios debe cuadrar con `team_match_op_passes`.

## B5. Fase de presión

- **Qué mide.** Una ráfaga de presiones del EQ para recuperar el balón.
- **Entrada.** `events`: `type.name` (`Pressure`, `Ball Recovery`, `Duel`, `Interception`), `duel.type.name`, `team.id`, `period`, `timestamp`, `location`.
- **Cálculo.** Intento = `Pressure`, `Ball Recovery`, `Duel` con `duel.type.name = Tackle` o `Interception` del EQ. Se ordenan por `(match_id, period, timestamp)`. Una fase es un grupo de al menos 3 intentos en los que cada uno queda a menos de 10 s del anterior. Se guardan inicio, fin, n de intentos, x medio y si el EQ recuperó la posesión durante la fase o en los 5 s siguientes. Variante de sensibilidad: contar solo `Pressure`.
- **Unidad y nivel.** Por fase; número de fases y duración promedio por partido.
- **Umbrales.** 3 intentos y 10 s (sugerido en `Umbrales.pdf`).
- **No se considera.** `period` = 5.
- **Validación.** La suma de `Pressure` del EQ por partido debe coincidir con `team_match_pressures`. Se revisan 10 fases en un mapa.

## B6. Contragolpe

- **Qué mide.** Una posesión que nace de una pérdida rival y avanza rápido y en línea recta.
- **Entrada.** `events`: `play_pattern.id`, `possession_directness`, `location`, `pass.end_location`, `carry.end_location`.
- **Cálculo.** Contragolpe = posesión del EQ con `play_pattern.id = 6` (From Counter). Verificación de los criterios de `Umbrales.pdf`: `possession_directness` ≥ 0.75, avance (x máximo alcanzado − x del primer evento) ≥ 18 yardas y primer evento en x ≥ 40 (fuera del tercio más cercano a su propia portería).
- **Unidad y nivel.** Por posesión; conteo y xG por partido.
- **Umbrales.** 75% de `directness` y 18 yardas.
- **No se considera.** Posesiones sin `possession_directness` (fuera de juego abierto) y `period` = 5.
- **Validación.** Casi el 100% de las posesiones con `play_pattern` 6 debe cumplir los dos criterios; el porcentaje que no cumple se reporta como discrepancia.
