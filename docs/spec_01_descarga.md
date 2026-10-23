# Spec 01: descarga de los partidos de Jardine (scripts/01_descarga.py)

Estado: v0.1, 17-oct-2026 (corregido tras la auditoría). Dueño: Yordi. Referencia: `Plan_de_trabajo_Kpumas.md` secciones 6.5, 7.1 y 14.2.

## Problema

Hace falta una descarga reproducible de los 91 partidos de André Jardine con América (`manager_id` 1000116, `team_id` 1229, Ap23 a Cl25) y, opcionalmente, de la línea base de la liga. El resultado son seis tablas crudas en parquet más un inventario, para que la limpieza (`02_limpieza.py`) arranque sin tocar la API. Son unos 11 MB de JSON por partido (cerca de 1 GB en total), así que la descarga debe poder reanudarse y no puede repetir llamadas. Los datos no se publican: todo `data/` queda fuera de git.

## Criterios de aceptación

- AC1: D1 contiene solo partidos de `TEMPORADAS_RETO` donde `manager_id` está en `managers` del lado de `team_id`, con `match_status` = available, `collection_status` = Complete, `play_status` = Normal y `match_status_360` = available, cuando se corre sin `--solo-partido`. Se espera 91 filas.
- AC2: `partidos.parquet` incluye `torneo`, `fase`, `es_play_in`, `es_final`, `entrenador_id`, `equipo_id`, `es_local`, `rival_id`, `rival_nombre`, `entrenador_rival`, `entrenador_rival_id`, `rival_coentrenador`, `goles_favor`, `goles_contra`, `resultado` y `coentrenador`, con `fase` = regular solo si `competition_stage.id` está en {1, 42, 44} y liguilla en otro caso; `es_play_in` es verdadero con el stage id 2.
- AC3: `es_final` es verdadero solo en los dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos, calculados sobre todos los partidos de la liga del torneo y no sobre las etiquetas de stage.
- AC4: se escriben `partidos`, `events`, `frames_360`, `lineups`, `team_match_stats` y `player_match_stats` en `data/raw/parquet/`, todos con `match_id`, y las listas o dicts quedan como texto JSON.
- AC5: una segunda ejecución no hace ninguna llamada HTTP cuando la caché de `sb_api` ya tiene las respuestas.
- AC6: las llamadas son secuenciales y llevan una pausa configurable (`--pausa`, default 0.3 s) solo cuando hubo descarga real; cada partido imprime una línea de progreso.
- AC7: con `--linea-base` se escribe `team_match_stats_liga.parquet` con los partidos `available`, `Complete` y `Normal` de las 4 temporadas, más `torneo`, `fase`, `es_play_in`, `es_final` y los ids de equipo; los excluidos se listan en el inventario.
- AC8: `docs/inventario_descarga.md` reporta filas por tabla, partidos por torneo y fase, % de eventos con frame 360 (`id` contra `event_uuid`), partidos excluidos con motivo, fecha de descarga y `last_updated_360` por partido.
- AC9: el script termina con código 2 y un mensaje claro sin imprimir valores, si faltan `SB_USER` o `SB_PASS`, o si la API responde 401 o 403 ("credenciales rechazadas").
- AC10: si falla un endpoint de un partido, el partido se registra como fallido en el inventario, la corrida continúa y el código de salida es 1.
- AC11: `--solo-partido` y `--limite` escriben en `data/raw/parquet_prueba/` e `inventario_descarga_prueba.md`, para no pisar la salida completa; con otros `--manager-id` / `--team-id` la salida va a `data/raw/parquet/m{manager}_t{team}/` e `inventario_descarga_m{manager}_t{team}.md`.
- AC12: ningún parquet pasa de 50 MB: si uno lo supera con zstd se parte por torneo (`events__Apertura_2023.parquet`, etc.); la escritura es atómica (`.tmp` y `os.replace`).
- AC13: el inventario compara esperado contra obtenido (91 partidos, 25 de liguilla, 8 con `es_final`) y, si no cuadra, imprime una advertencia y sale con código 1; incluye la sección "Columnas convertidas a texto" y los partidos del equipo en el periodo con otro manager como "excluido: otro manager".
- AC14: `sb_api.fetch` escribe la caché de forma atómica, borra y vuelve a pedir un archivo corrupto, no cachea respuestas que no sean una lista con elementos y lanza `SBAuthError` ante 401 o 403.

