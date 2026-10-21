[Volver al índice](README.md)

# 5. Métricas finales

## Resumen general

La definición final de los ocho objetos con los que el equipo describe el juego: qué mide cada uno, cómo se reconoce, en qué unidad se cuenta y desde qué umbral cuenta. Son las palabras que usan el HTML y el video. Al final, una tabla dice dónde se calcula cada uno en el código y en qué se aparta de esta definición.

## Definiciones

| Métrica | Qué mide | Fórmula o consideración | Unidad | Umbral |
| :--- | :--- | :--- | :--- | :--- |
| Posesión válida | Tramo en el que un equipo demuestra control efectivo del balón. | Los toques rivales sin dirección no cambian la posesión. | Conteo (pases o tiros) | Mínimo 3 pases (si no es a balón parado) o al menos 1 tiro. |
| Transición | Cómo actúa el equipo justo después de un cambio de control del balón. | Reacción tras perder el balón (defensiva) o tras recuperarlo (ofensiva). | Tiempo (segundos) | Los primeros 5 segundos tras ganar o perder la posesión. |
| Secuencia ofensiva | Posesión que amenaza a la defensa rival. Su efectividad se puede medir con la suma de xG. | Toda secuencia de pases profunda o jugada que termine en una oportunidad a puerta. | Conteo y xG | Cruce al tercio final de la cancha o finalización en tiro. |
| Fase de construcción | Secuencias que estructuran un ataque hacia la zona rival. | Todos los pases que buscan llegar a una secuencia ofensiva. | Geográfica (tercios) y conteo de secuencias | Ocurre solo dentro del segundo tercio de la cancha. |
| Fase de inicio | Salida estructurada desde la propia zona defensiva. | Toda salida controlada que evita las presiones rivales en esa zona. | Geográfica (tercios) y conteo de secuencias | Salida desde el primer tercio de la cancha. |
| Fase de presión | Esfuerzo colectivo para forzar una pérdida o recuperar la posesión. | Conjunto de acciones de presión sobre el rival agrupadas en poco tiempo. | Intentos de recuperación y tiempo | 3 intentos de recuperación o presión en menos de 10 segundos. |
| Zona de presión alta | Bloque de presiones aplicadas lo más cerca posible del arco rival. | Todo evento de presión en la zona defensiva del rival. | Geográfica (metros) | Últimos 40 metros de la cancha rival. |
| Salto de líneas | Acción que supera la estructura defensiva y genera un espacio aprovechable. | Pase acertado que divide o supera el posicionamiento del rival. | Conteo (pases) | Cruce de al menos 1 de los 3 bloques horizontales del rival (delanteros, mediocampistas o defensas). |

## Dónde se calculan

| Métrica | Dónde está | Diferencia con la definición |
| :--- | :--- | :--- |
| Posesión válida | `03_contexto.py` (Yordi), columna `is_valid_possession` de `contexto_posesiones` (ficha B1) | Un penal no cuenta como el tiro que vuelve válida una posesión. |
| Transición | `03_defensa.py` (Pablo): `defensa_transiciones` (ficha D5, ventana de 5 s) y `regain_5s` de `defensa_perdidas` (ficha D3) | Ninguna. |
| Secuencia ofensiva | `03_ataque.py` (Lee), dentro de `build_up_chain` (ficha I5): llegar a x ≥ 80 o terminar en tiro | No tiene columna propia y su xG no se guarda aparte. |
| Fase de construcción | Sin columna propia | `build_up_chain` cubre la cadena completa, del tercio propio al último. |
| Fase de inicio | `build_up_chain` exige que la posesión empiece en el tercio propio (`x_inicio` < 40) | Mide la cadena completa, no solo la salida. |
| Fase de presión | `03_defensa.py` (Pablo), `defensa_fases_presion` (ficha B5) | Pablo agrupa al menos 3 intentos con menos de 10 s entre uno y el siguiente. Si «en menos de 10 segundos» quiere decir 10 s en total, sus fases pueden durar más. Falta que Pato y Pablo lo confirmen. |
| Zona de presión alta | `03_defensa.py` (Pablo), `presiones_altas_40m` y `pct_presiones_altas_40m` de `defensa_partidos` (x ≥ 76.26 yardas) | Con 40 metros, estas son las columnas que valen (26.9% de las presiones son altas). `pct_presiones_altas` usa 40 yardas, el supuesto que había tomado Lee, y da 23.7%. |
| Salto de líneas | `03_ataque.py` (Lee), `line_breaking_pass` (ficha I3) | Usa la marca del 360 de StatsBomb en lugar de contar los 3 bloques. Solo existe en eventos con frame 360. |
