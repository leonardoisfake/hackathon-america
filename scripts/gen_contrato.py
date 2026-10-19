"""Genera la carpeta docs/contrato/ (README, un md por tabla, cambios.md y contrato_datos.csv) desde los parquet crudos completos.

Uso:  python scripts/gen_contrato.py [contrato_anterior.csv|contrato_anterior.md] [--version-anterior v0.1]

Los tipos y las cifras salen de data/raw/parquet, las descripciones de data/diccionario.json
y las reglas de limpieza del plan (7.1 a 7.3). Los md y el csv se arman con las mismas filas,
asi que no divergen. cambios.md sale de HISTORIAL (las versiones ya publicadas). Si VERSION todavia
no esta en HISTORIAL, su entrada se calcula contra el contrato anterior que se pase (el csv; el md
solo en el formato de un archivo de la v0.1). La version anterior se toma de --version-anterior,
del encabezado "# Contrato de datos vX" del md, o del README.md o el md del mismo nombre junto al csv.
Si VERSION ya esta en HISTORIAL, antes de escribir se compara lo generado contra el contrato_datos.csv que ya esta en
docs/contrato/: si cambian tablas, columnas o tipos, el script se detiene y pide subir VERSION y FECHA.
"""
import argparse
import glob
import json
import os
import pprint
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # contrato.py esta en scripts/
from contrato import ADMINISTRATIVOS, COLUMNAS, TIPOS_VALIDOS  # noqa: E402

PARQ = ROOT / "data" / "raw" / "parquet"
# version en preparacion; para publicar una nueva se suben las dos (ver "Cómo se publica una versión nueva" en el README)
FECHA = "2026-10-18"
VERSION = "v0.2"
OUT = ROOT / "docs" / "contrato"
CONFIRMAR = "vigente por defecto; confirmar antes del lun 19"
P02 = "02_limpieza.py (Yordi)"
PAUX = "02_auxiliares.py (Lee)"

MANUAL_DESC = {
    ("matches", "metadata.shot_fidelity_version"): "Versión de fidelidad con la que se capturaron los tiros.",
    ("matches", "metadata.xy_fidelity_version"): "Versión de fidelidad con la que se capturaron las coordenadas (sin documentar en el PDF).",
    ("events", "goalkeeper.end_location"): "Destino [x, y] de la acción del portero (sin documentar en el PDF).",
    ("matches", "home_team.country.id"): "Id del país del equipo local.",
    ("matches", "home_team.country.name"): "Nombre del país del equipo local.",
    ("matches", "away_team.country.id"): "Id del país del equipo visitante.",
    ("matches", "away_team.country.name"): "Nombre del país del equipo visitante.",
    # el diccionario repite "Pases largos completos" en las dos; en los datos successful / long_balls = long_ball_ratio
    ("player_match_stats", "player_match_long_balls"): "Pases largos intentados.",
    # el diccionario dice reloj del periodo; los datos traen el reloj corrido del partido (se verifica en cifras_lineups)
    ("lineups", "lineup[].positions[].from"): "Inicio del tramo: texto HH:MM:SS.mmm, reloj corrido del partido (el segundo tiempo empieza en 00:45:00.000). `to − from` es la duración solo si `from_period` = `to_period`; si no, ver la regla.",
    ("lineups", "lineup[].positions[].to"): "Fin del tramo: texto HH:MM:SS.mmm, reloj corrido del partido (el segundo tiempo empieza en 00:45:00.000). `to − from` es la duración solo si `from_period` = `to_period`; si no, ver la regla.",
}
# C12: los nombres de personas son string; los de equipos y catalogos, category
PERSONAS = ("referee_name", "player_name", "pass_recipient_name", "substitution_replacement_name", "counterpart_name",
            "entrenador_rival", "player_nickname")
EQUIPO_O_CATALOGO = frozenset({
    # partidos
    "competition_country_name", "competition_name", "season_name", "home_team_name", "home_team_country_name",
    "away_team_name", "away_team_country_name", "competition_stage_name", "stadium_name", "stadium_country_name",
    "referee_country_name", "rival_nombre",
    # eventos
    "type_name", "possession_team_name", "play_pattern_name", "team_name", "position_name", "pass_height_name",
    "pass_body_part_name", "pass_type_name", "shot_type_name", "shot_technique_name", "shot_outcome_name",
    "shot_body_part_name", "goalkeeper_type_name", "goalkeeper_position_name", "pass_outcome_name",
    "ball_receipt_outcome_name", "interception_outcome_name", "clearance_body_part_name", "goalkeeper_body_part_name",
    "goalkeeper_outcome_name", "goalkeeper_technique_name", "dribble_outcome_name", "duel_type_name", "duel_outcome_name",
    "fifty_fifty_outcome_name", "pass_technique_name", "foul_committed_card_name", "foul_committed_type_name",
    "substitution_outcome_name", "bad_behaviour_card_name",
    # alineaciones y stats
    "country_name", "opposition_name",
})
PATRON_NOMBRE = re.compile(r"_name|_nombre|nickname")

# eventos
LISTAS_AUX = {"tactics.lineup", "related_events", "defensive_responsibility.players", "shot.freeze_frame"}
COORD = {"location": ("x", "y"), "pass.end_location": ("end_x", "end_y"), "carry.end_location": ("end_x", "end_y"),
         "shot.end_location": ("end_x", "end_y", "end_z"), "goalkeeper.end_location": ("end_x", "end_y")}
BOOL_NULL_LEGIT = {"is_transition", "is_controlled_possession"}
STR_LIBRE = {"id", "timestamp", "pass.assisted_shot_id", "shot.key_pass_id", "player.name", "pass.recipient.name",
             "substitution.replacement.name"}
JSON_STR = {"defensive_responsibility.categories"}
RELOJ = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
INICIO_2T = "00:45:00.000"
# inicios supuestos del tiempo extra (periodos 3 y 4); ningun tramo empieza ahi, asi que solo sirven como cota
COTA_TE = {3: "01:30:00.000", 4: "01:45:00.000"}

# reglas de negocio de 01_descarga.py (ETAPAS_REGULARES, ETAPA_PLAY_IN y torneo_de)
STAGES_REGULAR = (1, 42, 44)
STAGE_PLAY_IN = 2
REGLA_TORNEO = "julio a diciembre = Apertura, enero a junio = Clausura"
DESC_TORNEO = "Torneo del partido, derivado de la fecha (por ejemplo 'Apertura 2023')."
DESC_FASE = "regular o liguilla."
REGLA_FASE = f"regular si competition_stage.id en {{{', '.join(map(str, STAGES_REGULAR))}}}; liguilla en otro caso."
DESC_PLAY_IN = "El partido es de la ronda Play-In."
REGLA_PLAY_IN = f"competition_stage.id = {STAGE_PLAY_IN}."
DESC_ES_FINAL = "Uno de los dos partidos de la final del torneo."
REGLA_ES_FINAL = "Dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos (calculado sobre toda la liga)."
# filtros de calidad de 02_limpieza.py (PARTIDO_OK); son los valores posibles de `campo` en partidos_excluidos.csv
FILTROS_PARTIDO = (("play_status", "Normal"), ("match_status", "available"), ("collection_status", "Complete"),
                   ("match_status_360", "available"))

# partidos
DROP_P = {"attendance", "home_team.home_team_group", "away_team.away_team_group", "home_team.managers", "away_team.managers"}
# se descartan por vacias; cifras_partidos comprueba que sigan sin datos
VACIAS_P = ("attendance", "home_team.home_team_group", "away_team.away_team_group")
INT_P = {"match_id", "match_week", "competition.competition_id", "season.season_id", "competition_stage.id", "stadium.id",
         "referee.id", "home_team.country.id", "away_team.country.id", "stadium.country.id", "referee.country.id",
         "home_team.home_team_id", "away_team.away_team_id", "rival_id", "goles_favor", "goles_contra", "home_score",
         "away_score", "entrenador_id", "equipo_id", "entrenador_rival_id"}
BOOL_P = {"behind_closed_doors", "neutral_ground", "home_team.home_team_youth", "away_team.away_team_youth",
          "es_final", "es_play_in", "es_local", "coentrenador", "rival_coentrenador"}
CAT_P = {"torneo", "fase", "resultado", "collection_status", "play_status", "match_status", "match_status_360",
         "competition.competition_name", "competition.country_name", "season.season_name", "home_team.home_team_gender",
         "away_team.away_team_gender", "competition_stage.name", "metadata.data_version",
         "metadata.shot_fidelity_version", "metadata.xy_fidelity_version"}
FECHAS_P = {"match_date": "Texto -> fecha.", "last_updated": "Texto ISO -> fecha y hora.",
            "last_updated_360": "Texto ISO -> fecha y hora."}
TIPO_FECHA = "datetime64[us]"
DERIV_P = {
    "torneo": (DESC_TORNEO, f"Derivada de match_date: {REGLA_TORNEO}."),
    "fase": (DESC_FASE, REGLA_FASE),
    "es_play_in": (DESC_PLAY_IN, REGLA_PLAY_IN),
    "es_final": (DESC_ES_FINAL, REGLA_ES_FINAL),
    "es_local": ("El equipo analizado juega de local.", "Derivada en la descarga."),
    "rival_id": ("team_id del rival.", "Derivada en la descarga."),
    "rival_nombre": ("Nombre del rival.", "Derivada en la descarga."),
    "entrenador_rival": ("Entrenador(es) del rival, separados por ' / '.", "Derivada en la descarga."),
    "entrenador_rival_id": ("manager_id del primer entrenador del rival.", "Derivada en la descarga; Int64."),
    "rival_coentrenador": ("El rival tuvo más de un manager en el partido.", "Derivada en la descarga."),
    "goles_favor": ("Goles del equipo analizado.", "Derivada en la descarga."),
    "goles_contra": ("Goles del rival.", "Derivada en la descarga."),
    "resultado": ("G, E o P para el equipo analizado.", "Derivada en la descarga."),
    "coentrenador": ("El equipo analizado tuvo más de un manager en el partido.", "Derivada en la descarga."),
    "entrenador_id": ("manager_id del entrenador analizado.", "Agregada en la descarga con --manager-id."),
    "equipo_id": ("team_id del equipo analizado.", "Agregada en la descarga con --team-id."),
}

STATS_L = ("goals", "assists", "own_goals", "penalties_scored", "penalties_missed", "penalties_saved")
# plan 7.1: los errores de video son valores de collection_status, asi que el filtro Complete los deja fuera
VIDEO = ("NoVidError", "IncVidError", "PoorVidError")
# filtro de descargar_linea_base en 01_descarga.py
FILTRO_LIGA = "`match_status` = available, `collection_status` = Complete y `play_status` = Normal"
# proporciones conocidas por nombre (revisado contra el diccionario); *_per_possession es xG por posesion
PROPORCION = re.compile(r"(_ratio|_ratio_conceded|_rate|possession)$")
NO_PROPORCION = re.compile(r"_per_possession$")

ORDEN = ["partidos", "eventos", "frames_360", "frames_360_evento", "alineaciones", "posiciones",
         "team_match_stats", "player_match_stats", "team_match_stats_liga",
         "related_events", "tactics_lineup", "defensive_responsibility", "shot_freeze_frame"]
# tablas de 02_limpieza.py que solo traen los match_id de `partidos` (C18)
POR_PARTIDO = ["partidos", "eventos", "frames_360", "frames_360_evento", "alineaciones", "posiciones",
               "team_match_stats", "player_match_stats"]
# tablas de 02_auxiliares.py; C18 pide que salgan de data/interim/eventos.parquet y no de los crudos
AUXILIARES = ["related_events", "tactics_lineup", "defensive_responsibility", "shot_freeze_frame"]

# numero C publicado de cada decision; solo agregar al final
PUBLICADAS = {
    "unidad": 1, "destino_unico": 2, "dos_tablas_360": 3, "shot_freeze_frame": 4, "administrativos": 5,
    "match_clock": 6, "categories_json": 7, "tarjetas_formaciones": 8, "posiciones_to": 9, "columnas_ausentes": 10,
    "nulo_legitimo": 11, "nombres_c12": 12, "penales": 13, "sin_ubicacion": 14, "perspectiva_360": 15,
    "donde_parquet": 16, "produce_posiciones": 17, "filtros_calidad": 18, "umbral_360": 19, "managers": 20,
    "conteo_360_vacio": 21,
}

ESCALA_STATS = ("Las proporciones que se reconocen por el nombre (`*_ratio`, `*_ratio_conceded`, `*_rate` y `*possession`, sin "
                "contar `*_per_possession`) llevan una etiqueta según su rango observado: \"Proporción; rango observado dentro de "
                "[0, 1]\" si cabe en [0, 1] (es una observación de estos datos, no una garantía de StatsBomb); \"Razón que puede "
                "pasar de 1\" con el máximo observado si lo pasa; \"No es una escala 0 a 1\" con el rango si baja de 0; \"Un solo "
                "valor observado\" si el mínimo y el máximo coinciden, y \"Sin datos observados\" si no hay valores. `directness` "
                "no es una proporción; su regla da el rango observado. Los infinitos se descartan antes de calcular el rango.")
ENC_DEC = "| # | decisión | default vigente | quién decide | fecha límite |"
ATRAS = "[Volver al índice](README.md)\n"

