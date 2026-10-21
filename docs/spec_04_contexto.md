# Spec 04: métricas por contexto (scripts/04_contexto.py)

Estado: v0.2, 20-oct-2026 (correcciones de la revisión doble: cuatro lecturas, celdas de un partido sin IC, validaciones de la tabla de cada métrica y ajuste con estratos fijos). Dueño: Yordi. Referencia: plan de trabajo, tarea 14.6 de la fase 4; nombres de salidas, columnas y métricas aprobados por el equipo el 20-oct (este documento es la referencia); salidas de `03_contexto.py` (`docs/spec_03_contexto.md`).

## Problema

La pregunta de la fase 4 es si Jardine ajusta el juego del América según el contexto: el marcador, la localía, la fuerza del rival, el minuto, la fase del torneo y la superioridad numérica. Para contestarla no basta con promedios por grupo: los grupos tienen tamaños muy distintos (37 partidos perdiendo contra 91 empatando, 21 posesiones en tiempo extra) y las posesiones de un mismo partido no son independientes. `04_contexto.py` toma las tablas de contexto de la fase 3, calcula cada métrica en cada nivel de cada contexto con su intervalo del 95% y su n, y compara cada nivel contra un nivel de referencia con una diferencia, un tamaño de efecto y una lectura corta. Los intervalos salen de un bootstrap que remuestrea partidos completos. Las métricas viven en un registro al inicio del script, así que otra persona agrega la suya con una entrada nueva sin tocar el resto del código.

## Salidas (nombres aprobados por el equipo el 20-oct, en constantes al inicio del script)

- `data/processed/celdas_contexto.parquet`: una fila por (`metrica`, `contexto`, `nivel`), con todos los niveles de la lista fija del contexto aunque alguno quede vacío.
- `data/processed/comparaciones_contexto.parquet`: una fila por (`metrica`, `contexto`, `nivel`, `ajuste`), sin el nivel de referencia.

`celdas_contexto`:

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `metrica`, `etiqueta_metrica`, `unidad`, `agregacion` | string | Del registro `METRICAS`. |
| `nivel_dato` | string | Sale de la llave: (`match_id`, `possession`) → `posesion`; (`match_id`, `index`) → `evento`; (`match_id`) → `partido`. |
| `contexto`, `nivel` | string | Contexto y nivel en texto (ver abajo). |
| `es_referencia` | boolean | El nivel es la referencia del contexto. |
| `valor` | float64 | Métrica en la celda, con todas las filas. Nulo solo si la celda está vacía. |
| `ic_inf`, `ic_sup` | float64 | Percentiles 2.5 y 97.5 de las réplicas bootstrap en que la celda no queda vacía. Nulos si la celda tiene menos de 2 partidos o si menos del 90% de las réplicas tienen valor. |
| `n_obs` | Int64 | Filas de la celda: posesiones, eventos o partidos según `nivel_dato`. |
| `n_partidos` | Int64 | Partidos distintos que aportan filas a la celda. |
| `inestable` | boolean | `n_partidos` < 10, o `n_obs` < 100 cuando `nivel_dato` es `posesion` o `evento`. |

`comparaciones_contexto`:

| Columna | Tipo | Regla |
| :--- | :--- | :--- |
| `metrica`, `contexto`, `nivel`, `referencia` | string | `referencia` es el nivel de referencia del contexto. |
| `ajuste` | string | `simple` siempre; además `mitad_x_tercil` en `score_state` cuando `nivel_dato` es `posesion` o `evento`. |
| `diferencia`, `dif_ic_inf`, `dif_ic_sup` | float64 | Nivel menos referencia, en la unidad de la métrica, con su IC del 95%. |
| `tipo_efecto` | string | `g de Hedges` (media), `h de Cohen` (proporcion y ponderada), `dif/MAD` (mediana). |
| `efecto`, `efecto_ic_inf`, `efecto_ic_sup` | float64 | Efecto estandarizado con su IC del mismo bootstrap. |
| `n_obs_nivel`, `n_obs_ref`, `n_partidos_nivel`, `n_partidos_ref` | Int64 | Los de las dos celdas (en `mitad_x_tercil`, los de la fila `simple`). |
| `inestable` | boolean | Alguna de las dos celdas es inestable. |
| `lectura` | string | `diferencia`, `diferencia pequena`, `indicio` o `sin diferencia clara`. |

