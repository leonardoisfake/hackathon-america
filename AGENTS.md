# AGENTS.md

Contexto del repo para quien trabaje en él, sea persona o agente de IA. Todo está en español.

## Qué es este repo

Es el código del equipo para el Hackathon ITAM + Club América: un análisis táctico de André Jardine con el América (`manager_id` 1000116, `team_id` 1229), del Apertura 2023 al Clausura 2025. Son 91 partidos: 66 de fase regular y 25 de liguilla, de los cuales 8 son finales (2 por torneo). Los datos son de Hudl StatsBomb (eventos y 360). El grupo de contraste son Fernando Ortiz y Santiago Solari, también del América.

La entrega es el jueves 22 de octubre de 2026 por correo. La meta interna es tener el análisis congelado el martes 20.

## Equipo y ramas

| Persona | Rol | Rama |
| :--- | :--- | :--- |
| Yordi | Datos | `A/datos` |
| Lee | Métricas | `B/metricas` |
| Pablo | Visualización | `C/visualizacion` |
| Pato | Narrativa y coordinación | `D/narrativa` |

## Reglas que no se rompen

Datos:

- Los datos de StatsBomb no se publican y no van al repo. `.gitignore` excluye `data/`, `*.parquet`, `*.json`, `*.csv` y `*.xlsx`. La única excepción es `docs/contrato/contrato_datos.csv`.
- Los datos se comparten por un Drive privado del equipo, con la misma estructura de carpetas (`data/raw/parquet/`, `data/interim/` y `data/processed/`). La caché JSON de la API (`data/raw/*.json`) no se comparte: cada quien la regenera con `sb_api.py`.
- Al HTML y a cualquier repositorio público solo llegan resultados, nunca datos crudos.

Credenciales:

- Viven en `.env` (variables `SB_USER` y `SB_PASS`). No se leen en voz alta, no se imprimen y no se suben.

Git:

- Todos los PR van a `dev`. No se hace nada hacia `main`.
- La rama por defecto de GitHub es `main`, así que al abrir un PR hay que cambiar la base a `dev` y verificarla.
- Los archivos se agregan uno por uno, nunca con `git add .`.
- Los commits siguen Conventional Commits en español, por ejemplo `feat(limpieza): ...` o `docs(contrato): ...`.
- Los commits y los PR no llevan atribución a ninguna IA: ni `Co-Authored-By` ni "Generated with".

Estilo de trabajo:

- Scripts `.py`, no notebooks.
- Comentarios en español. Los de una línea van con `#`; el docstring se usa solo cuando son varias líneas o cuando argparse lo muestra como ayuda.
- No hay tests ni linter. La verificación es correr los scripts y `contrato.validar()` (ver [Cómo verificar un cambio](#cómo-verificar-un-cambio)).
- No te adelantes al plan: cada entrega cubre solo la fase del día.

## Mapa del repo

| Ruta | Qué hay |
| :--- | :--- |
| `sb_api.py` | Acceso a la API de StatsBomb con caché en `data/raw/`. Lee las credenciales de `.env` y define `TEMPORADAS_RETO` (108, 235, 281, 317). |
| `scripts/01_descarga.py` | Fase 1. Baja los partidos de un entrenador y los guarda en parquet crudo. |
| `scripts/02_limpieza.py` | Fase 2. Limpia el crudo según el contrato y escribe `data/interim/`. |
| `scripts/03_contexto.py` | Fase 3. Contexto y espacio por evento, posesión y partido (fichas B1, C1 a C5, E1 y E2 de Lee). Escribe `data/processed/`. |
| `scripts/contrato.py` | Lee el contrato (`cargar`, `esquema`, `vacio`, `validar`) y define `ADMINISTRATIVOS`. |
| `scripts/gen_contrato.py` | Genera todo `docs/contrato/` desde los parquet crudos. |
| `docs/contrato/` | Contrato de datos: `README.md`, un `.md` por tabla, `cambios.md` y `contrato_datos.csv`. |
| `docs/spec_01_descarga.md` | Especificación de la descarga: criterios de aceptación, alternativas descartadas, pendientes. |
| `docs/inventario_descarga.md` | Reporte de la última descarga completa (17 de octubre): filas por tabla, cobertura 360, partidos excluidos. |
| `docs/spec_03_contexto.md` | Especificación del contexto: columnas, desviaciones de las fichas, regla de B1 y criterios de aceptación. |
| `requirements.txt` | `pandas==3.0.5`, `pyarrow==26.0.0`, `requests==2.33.1`. |
| `data/` | Local e ignorado por git. `data/raw/` (caché JSON y `parquet/`), `data/interim/` (tablas limpias), `data/processed/` (tablas de la fase 3), `data/diccionario.json` (lo lee `gen_contrato.py`). |

Fuera del repo, en la carpeta `Local` del equipo:

- `Plan_de_trabajo_Kpumas.md`: el plan. Las secciones 7.1 a 7.3 definen la limpieza; la 12 y la 14 dan el calendario y el reparto por fase.
- `METRICAS_LEE.md`: la especificación de métricas de Lee (34 fichas). La sección 1 reúne las convenciones comunes. Las mismas fichas llegan al repo en `especificaciones_metricas/`, por la rama de Lee.

De la fase 3 solo existe `scripts/03_contexto.py`. Los demás scripts `03_*.py`, los `04_*.py` y `graficas.py` todavía no están en ninguna rama. Por la rama de Lee llegan `scripts/02_auxiliares.py`, que arma las 4 tablas auxiliares del contrato desde los eventos crudos (se corre después de `02_limpieza.py` con `python scripts/02_auxiliares.py`), y dos scripts de revisión, `control_calidad.py` y `gen_reporte_nulos.py`, que escriben CSV en `data/interim/`.

## Cómo correr el pipeline

Instala con `pip install -r requirements.txt` y corre todo desde la raíz del repo.

### Descarga

```
python scripts/01_descarga.py                          # los 91 partidos de Jardine
python scripts/01_descarga.py --linea-base             # además, team_match_stats de toda la liga
python scripts/01_descarga.py --solo-partido 3995374   # prueba con un partido
python scripts/01_descarga.py --limite 3               # prueba con los primeros 3 partidos
```

Otros argumentos: `--manager-id`, `--team-id` y `--pausa` (segundos entre llamadas HTTP reales, 0.3 por defecto).

| Modo | Parquet | Inventario |
| :--- | :--- | :--- |
| Ids por defecto | `data/raw/parquet/` | `docs/inventario_descarga.md` |
| Otros ids | `data/raw/parquet/m{manager}_t{team}/` | `docs/inventario_descarga_m{manager}_t{team}.md` |
| `--solo-partido` o `--limite` | `data/raw/parquet_prueba/` | `docs/inventario_descarga_prueba.md` |

- Produce `partidos`, `events`, `frames_360`, `lineups`, `team_match_stats` y `player_match_stats`, más `team_match_stats_liga` con `--linea-base`. Las listas y dicts quedan como texto JSON.
- Un parquet de más de 50 MB se parte por torneo (`events__Apertura_2023.parquet`).
- Se puede reanudar: no vuelve a pedir lo que ya está en `data/raw/*.json`.
- Códigos de salida: 0 bien; 1 hubo fallos o el resultado no cuadra con 91 partidos, 25 de liguilla y 8 `es_final`; 2 credenciales faltantes o rechazadas, o filtro vacío.

### Limpieza

```
python scripts/02_limpieza.py --solo-partido 3995374   # escribe en data/interim/muestra/
python scripts/02_limpieza.py                          # todos los partidos, escribe en data/interim/
```

- Produce nueve parquet: `partidos`, `eventos`, `frames_360`, `frames_360_evento`, `alineaciones`, `posiciones`, `team_match_stats`, `player_match_stats` y `team_match_stats_liga`.
- Escribe además tres CSV de control: `partidos_excluidos.csv`, `calidad_limpieza.csv` y `cobertura_360_por_partido.csv`. El contrato los describe en la sección "Salidas de control de `02_limpieza.py`".
- Antes de escribir valida cada tabla con `contrato.validar()` y revisa cobertura, llaves duplicadas y huérfanos. Si algo falla no escribe nada.

| Código | Significa |
| :--- | :--- |
| 0 | Todo se escribió. |
| 1 | Error de datos, contrato, cobertura o escritura. Casi siempre sin escribir nada; si el reemplazo queda a medias, el mensaje dice qué archivos se reemplazaron y dónde quedó la carpeta temporal. |
| 2 | Con `--solo-partido`, el partido no existe o no pasa los filtros de calidad. |

### Contexto

```
python scripts/03_contexto.py                  # escribe en data/processed/
python scripts/03_contexto.py --sin-escribir   # calcula y valida, sin escribir
```

Lee `eventos`, `partidos`, `posiciones`, `team_match_stats` y `team_match_stats_liga` de `data/interim/`, así que va después de `02_limpieza.py`. Tarda unos 4 segundos y produce cuatro parquet:

| Tabla | Una fila por | Llave |
| :--- | :--- | :--- |
| `contexto_eventos` | evento (317,849) | `match_id`, `index` |
| `rival_strength` | equipo y torneo de toda la liga, sin el América (136) | `team_id`, `torneo` |
| `contexto_posesiones` | posesión de StatsBomb de los periodos 1 a 4 (19,053) | `match_id`, `possession` |
| `contexto_partidos` | partido (91) | `match_id` |

- Escribe además `control_posesiones_fundidas.csv`, para revisar B1 a mano.
- Las tablas no copian `eventos`: traen la llave y las columnas nuevas, y se usan con un `merge` por la llave.
- `score_state`, `goal_diff`, `numerical_state` y `rival_strength_tercil` se leen siempre desde el América, también en los eventos y las posesiones del rival.
- Para contar posesiones hay que excluir las que tienen `es_administrativa` en True (solo traen alineación, medio tiempo o cambios). La posesión válida de B1 es `is_valid_possession`.
- Códigos de salida: 0 si todo pasó (y se escribió, cuando se pidió); 1 si falló una validación dura, falta un dato o falló la escritura. Si falla una validación no escribe nada. Las validaciones y las desviaciones de las fichas están en `docs/spec_03_contexto.md`.

### Contrato

```
python scripts/gen_contrato.py                         # regenera docs/contrato/
python scripts/contrato.py eventos data/interim/muestra/eventos.parquet   # valida un parquet
```

`gen_contrato.py` lee `data/raw/parquet/` y `data/diccionario.json`, así que necesita los datos locales. `diccionario.json` no está en el repo; quien vaya a regenerar el contrato se lo pide a Yordi o lo toma del Drive.

## El contrato de datos

Está en `docs/contrato/`. Empieza por `README.md` (convenciones, resumen de las 13 tablas y tabla de decisiones C1 a C21) y sigue con el `.md` de la tabla que uses. `contrato_datos.csv` es la versión ejecutable: tabla, columna, tipo, origen, regla, `relleno` y `puede_faltar`. Versión actual: v0.2, del 18 de octubre.

Convenciones clave:

- Unidad: yardas, cancha de 120 x 80, ataque hacia x = 120.
- `x`, `y`, `end_x` y `end_y` vienen en la perspectiva del equipo del evento. Para comparar al equipo analizado con sus rivales en una misma cancha se usan `x_eq`, `y_eq`, `end_x_eq` y `end_y_eq`.
- Llaves: `eventos` (`match_id`, `index`); `frames_360` (`match_id`, `event_uuid`, `jugador_idx`); `frames_360_evento` (`match_id`, `event_uuid`); `partidos` (`match_id`). Ordena siempre por (`match_id`, `index`).
- Los nulos legítimos no se imputan. Las banderas que solo aparecen cuando son verdaderas se rellenan con False.
- Todo texto pasa por strip. Las categorías salen de cada corrida, así que hay que alinearlas antes de concatenar tablas.
- Tipos: `Int64`, `float64`, `boolean`, `string`, `category` y `datetime64[us]`.

### Cómo se cambia

El contrato nunca se edita a mano. Se cambia `scripts/gen_contrato.py` y se regenera.

Una versión publicada no cambia columnas ni tipos. Si el cambio los toca, `gen_contrato.py` se detiene y pide subir `VERSION` y `FECHA`. Los pasos completos están en "Cómo se publica una versión nueva" de `docs/contrato/README.md`:

1. Copia el csv publicado fuera de la carpeta antes de correr nada.
2. Sube `VERSION` y `FECHA` en `scripts/gen_contrato.py`.
3. Corre `python scripts/gen_contrato.py <copia del csv publicado>`.
4. Pega la entrada que imprime al principio de `HISTORIAL` y vacía `NOTAS_VERSION`.

## Decisiones de diseño vigentes

No se revierten sin hablarlo con el equipo.

| Decisión | Por qué |
| :--- | :--- |
| La limpieza no borra filas por criterios de análisis: solo marca (por ejemplo `es_administrativo`). Cada métrica filtra en la fase 3. | Cada métrica define su propio criterio (C5, C19) y la limpieza no debe decidir por ella. |
| La única exclusión es la de partidos que no pasan los filtros 7.1 (C18): `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. | Un partido sin datos completos contamina todas las métricas. Los excluidos quedan en `partidos_excluidos.csv`. |
| `team_match_stats_liga` no se filtra por los partidos de Jardine. | Es la línea base de toda la liga (1,364 partidos). |
| Un hueco de cobertura detiene toda la corrida y no excluye el partido. | Decisión de Yordi para la fase 2: falla en voz alta en lugar de dejar un partido incompleto. Se revisa si el grupo de contraste trae huecos. |
| El umbral de jugadores visibles del 360 no está en la tabla limpia (C19). | Cada métrica aplica el suyo. El provisional de Lee es actor visible y al menos 10 visibles. |
| El contrato se genera y no se edita. | Los md y el csv salen de las mismas filas y no divergen. |
| Los conteos 360 vacíos quedan nulos, no cero (C21). | Nulo quiere decir que no hay conteo. |
| `es_final` marca los dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos. | Las etiquetas de `competition_stage` no son confiables: hay Play-In etiquetados como Final. |
| Siempre se filtra por `manager_id` y `team_id` a la vez, nunca por nombre. | Jardine aparece también con Atlético San Luis, y el nombre viene en varias versiones. |
| B1 no funde posesiones: `posesion_fundida_id` es igual a `possession`. | StatsBomb ya deja dentro de la posesión el toque sin dirección del rival. Lo único que se fundiría es una reanudación (banda, córner, saque de meta), y la ficha dice que la reanudación abre una posesión nueva. |
| Un penal no vuelve válida una posesión; `n_tiros` sí lo cuenta. | Es el mismo criterio del `xg` de la posesión, que va sin penales. Decisión de Yordi del 19 de octubre. |
| `numerical_state` solo cuenta las expulsiones de jugadores que estaban en cancha. | Hay 2 rojas a jugadores que ya no jugaban (uno ya cambiado y un portero suplente) y no cambian cuántos hay en cancha. |
| Las columnas mezclan inglés y español. Unificar el idioma queda para después del 22 de octubre. | Cambiarlo ahora rompe el contrato, la limpieza y los scripts de los demás a mitad de la fase 3. |

## Cómo verificar un cambio

No hay tests, así que la verificación es ejecutar.

1. Muestra: `python scripts/02_limpieza.py --solo-partido 3995374` debe terminar con código 0 y mostrar `[OK]` en cada tabla.
2. Corrida completa: `python scripts/02_limpieza.py`. Revisa `data/interim/calidad_limpieza.csv`: `llaves_duplicadas` y `huerfanos` deben ser 0 en todas las tablas. Mira también el porcentaje de 360 que imprime al final.
3. Contrato idempotente: corre `python scripts/gen_contrato.py` dos veces. La segunda no debe cambiar nada en `docs/contrato/` (compáralo con `git diff`).
4. Regresión: antes de tocar la limpieza, copia `data/interim/` a otra carpeta de `data/`. Después de cambiar, corre de nuevo y compara tabla por tabla:

```python
import pandas as pd
from pandas.testing import assert_frame_equal

antes = pd.read_parquet("data/interim_anterior/eventos.parquet")
despues = pd.read_parquet("data/interim/eventos.parquet")
assert_frame_equal(antes, despues)   # falla si cambia una columna, un tipo o un valor
```

5. Contexto: `python scripts/03_contexto.py --sin-escribir` debe terminar con código 0. Las líneas `AVISO` son informativas; una falla dura termina con código 1.

## Estado y siguiente fase

Estado al 19 de octubre de 2026:

- Fase 1 (descarga): cerrada.
- Fase 2 (limpieza): terminada por Yordi. Hay 9 tablas en `data/interim/`, 0 duplicados, 0 huérfanos y 89.3% de los eventos con frame 360.
- Contrato v0.2 con 21 decisiones: 17 resueltas y 4 abiertas, todas de Lee (C4, C7, C11 y C20). Tienen un default vigente y falta que Lee las confirme.
- Lee entregó la especificación de métricas: 34 fichas, que llegan al repo en `especificaciones_metricas/`.
- Fase 3: `03_contexto.py` está terminado. Sus cuatro tablas pasan las validaciones con los 91 partidos.

Fase 3, del lunes 19 de octubre:

| Script | Responsable | Estado |
| :--- | :--- | :--- |
| `scripts/03_contexto.py` | Yordi | Terminado |
| `scripts/03_ataque.py` | Lee | Todavía no está en el repo |
| `scripts/03_defensa.py` | Pablo | Todavía no está en el repo |
| `scripts/03_jugadores.py` | Pato | Todavía no está en el repo |

## Ver también

- `docs/contrato/README.md` y `docs/contrato/cambios.md`: contrato, decisiones e historial de versiones.
- `docs/spec_01_descarga.md`: criterios de aceptación y pendientes de la descarga.
- `docs/spec_03_contexto.md`: columnas, reglas y validaciones del contexto.