# notas escritas a mano de la version en preparacion; al publicarla pasan a su entrada de HISTORIAL y esto se vacia
NOTAS_VERSION = []
# entradas publicadas de cambios.md, de la mas reciente a la mas antigua; no se recalculan con los datos
HISTORIAL = [
    {'version': 'v0.2',
     'fecha': '2026-10-18',
     'desde': 'v0.1',
     'cambios': ['Respecto a v0.1: 23 cambios de tipo (tabla abajo), 0 columnas nuevas y 0 columnas quitadas. Las 13 '
                 'tablas suman 938 columnas.',
                 'C12: 18 columnas de nombre de equipos y catálogos (los `*_name` y `partidos.rival_nombre`) pasan de '
                 'string a category. Los nombres de personas siguen como string.',
                 '5 columnas de fecha pasan de datetime64[ns] a datetime64[us]: `partidos.match_date`, '
                 '`partidos.last_updated`, `partidos.last_updated_360`, `alineaciones.birth_date` y '
                 '`team_match_stats_liga.match_date`.',
                 'datetime64[us] es la resolución que da pandas 3 al convertir texto y la que ya produce la limpieza. '
                 '`validar()` ahora exige el dtype exacto y rechaza otra resolución y las fechas con zona horaria.',
                 'El csv agrega las columnas `relleno` y `puede_faltar`. `relleno` dice con qué se llenan los '
                 'ausentes: hoy es False en 64 banderas, justo las que tienen una regla que empieza con "Ausente = '
                 'False". `puede_faltar` es True en 8 columnas, las banderas de C10, que no existen en el parquet '
                 'crudo de ninguno de los 91 partidos. Estas dos columnas permiten dejar de interpretar el texto de la '
                 'regla; la limpieza lo adopta en su propio PR.',
                 '`scripts/contrato.py` carga las dos columnas nuevas, rechaza un csv con tipos fuera de '
                 '`TIPOS_VALIDOS` y expone `ADMINISTRATIVOS`, la lista de los tipos de evento administrativos. '
                 '`cargar()` solo acepta True o False en `puede_faltar` (0 y 1 dan error), y en `relleno` solo vacío o '
                 'False, únicamente en columnas boolean. Por eso ya no lee un csv de la v0.1, que no trae `relleno` ni '
                 '`puede_faltar`.',
                 '`validar()` también marca como falla una columna con `relleno` que trae nulos y una category cuyas '
                 'categorías no son texto.',
                 '`ADMINISTRATIVOS` agrega Camera On, como en la especificación de Lee; tiene 0 filas en los 91 '
                 'partidos.',
                 'La regla de `posiciones.to` ahora es definitiva: el nulo significa que el jugador siguió hasta el '
                 'silbatazo final (1,976 de 4,150 tramos, 47.6%). Sustituye al "~55%, verificar" de la v0.1.',
                 'El diccionario dice que `posiciones.from` y `posiciones.to` usan el reloj del periodo, pero los '
                 'datos traen el reloj corrido del partido: con `from_period` = 2 el mínimo de `from` es 00:45:00.000 '
                 'y el máximo de `to` es 02:01:11.394. `to − from` es la duración del tramo solo si `from_period` = '
                 '`to_period`; si cruza de periodo, la duración se suma por periodo (ver la regla de `posiciones.to`). El '
                 'generador lo comprueba en cada corrida.',
                 'El contrato pasa de un solo md a la carpeta `docs/contrato/`: README, un md por tabla, `cambios.md` '
                 'y `contrato_datos.csv`. `scripts/contrato.py` lee el csv desde ahí.',
                 'Resueltas el 18 de octubre: C5 (los eventos administrativos se conservan), C8 (se cierra sin tablas '
                 'nuevas), C9 (nulo en `to`), y C10, C12, C16 con el default vigente.',
                 'Resueltas por Lee en su especificación de métricas: C6 (`match_clock` y `minute_bin` no van en la '
                 'tabla limpia; se calculan en la fase 3, `scripts/03_contexto.py`) y C13 (los penales se conservan '
                 'con `period = 5` y todas las fichas los excluyen).',
                 'Resueltas por Pablo: C14 (los eventos con `x`/`y` nulos no entran a las gráficas) y C15 (en '
                 '`frames_360` usa `es_equipo_analizado` y no toma los nulos).',
                 'Decisiones nuevas: C17 (`posiciones` la produce `02_limpieza.py`), C18 (los partidos que no pasan '
                 'los filtros del plan 7.1 se excluyen de todas las tablas de `02_limpieza.py` salvo '
                 '`team_match_stats_liga`, y se reportan), C19 (el umbral de jugadores visibles lo aplica cada métrica '
                 'y lo define Lee; valor provisional: actor visible y al menos 10 jugadores visibles), C20 (`managers` '
                 'se queda resumido en `partidos`; abierta, la confirma Lee) y C21 (los conteos 360 vacíos quedan '
                 'nulos; resuelta).',
                 'C10 se amplía: las 8 banderas que no salen en ningún partido se conservan en False. C11 anota que '
                 '`out` y `off_camera` ya se rellenan con False. C19 reemplaza el punto 7 de la sección 11 del plan.',
                 'Siguen abiertas con su default: C4, C7, C11 y C20 (Lee), vigente por defecto; '
                 'confirmar antes del lun 19. Las decisiones resueltas pasan de 3 a 17.',
                 'Correcciones de texto: el orden es siempre (`match_id`, `index`) y `match_second` sirve para agrupar '
                 'dentro de (`match_id`, `period`); `timestamp` queda verificado; "Escala 0 a 1" solo aparece en las '
                 'proporciones conocidas por nombre cuyo rango observado cabe en [0, 1], y `directness` ya no la '
                 'lleva; `player_match_long_balls` dice pases largos intentados; los % de nulos de `alineaciones` se '
                 'recalculan y se documenta la banca que no entró; `partidos.md` explica `partidos_excluidos.csv` y '
                 'los errores de video; la línea base aclara qué filtros no se le aplican; se quita la etiqueta "D1:" '
                 'del grano de `partidos`.',
                 'Convenciones nuevas en el README: todo texto pasa por strip, las categorías salen de cada corrida '
                 '(hay que alinearlas antes de concatenar), el csv tiene `relleno` y `puede_faltar`, y el alcance de '
                 'C18 lista los cuatro filtros. `eventos` aclara que también trae `es_play_in` y `es_final` desde '
                 '`partidos`.',
                 '`cambios.md` sale de una lista fija de versiones publicadas en el script, así que regenerar ya no '
                 'borra la historia. El README explica cómo se publica una versión nueva.',
                 'Se documentan las salidas de control de `02_limpieza.py` y se precisan las reglas de '
                 '`pass_completed`, `receipt_ok` y `n_visibles_*`.'],
     'tipos_titulo': 'Tipos que cambian, calculados contra el `contrato_datos.csv` de v0.1:',
     'tipos': [('partidos', 'match_date', 'datetime64[ns]', 'datetime64[us]'),
               ('partidos', 'last_updated', 'datetime64[ns]', 'datetime64[us]'),
               ('partidos', 'last_updated_360', 'datetime64[ns]', 'datetime64[us]'),
               ('partidos', 'home_team_name', 'string', 'category'),
               ('partidos', 'home_team_country_name', 'string', 'category'),
               ('partidos', 'away_team_name', 'string', 'category'),
               ('partidos', 'away_team_country_name', 'string', 'category'),
               ('partidos', 'stadium_name', 'string', 'category'),
               ('partidos', 'stadium_country_name', 'string', 'category'),
               ('partidos', 'referee_country_name', 'string', 'category'),
               ('partidos', 'rival_nombre', 'string', 'category'),
               ('alineaciones', 'team_name', 'string', 'category'),
               ('alineaciones', 'birth_date', 'datetime64[ns]', 'datetime64[us]'),
               ('team_match_stats', 'team_name', 'string', 'category'),
               ('team_match_stats', 'opposition_name', 'string', 'category'),
               ('team_match_stats', 'competition_name', 'string', 'category'),
               ('team_match_stats', 'season_name', 'string', 'category'),
               ('player_match_stats', 'team_name', 'string', 'category'),
               ('team_match_stats_liga', 'team_name', 'string', 'category'),
               ('team_match_stats_liga', 'opposition_name', 'string', 'category'),
               ('team_match_stats_liga', 'competition_name', 'string', 'category'),
               ('team_match_stats_liga', 'season_name', 'string', 'category'),
               ('team_match_stats_liga', 'match_date', 'datetime64[ns]', 'datetime64[us]')],
     'nuevas': {},
     'quitadas': [],
     'extra': []},
    {
        "version": "v0.1", "fecha": "2026-10-17", "desde": "v0",
        "cambios": [
            "`fase` pasa de `regular`/`final` a `regular`/`liguilla`; nueva columna `es_play_in` (stage id 2).",
            "`partidos` agrega `entrenador_id`, `equipo_id`, `entrenador_rival_id` y `rival_coentrenador`; se quita la decisión abierta sobre ellos.",
            "Los tipos y los % de nulos se recalcularon con los parquet completos (91 partidos, 317,849 eventos) en lugar de la muestra de 3 a 5 partidos.",
            "`eventos` tiene 180 columnas de origen con los 91 partidos (170 en la muestra de 5). De las 17 banderas documentadas que no salieron en la muestra, 9 sí aparecen con los datos completos y 8 siguen sin aparecer (se crean con False).",
            "Las 6 columnas de `team_match_stats` que la API no devolvía en la muestra (tiros libres directos) sí aparecen con los datos completos.",
            "Nueva tabla `team_match_stats_liga` (línea base de la liga).",
            "Perspectiva del equipo analizado: `es_equipo_analizado`, `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq` en `eventos`; `es_equipo_analizado` en `frames_360`.",
            "`match_second` aclara que no es único entre periodos; se ordena por (`period`, `match_second`).",
            "Columna 'produce' en el resumen: `02_limpieza.py` (Yordi) y `02_auxiliares.py` (Lee).",
            "Las decisiones abiertas pasan a tabla con default, responsable y fecha límite; 3 quedan resueltas.",
            "Se corrigen descripciones cortadas y vacías.",
        ],
        "tipos_titulo": "Tipos que cambiaron al recalcular con los datos completos:",
        "tipos": [("team_match_stats", "team_match_direct_free_kick_xg", "Int64", "float64"),
                  ("team_match_stats", "team_match_direct_free_kick_xg_conceded", "Int64", "float64")],
        "extra": [("Columnas nuevas respecto a v0 (por tabla):", [
            "- `partidos` (3): `es_play_in`, `entrenador_rival_id`, `rival_coentrenador`",
            "- `eventos` (6): `es_play_in`, `es_equipo_analizado`, `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`",
            "- `frames_360` (1): `es_equipo_analizado`",
        ])],
    },
    {
        "version": "v0", "fecha": "2026-10-17", "desde": None,
        "cambios": ["Primera versión, calculada con la muestra de 3 a 5 partidos."],
        "tipos_titulo": None, "tipos": [], "extra": [],
    },
]


# ---------- utilidades ----------