### Contextos, niveles y referencias

| Contexto | Niveles, en orden (la referencia primero) | Fuente del nivel |
| :--- | :--- | :--- |
| `score_state` | `empatando`, `perdiendo`, `ganando` | texto de la columna |
| `is_home` | `visitante`, `local` | False → `visitante`, True → `local` |
| `rival_strength_tercil` | `débil`, `medio`, `fuerte` | texto de la columna |
| `minute_bin` | `0-15`, `15-30`, `30-45`, `45+`, `45-60`, `60-75`, `75-90`, `90+`, `ET` | texto de la columna |
| `stage` | `regular`, `fase final` | texto de la columna |
| `numerical_state` | `igualdad`, `inferioridad`, `superioridad` | entero: < 0, 0, > 0 |

El contexto se pega por la llave desde la tabla de la fase 3 que le toca al nivel de dato: `contexto_posesiones` (más `is_home` de `contexto_partidos` por `match_id`), `contexto_eventos` (carga perezosa, solo si alguna métrica la pide) o `contexto_partidos`. Las métricas por partido solo se cruzan con `is_home`, `rival_strength_tercil` y `stage`. Una fila con el contexto nulo no entra en ese contexto, pero sí en los demás.

### Registro `METRICAS` y las 16 métricas de la fase

Cada entrada es un `Metrica` (dataclass congelada) con `metrica`, `etiqueta`, `unidad`, `ruta`, `llave`, `columna`, `agregacion`, `filtro` y `peso`.

- `metrica` solo lleva minúsculas, dígitos y guion bajo (`^[a-z0-9_]+$`); `etiqueta` no puede estar vacía. `unidad` es una lista abierta: las de esta fase son `s`, `pases`, `proporcion`, `xG`, `yardas`, `puntos` y `goles`, y una métrica nueva puede traer otra.
- `filtro` se escribe como dict columna = valor y se guarda inmutable. Un valor puede ser una lista o tupla, y entonces la condición es "columna en la lista". Se aplica después de pegar el contexto, así que puede usar columnas de la tabla de la métrica o de su contexto.
- `ruta` no puede ser la tabla de contexto de otro nivel (por ejemplo `contexto_partidos` con llave de posesión).
- `columna` y `peso` tienen que ser numéricas o booleanas.
- Se quitan siempre las posesiones con `es_administrativa` y, si la tabla de la métrica trae `es_administrativo`, también esas filas. Cada métrica excluye los nulos de su `columna` y, en `ponderada`, las filas con `peso` nulo o 0 (el script imprime cuántas quitó por peso 0).
- Una métrica de evento tiene que traer `es_eq` en su propia tabla, porque `contexto_eventos` no lo tiene. Si una métrica de evento no filtra por `es_eq`, el script imprime un `AVISO`, ya que mezclaría los eventos de los dos equipos.

