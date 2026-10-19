[Volver al índice](README.md)

# 5. Espacio

## Resumen general

Las dos fichas que ubican cada evento en la cancha: coordenadas, tercios, celdas y zona 14 en E1, y distancia y ángulo a la portería en E2.

## E1. x, y, end_x, end_y, third, cell_6x5, zona 14

- **Qué mide.** Dónde ocurre cada evento y dónde termina.
- **Entrada.** `events`: `location`, `pass.end_location`, `carry.end_location`, `shot.end_location`, `location_bucket`.
- **Cálculo.** `x`, `y` = primer y segundo valor de `location`. `end_x`, `end_y` = el `end_location` que corresponda al tipo de evento (`Pass`, `Carry` o `Shot`; en `Shot` se ignora z). `third` según x (< 40, 40–80, ≥ 80). `cell_6x5`: columna = min(⌊x/20⌋, 5) y fila = min(⌊y/16⌋, 4), celdas de 20 × 16 yardas, id de 0 a 29 (campograma de 6 columnas por 5 filas). `zona 14` = 80 ≤ x < 102 y 26.7 ≤ y ≤ 53.3.
- **Unidad y nivel.** Yardas y entero; una fila por evento.
- **Umbrales.** Celdas de 20 × 16 yardas. Zona 14 (propuesta: el reporte de StatsBomb solo la describe como la franja central frente al área).
- **No se considera.** Los eventos sin `location` (cerca del 1%): quedan en nulo, no se imputan.
- **Validación.** x debe estar entre 0 y 120 y y entre 0 y 80. `location_bucket` debe coincidir con `third` en juego abierto.

## E2. Distancia y ángulo a portería

- **Qué mide.** Qué tan cerca está la portería y qué tan abierto es el ángulo de tiro desde la posición del evento.
- **Entrada.** `events`: `location`.
- **Cálculo.** `dist_goal = √((120 − x)² + (40 − y)²)`, hacia el centro de la portería [120, 40]. `ángulo = |atan2(44 − y, 120 − x) − atan2(36 − y, 120 − x)|`, con los postes en y = 36 y y = 44, convertido a grados.
- **Unidad y nivel.** Yardas y grados; una fila por evento (se usa sobre todo en tiros).
- **Umbrales.** Portería de 8 yardas de ancho (postes en y = 36 y y = 44).
- **No se considera.** Eventos sin `location`. Los eventos del rival se espejan antes de calcular.
- **Validación.** Los penales (x = 108, y = 40) deben dar 12 yardas. En los tiros, el xG debe bajar al aumentar la distancia.