def version_de(ruta):
    # Version del contrato anterior: encabezado del md, o del README.md o el md del mismo nombre junto al csv.
    if ruta.suffix == ".md":
        candidatos = [ruta]
    else:
        candidatos = [p for p in (ruta.parent / "README.md", ruta.with_suffix(".md")) if p.is_file()]
    for a in candidatos:
        m = re.search(r"^# Contrato de datos (v\d+(?:\.\d+)*)", a.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return None


def archivos_tabla(nombre):
    return sorted(glob.glob(str(PARQ / f"{nombre}__*.parquet"))) or [str(PARQ / f"{nombre}.parquet")]


def leer_tabla(nombre):
    return pa.concat_tables([pq.read_table(a) for a in archivos_tabla(nombre)], promote_options="permissive")


def pct(parte, total, que):
    if not total:
        raise ValueError(f"no se puede calcular el % de {que}: el total es 0")
    return 100 * parte / total


def tipo_pandas_arrow(t):
    if pa.types.is_boolean(t):
        return "bool"
    if pa.types.is_integer(t):
        return "int"
    if pa.types.is_floating(t):
        return "float"
    return "str"


def tipo_c12(nombre, tipo):
    # C12: personas string, equipos y catalogos category; un nombre que no este en ninguna lista es un error.
    if nombre in PERSONAS:
        return "string"
    if nombre in EQUIPO_O_CATALOGO:
        return "category"
    if PATRON_NOMBRE.search(nombre):
        raise ValueError(f"`{nombre}` parece un nombre y no está en PERSONAS ni en EQUIPO_O_CATALOGO (C12); agrégalo a una de las dos")
    return tipo


def desc_corta(doc, slug, col):
    if (slug, col) in MANUAL_DESC:
        return MANUAL_DESC[(slug, col)]
    c = doc.get(slug, {}).get(col)
    t = ""
    if c:
        t = (c.get("significado") or "").strip() or (c.get("descripcion_en") or "").strip()
    ambiguo = bool(re.match(r"\s*\[ambiguo\]", t))
    t = re.sub(r"^\s*\[ambiguo\]\s*", "", t)
    t = re.sub(r"\s*\[ambiguo\].*", "", t)
    t = re.sub(r"\s+", " ", t)
    if not t:
        return "Sin documentar en el PDF oficial."
    # primera oracion; no se corta en abreviaturas como "ej." o "etc."
    m = re.match(r"(.+?(?<!\bej)(?<!\betc)(?<!\bEj)[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    if len(t) > 240:
        corte = max(t.rfind("; ", 0, 240), t.rfind(", ", 0, 240))
        t = (t[:corte] if corte > 120 else t[:t.rfind(" ", 0, 240)]).rstrip(",;") + "."
    t = ("Ambiguo en el PDF: " + t[0].lower() + t[1:]) if ambiguo and t else t
    return t.replace("|", "/")


def es_bandera_documentada(doc, col):
    # El diccionario la describe como bandera ("TRUE si...", "Added if...") o le da tipo booleano.
    e = doc.get("events", {}).get(col)
    if not e:
        return False
    significado, en = (e.get("significado") or "").strip(), e.get("descripcion_en") or ""
    return significado.startswith("TRUE si") or "Added if" in en or str(e.get("tipo")).lower() in ("bool", "boolean")


def snake(col, colapsar=False):
    n = col.replace("[]", "").replace(".", "_").replace("50_50", "fifty_fifty")
    partes = col.split(".")
    if colapsar and len(partes) == 2 and partes[1].startswith(partes[0]):
        n = partes[1]
    return n.lower()


def fila(columna, tipo, desc, origen, regla, relleno=None, puede_faltar=False):
    return {"columna": columna, "tipo": tipo, "descripcion": desc, "origen": origen, "regla": regla,
            "relleno": relleno, "puede_faltar": puede_faltar}


def lista_md(cols):
    cols = [f"`{c}`" for c in cols]
    return ", ".join(cols[:-1]) + " y " + cols[-1] if len(cols) > 1 else "".join(cols)


def C(*llaves):
    return ", ".join(f"C{PUBLICADAS[k]}" for k in llaves)


def n_json(tabla_arrow, col):
    return sum(len(json.loads(x)) if isinstance(x, str) else len(x or []) for x in tabla_arrow.column(col).to_pylist() if x)


def n_json_events(col):
    return sum(n_json(pq.read_table(a, columns=[col]), col) for a in archivos_tabla("events"))


def no_existe(n, plural=False):
    # definicion unica de puede_faltar
    return f"no {'existen' if plural else 'existe'} en el parquet crudo de ninguno de los {n:,} partidos"


def texto_filtros():
    return ", ".join(f"`{k}` = {v}" for k, v in FILTROS_PARTIDO[:-1]) + f" y `{FILTROS_PARTIDO[-1][0]}` = {FILTROS_PARTIDO[-1][1]}"


# ---------- fuentes y cifras ----------

def leer_fuentes():
    # Diccionario y parquet crudos que usa el generador.
    dic = json.loads((ROOT / "data" / "diccionario.json").read_text(encoding="utf-8"))
    return {
        "dic": dic,
        "doc": {e["slug"]: {c["columna"]: c for c in e["columnas"]} for e in dic["endpoints"]},
        "endpoint": {e["slug"]: e for e in dic["endpoints"]},
        "events": leer_tabla("events"),
        "partidos": leer_tabla("partidos"),
        "frames_360": pq.read_table(PARQ / "frames_360.parquet", columns=["freeze_frame", "visible_player_counts"]),
        "lineups": pq.read_table(PARQ / "lineups.parquet", columns=["match_id", "lineup"]),
        "team_match_stats": leer_tabla("team_match_stats"),
        "player_match_stats": leer_tabla("player_match_stats"),
        "team_match_stats_liga": leer_tabla("team_match_stats_liga"),
    }


def cifras_eventos(f):
    t_ev = f["events"]
    n_ev = t_ev.num_rows
    ev_df = t_ev.select(["match_id", "period", "timestamp", "type.name", "obv_total_net"]).to_pandas()
    conteo_tipos = ev_df["type.name"].value_counts()
    # un tipo administrativo puede no salir en los datos (Camera On), pero debe ser un tipo de evento de StatsBomb
    tipos_dic = {v["valor_nombre"].rstrip("*") for v in f["dic"]["valores"]["events"] if v["ruta_json"] == "type.id"}
    desconocidos = sorted(t for t in ADMINISTRATIVOS if t not in conteo_tipos.index and t not in tipos_dic)
    if desconocidos:
        raise ValueError(f"ADMINISTRATIVOS trae tipos que no salen en eventos ni en el diccionario: {desconocidos}")
    # plan 7.2: timestamp se mide desde el inicio de cada periodo
    ts_min = ev_df.groupby(["match_id", "period"])["timestamp"].min()
    if not (ts_min == "00:00:00.000").all():
        raise ValueError(f"timestamp no arranca en 00:00:00.000 en {(ts_min != '00:00:00.000').sum()} periodos: "
                         f"{ts_min[ts_min != '00:00:00.000'].head().to_dict()}")
    docs_solo = [c["columna"] for c in f["endpoint"]["events"]["columnas"] if c["estado_cruce"] == "no_aparecio_en_muestra"]
    ev_pct = {c: 100 - pct(t_ev.column(c).null_count, n_ev, f"nulos de events.{c}") for c in t_ev.column_names}
    return {
        "n_ev": n_ev,
        "n_archivos_ev": len(archivos_tabla("events")),
        "ev_tipo": {fl.name: tipo_pandas_arrow(fl.type) for fl in t_ev.schema},
        "ev_pct": ev_pct,
        "n_partidos": ev_df["match_id"].nunique(),
        "n_obv_tipos": ev_df.loc[ev_df["obv_total_net"].notna(), "type.name"].nunique(),
        "n_periodos": len(ts_min),
        "n_admin": {t: int(conteo_tipos.get(t, 0)) for t in ADMINISTRATIVOS},
        "faltan_en_91": [c for c in docs_solo if c not in t_ev.column_names],
        "pct_sin_loc": 100 - ev_pct["location"],
    }


def cifras_lineups(f):
    # tramos de posicion desde lineups crudo; el nulo de `to` debe coincidir con Final Whistle y ser el ultimo tramo
    n_jugadores, n_tramos, to_nulo = 0, 0, 0
    nulos_l = dict.fromkeys(["player_nickname", "player_height", "player_weight", "skills_hops_rating", "skills_hops_raw_rating"]
                            + [f"stats_{k}" for k in STATS_L], 0)
    sin_tramos, todos_l = set(), set()
    reloj_mal, from_min, to_max = [], {}, None
    n_cruzan, n_to_menor, periodos_usados, tramos_te = 0, 0, set(), 0
    lu = f["lineups"]
    for mid, txt in zip(lu.column("match_id").to_pylist(), lu.column("lineup").to_pylist()):
        for j in json.loads(txt):
            n_jugadores += 1
            todos_l.add((mid, j["player_id"]))
            hops = (j.get("skills") or {}).get("HOPS") or {}
            valores = {"player_nickname": j.get("player_nickname"), "player_height": j.get("player_height"),
                       "player_weight": j.get("player_weight"), "skills_hops_rating": hops.get("rating"),
                       "skills_hops_raw_rating": hops.get("raw_rating"),
                       **{f"stats_{k}": (j.get("stats") or {}).get(k) for k in STATS_L}}
            for k, v in valores.items():
                nulos_l[k] += v is None
            tramos = j.get("positions") or []
            if not tramos:
                sin_tramos.add((mid, j["player_id"]))
            n_tramos += len(tramos)
            for i, p in enumerate(tramos):
                reloj_mal += [(mid, j["player_id"], k, p[k]) for k in ("from", "to")
                              if p.get(k) is not None and not RELOJ.match(p[k])]
                if p.get("from") is not None:
                    fp = p.get("from_period")
                    from_min[fp] = p["from"] if fp not in from_min else min(from_min[fp], p["from"])
                periodos_usados |= {(mid, p[k]) for k in ("from_period", "to_period") if p.get(k) is not None}
                tramos_te += any(p.get(k) in COTA_TE for k in ("from_period", "to_period"))
                if p.get("to") is not None:
                    to_max = p["to"] if to_max is None else max(to_max, p["to"])
                    n_cruzan += p.get("to_period") != p.get("from_period")
                    n_to_menor += p.get("from") is not None and p["to"] < p["from"]
                if p.get("to") is None:
                    to_nulo += 1
                    if p.get("end_reason") != "Final Whistle" or i != len(tramos) - 1:
                        raise ValueError(f"`to` nulo que no es el ultimo tramo con Final Whistle: player_id {j.get('player_id')}, {p}")
    # posiciones.from y to: reloj corrido del partido, el 2o tiempo arranca en 00:45:00.000
    if reloj_mal:
        raise ValueError(f"posiciones.from/to sin formato HH:MM:SS.mmm en {len(reloj_mal)} valores: {reloj_mal[:5]}")
    if from_min.get(2) != INICIO_2T:
        raise ValueError(f"posiciones.from con from_period = 2 ya no arranca exactamente en {INICIO_2T} "
                         f"(mínimo {from_min.get(2, 'sin tramos')}): el reloj no es el corrido del partido")
    # el tiempo extra no tiene inicio verificado: el minimo de from solo puede ser una cota
    bajo_cota = {per: v for per, v in from_min.items() if per in COTA_TE and v < COTA_TE[per]}
    if bajo_cota:
        raise ValueError(f"posiciones.from en tiempo extra baja de la cota {COTA_TE}: {bajo_cota}")
    # el fin de cada periodo se calcula con su Half End en eventos
    ev = f["events"].select(["match_id", "period", "type.name"]).to_pandas()
    half_end = set(zip(*ev.loc[ev["type.name"] == "Half End", ["match_id", "period"]].to_numpy().T.tolist()))
    sin_half_end = sorted(periodos_usados - half_end)
    if sin_half_end:
        raise ValueError(f"periodos de posiciones sin evento Half End en eventos: {sin_half_end[:5]}")
    # banca que no entro: sin tramos en posiciones y sin fila en player_match_stats
    pms_ids = f["player_match_stats"].select(["match_id", "player_id"]).to_pandas()
    con_pms = set(zip(pms_ids["match_id"], pms_ids["player_id"]))
    if todos_l - con_pms != sin_tramos:
        raise ValueError(f"la banca sin tramos no coincide con la que no tiene player_match_stats: "
                         f"{len(sin_tramos)} sin tramos, {len(todos_l - con_pms)} sin player_match_stats")
    return {"n_jugadores": n_jugadores, "n_tramos": n_tramos, "to_nulo": to_nulo,
            "pct_to_nulo": pct(to_nulo, n_tramos, "tramos con `to` nulo"),
            "inicio_periodos": {per: from_min[per] for per in (1, 2)}, "min_from_te": {per: from_min[per] for per in COTA_TE if per in from_min},
            "n_partidos_te": len({m for m, per in periodos_usados if per in COTA_TE}), "n_tramos_te": int(tramos_te), "n_cruzan": int(n_cruzan), "n_to_menor": int(n_to_menor),
            "max_to": to_max,
            "pct_l": {k: pct(v, n_jugadores, f"nulos de alineaciones.{k}") for k, v in nulos_l.items()},
            "n_banca": len(sin_tramos)}


def comprobar_long_balls(f):
    lb = f["player_match_stats"].select(["player_match_long_balls", "player_match_successful_long_balls",
                                         "player_match_long_ball_ratio"]).to_pandas().query("player_match_long_balls > 0")
    if lb.empty:
        raise ValueError("no hay filas con player_match_long_balls > 0; no se puede comprobar que sean los intentos")
    sin_ratio = lb["player_match_long_ball_ratio"].isna()
    if sin_ratio.any():
        raise ValueError(f"player_match_long_ball_ratio es nulo en {sin_ratio.sum()} filas con player_match_long_balls > 0")
    if not ((lb["player_match_successful_long_balls"] / lb["player_match_long_balls"] - lb["player_match_long_ball_ratio"]).abs() < 1e-6).all():
        raise ValueError("player_match_long_balls ya no son los intentos: successful / long_balls != long_ball_ratio")


def cifras_partidos(f):
    t_p = f["partidos"]
    llenas = {c: t_p.num_rows - t_p.column(c).null_count for c in VACIAS_P}
    if any(llenas.values()):
        raise ValueError(f"columnas de partidos que se descartan por vacías ya traen datos: {llenas}")
    return {"n_filas_partidos": t_p.num_rows,
            "entrenador_cols": [snake(x, colapsar=True) for x in t_p.column_names if "entrenador" in x]}


def calcular_cifras(f):
    # Cifras que se citan en el contrato y comprobaciones de los datos; falla con ValueError si un supuesto ya no se cumple.
    c = cifras_eventos(f)
    t_f = f["frames_360"]
    # C21: frames sin visible_player_counts; los conteos quedan nulos (sin conteo, no cero)
    c["n_vpc_vacio"] = sum(not (json.loads(v) if isinstance(v, str) else v) for v in t_f.column("visible_player_counts").to_pylist())
    c["pct_vpc_vacio"] = pct(c["n_vpc_vacio"], t_f.num_rows, "frames sin visible_player_counts")
    c.update(cifras_lineups(f))
    comprobar_long_balls(f)
    c.update(cifras_partidos(f))
    t_liga = f["team_match_stats_liga"].select(["match_id", "season_name"]).to_pandas()
    c["n_liga"], c["n_temporadas"] = t_liga["match_id"].nunique(), t_liga["season_name"].nunique()
    c["fuera"] = [snake(x) for x in c["faltan_en_91"]]
    valores_cs = {v["valor_nombre"] for v in f["dic"]["valores"]["matches"] if v["ruta_json"] == "collection_status"}
    if not set(VIDEO) <= valores_cs:
        raise ValueError(f"{sorted(set(VIDEO) - valores_cs)} no son valores de collection_status en el diccionario")
    # filas de cada tabla, contadas sobre los parquet crudos (antes de la limpieza)
    c["filas_tabla"] = {
        "partidos": f["partidos"].num_rows,
        "eventos": c["n_ev"],
        "frames_360": n_json(t_f, "freeze_frame"),
        "frames_360_evento": t_f.num_rows,
        "alineaciones": c["n_jugadores"],
        "posiciones": c["n_tramos"],
        "team_match_stats": f["team_match_stats"].num_rows,
        "player_match_stats": f["player_match_stats"].num_rows,
        "team_match_stats_liga": f["team_match_stats_liga"].num_rows,
        "related_events": n_json_events("related_events"),
        "tactics_lineup": n_json_events("tactics.lineup"),
        "defensive_responsibility": n_json_events("defensive_responsibility.players"),
        "shot_freeze_frame": n_json_events("shot.freeze_frame"),
    }
    return c


# ---------- filas del contrato por tabla ----------

def filas_eventos(f, c):
    doc, n_partidos, ev_pct = f["doc"], c["n_partidos"], c["ev_pct"]
    filas = [fila("match_id", "Int64", "Partido al que pertenece el evento.", "match_id (agregado por la descarga)", "Llave junto con `index`.")]

    def agrega_evento(col, tipo_src, fuera=False):
        if col in LISTAS_AUX or col == "match_id":
            return
        if fuera and not es_bandera_documentada(doc, col):
            raise ValueError(f"`{col}` no sale en los parquet y el diccionario no la documenta como bandera; "
                             "no se puede suponer que sea boolean con False")
        d = desc_corta(doc, "events", col)
        pref = f" {no_existe(n_partidos).capitalize()}; se crea con False." if fuera else ""
        if col in COORD:
            for suf in COORD[col]:
                eje = suf.split("_")[-1]
                if col == "location":
                    dd = f"Coordenada {eje} del evento (yardas, cancha 120x80, ataque hacia x=120)."
                    regla = "Lista JSON [x, y] -> columnas; sin ubicación queda nulo (no imputar, excluir de mapas)."
                else:
                    dd = f"Coordenada {eje} del destino del evento (pase, conducción, tiro o portero), en yardas."
                    regla = ("Se separa [x, y(, z)]; un solo juego de columnas end_* para pass, carry, shot y goalkeeper "
                             "(cada evento tiene a lo sumo uno; se interpreta con `type_name`). Nulo si no hay destino.")
                existente = [x for x in filas if x["columna"] == suf]
                if existente:
                    existente[0]["origen"] += f"; `{col}`"
                else:
                    filas.append(fila(suf, "float64", dd, f"`{col}`", regla))
            return
        n = snake(col)
        tipo, regla, relleno = tipo_src, "Sin cambios.", None
        if tipo_src == "bool":
            if col in BOOL_NULL_LEGIT:
                tipo, regla = "boolean", "Nulo legítimo (solo juego abierto); no imputar."
            else:
                tipo, regla, relleno = "boolean", "Ausente = False (rellenar con False)." + pref, "False"
        elif tipo_src in ("float", "int") and (col.endswith(".id") or col.endswith("_id") or col == "tactics.formation" or tipo_src == "int"):
            tipo = "Int64"
            regla = "Entero." if ev_pct.get(col, 0) >= 100 and tipo_src == "int" else "Entero con nulos (Int64)."
            if tipo_src == "float":
                regla = "Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente."
        elif tipo_src == "float":
            tipo = "float64"
            if col.startswith("obv_"):
                regla = f"Nulo legítimo (OBV solo en {c['n_obv_tipos']} tipos de evento); no imputar."
            elif ev_pct.get(col, 100) < 99.9:
                regla = "Nulo fuera del tipo de evento correspondiente; no imputar."
        elif tipo_src == "str":
            if col in JSON_STR:
                tipo, regla = "string", "Lista guardada como texto JSON."
            elif col in STR_LIBRE:
                tipo, regla = "string", "strip."
                if col == "id":
                    regla = "UUID; solo llave (no modelar). strip."
                elif col == "timestamp":
                    regla = (f"Texto HH:MM:SS.mmm desde el inicio del periodo. Verificado: el mínimo por (match_id, period) "
                             f"es 00:00:00.000 en los {c['n_periodos']} periodos de los {n_partidos} partidos.")
                elif col in ("pass.assisted_shot_id", "shot.key_pass_id"):
                    regla = "UUID que apunta a `id` de otro evento; strip."
            else:
                tipo = "category"
                regla = "strip." if ev_pct.get(col, 0) >= 99.9 else "strip; nulo fuera del tipo de evento correspondiente."
        filas.append(fila(n, tipo, d, f"`{col}`", regla, relleno=relleno, puede_faltar=fuera))

    for col in f["events"].column_names:
        agrega_evento(col, c["ev_tipo"][col])
    for col in c["faltan_en_91"]:
        agrega_evento(col, "bool", fuera=True)

    sin_filas = [t for t, n in c["n_admin"].items() if n == 0]
    nota_admin = (f" {lista_md(sin_filas)} no tiene filas en los {n_partidos} partidos; está en la lista porque la especificación de Lee lo cuenta como administrativo."
                  if sin_filas else "")
    filas += [
        fila("pass_completed", "boolean", "Pase completado (True) o fallido (False); nulo si el evento no es Pass.", "`pass.outcome.name`", "Resultado vacío = éxito: True si type_name = Pass y pass_outcome_name es nulo; False si trae resultado. Nulo cuando type_name no es Pass."),
        fila("receipt_ok", "boolean", "Recepción buena (True) o mala (False); nulo si el evento no es Ball Receipt*.", "`ball_receipt.outcome.name`", "Resultado vacío = éxito: True si type_name = 'Ball Receipt*' y el resultado es nulo; False si trae resultado. Nulo cuando type_name no es 'Ball Receipt*'."),
        fila("match_second", "Int64", "Segundo del partido desde el inicio.", "`minute`, `second`", "minute * 60 + second. NO es único entre periodos (el 2o tiempo arranca en 2700 pero el 1o puede pasar de 2700): ordenar siempre por (`match_id`, `index`); `match_second` sirve para agrupar por tiempo dentro de (`match_id`, `period`)."),
        fila("es_administrativo", "boolean", "Evento que no entra al análisis táctico.", "`type.name`", f"True para {', '.join(ADMINISTRATIVOS[:-1])} y {ADMINISTRATIVOS[-1]} (`contrato.ADMINISTRATIVOS`); se conservan en la tabla.{nota_admin}"),
        fila("torneo", "category", DESC_TORNEO, "`partidos.torneo`", f"Unión con partidos por match_id; {REGLA_TORNEO}."),
        fila("fase", "category", DESC_FASE, "`partidos.fase`", REGLA_FASE),
        fila("es_play_in", "boolean", DESC_PLAY_IN, "`partidos.es_play_in`", REGLA_PLAY_IN),
        fila("es_final", "boolean", DESC_ES_FINAL, "`partidos.es_final`", REGLA_ES_FINAL),
        fila("es_equipo_analizado", "boolean", "El evento lo ejecuta el equipo analizado (América).", "`team.id`, `partidos.equipo_id`", "team_id == equipo_id del partido."),
        fila("x_eq", "float64", "Coordenada x en la perspectiva del equipo analizado.", "`x`, `es_equipo_analizado`", "x si es del equipo analizado; 120 - x si es del rival (así el equipo analizado siempre ataca hacia x = 120)."),
        fila("y_eq", "float64", "Coordenada y en la perspectiva del equipo analizado.", "`y`, `es_equipo_analizado`", "y si es del equipo analizado; 80 - y si es del rival."),
        fila("end_x_eq", "float64", "Coordenada x de destino en la perspectiva del equipo analizado.", "`end_x`, `es_equipo_analizado`", "end_x si es del equipo analizado; 120 - end_x si es del rival."),
        fila("end_y_eq", "float64", "Coordenada y de destino en la perspectiva del equipo analizado.", "`end_y`, `es_equipo_analizado`", "end_y si es del equipo analizado; 80 - end_y si es del rival."),
    ]
    return filas


def filas_auxiliares():
    return {
        "related_events": [
            fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
            fila("index", "Int64", "Índice del evento que declara la relación.", "`index` del evento", "Llave junto con match_id."),
            fila("id", "string", "UUID del evento que declara la relación.", "`id`", "strip."),
            fila("related_id", "string", "UUID del evento relacionado.", "`related_events`", "explode de la lista JSON; una fila por relación."),
            fila("related_index", "Int64", "Índice del evento relacionado en el mismo partido.", "`related_events` + `id`", "Join de related_id contra id dentro del partido; nulo si no se encuentra."),
        ],
        "tactics_lineup": [
            fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
            fila("index", "Int64", "Índice del evento Starting XI o Tactical Shift.", "`index`", "Llave junto con match_id."),
            fila("team_id", "Int64", "Equipo del evento táctico.", "`team.id`", "Int64."),
            fila("tactics_formation", "Int64", "Formación (por ejemplo 4231).", "`tactics.formation`", "Float por los vacíos -> Int64."),
            fila("jersey_number", "Int64", "Dorsal.", "`tactics.lineup[].jersey_number`", "explode de la lista JSON."),
            fila("player_id", "Int64", "Jugador.", "`tactics.lineup[].player.id`", "explode."),
            fila("player_name", "string", "Nombre del jugador.", "`tactics.lineup[].player.name`", "strip."),
            fila("position_id", "Int64", "Posición (1 a 25).", "`tactics.lineup[].position.id`", "Int64."),
            fila("position_name", "category", "Nombre de la posición.", "`tactics.lineup[].position.name`", "strip."),
        ],
        "defensive_responsibility": [
            fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
            fila("index", "Int64", "Índice del evento.", "`index`", "Llave junto con match_id."),
            fila("player_id", "Int64", "Jugador con responsabilidad defensiva.", "`defensive_responsibility.players[].player_id`", "explode de la lista JSON."),
            fila("probability", "float64", "Probabilidad de responsabilidad defensiva del jugador.", "`defensive_responsibility.players[].probability`", "Sin cambios."),
            fila("interception_like_probability", "float64", "Probabilidad de acción tipo intercepción.", "`defensive_responsibility.players[].interception_like_probability`", "Nulo legítimo; no imputar."),
            fila("pressure_like_probability", "float64", "Probabilidad de acción tipo presión.", "`defensive_responsibility.players[].pressure_like_probability`", "Nulo legítimo; no imputar."),
        ],
        "shot_freeze_frame": [
            fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
            fila("index", "Int64", "Índice del tiro.", "`index`", "Llave junto con match_id."),
            fila("jugador_idx", "Int64", "Orden del jugador dentro del freeze frame.", "posición en la lista", "explode con contador desde 0."),
            fila("teammate", "boolean", "El jugador es compañero del tirador.", "`shot.freeze_frame[].teammate`", "Sin cambios."),
            fila("player_id", "Int64", "Jugador.", "`shot.freeze_frame[].player.id`", "Int64."),
            fila("player_name", "string", "Nombre.", "`shot.freeze_frame[].player.name`", "strip."),
            fila("position_id", "Int64", "Posición.", "`shot.freeze_frame[].position.id`", "Int64."),
            fila("position_name", "category", "Nombre de la posición.", "`shot.freeze_frame[].position.name`", "strip."),
            fila("x", "float64", "Coordenada x.", "`shot.freeze_frame[].location`", "Se separa [x, y]."),
            fila("y", "float64", "Coordenada y.", "`shot.freeze_frame[].location`", "Se separa [x, y]."),
        ],
    }


def filas_frames_360():
    return [
        fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
        fila("event_uuid", "string", "Evento al que pertenece el frame; se une con `eventos.id`.", "`event_uuid`", "strip. Llave junto con jugador_idx."),
        fila("jugador_idx", "Int64", "Orden del jugador dentro del freeze frame.", "posición en la lista `freeze_frame`", "explode con contador desde 0; el freeze frame no trae ids de jugador."),
        fila("teammate", "boolean", "El jugador visible es compañero de quien ejecuta el evento.", "`freeze_frame[].teammate`", "Sin cambios."),
        fila("actor", "boolean", "El jugador visible es quien ejecuta el evento.", "`freeze_frame[].actor`", "Sin cambios."),
        fila("keeper", "boolean", "El jugador visible es portero.", "`freeze_frame[].keeper`", "Sin cambios."),
        fila("x", "float64", "Coordenada x del jugador visible (yardas, perspectiva del equipo que ejecuta el evento).", "`freeze_frame[].location`", "Se separa [x, y]."),
        fila("y", "float64", "Coordenada y del jugador visible (yardas, perspectiva del equipo que ejecuta el evento).", "`freeze_frame[].location`", "Se separa [x, y]."),
        fila("es_equipo_analizado", "boolean", "El jugador visible pertenece al equipo analizado.", "`freeze_frame[].teammate`, `eventos.team_id`, `partidos.equipo_id`", "Si el equipo del evento es el analizado: teammate; si no: not teammate. Que el evento no esté en `eventos` no ocurre en las tablas escritas: un frame sin su evento es un huérfano y detiene la corrida."),
    ]


def filas_frames_360_evento(f, c):
    D = lambda col: desc_corta(f["doc"], "frames_360", col)
    nulo_conteo = (f" Nulo si `visible_player_counts` viene vacío ({c['n_vpc_vacio']:,} frames, {c['pct_vpc_vacio']:.1f}%). Que el evento no esté en `eventos` "
                   "no ocurre en las tablas escritas: un frame sin su evento es un huérfano y detiene la corrida. El nulo significa sin conteo, no cero.")
    return [
        fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
        fila("event_uuid", "string", "Evento (unión con `eventos.id`). Llave junto con match_id.", "`event_uuid`", "strip."),
        fila("visible_area", "string", D("visible_area"), "`visible_area`", "Polígono [x1, y1, x2, y2, ...] guardado como texto JSON."),
        fila("visible_area_yd2", "float64", "Área del polígono visible en yardas cuadradas.", "`visible_area`", "Fórmula del polígono (shoelace) sobre los puntos."),
        fila("n_visibles_equipo", "Int64", "Jugadores visibles del equipo que ejecuta el evento.", "`visible_player_counts[].count`", "count del `team_id` igual al `eventos.team_id` del evento (unión por `match_id` y `event_uuid`); vale 0 si ese equipo no aparece en `visible_player_counts`. Es el equipo del evento (el actor), no el equipo analizado." + nulo_conteo),
        fila("n_visibles_rival", "Int64", "Jugadores visibles del equipo rival.", "`visible_player_counts[].count`", "count del otro equipo del partido (`home_team_id`/`away_team_id` de `partidos`); vale 0 si ese equipo no aparece en `visible_player_counts` y queda nulo si el equipo del evento no es ninguno de los dos." + nulo_conteo),
        fila("line_breaking_pass", "boolean", D("line_breaking_pass"), "`line_breaking_pass`", "Ausente = False.", relleno="False"),
        fila("ball_receipt_in_space", "boolean", D("ball_receipt_in_space"), "`ball_receipt_in_space`", "Ausente = False.", relleno="False"),
        fila("num_defenders_on_goal_side_of_actor", "float64", D("num_defenders_on_goal_side_of_actor"), "`num_defenders_on_goal_side_of_actor`", "Nulo legítimo; no imputar."),
        fila("distance_to_nearest_defender", "float64", D("distance_to_nearest_defender"), "`distance_to_nearest_defender`", "Nulo legítimo; filtrar por `n_visibles_rival` antes de usarlo."),
        fila("ball_receipt_exceeds_distance", "float64", D("ball_receipt_exceeds_distance"), "`ball_receipt_exceeds_distance`", "Nulo legítimo; no imputar."),
        fila("distances_from_edge_of_visible_area", "string", D("distances_from_edge_of_visible_area"), "`distances_from_edge_of_visible_area`", "Lista de {point_id, distance} guardada como texto JSON."),
    ]


def filas_partidos(f):
    partidos = []
    for col in f["partidos"].column_names:
        if col in DROP_P:
            continue
        n = snake(col, colapsar=True)
        if col in INT_P:
            tipo = "Int64"
        elif col in BOOL_P:
            tipo = "boolean"
        elif col in FECHAS_P:
            tipo = TIPO_FECHA
        elif col in CAT_P:
            tipo = "category"
        else:
            tipo = tipo_c12(n, "string")
        if col in DERIV_P:
            d, regla = DERIV_P[col]
            origen = "`partidos.parquet` (derivada)"
        else:
            d, regla, origen = desc_corta(f["doc"], "matches", col), FECHAS_P.get(col, "Sin cambios."), f"`{col}`"
        partidos.append(fila(n, tipo, d, origen, regla))
    return partidos


def filas_alineaciones(f, c):
    L = lambda col: desc_corta(f["doc"], "lineups", col)
    pct_l = c["pct_l"]
    return [
        fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
        fila("team_id", "Int64", "Equipo.", "`team_id`", "Llave junto con player_id."),
        fila("team_name", "category", L("team_name"), "`team_name`", "strip."),
        fila("player_id", "Int64", L("lineup[].player_id"), "`lineup[].player_id`", "explode de `lineup`."),
        fila("player_name", "string", L("lineup[].player_name"), "`lineup[].player_name`", "strip."),
        fila("player_nickname", "string", L("lineup[].player_nickname"), "`lineup[].player_nickname`", f"strip; nulo en {pct_l['player_nickname']:.1f}% de las filas."),
        fila("birth_date", TIPO_FECHA, L("lineup[].birth_date"), "`lineup[].birth_date`", "Texto -> fecha."),
        fila("player_gender", "category", L("lineup[].player_gender"), "`lineup[].player_gender`", "Sin cambios."),
        fila("player_height", "float64", L("lineup[].player_height"), "`lineup[].player_height`", f"Sin cambios (cm); nulo en {pct_l['player_height']:.1f}% de las filas, no se imputa."),
        fila("player_weight", "float64", L("lineup[].player_weight"), "`lineup[].player_weight`", f"Sin cambios (kg); nulo en {pct_l['player_weight']:.1f}% de las filas, no se imputa."),
        fila("jersey_number", "Int64", L("lineup[].jersey_number"), "`lineup[].jersey_number`", "Int64."),
        fila("country_id", "Int64", L("lineup[].country.id"), "`lineup[].country.id`", "Int64."),
        fila("country_name", "category", L("lineup[].country.name"), "`lineup[].country.name`", "strip."),
        fila("stats_goals", "Int64", L("lineup[].stats.goals"), "`lineup[].stats.goals`", f"Vacío en {pct_l['stats_goals']:.1f}% de las filas; se recalcula desde eventos, no se usa como fuente."),
        *[fila(f"stats_{k}", "Int64", L(f"lineup[].stats.{k}"), f"`lineup[].stats.{k}`", f"Ídem (vacío en {pct_l[f'stats_{k}']:.1f}%).")
          for k in STATS_L[1:]],
        fila("skills_hops_rating", "float64", L("lineup[].skills.HOPS.rating"), "`lineup[].skills.HOPS.rating`", f"Nulo legítimo ({pct_l['skills_hops_rating']:.1f}%); no imputar."),
        fila("skills_hops_raw_rating", "float64", L("lineup[].skills.HOPS.raw_rating"), "`lineup[].skills.HOPS.raw_rating`", f"Nulo legítimo ({pct_l['skills_hops_raw_rating']:.1f}%); no imputar."),
    ]


def regla_reloj(c):
    n_con_to = c["n_tramos"] - c["to_nulo"]
    inicios = " y ".join(f"periodo {p} en {v}" for p, v in c["inicio_periodos"].items())
    minimos = " y ".join(f"{v} en el periodo {p}" for p, v in c["min_from_te"].items())
    cotas = " y ".join(f"{COTA_TE[p]}" for p in c["min_from_te"])
    return (f"Texto HH:MM:SS.mmm, reloj corrido del partido: el segundo tiempo empieza en {INICIO_2T} aunque el primero haya terminado "
            f"más tarde. `to − from` es la duración solo si `from_period` = `to_period`. {c['n_cruzan']:,} de los {n_con_to:,} tramos con `to` "
            f"cruzan de periodo y en {c['n_to_menor']} de ellos `to` es menor que `from`. Si el tramo cruza de periodo, la duración se suma por "
            "periodo: el fin de cada periodo en el reloj corrido es el inicio de ese periodo más el `timestamp` del evento Half End de ese "
            f"periodo en `eventos` (el `timestamp` se reinicia en cada periodo). Inicio verificado de los periodos 1 y 2 "
            f"(mínimo de `from` por `from_period`): {inicios}. Los periodos 3 y 4 (tiempo extra) no tienen inicio verificado, porque ningún "
            f"tramo empieza al arrancarlos: {c['n_partidos_te']} {'partido tiene' if c['n_partidos_te'] == 1 else 'partidos tienen'} tiempo extra y {c['n_tramos_te']} tramos tocan esos periodos. "
            f"Los datos son consistentes con inicios en {cotas}, pero eso no está comprobado; el mínimo observado de `from` es {minimos} "
            f"y solo sirve como cota, no como inicio. Verificado en los {c['n_tramos']:,} tramos: todos los valores no nulos tienen el formato, el "
            f"mínimo de `from` con `from_period` = 2 es exactamente {INICIO_2T} y el máximo de `to` es {c['max_to']}.")


def filas_posiciones(f, c):
    L = lambda col: desc_corta(f["doc"], "lineups", col)
    return [
        fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
        fila("team_id", "Int64", "Equipo.", "`team_id`", "Llave."),
        fila("player_id", "Int64", "Jugador.", "`lineup[].player_id`", "Llave."),
        fila("posicion_idx", "Int64", "Orden del tramo del jugador en el partido.", "posición en `lineup[].positions`", "explode con contador desde 0."),
        fila("position_id", "Int64", L("lineup[].positions[].position_id"), "`lineup[].positions[].position_id`", "Int64."),
        fila("position", "category", L("lineup[].positions[].position"), "`lineup[].positions[].position`", "strip."),
        fila("from", "string", L("lineup[].positions[].from"), "`lineup[].positions[].from`", regla_reloj(c)),
        fila("to", "string", L("lineup[].positions[].to"), "`lineup[].positions[].to`", regla_reloj(c) + f" Nulo en {c['to_nulo']:,} de {c['n_tramos']:,} tramos ({c['pct_to_nulo']:.1f}%): el jugador siguió hasta el silbatazo final (end_reason = Final Whistle, último tramo del jugador). No se imputa un minuto; para calcular la duración, el fin es el Half End del último periodo jugado ({C('posiciones_to')}; el periodo 5 son penales)."),
        fila("from_period", "Int64", L("lineup[].positions[].from_period"), "`lineup[].positions[].from_period`", "Int64."),
        fila("to_period", "Int64", L("lineup[].positions[].to_period"), "`lineup[].positions[].to_period`", "Float con vacíos -> Int64."),
        fila("start_reason", "category", L("lineup[].positions[].start_reason"), "`lineup[].positions[].start_reason`", "strip."),
        fila("end_reason", "category", L("lineup[].positions[].end_reason"), "`lineup[].positions[].end_reason`", "strip; sirve para detectar rojas."),
        fila("counterpart_id", "Int64", L("lineup[].positions[].counterpart_id"), "`lineup[].positions[].counterpart_id`", "Float con vacíos -> Int64."),
        fila("counterpart_name", "string", L("lineup[].positions[].counterpart_name"), "`lineup[].positions[].counterpart_name`", "strip."),
    ]


def es_proporcion(col):
    return bool(PROPORCION.search(col)) and not NO_PROPORCION.search(col)


def escala(t, col):
    # Etiqueta de escala para proporciones conocidas por nombre y rango de directness; NaN e infinitos cuentan como vacio.
    s = t.column(col).to_pandas().dropna().astype("float64")
    s = s[np.isfinite(s)]
    if s.empty:
        return " Sin datos observados."
    lo, hi = float(s.min()), float(s.max())
    if "directness" in col:
        return f" No es una proporción: rango observado de {lo:.2f} a {hi:.2f}."
    if lo == hi:
        return f" Un solo valor observado ({lo:g}); no alcanza para etiquetar la escala."
    if lo >= 0 and hi <= 1:
        return " Proporción; rango observado dentro de [0, 1] (observación de estos datos, no una garantía de StatsBomb)."
    if lo >= 0:
        return f" Razón que puede pasar de 1 (máximo observado {hi:g})."
    return f" No es una escala 0 a 1: rango observado de {lo:.2f} a {hi:.2f}."


def tabla_stats(f, slug, parquet, n_partidos, extras=()):
    t = f[parquet]
    cols = [c for c in t.column_names if c != "account_id"]
    docs_solo_s = [c["columna"] for c in f["endpoint"][slug]["columnas"]
                   if c["estado_cruce"] == "no_devuelto_por_api" and c["columna"] not in cols]
    out = []
    for c in cols + docs_solo_s:
        if c in extras:
            continue
        ta = tipo_pandas_arrow(t.schema.field(c).type) if c in cols else "float"
        regla = "Sin cambios."
        if c == "match_id" or c.endswith("_id"):
            tipo, regla = "Int64", "Int64."
        elif ta == "bool":
            tipo = "boolean"
        elif ta == "str":
            tipo, regla = tipo_c12(c, "string"), "strip."
        elif ta == "int":
            tipo = "Int64"
        else:
            tipo = "float64"
        if c in docs_solo_s:
            regla = f"Documentada en el diccionario, pero {no_existe(n_partidos)}; la limpieza la crea nula."
        elif tipo == "float64" and (es_proporcion(c) or "directness" in c):
            regla += escala(t, c)
        out.append(fila(c, tipo, desc_corta(f["doc"], slug, c), f"`{c}`", regla, puede_faltar=c in docs_solo_s))
    return out


def filas_liga(f, c):
    liga = tabla_stats(f, "team_match_stats", "team_match_stats_liga", c["n_liga"],
                       extras={"torneo", "fase", "es_play_in", "es_final", "match_date", "match_week"})
    origen = "`team_match_stats_liga.parquet`"
    return liga + [
        fila("torneo", "category", DESC_TORNEO, origen, f"Derivada de match_date: {REGLA_TORNEO}."),
        fila("fase", "category", DESC_FASE, origen, REGLA_FASE),
        fila("es_play_in", "boolean", DESC_PLAY_IN, origen, REGLA_PLAY_IN),
        fila("es_final", "boolean", DESC_ES_FINAL, origen, REGLA_ES_FINAL),
        fila("match_date", TIPO_FECHA, "Fecha del partido.", origen, "Texto -> fecha."),
        fila("match_week", "Int64", "Jornada.", origen, "Int64."),
    ]


def armar_tablas(f, c):
    # Filas del contrato (dict por columna) por tabla, grano de cada tabla y quien la produce.
    tablas = {"eventos": filas_eventos(f, c), **filas_auxiliares(),
              "frames_360": filas_frames_360(), "frames_360_evento": filas_frames_360_evento(f, c),
              "partidos": filas_partidos(f), "alineaciones": filas_alineaciones(f, c), "posiciones": filas_posiciones(f, c),
              "team_match_stats": tabla_stats(f, "team_match_stats", "team_match_stats", c["n_partidos"]),
              "player_match_stats": tabla_stats(f, "player_match_stats", "player_match_stats", c["n_partidos"]),
              "team_match_stats_liga": filas_liga(f, c)}
    notas = {
        "eventos": "Una fila por evento. Llave (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`).",
        "related_events": "Una fila por (evento, evento relacionado).",
        "tactics_lineup": "Una fila por jugador en cada evento Starting XI / Tactical Shift.",
        "defensive_responsibility": "Una fila por (evento, jugador). `probability_sum` y `categories` quedan en `eventos`.",
        "shot_freeze_frame": "Una fila por jugador en el freeze frame de cada tiro. Llave (`match_id`, `index`, `jugador_idx`).",
        "frames_360": "Una fila por jugador visible en cada frame. Solo incluye a quienes ve la cámara.",
        "frames_360_evento": "Una fila por evento con frame (área visible y métricas 360 a nivel evento).",
        "partidos": (f"Un partido por fila ({c['n_filas_partidos']} filas en el crudo; menos si {C('filtros_calidad')} excluye partidos). "
                     "Se descartan attendance, home_team_group y away_team_group (0% de datos) "
                     "y las listas de managers (se resumen en entrenador_*)."),
        "alineaciones": "Una fila por (partido, equipo, jugador) de la cédula (titulares y banca).",
        "posiciones": "Una fila por tramo de posición de cada jugador (explode de `lineup[].positions`).",
        "team_match_stats": "Una fila por (partido, equipo). Se descarta account_id.",
        "player_match_stats": "Una fila por (partido, jugador). Se descarta account_id.",
        "team_match_stats_liga": (f"Línea base: una fila por (partido, equipo) de los {c['n_liga']:,} partidos de las {c['n_temporadas']} temporadas "
                                  "(available, Complete, Normal). Sirve para comparar al equipo contra la liga."),
    }
    produce = {t: PAUX if t in AUXILIARES else P02
               for t in ORDEN}
    produce["posiciones"] = "02_limpieza.py (Yordi), con acuerdo de Lee"
    return {t: tablas[t] for t in ORDEN}, notas, produce


def comprobar_tablas(tablas):
    # colisiones de nombre dentro de una tabla
    for t in ORDEN:
        nombres = [x["columna"] for x in tablas[t]]
        if len(nombres) != len(set(nombres)):
            raise ValueError(f"columnas repetidas en {t}: {sorted({n for n in nombres if nombres.count(n) > 1})}")
    todas = [(t, x) for t in ORDEN for x in tablas[t]]
    malos = [(t, x["columna"], x["tipo"]) for t, x in todas if x["tipo"] not in TIPOS_VALIDOS]
    if malos:
        raise ValueError(f"tipos fuera de TIPOS_VALIDOS: {malos}")
    malos = [(t, x["columna"], x["tipo"]) for t, x in todas if x["tipo"] != tipo_c12(x["columna"], x["tipo"])]
    if malos:
        raise ValueError(f"columnas de nombre que no cumplen C12: {malos}")
    # relleno es la version estructurada de las reglas "Ausente = False"; en esta version deben coincidir
    con_relleno = {(t, x["columna"]) for t, x in todas if x["relleno"] is not None}
    por_regla = {(t, x["columna"]) for t, x in todas if x["regla"].startswith("Ausente = False")}
    otros = sorted((t, x["columna"]) for t, x in todas if x["relleno"] is not None and (x["relleno"], x["tipo"]) != ("False", "boolean"))
    if con_relleno != por_regla or otros:
        raise ValueError(f"relleno no coincide con las reglas 'Ausente = False': solo relleno {sorted(con_relleno - por_regla)}, "
                         f"solo regla {sorted(por_regla - con_relleno)}, relleno que no es False en un boolean {otros}")
    fila_ev = {x["columna"]: x for x in tablas["eventos"]}
    if any(fila_ev[col]["relleno"] != "False" for col in ("out", "off_camera")):
        raise ValueError("C11 dice que la limpieza rellena `out` y `off_camera` con False, y el contrato no lo hace")


# ---------- decisiones y resumenes ----------

def decisiones(c):
    fuera = c["fuera"]
    dec = [
        ("unidad", "Unidad de distancia", "Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m)", "RESUELTA (Yordi)", "-"),
        ("destino_unico", "Destino unificado `end_x`, `end_y`, `end_z`", "Un solo juego para pass, carry, shot y goalkeeper, interpretado con `type_name`", "RESUELTA (Yordi)", "-"),
        ("dos_tablas_360", "360 en dos tablas", "`frames_360` (jugador visible) y `frames_360_evento` (área y conteos)", "RESUELTA (Yordi)", "-"),
        ("shot_freeze_frame", "Tabla extra `shot_freeze_frame`", "Se incluye; la produce `02_auxiliares.py`", "Lee", CONFIRMAR),
        ("administrativos", "Eventos administrativos", "Se conservan en `eventos` con `es_administrativo = True`", "RESUELTA (Yordi)", "-"),
        ("match_clock", "`match_clock` y `minute_bin`", "No van en la tabla limpia. Se calculan en la fase 3 (`scripts/03_contexto.py`, Yordi) con la ficha C1 (`match_clock` y `minute_bin`) de la especificación de métricas de Lee: `match_clock = match_second / 60` y `minute_bin` en ventanas de 15 minutos por periodo", "RESUELTA (Lee)", "-"),
        ("categories_json", "`defensive_responsibility.categories`", "Texto JSON en `eventos`; no se explota", "Lee", CONFIRMAR),
        ("tarjetas_formaciones", "Tarjetas y formaciones de lineups", "Se cierra sin tablas nuevas: las formaciones salen de `tactics_formation` (eventos Starting XI y Tactical Shift) y las tarjetas de `foul_committed_card_*` y `bad_behaviour_card_*`, que ya están en `eventos`", "RESUELTA (Yordi)", "-"),
        ("posiciones_to", f"`posiciones.to` nulo ({c['pct_to_nulo']:.1f}%)", f"El nulo significa que el jugador siguió hasta el silbatazo final; no se imputa un minuto. Verificado con los {c['n_partidos']} partidos: {c['to_nulo']:,} de {c['n_tramos']:,} tramos tienen `to` nulo, todos con `end_reason` = Final Whistle y último tramo del jugador", "RESUELTA (Yordi)", "-"),
        ("columnas_ausentes", "Columnas que no aparecen siempre", f"Las banderas ausentes se crean con False y las stats ausentes, nulas. Las que no salen en ninguno de los {c['n_partidos']} partidos se quedan en False para que el esquema no cambie entre corridas; hoy son {len(fuera)} en `eventos`: {lista_md(fuera)}", "RESUELTA (Yordi)", "-"),
        ("nulo_legitimo", "Banderas con nulo legítimo", "Solo `is_transition` e `is_controlled_possession` conservan el nulo; el resto va a False. La limpieza ya rellena `out` y `off_camera` con False; Lee confirma que así debe ser", "Lee", CONFIRMAR),
        ("nombres_c12", "`category` o `string` en nombres", f"Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas ({lista_md(PERSONAS)}) son string aunque terminen en `_name`", "RESUELTA (Yordi)", "-"),
        ("penales", "Penales (periodo 5)", "Se conservan con `period = 5`. Todas las fichas de la especificación de Lee los excluyen (exclusión global de su sección 1)", "RESUELTA (Lee)", "-"),
        ("sin_ubicacion", f"Eventos sin ubicación ({c['pct_sin_loc']:.1f}%)", "`x` e `y` nulos; se excluyen de los mapas, sin imputar", "RESUELTA (Pablo)", "-"),
        ("perspectiva_360", "Perspectiva en `frames_360`", "Solo `es_equipo_analizado`; `x` e `y` quedan en la perspectiva del equipo del evento (sin `x_eq`/`y_eq`)", "RESUELTA (Pablo)", "-"),
        ("donde_parquet", "Dónde viven los parquet limpios", "`data/interim/` (limpias) y `data/processed/` (agregadas del lunes)", "RESUELTA (Yordi)", "-"),
        ("produce_posiciones", "Quién produce `posiciones`", "`02_limpieza.py` (Yordi), con acuerdo de Lee", "RESUELTA (Yordi)", "-"),
        ("filtros_calidad", "Partidos que no pasan los filtros de calidad (plan 7.1)", f"Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son {texto_filtros()}. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos`", "RESUELTA (Yordi)", "-"),
        ("umbral_360", "Umbral de jugadores visibles del 360", "No se fija en la tabla limpia: `frames_360_evento` entrega `n_visibles_equipo` y `n_visibles_rival`, y cada métrica aplica su propio filtro. Lee define el umbral en la especificación de métricas; su valor provisional es actor visible y al menos 10 jugadores visibles, por calibrar con la distribución real de `visible_player_counts`. Esta decisión reemplaza el punto 7 de la sección 11 del plan", "RESUELTA (Yordi)", "-"),
        ("managers", "Listas de managers", f"`managers` no se explota: queda resumido en {lista_md(c['entrenador_cols'])} de `partidos`", "Lee", CONFIRMAR),
        ("conteo_360_vacio", "Conteos 360 sin `visible_player_counts`", f"`n_visibles_equipo` y `n_visibles_rival` quedan nulos cuando `visible_player_counts` viene vacío ({c['n_vpc_vacio']:,} frames, {c['pct_vpc_vacio']:.1f}%). El nulo quiere decir que no hay conteo y no equivale a cero", "RESUELTA (Yordi)", "-"),
    ]
    # los numeros C ya publicados no se mueven: dec va en el orden de PUBLICADAS y los numeros son 1..n
    if list(PUBLICADAS.values()) != list(range(1, len(PUBLICADAS) + 1)):
        raise ValueError(f"PUBLICADAS debe numerar 1..{len(PUBLICADAS)} en orden: {PUBLICADAS}")
    if [d[0] for d in dec] != list(PUBLICADAS):
        raise ValueError(f"las llaves de dec no coinciden con PUBLICADAS: {[d[0] for d in dec]}")
    return dec


def resumenes(c):
    # Resumen general por tabla: que, grano y llave, fuente, reglas principales y decisiones que la afectan (por llave).
    pct_l = c["pct_l"]
    banca = (f"{c['n_banca']:,} de los {c['n_jugadores']:,} jugadores de la cédula no tienen tramos en `posiciones` ni fila en "
             "`player_match_stats`: son la banca que no entró.")
    stats_ausente = ("Las columnas que el diccionario documenta y la API no devolvió se marcan con `puede_faltar = True`. "
                     "Si otra columna deja de llegar, sale del contrato y la protección de versión lo detecta como cambio.")
    res = {
        "partidos": dict(
            que="Una fila por partido de América con Jardine. Junta fecha, torneo, fase, rival, marcador y entrenadores, y es la tabla a la que se unen todas las demás por `match_id`.",
            llave="Un partido por fila. Llave: `match_id`.",
            fuente="Endpoint `matches` (`data/raw/parquet/partidos.parquet`) más las columnas derivadas que agrega `01_descarga.py`.",
            reglas=[
                f"Se descartan `attendance`, `home_team_group` y `away_team_group` (0% de datos). Las listas de managers no se explotan: quedan resumidas en {lista_md(c['entrenador_cols'])} ({C('managers')}).",
                f"`torneo` sale de `match_date` ({REGLA_TORNEO}). `fase` vale `regular` o `liguilla`; `es_play_in` marca el stage id {STAGE_PLAY_IN} y `es_final` los dos partidos de la final.",
                f"Los partidos que no pasan los filtros de calidad (plan 7.1) se excluyen y no detienen la corrida, así que la tabla limpia puede tener menos de {c['n_filas_partidos']} filas. La limpieza los anota en `data/interim/partidos_excluidos.csv`, con las columnas `match_id`, `campo` y `valor` y una fila por partido y por filtro que falla. Los filtros son {texto_filtros()}. Con `--solo-partido` y un partido excluido, solo se imprime el motivo y se sale con código 2, sin escribir nada.",
                f"Los errores de video ({', '.join(VIDEO[:-1])} y {VIDEO[-1]}) son valores de `collection_status`, así que el filtro `collection_status = Complete` ya los deja fuera.",
            ],
            filas_nota=" en los parquet crudos, antes de excluir partidos",
            dec=["filtros_calidad", "nombres_c12", "managers"]),
        "eventos": dict(
            que=f"Una fila por evento de los partidos de `partidos` ({c['n_partidos']} en el crudo): pases, tiros, presiones, conducciones y el resto de tipos de StatsBomb. Trae las coordenadas, las banderas de cada evento y las columnas que ponen al equipo analizado siempre atacando hacia x = 120.",
            llave="Un evento por fila. Llave: (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`).",
            fuente=f"Endpoint `events` (`data/raw/parquet/events__<torneo>.parquet`, {c['n_archivos_ev']} archivos) unido con `partidos` para `torneo`, `fase`, `es_play_in`, `es_final` y `equipo_id`.",
            reglas=[
                "Nombres en snake_case; `location` y los destinos se separan en `x`, `y` y un solo juego `end_x`, `end_y`, `end_z` que se interpreta con `type_name`.",
                "Las banderas ausentes se rellenan con False, salvo `is_transition` e `is_controlled_possession`, que conservan el nulo.",
                f"Los eventos administrativos ({', '.join(ADMINISTRATIVOS[:-1])} y {ADMINISTRATIVOS[-1]}) se conservan con `es_administrativo = True`.",
                "`x_eq`, `y_eq`, `end_x_eq` y `end_y_eq` voltean al rival (`120 - x`, `80 - y`) para comparar ambos equipos en una misma cancha.",
                "Se ordena siempre por (`match_id`, `index`). `match_second` no es único entre periodos y sirve para agrupar por tiempo dentro de (`match_id`, `period`). Los penales llevan `period = 5`.",
                f"`timestamp` se mide desde el inicio de cada periodo: el mínimo por (`match_id`, `period`) es 00:00:00.000 en los {c['n_periodos']} periodos.",
                "Las listas anidadas (`tactics.lineup`, `related_events`, `defensive_responsibility.players`, `shot.freeze_frame`) salen a las tablas auxiliares. Las formaciones y las tarjetas se leen de `tactics_formation`, `foul_committed_card_*` y `bad_behaviour_card_*`.",
            ],
            dec=["unidad", "destino_unico", "administrativos", "match_clock", "categories_json", "tarjetas_formaciones",
                 "columnas_ausentes", "nulo_legitimo", "nombres_c12", "penales", "sin_ubicacion"]),
        "frames_360": dict(
            que="Una fila por jugador visible en cada frame 360. Sirve para dibujar dónde estaban compañeros y rivales cuando ocurrió el evento.",
            llave="Un jugador visible por frame. Llave: (`match_id`, `event_uuid`, `jugador_idx`).",
            fuente="Endpoint `frames_360` (`data/raw/parquet/frames_360.parquet`), columna `freeze_frame` (texto JSON).",
            reglas=[
                "`freeze_frame` se explota con un contador `jugador_idx` desde 0; el freeze frame no trae ids de jugador.",
                "Solo aparecen los jugadores que ve la cámara.",
                "`x` e `y` quedan en la perspectiva del equipo que ejecuta el evento; `es_equipo_analizado` dice si el jugador visible es del equipo analizado que el evento no esté en `eventos` no ocurre en las tablas escritas: un frame sin su evento es un huérfano y detiene la corrida.",
                "`event_uuid` se une con `eventos.id` dentro del partido, por (`match_id`, `event_uuid`).",
                "Las filas van ordenadas por la llave (`match_id`, `event_uuid`, `jugador_idx`). `event_uuid` es un UUID, así que ese orden no es cronológico: para seguir el partido, une con `eventos` por (`match_id`, `event_uuid` = `id`) y ordena por `index`.",
            ],
            dec=["unidad", "dos_tablas_360", "sin_ubicacion", "perspectiva_360"]),
        "frames_360_evento": dict(
            que="Una fila por evento con frame 360. Guarda el área visible, cuántos jugadores se ven de cada equipo y las métricas 360 que StatsBomb calcula a nivel evento.",
            llave="Un evento con frame por fila. Llave: (`match_id`, `event_uuid`).",
            fuente="Endpoint `frames_360` (`data/raw/parquet/frames_360.parquet`), columnas de nivel evento.",
            reglas=[
                "`visible_area` queda como texto JSON y `visible_area_yd2` es su área en yardas cuadradas (fórmula del polígono).",
                "`n_visibles_equipo` cuenta al equipo del evento (el actor, no el equipo analizado) y `n_visibles_rival` al otro equipo del partido, según `home_team_id` y `away_team_id` de `partidos`. Los dos salen de `visible_player_counts` y valen 0 si su equipo no aparece; `n_visibles_rival` queda nulo si el equipo del evento no es ni el local ni el visitante.",
                "Las filas van ordenadas por la llave (`match_id`, `event_uuid`). `event_uuid` es un UUID, así que ese orden no es cronológico: para seguir el partido, une con `eventos` por (`match_id`, `event_uuid` = `id`) y ordena por `index`.",
                f"Si `visible_player_counts` viene vacío ({c['n_vpc_vacio']:,} frames, {c['pct_vpc_vacio']:.1f}%), los dos conteos quedan nulos. El nulo quiere decir que no hay conteo y no equivale a cero ({C('conteo_360_vacio')}).",
                f"El umbral de jugadores visibles no se fija en esta tabla. Cada métrica aplica su propio filtro con `n_visibles_equipo` y `n_visibles_rival`, y Lee lo define en la especificación de métricas. Su valor provisional es actor visible y al menos 10 jugadores visibles, por calibrar con la distribución real ({C('umbral_360')}).",
                "`line_breaking_pass` y `ball_receipt_in_space` ausentes valen False; el resto de las métricas conserva el nulo.",
            ],
            dec=["unidad", "dos_tablas_360", "umbral_360", "conteo_360_vacio"]),
        "alineaciones": dict(
            que="La cédula de cada partido: titulares y banca de cada equipo, con los datos del jugador (nacimiento, estatura, peso, dorsal, país) y su rating HOPS.",
            llave="Un jugador por equipo y partido. Llave: (`match_id`, `team_id`, `player_id`).",
            fuente="Endpoint `lineups` (`data/raw/parquet/lineups.parquet`), columna `lineup` (texto JSON con la lista de jugadores).",
            reglas=[
                "`lineup` se explota con una fila por jugador.",
                f"Las columnas `stats_*` vienen vacías en {pct_l['stats_goals']:.1f}% de las filas, así que los goles y asistencias se recalculan desde `eventos`.",
                f"Tienen nulos que no se imputan: `player_nickname` ({pct_l['player_nickname']:.1f}%), `skills_hops_*` ({pct_l['skills_hops_rating']:.1f}%), `player_weight` ({pct_l['player_weight']:.1f}%) y `player_height` ({pct_l['player_height']:.1f}%).",
                banca,
            ],
            dec=["nombres_c12"]),
        "posiciones": dict(
            que="Los tramos de posición de cada jugador en el partido: dónde jugó, desde y hasta qué momento, y por qué empezó y terminó cada tramo. Con ella se calculan minutos y se detectan cambios y rojas.",
            llave="Un tramo por fila. Llave: (`match_id`, `team_id`, `player_id`, `posicion_idx`).",
            fuente="Endpoint `lineups` (`data/raw/parquet/lineups.parquet`), lista `positions` dentro de cada jugador de `lineup`.",
            reglas=[
                f"`to` nulo significa que el jugador siguió hasta el silbatazo final: {c['to_nulo']:,} de {c['n_tramos']:,} tramos ({c['pct_to_nulo']:.1f}%), todos con `end_reason` = Final Whistle y último tramo del jugador. No se imputa un minuto.",
                f"`from` y `to` son texto HH:MM:SS.mmm con el reloj corrido del partido: el segundo tiempo empieza en {INICIO_2T}. `to − from` es la duración solo si `from_period` = `to_period`; en los {c['n_cruzan']:,} tramos que cruzan de periodo la duración se suma por periodo, con el evento Half End de `eventos` (detalle en la regla de `to`). El inicio de los periodos 3 y 4 (tiempo extra) no está verificado, y la regla da solo una cota. `from_period` y `to_period` son enteros (`to_period` con nulos).",
                "`posicion_idx` cuenta los tramos del jugador desde 0.",
                "`end_reason` sirve para detectar rojas.",
                banca + " No aparecen en esta tabla.",
            ],
            dec=["posiciones_to", "produce_posiciones"]),
        "team_match_stats": dict(
            que="Las estadísticas de cada equipo en cada partido, tal como las entrega la API de StatsBomb.",
            llave="Un equipo por partido. Llave: (`match_id`, `team_id`).",
            fuente="Endpoint `team_match_stats` (`data/raw/parquet/team_match_stats.parquet`).",
            reglas=["Se descarta `account_id`.", ESCALA_STATS, stats_ausente],
            dec=["columnas_ausentes", "nombres_c12"]),
        "player_match_stats": dict(
            que="Las estadísticas de cada jugador en cada partido, tal como las entrega la API de StatsBomb.",
            llave="Un jugador por partido. Llave: (`match_id`, `team_id`, `player_id`).",
            fuente="Endpoint `player_match_stats` (`data/raw/parquet/player_match_stats.parquet`).",
            reglas=[
                "Se descarta `account_id`.",
                ESCALA_STATS,
                stats_ausente,
                "Solo trae a los jugadores que entraron al campo; la banca que no jugó está en `alineaciones` y no aquí.",
            ],
            dec=["nombres_c12"]),
        "team_match_stats_liga": dict(
            que=f"La línea base de la liga: las mismas estadísticas de equipo para los {c['n_liga']:,} partidos de las {c['n_temporadas']} temporadas. Sirve para comparar a América contra el resto.",
            llave="Un equipo por partido de la liga. Llave: (`match_id`, `team_id`).",
            fuente=f"Endpoint `team_match_stats` (`data/raw/parquet/team_match_stats_liga.parquet`), solo partidos con {FILTRO_LIGA} (filtro de `01_descarga.py`).",
            reglas=[
                "Mismas columnas que `team_match_stats`, más `torneo`, `fase`, `es_play_in`, `es_final`, `match_date` y `match_week`.",
                f"No se le aplica la exclusión de partidos de {C('filtros_calidad')} ni el filtro de 360 (`match_status_360`): la línea base solo usa {FILTRO_LIGA}.",
                "`es_final` se calcula sobre toda la liga, no solo sobre los partidos de América.",
                "Con `--solo-partido` se recorta a las filas de ese partido.",
                "Se descarta `account_id`.",
            ],
            dec=["columnas_ausentes", "nombres_c12"]),
        "related_events": dict(
            que="Una fila por cada relación entre dos eventos, por ejemplo un pase y su recepción.",
            llave="Una relación por fila. Llave: (`match_id`, `index`, `related_id`).",
            fuente="Endpoint `events`, columna `related_events` (lista JSON de UUID).",
            reglas=[
                "La lista se explota con una fila por relación.",
                "`related_index` sale de unir `related_id` contra `id` dentro del partido; queda nulo si no se encuentra.",
            ],
            dec=[]),
        "tactics_lineup": dict(
            que="Los jugadores de cada evento Starting XI y Tactical Shift, con su posición y dorsal. De aquí salen las formaciones en juego.",
            llave="Un jugador por evento táctico. Llave: (`match_id`, `index`, `player_id`).",
            fuente="Endpoint `events`, columna `tactics.lineup` (lista JSON).",
            reglas=[
                "La lista se explota con una fila por jugador.",
                "`tactics_formation` es entero (por ejemplo 4231).",
                "Las formaciones se leen de `tactics_formation`; no hay tabla aparte.",
            ],
            dec=["tarjetas_formaciones"]),
        "defensive_responsibility": dict(
            que="La probabilidad de responsabilidad defensiva que StatsBomb asigna a cada jugador en cada evento.",
            llave="Un jugador por evento. Llave: (`match_id`, `index`, `player_id`).",
            fuente="Endpoint `events`, columna `defensive_responsibility.players` (lista JSON).",
            reglas=[
                "La lista se explota con una fila por jugador.",
                "`probability_sum` y `categories` se quedan en `eventos`; `categories` como texto JSON.",
                "`interception_like_probability` y `pressure_like_probability` tienen nulo legítimo y no se imputan.",
            ],
            dec=["categories_json"]),
        "shot_freeze_frame": dict(
            que="Los jugadores visibles en el momento de cada tiro, con su posición en la cancha. Sirve para ver quién estaba en la línea de tiro y dónde estaba el portero.",
            llave="Un jugador visible por tiro. Llave: (`match_id`, `index`, `jugador_idx`).",
            fuente="Endpoint `events`, columna `shot.freeze_frame` (lista JSON).",
            reglas=[
                "La lista se explota con un contador `jugador_idx` desde 0.",
                "`x` e `y` salen de `location`.",
                "No estaba en la lista original de tareas; se agregó porque el plan 7.3.7 pide explotar `shot.freeze_frame`.",
            ],
            dec=["unidad", "shot_freeze_frame"]),
    }
    # C18 afecta a las tablas por partido de 02_limpieza.py y a las de 02_auxiliares.py
    for t in POR_PARTIDO + AUXILIARES:
        if "filtros_calidad" not in res[t]["dec"]:
            res[t]["dec"].append("filtros_calidad")
    for t in AUXILIARES:
        res[t]["reglas"].append(f"Debe salir de `data/interim/eventos.parquet` y no de los crudos, para traer solo los `match_id` de `partidos` ({C('filtros_calidad')}).")
    return res


# ---------- contrato anterior y historial ----------

def leer_anterior(ruta):
    # Tipos del contrato anterior por (tabla, columna).
    viejo = {}
    if ruta.suffix == ".csv":
        v0 = pd.read_csv(ruta, encoding="utf-8")
        for r in v0.itertuples():
            viejo[(r.tabla, r.columna)] = r.tipo
    else:
        # formato de un solo md de la v0.1; desde la v0.2 se compara contra el csv
        tabla_act = None
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^## `(\w+)`", linea)
            if linea.startswith("## "):
                tabla_act = m.group(1) if m else None
            m = re.match(r"^\| `([^`]+)` \| ([^|]+) \|", linea)
            if m and tabla_act:
                viejo[(tabla_act, m.group(1))] = m.group(2).strip()
    if not viejo:
        sys.exit(f"No se encontraron columnas en {ruta}; desde la v0.2 pasa el contrato_datos.csv")
    return viejo


def comparar(tablas, viejo):
    # Cambios de tipo, columnas nuevas y quitadas por tabla; una tabla entera nueva o quitada cuenta todas sus columnas.
    cambios_tipo, nuevas = [], {}
    actuales = {(t, x["columna"]) for t in ORDEN for x in tablas[t]}
    quitadas = sorted(k for k in viejo if k not in actuales)
    for t in ORDEN:
        for x in tablas[t]:
            k = (t, x["columna"])
            if k in viejo and viejo[k] != x["tipo"]:
                cambios_tipo.append((t, x["columna"], viejo[k], x["tipo"]))
            elif k not in viejo:
                nuevas.setdefault(t, []).append(x["columna"])
    return cambios_tipo, nuevas, quitadas


def tablas_de_mas_y_de_menos(viejo):
    # Tablas que el contrato anterior no tenia y tablas que ya no estan.
    previas = {t for t, _ in viejo}
    return [t for t in ORDEN if t not in previas], sorted(previas - set(ORDEN))


def describe_cambios(tablas, viejo):
    # Lineas que explican las diferencias contra un contrato anterior; vacio si no hay.
    cambios_tipo, nuevas, quitadas = comparar(tablas, viejo)
    t_nuevas, t_quitadas = tablas_de_mas_y_de_menos(viejo)
    lineas = [f"tabla nueva `{t}` ({len(nuevas[t])} columnas)" for t in t_nuevas]
    lineas += [f"tabla quitada `{t}`" for t in t_quitadas]
    lineas += [f"`{t}` agrega {lista_md(cs)}" for t, cs in nuevas.items() if t not in t_nuevas]
    lineas += [f"`{t}.{col}` ya no está" for t, col in quitadas if t not in t_quitadas]
    lineas += [f"`{t}.{col}` pasa de {a} a {b}" for t, col, a, b in cambios_tipo]
    return lineas


def proteger_publicada(tablas):
    # VERSION ya publicada: lo generado no puede cambiar tablas, columnas ni tipos del csv que esta en docs/contrato/.
    csv = OUT / "contrato_datos.csv"
    if not csv.is_file():
        print(f"Aviso: no existe {csv}; no hay contrato publicado contra el que comparar {VERSION}.")
        return
    lineas = describe_cambios(tablas, leer_anterior(csv))
    if lineas:
        mostrar = lineas[:15] + ([f"... y {len(lineas) - 15} más"] if len(lineas) > 15 else [])
        sys.exit(f"{VERSION} ya está publicada y lo generado cambia tablas, columnas o tipos respecto a {csv}; no se escribió nada:\n- "
                 + "\n- ".join(mostrar) + "\nSi el cambio es intencional, sube VERSION y FECHA en scripts/gen_contrato.py "
                 "(ver \"Cómo se publica una versión nueva\" en el README) y copia antes el csv publicado fuera de docs/contrato/.")


def comprobar_ruta_fuera_de_salida(ruta, publicada):
    # Una version nueva sobrescribe docs/contrato/contrato_datos.csv, asi que el csv anterior no puede estar ahi.
    if publicada is None and ruta is not None and ruta.resolve().is_relative_to(OUT.resolve()):
        sys.exit(f"{ruta} está dentro de {OUT}, y la corrida de {VERSION} sobrescribe esa carpeta. Copia primero el csv publicado "
                 "fuera de ella, por ejemplo con `git show HEAD:docs/contrato/contrato_datos.csv > %TEMP%\\contrato_anterior.csv`, "
                 "y pasa esa copia.")


def es_c12(cambio):
    return cambio[1] in EQUIPO_O_CATALOGO and (cambio[2], cambio[3]) == ("string", "category")


def es_fecha(cambio):
    return cambio[2].startswith("datetime64") and cambio[3].startswith("datetime64")


def entrada_calculada(tablas, viejo, version_ant, notas):
    # Entrada de VERSION para cambios.md: diferencias contra el contrato anterior mas las notas escritas a mano.
    cambios_tipo, nuevas, quitadas = comparar(tablas, viejo)
    n_cols = sum(len(tablas[t]) for t in ORDEN)
    if not (cambios_tipo or nuevas or quitadas):
        lineas = [f"Sin cambios de columnas ni de tipos respecto a {version_ant}: las {len(ORDEN)} tablas conservan sus {n_cols} columnas con los mismos tipos."]
    else:
        lineas = [f"Respecto a {version_ant}: {len(cambios_tipo)} cambios de tipo (tabla abajo), {sum(len(v) for v in nuevas.values())} columnas nuevas y {len(quitadas)} columnas quitadas. Las {len(ORDEN)} tablas suman {n_cols} columnas."]
    c12 = [x for x in cambios_tipo if es_c12(x)]
    if c12:
        lineas.append(f"{C('nombres_c12')}: {len(c12)} columnas de nombre de equipos y catálogos (los `*_name` y `partidos.rival_nombre`) pasan de string a category. Los nombres de personas siguen como string.")
    fechas = [x for x in cambios_tipo if es_fecha(x)]
    for a, b in sorted({(x[2], x[3]) for x in fechas}):
        grupo = [f"{x[0]}.{x[1]}" for x in fechas if (x[2], x[3]) == (a, b)]
        lineas.append(f"{len(grupo)} columnas de fecha pasan de {a} a {b}: {lista_md(grupo)}.")
    for t, col, a, b in cambios_tipo:
        if not (es_c12((t, col, a, b)) or es_fecha((t, col, a, b))):
            lineas.append(f"`{t}.{col}` pasa de {a} a {b}.")
    t_nuevas, t_quitadas = tablas_de_mas_y_de_menos(viejo)
    for t in t_nuevas:
        lineas.append(f"Tabla nueva `{t}` con {len(nuevas[t])} columnas.")
    for t in t_quitadas:
        lineas.append(f"La tabla `{t}` ya no está.")
    for t, cs in nuevas.items():
        if t not in t_nuevas:
            lineas.append(f"`{t}` agrega " + ", ".join(f"`{x}`" for x in cs) + ".")
    for t, col in quitadas:
        if t not in t_quitadas:
            lineas.append(f"`{t}.{col}` ya no está.")
    return {"version": VERSION, "fecha": FECHA, "desde": version_ant, "cambios": lineas + notas,
            "tipos_titulo": f"Tipos que cambian, calculados contra el `contrato_datos.csv` de {version_ant}:",
            "tipos": cambios_tipo, "nuevas": nuevas, "quitadas": quitadas, "extra": []}


# ---------- contenido de los archivos ----------

def fila_decision(d):
    llave, dec, dflt, quien, lim = d
    return f"| C{PUBLICADAS[llave]} | {dec} | {dflt} | {quien} | {lim if not quien.startswith('RESUELTA') else 'resuelta'} |"


def md_readme(tablas, notas, produce, c, decs):
    md = []
    md.append(f"# Contrato de datos {VERSION}\n")
    md.append(f"Estado: {VERSION}, {FECHA}. Dueño: Yordi.\n")
    md.append("## Para qué sirve\n")
    md.append(f"Es el acuerdo entre quien limpia los datos y quien los usa. Lee (métricas) y Pablo (gráficas) programan contra los nombres, tipos y llaves de las tablas limpias que producen `scripts/02_limpieza.py` y `scripts/02_auxiliares.py`. Los tipos salen de los parquet completos de los {c['n_partidos']} partidos de Jardine con América. Este contrato no trae el % de nulos por columna; ese reporte lo entrega Lee.\n")
    md.append(f"La versión ejecutable es `contrato_datos.csv`, que lee `scripts/contrato.py` para crear DataFrames vacíos y validar las tablas. Además de `tabla`, `columna`, `tipo`, `origen` y `regla`, trae `relleno` (con qué se llenan los ausentes; hoy solo False en las banderas) y `puede_faltar`. `puede_faltar` es True cuando la columna {no_existe(c['n_partidos'])}; la limpieza la crea igual, con su `relleno` o nula.\n")
    md.append("## Cómo se genera\n")
    md.append("Todo lo de esta carpeta sale de `python scripts/gen_contrato.py`; no se edita a mano. Para cambiar una regla o una decisión se modifica el script y se vuelve a correr. `cambios.md` sale de `HISTORIAL`, la lista de versiones ya publicadas que vive en el script. Si `VERSION` ya está en `HISTORIAL`, el script corre sin argumento y, antes de escribir, compara lo generado contra el `contrato_datos.csv` que ya está en esta carpeta: si cambian tablas, columnas o tipos, se detiene y pide subir `VERSION` y `FECHA`. Los cambios solo de texto de las reglas pasan.\n")
    md.append("## Cómo se publica una versión nueva\n")
    for i, t in enumerate([
        "Antes de correr nada, copia el csv publicado fuera de la carpeta, por ejemplo con `git show HEAD:docs/contrato/contrato_datos.csv > %TEMP%\\contrato_anterior.csv`. La corrida sobrescribe `docs/contrato/contrato_datos.csv`, y el script se detiene si le pasas ese archivo con una versión nueva.",
        "Sube `VERSION` y `FECHA` en `scripts/gen_contrato.py`. Si el contrato anterior que le pasas ya es `VERSION`, el script se detiene y pide subirlas.",
        "Corre `python scripts/gen_contrato.py <la copia del csv publicado>`. La versión anterior se lee del `README.md` que está junto al csv; si no está, pásala con `--version-anterior`.",
        "Como la versión nueva todavía no está en `HISTORIAL`, el script calcula su entrada (cambios de tipo, columnas nuevas o quitadas y las notas de `NOTAS_VERSION`) y la imprime como literal de Python.",
        "Al publicar, pega esa entrada al principio de `HISTORIAL` y vacía `NOTAS_VERSION`. Desde ahí la entrada queda fija y no depende del csv anterior.",
    ], start=1):
        md.append(f"{i}. {t}")
    md.append("")
    md.append("## Fuentes\n")
    md.append("`data/diccionario.json`, `data/raw/parquet/*.parquet` (salida de `scripts/01_descarga.py`) y `Plan_de_trabajo_Kpumas.md`, secciones 7.1 a 7.3.\n")
    md.append("## Convenciones\n")
    for t in [
        "Nombres en snake_case con `_` en lugar de `.` (`pass.length` -> `pass_length`, `shot.statsbomb_xg` -> `shot_statsbomb_xg`). La columna **origen** conserva la ruta con punto del diccionario para trazabilidad.",
        "En `partidos` se quita el prefijo repetido (`home_team.home_team_id` -> `home_team_id`); `50_50.*` pasa a `fifty_fifty_*` (un nombre no puede empezar con dígito).",
        f"Tipos pandas: `Int64` (entero con nulos), `float64`, `boolean` (con nulos), `string`, `category`, `{TIPO_FECHA}`. Ningún id queda como float. Las fechas van sin zona horaria en `{TIPO_FECHA}`, la resolución que da pandas 3 al convertir texto, y `validar()` exige ese dtype exacto.",
        "Llaves: eventos (`match_id`, `index`); frames_360 (`match_id`, `event_uuid`, `jugador_idx`); frames_360_evento (`match_id`, `event_uuid`); partidos `match_id`. `id` y `event_uuid` son UUID de texto y solo sirven como llave.",
        "Unidad: yardas, cancha 120 x 80, ataque hacia x = 120. Las coordenadas vienen en la perspectiva del equipo que ejecuta el evento (también en 360).",
        "**Perspectiva del equipo analizado.** `x`, `y`, `end_x`, `end_y` están en la perspectiva de `team_id` (el equipo del evento). Para comparar al equipo analizado contra sus rivales en una misma cancha, usar `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`: igual que `x`/`y` si `es_equipo_analizado`; `120 - x` y `80 - y` si el evento es del rival.",
        "**Orden.** Ordenar siempre por (`match_id`, `index`). `match_second` no es único entre periodos: sirve para agrupar por tiempo dentro de (`match_id`, `period`).",
        "**Texto.** Todo texto (string y category) pasa por strip. En una columna de texto, \"Sin cambios.\" quiere decir \"solo strip\".",
        "**Categorías.** Las categorías de una columna category salen de los valores de cada corrida, así que dos corridas (o dos tablas) pueden traer categorías distintas. Antes de concatenarlas hay que alinearlas con `pandas.api.types.union_categoricals` o pasar la columna a string.",
        "Nulo legítimo no se imputa; las banderas que solo aparecen si son verdaderas se rellenan con False (plan 7.3).",
        f"`fase` vale `regular` (competition_stage.id en {{{', '.join(map(str, STAGES_REGULAR))}}}) o `liguilla`; `es_play_in` marca el stage id {STAGE_PLAY_IN} y `es_final` los dos partidos de la final. `torneo` sale de la fecha: {REGLA_TORNEO}.",
        "Los parquet limpios se guardan en `data/interim/` con el nombre de la tabla (`data/interim/eventos.parquet`); la muestra de un partido en `data/interim/muestra/`.",
        f"Las columnas documentadas que faltan en un partido se crean igual (False o nulo) para que el esquema no cambie entre corridas. `puede_faltar = True` marca solo las que {no_existe(c['n_partidos'], plural=True)}, y su regla lo dice.",
        f"**Alcance ({C('filtros_calidad')}).** Los partidos que no pasan los filtros de calidad (plan 7.1) los anota la limpieza en `data/interim/partidos_excluidos.csv`, con las columnas `match_id`, `campo` y `valor` y una fila por partido y por filtro que falla. Los valores posibles de `campo` son los cuatro filtros: {texto_filtros()}. Todas las tablas de `02_limpieza.py`, salvo `team_match_stats_liga`, traen solo los `match_id` que quedan en `partidos`; las 4 de `02_auxiliares.py` deben salir de `data/interim/eventos.parquet`, y no de los crudos, para cumplirlo.",
    ]:
        md.append(f"- {t}")
    md.append("")
    md.append("### Salidas de control de `02_limpieza.py`\n")
    md.append("Además de los parquet, `02_limpieza.py` escribe tres CSV de control en la misma carpeta (`data/interim/`, o `data/interim/muestra/` con `--solo-partido`):\n")
    for t in [
        "`partidos_excluidos.csv`: `match_id`, `campo` y `valor`, con una fila por partido y por filtro de 7.1 que falla. Los partidos que no pasan esos filtros se excluyen de todas las tablas salvo `team_match_stats_liga`, se reportan aquí y no detienen la corrida.",
        f"`calidad_limpieza.csv`: una fila por tabla con `tabla`, `filas_crudas`, `filas`, `filas_descartadas`, `columnas`, `llave`, `llaves_duplicadas`, `padre`, `huerfanos`, `huerfanos_por_padre` y `columnas_creadas_vacias`. En `partidos`, `filas_crudas` cuenta todas las filas leídas; en las tablas hijas cuenta solo las filas de los partidos que pasaron 7.1 y, en las que salen de explotar una lista, las filas ya explotadas. Las exclusiones de C18 ({C('filtros_calidad')}) se ven solo en `partidos`, así que `filas_descartadas` en las hijas es 0 por construcción. `padre` y `huerfanos_por_padre` listan las tablas padre en el mismo orden; `huerfanos` cuenta las filas que faltan en al menos uno de sus padres.",
        f"`cobertura_360_por_partido.csv`: una fila por partido con `match_id`, `eventos`, `eventos_con_frame`, `pct_con_frame`, `eventos_tacticos`, `pct_tacticos_con_frame`, `eventos_equipo_analizado`, `pct_equipo_con_frame`, `frames_sin_conteo` y `frames_umbral_provisional`. Los tácticos son los eventos con `es_administrativo = False`, y los del equipo analizado, los que tienen `es_equipo_analizado = True`. `frames_umbral_provisional` cuenta los frames que cumplen la regla provisional de Lee (actor visible y al menos 10 jugadores visibles, {C('umbral_360')}); es solo informativo y ninguna tabla se filtra con él.",
    ]:
        md.append(f"- {t}")
    md.append("")
    md.append("La corrida se detiene con código 1, sin escribir nada, cuando:\n")
    for t in [
        "alguna tabla no pasa `contrato.validar()`;",
        "a un partido le falta cobertura: debe tener filas en `eventos`, `frames_360`, `frames_360_evento` y `player_match_stats`; `home_team_id`, `away_team_id` y `equipo_id` no nulos; `equipo_id` igual al local o al visitante; exactamente el local y el visitante en `alineaciones` y `team_match_stats`; y al menos un evento con `es_equipo_analizado` no nulo. Un hueco detiene toda la corrida y no excluye el partido;",
        "alguna tabla tiene llaves duplicadas o huérfanos;",
        "ningún partido pasa los filtros de calidad;",
        "falta una columna cruda que el contrato no marca con `puede_faltar`;",
        "una conversión de tipo deja nulo un valor que no lo era;",
        "un evento tiene más de un destino no nulo entre `pass`, `carry`, `shot` y `goalkeeper`;",
        "llega un valor de tipo inesperado: un booleano donde va un número, una fecha numérica o con zona horaria, o un JSON inválido o de otro tipo;",
        "al unir con 360 hay eventos repetidos en (`match_id`, `id`);",
        "`match_id` aparece repetido en `partidos`;",
        "falla la preparación o la escritura de la carpeta temporal;",
        "algún archivo de destino está bloqueado (por ejemplo, abierto en Excel).",
    ]:
        md.append(f"- {t}")
    md.append("")
    md.append("Si el reemplazo falla a medias después de esa revisión, también sale con 1, y el mensaje dice qué archivos ya se reemplazaron y en qué carpeta temporal quedaron los que faltan. Con `--solo-partido`, si el partido pedido no está en `partidos.parquet` o no pasa los filtros, solo imprime el motivo y sale con código 2, sin escribir nada.\n")
    md.append("## Resumen de tablas\n")
    md.append("Las filas se cuentan sobre los parquet crudos. Cada tabla tiene su propio archivo con el resumen y todas sus columnas.\n")
    md.append("| tabla | columnas | filas | produce | grano |")
    md.append("|---|---|---|---|---|")
    for t in ORDEN:
        md.append(f"| [`{t}`]({t}.md) | {len(tablas[t])} | {c['filas_tabla'][t]:,} | {produce[t]} | {notas[t]} |")
    md.append("")
    md.append("## Decisiones\n")
    md.append("Las resueltas llevan `RESUELTA (Yordi)`, `RESUELTA (Lee)` o `RESUELTA (Pablo)`. Las demás tienen un default vigente, un responsable y una fecha límite.\n")
    md.append(ENC_DEC)
    md.append("|---|---|---|---|---|")
    for d in decs:
        md.append(fila_decision(d))
    md.append("")
    md.append("## Historial\n")
    md.append("Las versiones anteriores y lo que cambió en cada una están en [`cambios.md`](cambios.md).\n")
    return "\n".join(md)


def md_tabla(t, filas, r, produce, c, decs):
    dec_por_llave = {d[0]: d for d in decs}
    md = [ATRAS, f"# `{t}`\n", "## Resumen general\n", r["que"] + "\n"]
    md.append(f"- Grano y llave: {r['llave']}")
    md.append(f"- Quién la produce: {produce}")
    md.append(f"- Columnas: {len(filas)}")
    md.append(f"- Filas: {c['filas_tabla'][t]:,}{r.get('filas_nota', ' en los parquet crudos')}")
    md.append(f"- Fuente: {r['fuente']}")
    md.append("")
    md.append("Reglas principales:\n")
    for x in r["reglas"]:
        md.append(f"- {x}")
    md.append("")
    if r["dec"]:
        md.append("Decisiones que la afectan:\n")
        md.append(ENC_DEC)
        md.append("|---|---|---|---|---|")
        for k in sorted(r["dec"], key=PUBLICADAS.get):
            md.append(fila_decision(dec_por_llave[k]))
        md.append("")
    md.append(f"## Columnas ({len(filas)})\n")
    md.append("| columna | tipo | descripción | origen | regla de limpieza |")
    md.append("|---|---|---|---|---|")
    for x in filas:
        md.append(f"| `{x['columna']}` | {x['tipo']} | {x['descripcion']} | {x['origen']} | {x['regla']} |")
    md.append("")
    return "\n".join(md)


def md_cambios(historial):
    md = [ATRAS, "# Cambios del contrato\n"]
    for e in historial:
        desde = f", cambios desde {e['desde']}" if e["desde"] else ""
        md.append(f"## {e['version']} ({e['fecha']}){desde}\n")
        for x in e["cambios"]:
            md.append(f"- {x}")
        md.append("")
        if e["tipos"]:
            md.append(e["tipos_titulo"] + "\n")
            md.append(f"| tabla | columna | {e['desde']} | {e['version']} |")
            md.append("|---|---|---|---|")
            for t, col, a, b in e["tipos"]:
                md.append(f"| `{t}` | `{col}` | {a} | {b} |")
            md.append("")
        for titulo, lineas in e["extra"]:
            md.append(titulo + "\n")
            md += lineas
            md.append("")
    return "\n".join(md)


def csv_texto(tablas):
    filas_csv = []
    for t in ORDEN:
        for x in tablas[t]:
            filas_csv.append({"tabla": t, "columna": x["columna"], "tipo": x["tipo"],
                              "origen": x["origen"].replace("`", ""), "regla": x["regla"].replace("`", ""),
                              "relleno": x["relleno"], "puede_faltar": x["puede_faltar"]})
    return pd.DataFrame(filas_csv, columns=COLUMNAS).to_csv(index=False, lineterminator="\n")


def escribir(textos, csv):
    # Escribe en una carpeta temporal y reemplaza con os.replace, el csv primero; borra los md que ya no se generan.
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".contrato_", dir=OUT.parent))
    try:
        archivos = {"contrato_datos.csv": csv, **textos}
        for nombre, texto in archivos.items():
            (tmp / nombre).write_text(texto, encoding="utf-8", newline="\n")
        for nombre in archivos:
            os.replace(tmp / nombre, OUT / nombre)
    finally:
        # borra la carpeta temporal, tambien si la escritura fallo; el error se propaga
        shutil.rmtree(tmp, ignore_errors=True)
    sobrantes = sorted(p.name for p in OUT.glob("*.md") if p.name not in textos)
    for nombre in sobrantes:
        (OUT / nombre).unlink()
    return sobrantes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("anterior", nargs="?", type=Path, help="csv (o md de la v0.1) del contrato anterior")
    ap.add_argument("--version-anterior", help="etiqueta de la version anterior (por ejemplo v0.1)")
    args = ap.parse_args()
    ruta = args.anterior
    if args.version_anterior and ruta is None:
        ap.error("--version-anterior necesita el contrato anterior (csv o md)")
    if ruta is not None and not ruta.is_file():
        sys.exit(f"No existe el contrato anterior: {ruta}")
    version_ant = args.version_anterior or (version_de(ruta) if ruta else None)
    if ruta is not None and version_ant is None:
        sys.exit(f"No se pudo detectar la version de {ruta}; pasala con --version-anterior")
    if version_ant == VERSION:
        sys.exit(f"El contrato anterior ({ruta}) ya es {VERSION}, la versión que se está generando. Para publicar una versión "
                 f"nueva, sube VERSION y FECHA en scripts/gen_contrato.py; para regenerar la {VERSION}, corre el script sin argumento.")
    publicada = next((e for e in HISTORIAL if e["version"] == VERSION), None)
    comprobar_ruta_fuera_de_salida(ruta, publicada)
    if publicada is None and ruta is None:
        sys.exit(f"{VERSION} todavía no está en HISTORIAL: pasa el contrato_datos.csv publicado de la versión anterior "
                 "para calcular su entrada de cambios.md.")

    f = leer_fuentes()
    c = calcular_cifras(f)
    tablas, notas, produce = armar_tablas(f, c)
    comprobar_tablas(tablas)
    decs = decisiones(c)
    res = resumenes(c)
    viejo = leer_anterior(ruta) if ruta else {}

    if publicada is None:
        nueva = entrada_calculada(tablas, viejo, version_ant, NOTAS_VERSION)
        historial = [nueva] + HISTORIAL
        print(f"Entrada calculada de {VERSION}; al publicar, pégala al principio de HISTORIAL:")
        print(pprint.pformat(nueva, width=120, sort_dicts=False))
    else:
        historial = HISTORIAL
        proteger_publicada(tablas)
        if ruta is not None and version_ant == publicada["desde"]:
            cambios_tipo, nuevas, quitadas = comparar(tablas, viejo)
            if (sorted(cambios_tipo) != sorted(publicada["tipos"]) or nuevas != publicada.get("nuevas", {})
                    or sorted(quitadas) != sorted(publicada.get("quitadas", []))):
                sys.exit(f"El contrato ya no coincide con la entrada publicada de {VERSION} en HISTORIAL (tipos, columnas nuevas "
                         f"o quitadas respecto a {version_ant}). Sube VERSION y FECHA para publicar una versión nueva.")
            print(f"{VERSION} ya está en HISTORIAL; los tipos coinciden con su entrada publicada respecto a {version_ant}.")
        elif ruta is not None:
            print(f"{VERSION} ya está en HISTORIAL; cambios.md sale de ahí y {ruta} no se usa.")

    textos = {"README.md": md_readme(tablas, notas, produce, c, decs)}
    for t in ORDEN:
        textos[f"{t}.md"] = md_tabla(t, tablas[t], res[t], produce[t], c, decs)
    textos["cambios.md"] = md_cambios(historial)
    sobrantes = escribir(textos, csv_texto(tablas))

    print(json.dumps({t: len(tablas[t]) for t in ORDEN}))
    if sobrantes:
        print("md borrados por no corresponder a ninguna tabla:", sobrantes)


if __name__ == "__main__":
    main()