| `metrica` | Columna | Agregación | Unidad | Filtro |
| :--- | :--- | :--- | :--- | :--- |
| `duracion` | `duracion` | mediana | `s` | `es_eq` = True |
| `pases` | `n_pases` | media | `pases` | `es_eq` = True |
| `con_tiro` | `con_tiro` (derivada) | proporcion | `proporcion` | `es_eq` = True |
| `xg` | `xg` | media | `xG` | `es_eq` = True |
| `valida` | `is_valid_possession` | proporcion | `proporcion` | `es_eq` = True |
| `altura_inicio` | `x_inicio` | media | `yardas` | `es_eq` = True |
| `inicio_ultimo_tercio` | `inicio_ultimo_tercio` (derivada) | proporcion | `proporcion` | `es_eq` = True |
| `balon_parado` | `es_balon_parado` | proporcion | `proporcion` | `es_eq` = True |
| `tiempo_con_balon` | `es_eq`, peso `duracion` | ponderada | `proporcion` | ninguno (los dos equipos) |
| `xg_rival` | `xg` | media | `xG` | `es_eq` = False |
| `con_tiro_rival` | `con_tiro` (derivada) | proporcion | `proporcion` | `es_eq` = False |
| `puntos` | `puntos` (derivada) | media | `puntos` | partido |
| `goles_favor` | `goles_eq` | media | `goles` | partido |
| `goles_contra` | `goles_rival` | media | `goles` | partido |
| `tiempo_ganando` | `tiempo_ganando` (derivada) | media | `proporcion` | partido |
| `tiempo_perdiendo` | `tiempo_perdiendo` (derivada) | media | `proporcion` | partido |

Columnas derivadas, agregadas al cargar la tabla para que `columna` siga siendo un nombre de columna (solo para estas 16 métricas):

- `contexto_posesiones`: `con_tiro` = `n_tiros` > 0 (cuenta penales; el `xg` no los cuenta); `inicio_ultimo_tercio` = `third_inicio` es `final_third`.
- `contexto_partidos`: `puntos` = 3, 1 o 0 con `goles_eq` contra `goles_rival`; `tiempo_ganando` y `tiempo_perdiendo` = `minutos_ganando` o `minutos_perdiendo` entre la suma de los tres `minutos_*`.

Puntos y goles: `goles_eq` y `goles_rival` vienen de los periodos 1 a 4 de C2, así que incluyen el tiempo extra y no cuentan la tanda de penales. Una serie de liguilla que se define en penales vale 1 punto, como un empate. Es una convención por partido para comparar contextos, no la tabla del torneo; en la liguilla no hay puntos reales, así que `puntos` × `stage` es solo descriptivo.

### Cómo agrega una métrica alguien del equipo

1. Calcula la columna en su propio script y la deja en un parquet de `data/processed/` con la llave de su nivel (y `es_eq` si es por evento). `derivar` es solo para las 16 métricas de esta fase; las métricas nuevas no se calculan dentro de `04_contexto.py`.
2. Agrega una entrada a `METRICAS` en su rama, por ejemplo `Metrica("pases_progresivos", "Pases progresivos por posesión", "pases", "data/processed/ataque_posesiones.parquet", ("match_id", "possession"), "n_pases_progresivos", "media", {"es_eq": True})`.
3. Corre `python scripts/04_contexto.py --sin-escribir` hasta que termine con código 0. Después abre el PR a `dev` y, ya integrado, se corre `python scripts/04_contexto.py` para regenerar las dos salidas.
4. El análisis se congela según el plan. Después del congelamiento, una métrica nueva se acuerda antes con el equipo.

### Estadística