## Fuera de alcance

- Limpieza, tipos finales y tablas auxiliares: son `02_limpieza.py` (domingo 18).
- Descarga de events o 360 de partidos que no sean de D1 — pesan demasiado y no se usan.
- Season stats, player mapping y competitions — no los usa el análisis por partido.
- Paralelizar las llamadas — el brief de la API pide llamadas secuenciales.
- Lanzar la descarga completa desde esta tarea — la lanza Yordi en segundo plano.
- Cambiar la interfaz pública de `sb_api.py` — solo se agrega un helper (`en_cache`).

## Plan de pruebas

- AC1, AC2, AC3 → manual: correr con `--limite 3` y revisar la selección; además una verificación en frío sobre las matches cacheadas (91 filas, 8 partidos con `es_final`, 4 torneos con 2 finales).
- AC4 → manual: abrir cada parquet con pandas y comprobar `match_id` y tipos de las columnas JSON.
- AC5 → manual: repetir la corrida de 3 partidos y comprobar que no hay descargas en el log ("cache").
- AC6 → manual: leer el log de progreso y el tiempo por partido.
- AC7 → no se ejecuta en esta tarea (la lanza Yordi); se prueba la función con 3 partidos.
- AC8 → manual: leer el inventario generado.
- AC12 a AC14 → manual (ver la sección de verificación del reporte): tamaños de `data/raw/parquet/`, inventario de la corrida completa y pruebas con `requests.get` simulado en una caché temporal.
- AC9 → manual: llamar `main()` con `sb_api._leer_env_archivo` reemplazado por una función que devuelve un dict vacío y sin variables de entorno; debe devolver 2 y el mensaje.
- AC10 → no se prueba con la API; revisado por lectura de código.
- AC11 → manual: confirmar que `data/raw/parquet/` no cambia tras una corrida de prueba.

## Helpers agregados a `sb_api.py`

La interfaz pública anterior no cambia. Se agregaron tres funciones y una excepción:

- `en_cache(path, params=None)`: devuelve True si la respuesta ya está en `data/raw/`, para saber si `fetch` hará una llamada HTTP.
- `ruta_cache(path, params=None)`: ruta del archivo de caché (el inventario usa su fecha de modificación como fecha de descarga).
- `verificar_credenciales()`: lanza `RuntimeError` si faltan `SB_USER` o `SB_PASS`, sin imprimir valores.
- `SBAuthError`: excepción específica para 401 y 403.

## Alternativas descartadas

- Un parquet por partido — se prefirió una tabla por endpoint con `match_id` para que la limpieza lea un solo archivo; los archivos pasan de 50 MB solo en `events` y se parten por torneo.
- Partir `events` por partido al superar 50 MB — habría dejado 91 archivos; por torneo quedan 4 de unos 15 MB.
- Usar `statsbombpy` — se descartó desde el inicio por la incompatibilidad con pandas 3 y las versiones propias de endpoint.
- Detectar la final con la etiqueta de `competition_stage` — no es confiable (hay Play-In etiquetados como "Final" y una vuelta de final como "Semi-finals").
- Subir el `.gitignore` como lista negra — se cambió a lista blanca para que un archivo nuevo no se publique por accidente.
- Subir la caché JSON al repo — pesa unos 1.2 GB; se regenera con `sb_api`.
- Paralelizar las llamadas — la API pide llamadas secuenciales.
- Nivel de compresión zstd más alto para evitar partir `events` — el nivel 19 deja 50.7 MB y tarda 94 s; no compensa.

## Pendientes conocidos

Menores que no se arreglan hoy:

- Reintentos con backoff exponencial y límite de intentos (hoy hay un solo reintento con pausa fija de 2 s).
- Parquet por partido para poder reanudar sin releer la caché y reescribir todo ante un fallo a la mitad.
- Pruebas automáticas sin red (hoy la verificación es manual con una caché temporal y `requests.get` simulado).
- Invalidación de la caché cuando StatsBomb actualiza un partido (`last_updated_360` ya queda en el inventario para detectarlo).
- Columnas de serie y ganador de la eliminatoria en `partidos` (ida y vuelta, global).
- Rutas de endpoints duplicadas entre `sb_api.py` y `01_descarga.py` (`ENDPOINTS_PARTIDO`); conviene exponerlas desde `sb_api`.