- Bootstrap por partido: se remuestrean con reemplazo los `match_id` de `contexto_partidos` (91). B = 2,000 réplicas (`--replicas`), semilla 20261020 (`--semilla`). Se genera una sola matriz de multiplicidades B × partidos y se usa para todas las métricas, contextos y estratos, así que las réplicas de las dos celdas de una comparación son las mismas.
- Media, proporción y ponderada: por (partido, celda) se guardan n, Σw, Σwx y Σwx² (w = 1 salvo en ponderada); cada réplica es la matriz por esos estadísticos. Mediana: mediana ponderada por la multiplicidad del partido de cada fila (igual a la mediana de la muestra expandida, con el promedio de los dos centrales cuando el total es par). Las multiplicidades van en int32 y las réplicas se procesan en bloques de a lo más `MAX_ELEMENTOS_MEDIANA` (250,000) réplicas × filas: los bloques chicos caben en caché y son más rápidos que los grandes (0.29 s contra 0.72 s por contexto en `duracion`).
- IC del 95% por percentiles 2.5 y 97.5, sin las réplicas en que el valor queda indefinido. Si menos del 90% de las réplicas tienen valor (`MIN_REPLICAS_VIVAS`), el IC queda nulo.
- Celdas de un solo partido (`MIN_PARTIDOS_IC` = 2): al remuestrear partidos su valor no cambia, solo aparece o no, así que un IC no dice nada. Su `ic_inf` e `ic_sup` quedan nulos. En las comparaciones donde participan quedan nulos los IC de la diferencia y del efecto, y la lectura es `sin diferencia clara`. La celda sigue en la tabla con su valor y su n. Hoy son las 11 celdas de `minute_bin` = `ET`.
- Efectos: `g de Hedges` = J · (m1 − m0) / s_p, con s_p² = (SS1 + SS0) / (n1 + n0 − 2) y J = 1 − 3 / (4(n1 + n0) − 9); `h de Cohen` = 2·asin√p1 − 2·asin√p0; `dif/MAD` = (mediana1 − mediana0) / (1.4826 · MAD), con la MAD de la unión de las desviaciones de cada fila a la mediana de su celda, calculada en la muestra original y fija en las réplicas. Si la escala es 0 el efecto queda nulo.
- Ajuste `mitad_x_tercil` (solo `score_state`, solo posesión o evento): mitad = 1T si `minute_bin` es `0-15`, `15-30`, `30-45` o `45+`, y 2T en el resto (incluido `ET`); seis estratos = mitad × `rival_strength_tercil`. Los estratos que entran se fijan con la muestra original: los que tienen las dos celdas (nivel y referencia) con n > 0. La diferencia y el efecto ajustados son el promedio, ponderado por el n del nivel en el estrato, de la diferencia y el efecto de cada estrato. En una réplica en que alguno de esos estratos queda vacío, la réplica es nula, sin repartir el peso entre los demás; la misma máscara vale para la diferencia y el efecto. `inestable` y los n de la fila ajustada son los de la simple, pero el script imprime un `AVISO` por cada estrato que entra con menos de 10 partidos en alguna de sus dos celdas. Las filas sin `minute_bin` o sin tercil no entran en el ajuste.
- `lectura`, con ic0 = el IC de la diferencia no contiene el 0:
  - `diferencia`: ic0, |efecto| ≥ 0.2 y las dos celdas estables.
  - `diferencia pequena`: ic0, las dos celdas estables y |efecto| < 0.2.
  - `indicio`: ic0, |efecto| ≥ 0.2 y alguna celda inestable.
  - `sin diferencia clara`: cualquier otro caso, incluidos los IC nulos.
- Constantes con nombre al inicio: `MIN_PARTIDOS` = 10, `MIN_OBS` = 100, `EFECTO_MIN` = 0.2, `MIN_PARTIDOS_IC` = 2, `MIN_REPLICAS_VIVAS` = 0.9, `REPLICAS` = 2000, `SEMILLA` = 20261020, `TOL_IC` = 1e-12, `MAX_ELEMENTOS_MEDIANA` = 250,000.

## Cómo leer las tablas

- `diferencia`: el contexto mueve la métrica con un tamaño que se nota contra la dispersión entre posesiones (o entre partidos), y las dos celdas tienen datos suficientes. Es lo que la narrativa puede afirmar.
- `diferencia pequena`: el cambio es real en el sentido de que el IC no toca el 0, pero es chico contra la dispersión. Conviene leerlo en la unidad de la métrica: el 0.2 se mide contra la variación entre posesiones, que es grande, así que un ajuste táctico claro puede quedar aquí. Por ejemplo, `con_tiro` de 0.10 a 0.13 (30% más posesiones con tiro) da h ≈ 0.09.
- `indicio`: el efecto sería grande, pero alguna celda tiene pocos partidos o pocas posesiones. Sirve para señalar algo que revisar, no para afirmarlo.
- `sin diferencia clara`: no se puede afirmar un cambio. No prueba que no lo haya. Si el IC del efecto queda completo dentro de ±0.2, sí se puede escribir en la narrativa que no hay un cambio relevante; si el IC es ancho, solo que los datos no alcanzan.
- Hay 218 comparaciones: 176 simples de las 11 métricas de posesión (16 niveles cada una), 22 ajustadas `mitad_x_tercil` y 20 de las 5 métricas por partido. De las 207 que tienen IC (las 11 de `ET` no), si en ningún caso hubiera un efecto real cerca del 5% excluiría el 0 por azar, unas 10. Es aproximado, porque las comparaciones no son independientes (comparten referencia, partidos y métricas parecidas). Una `diferencia` aislada en un contexto donde el resto de las métricas no se mueve se lee con cuidado.

## Criterios de aceptación

- AC1: `python scripts/04_contexto.py` termina con código 0, escribe las dos tablas en `data/processed/` y tarda menos de 2 minutos con B = 2,000.
- AC2: `python scripts/04_contexto.py --sin-escribir` termina con código 0 y no crea ni cambia archivos en `data/processed/`.
- AC3: las dos salidas tienen exactamente las columnas y los tipos de las tablas de arriba, en ese orden, y su llave es única; si no, la corrida falla con código 1 sin escribir.
- AC4: para cada métrica y contexto, la suma de `n_obs` de sus niveles es igual a las filas usadas por la métrica con ese contexto no nulo; si un nivel no está en la lista fija, la suma no cuadra y la corrida falla con código 1.
- AC5: las celdas de las métricas del América cuadran con las cifras de la fase 3: 9,503 posesiones del América sin administrativas (3,388 válidas); `score_state` perdiendo 1,385 (37 partidos), empatando 5,030 (91) y ganando 3,088 (59); `numerical_state` inferioridad 48 (6), igualdad 8,822 (91) y superioridad 633 (615 con +1 y 18 con +2, 16 partidos, porque el partido con +2 también tuvo +1); `minute_bin` ET 21 posesiones de 1 partido; en las métricas por partido, local 45 y visitante 46, débil 23, medio 24 y fuerte 44, regular 66 y fase final 25.
- AC6: `valor` no es nulo en ninguna celda con `n_obs` > 0; si lo es, la corrida falla con código 1.
- AC7: la corrida falla con código 1, con un mensaje y sin traceback ni escritura, si: la `columna`, el `peso` o alguna columna de la llave no existen en la tabla de la métrica; `columna` o `peso` no son numéricas ni booleanas; una columna de `filtro` no está en la tabla ni en su contexto; la llave, la agregación, el id o la etiqueta no son válidos; `ruta` es la tabla de contexto de otro nivel; la tabla trae la llave repetida (con el conteo); alguna fila no encuentra su llave en la tabla de contexto (con el conteo y ejemplos); el merge falla por tipos incompatibles; o hay un `match_id` nulo o fuera de `contexto_partidos` (se revisa antes de filtrar, para que un partido ajeno no se pierda en silencio).
- AC8: las métricas por partido solo tienen filas de `is_home`, `rival_strength_tercil` y `stage`; las de posesión, de los seis contextos; solo `score_state` de posesión o evento tiene filas `mitad_x_tercil`.
- AC9: con la misma semilla y el mismo B, dos corridas dan tablas idénticas.
- AC10: `inestable` es True en las celdas con menos de 10 partidos o, en posesión y evento, menos de 100 filas; en comparaciones es True si alguna de las dos celdas lo es; `lectura` sigue las cuatro reglas de arriba.
- AC11: agregar una métrica es añadir una entrada a `METRICAS`: una métrica de evento corre sin tocar más código y solo entonces se carga `contexto_eventos`; si trae `es_administrativo`, esas filas se quitan.
- AC12: la escritura sigue el esquema de `03_contexto.py`: todo va a una carpeta temporal `data/processed/.tmp_04_contexto_*`, se revisa que ningún destino esté bloqueado y se reemplaza archivo por archivo; si falla, sale con 1 y no deja una tabla a medias sin decir cuál se reemplazó.
- AC13: la consola imprime las filas de cada salida, cuántas comparaciones hay por `lectura` y la lista de las `diferencia`, `diferencia pequena` e `indicio` (métrica, contexto, nivel, diferencia con IC y efecto). Los avisos informativos (IC que no contiene el valor puntual, celdas de un partido, IC nulos por pocas réplicas, celdas vacías en alguna réplica, estratos con menos de 10 partidos, métrica de evento sin filtro por `es_eq`) empiezan con `AVISO` y no cambian el código de salida.
- AC14: las celdas de un solo partido tienen `ic_inf` e `ic_sup` nulos, sus comparaciones tienen los cuatro IC nulos y lectura `sin diferencia clara`, y ningún otro IC es nulo con los datos de hoy.

## Fuera de alcance

- Métricas de ataque avanzado, presión, defensa y jugadores — son de Lee, Pablo y Pato; entran después como entradas nuevas de `METRICAS`.
- Leer cualquier cosa de `Local/` o salidas de otros integrantes — los insumos son solo las tablas de contexto de la fase 3.
- Gráficas y porcentajes — las proporciones quedan de 0 a 1 y las gráficas son de Pablo.
- Corrección por comparaciones múltiples — la lectura es descriptiva; la sección «Cómo leer las tablas» da la cifra de falsos positivos esperados para la narrativa.
- Comparar contra el grupo de contraste (Ortiz y Solari) — las tablas de la fase 3 son solo del América con Jardine.
- Interacciones entre contextos fuera de `mitad_x_tercil` — el brief solo pide ese ajuste para el marcador.
- Cambiar `03_contexto.py` o las tablas de la fase 3.

## Plan de pruebas

No hay tests ni linter: se verifica corriendo el script y leyendo las salidas. Para probar funciones sueltas o forzar fallas, el módulo se carga con `importlib`, porque su nombre empieza con un dígito:

```python
import importlib.util

spec = importlib.util.spec_from_file_location("c4", "scripts/04_contexto.py")
c4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c4)
c4.METRICAS.append(c4.Metrica("prueba", "Prueba", "xG", c4.POSESIONES, ("match_id", "possession"), "xg", "media"))
celdas, comparaciones, fallas = c4.calcular(c4.METRICAS, c4.Tablas(), 200, 1)
```

- AC1 → manual: `python scripts/04_contexto.py`, código 0, tiempo impreso al final.
- AC2 → manual: `--sin-escribir` con `data/processed/` listado antes y después (fechas y tamaños).
- AC3 → automático en el script (validación dura) y manual: `pd.read_parquet(...).dtypes`.
- AC4, AC6, AC7 → automáticos en el script; AC7 se fuerza cargando el módulo con métricas rotas (columna inexistente o de texto, llave repetida o ausente, fila sin contexto, tipos de llave incompatibles, `match_id` ajeno, registro inválido).
- AC5 → manual: leer `celdas_contexto` y comparar los `n_obs` y `n_partidos` de `valida`, `score_state`, `numerical_state`, `minute_bin` y de `puntos`.
- AC8 → manual: conteo de (`metrica`, `contexto`, `ajuste`) en las salidas.
- AC9 → manual: dos corridas y `assert_frame_equal`.
- AC10, AC14 → manual: recalcular `inestable`, `lectura` y los IC nulos desde las columnas de la salida.
- AC11 → manual: con el módulo cargado, agregar una métrica de evento (`dist_goal` de `contexto_eventos`) y otra de una tabla propia con `es_eq` y `es_administrativo`, y correr `calcular`.
- AC12 → manual: un destino de solo lectura debe dar código 1 sin reemplazar nada ni dejar `.tmp_04_contexto_*`.
- AC13 → manual: leer la salida de consola.
- Contraste de la estadística → manual: recalcular con pandas el `valor` de todas las celdas, una mediana, un `g de Hedges`, un `h de Cohen`, un `dif/MAD` y el ajuste de una comparación, y expandir a mano algunas réplicas.

## Desviaciones y decisiones fuera del brief

- `inestable` en métricas por partido: el umbral de 100 filas es de posesiones (propuesta: «menos de 10 partidos o menos de 100 posesiones»). En partido `n_obs` es el número de partidos, así que aplicarlo dejaría inestables todas las celdas por partido. Ahí solo cuenta `n_partidos` < 10. En evento se aplica igual que en posesión. Aprobado por el equipo el 20-oct.
- `nivel_dato` admite `evento` además de los dos valores de la propuesta, porque el registro acepta métricas por evento.
- Las celdas vacías (un nivel sin filas) se escriben con `n_obs` = 0 y `valor` nulo para que todas las métricas tengan los mismos niveles; sus comparaciones quedan sin IC y con `sin diferencia clara`.
- La carpeta temporal se llama `.tmp_04_contexto_*` y no `.tmp_contexto_*`, porque `03_contexto.py` borra las `.tmp_contexto_*` al terminar y podría borrar una temporal que este script dejó a propósito tras un reemplazo a medias (y al revés).
- `proporcion` y `ponderada` exigen valores entre 0 y 1 (validación dura), porque el `h de Cohen` solo tiene sentido ahí.
- `tiempo_con_balon` deja fuera 360 posesiones de duración 0. No cambian el valor ponderado, pero sí `n_obs`, que ahora cuenta solo filas con peso.
- Las etiquetas de las métricas llevan acentos, como el ejemplo aprobado («xG por posesión»), porque son texto para las gráficas.
- La consola: los mensajes del script van sin acentos, como en `03_contexto.py`, y la salida estándar usa `errors="replace"` para no romperse en una consola sin UTF-8. En la consola interactiva de Windows los niveles con acento (`débil`) se ven bien; si la salida se manda por tubería, depende de la codificación de quien la recibe.

## Alternativas descartadas

- Bootstrap por posesión — ignora que las posesiones de un mismo partido se parecen entre sí y da intervalos demasiado angostos.
- Remuestrear por separado cada celda — la diferencia y el efecto necesitan las mismas réplicas en las dos celdas; con una sola matriz de multiplicidades salen del mismo remuestreo de partidos.
- `scipy.stats.bootstrap` — agrega una dependencia y no remuestrea por grupo.
- Expandir las filas en cada réplica — 2,000 réplicas de 19 mil posesiones por métrica y contexto es mucho más lento que multiplicar estadísticos suficientes por la matriz de multiplicidades.
- Media para la duración — la duración máxima es de 1,431 s y movería la media; la mediana es robusta.
- Modelo mixto o regresión para el marcador — necesita dependencias y supuestos que el equipo no alcanza a revisar antes de la entrega; los estratos `mitad_x_tercil` controlan lo principal y se explican en una frase.
- Efecto estandarizado a nivel partido — con 91 partidos y celdas de 5 a 40 partidos sería muy ruidoso, y cambia la pregunta de "qué pasa en una posesión" a "qué pasa en un partido".
- IC BCa — necesita jackknife por partido y corrige poco con 2,000 réplicas; los percentiles bastan para una lectura descriptiva.
- Quitar o fundir `ET` con `90+` — cambiaría las categorías de la fase 3; se deja la celda con su n y sin IC.
- Otras convenciones de puntos en liguilla (por ejemplo, contar el global o dar 2 puntos al que avanza en penales) — ninguna es estándar; 3/1/0 por partido es la única que se compara igual en fase regular y liguilla.
- Umbral 0.1 en lugar de la categoría `diferencia pequena` — bajaría la vara para todo; la categoría aparte deja ver los cambios chicos sin mezclarlos con los grandes.

## Resultado de la corrida (20-oct, v0.2)

Código 0, de 2 a 4 s con B = 2,000 según la corrida (`--sin-escribir` igual, sin cambios en `data/processed/`). `celdas_contexto`: 277 filas (11 métricas de posesión × 22 niveles + 5 de partido × 7 niveles); `comparaciones_contexto`: 218 filas. Dos corridas con la misma semilla dan tablas idénticas (`assert_frame_equal`).

- Cuadre (métrica `valida`): 9,503 posesiones del América y 3,388 válidas; `score_state` 1,385 (37) / 5,030 (91) / 3,088 (59); `numerical_state` 48 (6) / 8,822 (91) / 633 (16); `minute_bin` ET 21 (1). Por partido: local 45, visitante 46; débil 23, medio 24, fuerte 44; regular 66, fase final 25. `duracion` usa 9,501 filas (2 nulas) y `tiempo_con_balon` 18,420 (de 18,784 no administrativas: 4 sin duración y 360 con duración 0).
- Contraste con pandas: el `valor` y el `n_obs` de las 277 celdas cuadran con un `groupby` independiente (diferencia máxima 4e-14); el `g de Hedges`, el `h de Cohen`, el `dif/MAD` y el ajuste `mitad_x_tercil` de una comparación cada uno cuadran exactos; la media y la mediana de 4 réplicas de 3 celdas cuadran con la muestra expandida a mano. `inestable` y `lectura` se recalculan desde las columnas sin diferencias.
- Lecturas: 11 `diferencia`, 50 `diferencia pequena`, 0 `indicio` y 157 `sin diferencia clara`. El marcador solo mueve con efecto ≥ 0.2 el `tiempo_con_balon` (perdiendo +0.113, que queda en +0.101 con el ajuste); el resto de sus cambios son `diferencia pequena` (por ejemplo, `altura_inicio` ganando −6.2 yardas con el ajuste).
- IC nulos: solo las 11 celdas de `ET` y sus 11 comparaciones. Ningún otro IC queda nulo por la regla del 90% (inferioridad queda vacía en 0.3% de las réplicas). Ningún IC calculado deja fuera su valor puntual.
- Estratos del ajuste con menos de 10 partidos en alguna celda (mínimo entre métricas): 1T-débil (perdiendo 7, ganando 9), 1T-medio (perdiendo 7), 1T-fuerte (perdiendo 9), 2T-débil (perdiendo 8) y 2T-medio (perdiendo 5).
- Fallas forzadas, todas con código 1, un mensaje sin traceback y las salidas sin cambios: columna inexistente, columna de filtro inexistente, columna de texto, llave ausente, llave repetida, fila sin contexto, llave de tipo incompatible, `match_id` ajeno, `ET` quitado de la lista de niveles, registro inválido (agregación, llave, peso, ruta de contexto de otro nivel, id con mayúsculas, etiqueta vacía) y un destino de solo lectura (detectado antes de reemplazar, sin temporales sueltas).
- Extensión: con una métrica de evento (`dist_goal` de `contexto_eventos`), una de una tabla propia por posesión y otra de una tabla propia por evento con `es_eq` y `es_administrativo`, el registro corre sin tocar más código. La de evento sin filtro por `es_eq` da su `AVISO`, la tabla propia por posesión da lo mismo que `xg` y la de evento quita las 1,588 filas administrativas del América. Un filtro con lista de valores (`play_pattern_name` en córner o tiro libre) da el n esperado, y el filtro no se puede modificar después de crear la métrica.

### Cumplimiento

- AC1 a AC14: cumplidos (ver arriba).
- Fuera de alcance: respetado. El script solo lee las tres tablas de contexto de `data/processed/` y las tablas que declare `METRICAS`.
