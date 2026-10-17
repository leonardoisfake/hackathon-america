"""Genera docs/contrato_datos.md y docs/contrato_datos.csv desde los parquet crudos completos.

Uso:  python scripts/gen_contrato.py [contrato_anterior.md]

Los tipos y los % de nulos salen de data/raw/parquet, las descripciones de data/diccionario.json
y las reglas de limpieza del plan (7.1 a 7.3). El markdown y el csv se arman con las mismas filas,
asi que no divergen. Si se pasa el md de la version anterior, los tipos que cambiaron se listan
en la seccion Cambios.
"""
import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PARQ = ROOT / "data" / "raw" / "parquet"
FECHA = "2026-10-17"
VERSION = "v0.1"

dic = json.loads((ROOT / "data" / "diccionario.json").read_text(encoding="utf-8"))
DOC = {e["slug"]: {c["columna"]: c for c in e["columnas"]} for e in dic["endpoints"]}


def leer_tabla(nombre):
    archivos = sorted(glob.glob(str(PARQ / f"{nombre}__*.parquet"))) or [str(PARQ / f"{nombre}.parquet")]
    return pa.concat_tables([pq.read_table(a) for a in archivos], promote_options="permissive")


def tipo_pandas_arrow(t):
    if pa.types.is_boolean(t):
        return "bool"
    if pa.types.is_integer(t):
        return "int"
    if pa.types.is_floating(t):
        return "float"
    return "str"


MANUAL_DESC = {
    ("matches", "metadata.shot_fidelity_version"): "Versión de fidelidad con la que se capturaron los tiros.",
    ("matches", "metadata.xy_fidelity_version"): "Versión de fidelidad con la que se capturaron las coordenadas (sin documentar en el PDF).",
    ("events", "goalkeeper.end_location"): "Destino [x, y] de la acción del portero (sin documentar en el PDF).",
    ("matches", "home_team.country.id"): "Id del país del equipo local.",
    ("matches", "home_team.country.name"): "Nombre del país del equipo local.",
    ("matches", "away_team.country.id"): "Id del país del equipo visitante.",
    ("matches", "away_team.country.name"): "Nombre del país del equipo visitante.",
    ("team_match_stats", "account_id"): "",
}


def desc_corta(slug, col):
    if (slug, col) in MANUAL_DESC and MANUAL_DESC[(slug, col)]:
        return MANUAL_DESC[(slug, col)]
    c = DOC.get(slug, {}).get(col)
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


def snake(col, colapsar=False):
    n = col.replace("[]", "").replace(".", "_").replace("50_50", "fifty_fifty")
    partes = col.split(".")
    if colapsar and len(partes) == 2 and partes[1].startswith(partes[0]):
        n = partes[1]
    return n.lower()


def fila(columna, tipo, desc, origen, regla):
    return {"columna": columna, "tipo": tipo, "descripcion": desc, "origen": origen, "regla": regla}


tablas, notas, produce = {}, {}, {}
P02 = "02_limpieza.py (Yordi)"
PAUX = "02_auxiliares.py (Lee)"

t_ev = leer_tabla("events")
n_ev = t_ev.num_rows
ev_tipo = {f.name: tipo_pandas_arrow(f.type) for f in t_ev.schema}
ev_pct = {c: 100 * (1 - t_ev.column(c).null_count / n_ev) for c in t_ev.column_names}

LISTAS_AUX = {"tactics.lineup", "related_events", "defensive_responsibility.players", "shot.freeze_frame"}
COORD = {"location": ("x", "y"), "pass.end_location": ("end_x", "end_y"), "carry.end_location": ("end_x", "end_y"),
         "shot.end_location": ("end_x", "end_y", "end_z"), "goalkeeper.end_location": ("end_x", "end_y")}
BOOL_NULL_LEGIT = {"is_transition", "is_controlled_possession"}
STR_LIBRE = {"id", "timestamp", "pass.assisted_shot_id", "shot.key_pass_id", "player.name", "pass.recipient.name",
             "substitution.replacement.name"}
JSON_STR = {"defensive_responsibility.categories"}

filas = [fila("match_id", "Int64", "Partido al que pertenece el evento.", "match_id (agregado por la descarga)", "Llave junto con `index`.")]


def agrega_evento(col, tipo_src, fuera=False):
    if col in LISTAS_AUX or col == "match_id":
        return
    d = desc_corta("events", col)
    pref = " No apareció en los 91 partidos; se crea con False." if fuera else ""
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
            existente = [f for f in filas if f["columna"] == suf]
            if existente:
                existente[0]["origen"] += f"; `{col}`"
            else:
                filas.append(fila(suf, "float64", dd, f"`{col}`", regla))
        return
    n = snake(col)
    tipo, regla = tipo_src, "Sin cambios."
    if tipo_src == "bool":
        if col in BOOL_NULL_LEGIT:
            tipo, regla = "boolean", "Nulo legítimo (solo juego abierto); no imputar."
        else:
            tipo, regla = "boolean", "Ausente = False (rellenar con False)." + pref
    elif tipo_src in ("float", "int") and (col.endswith(".id") or col.endswith("_id") or col == "tactics.formation" or tipo_src == "int"):
        tipo = "Int64"
        regla = "Entero." if ev_pct.get(col, 0) >= 100 and tipo_src == "int" else "Entero con nulos (Int64)."
        if tipo_src == "float":
            regla = "Float por los vacíos -> Int64; nulo fuera del tipo de evento correspondiente."
    elif tipo_src == "float":
        tipo = "float64"
        if col.startswith("obv_"):
            regla = "Nulo legítimo (OBV solo en 10 tipos de evento); no imputar."
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
                regla = "Texto HH:MM:SS.mmm desde el inicio del periodo; verificar con groupby('period')."
            elif col in ("pass.assisted_shot_id", "shot.key_pass_id"):
                regla = "UUID que apunta a `id` de otro evento; strip."
        else:
            tipo = "category"
            regla = "strip." if ev_pct.get(col, 0) >= 99.9 else "strip; nulo fuera del tipo de evento correspondiente."
    filas.append(fila(n, tipo, d, f"`{col}`", regla))


for c in t_ev.column_names:
    agrega_evento(c, ev_tipo[c])
docs_solo = [c["columna"] for c in dic["endpoints"][3]["columnas"] if c["estado_cruce"] == "no_aparecio_en_muestra"]
faltan_en_91 = [c for c in docs_solo if c not in t_ev.column_names]
for c in faltan_en_91:
    agrega_evento(c, "bool", fuera=True)

filas += [
    fila("pass_completed", "boolean", "Pase completado (True) o fallido (False); nulo si el evento no es Pass.", "`pass.outcome.name`", "Resultado vacío = éxito: True si type_name = Pass y pass_outcome_name es nulo."),
    fila("receipt_ok", "boolean", "Recepción buena (True) o mala (False); nulo si el evento no es Ball Receipt*.", "`ball_receipt.outcome.name`", "Resultado vacío = éxito: True si type_name = 'Ball Receipt*' y el resultado es nulo."),
    fila("match_second", "Int64", "Segundo del partido desde el inicio.", "`minute`, `second`", "minute * 60 + second. NO es único entre periodos (el 2o tiempo arranca en 2700 pero el 1o puede pasar de 2700): ordenar siempre por (`period`, `match_second`)."),
    fila("es_administrativo", "boolean", "Evento que no entra al análisis táctico.", "`type.name`", "True para Half Start/End, Starting XI, Tactical Shift, Substitution, Player On/Off, Injury Stoppage y Referee Ball-Drop; se conservan en la tabla."),
    fila("torneo", "category", "Torneo del partido (por ejemplo 'Apertura 2023').", "`partidos.torneo`", "Unión con partidos por match_id; julio a diciembre = Apertura, enero a junio = Clausura."),
    fila("fase", "category", "regular o liguilla.", "`partidos.fase`", "regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso."),
    fila("es_play_in", "boolean", "El partido es de la ronda Play-In.", "`partidos.es_play_in`", "competition_stage.id = 2."),
    fila("es_final", "boolean", "El partido es uno de los dos de la final del torneo.", "`partidos.es_final`", "Dos últimos partidos de eliminación directa entre el mismo par de equipos."),
    fila("es_equipo_analizado", "boolean", "El evento lo ejecuta el equipo analizado (América).", "`team.id`, `partidos.equipo_id`", "team_id == equipo_id del partido."),
    fila("x_eq", "float64", "Coordenada x en la perspectiva del equipo analizado.", "`x`, `es_equipo_analizado`", "x si es del equipo analizado; 120 - x si es del rival (así el equipo analizado siempre ataca hacia x = 120)."),
    fila("y_eq", "float64", "Coordenada y en la perspectiva del equipo analizado.", "`y`, `es_equipo_analizado`", "y si es del equipo analizado; 80 - y si es del rival."),
    fila("end_x_eq", "float64", "Coordenada x de destino en la perspectiva del equipo analizado.", "`end_x`, `es_equipo_analizado`", "end_x si es del equipo analizado; 120 - end_x si es del rival."),
    fila("end_y_eq", "float64", "Coordenada y de destino en la perspectiva del equipo analizado.", "`end_y`, `es_equipo_analizado`", "end_y si es del equipo analizado; 80 - end_y si es del rival."),
]
tablas["eventos"] = filas
notas["eventos"] = "Una fila por evento. Llave (`match_id`, `index`). Ordenar siempre por (`match_id`, `index`)."
produce["eventos"] = P02

tablas["related_events"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("index", "Int64", "Índice del evento que declara la relación.", "`index` del evento", "Llave junto con match_id."),
    fila("id", "string", "UUID del evento que declara la relación.", "`id`", "strip."),
    fila("related_id", "string", "UUID del evento relacionado.", "`related_events`", "explode de la lista JSON; una fila por relación."),
    fila("related_index", "Int64", "Índice del evento relacionado en el mismo partido.", "`related_events` + `id`", "Join de related_id contra id dentro del partido; nulo si no se encuentra."),
]
notas["related_events"] = "Una fila por (evento, evento relacionado)."
tablas["tactics_lineup"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("index", "Int64", "Índice del evento Starting XI o Tactical Shift.", "`index`", "Llave junto con match_id."),
    fila("team_id", "Int64", "Equipo del evento táctico.", "`team.id`", "Int64."),
    fila("tactics_formation", "Int64", "Formación (por ejemplo 4231).", "`tactics.formation`", "Float por los vacíos -> Int64."),
    fila("jersey_number", "Int64", "Dorsal.", "`tactics.lineup[].jersey_number`", "explode de la lista JSON."),
    fila("player_id", "Int64", "Jugador.", "`tactics.lineup[].player.id`", "explode."),
    fila("player_name", "string", "Nombre del jugador.", "`tactics.lineup[].player.name`", "strip."),
    fila("position_id", "Int64", "Posición (1 a 25).", "`tactics.lineup[].position.id`", "Int64."),
    fila("position_name", "category", "Nombre de la posición.", "`tactics.lineup[].position.name`", "strip."),
]
notas["tactics_lineup"] = "Una fila por jugador en cada evento Starting XI / Tactical Shift."
tablas["defensive_responsibility"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("index", "Int64", "Índice del evento.", "`index`", "Llave junto con match_id."),
    fila("player_id", "Int64", "Jugador con responsabilidad defensiva.", "`defensive_responsibility.players[].player_id`", "explode de la lista JSON."),
    fila("probability", "float64", "Probabilidad de responsabilidad defensiva del jugador.", "`defensive_responsibility.players[].probability`", "Sin cambios."),
    fila("interception_like_probability", "float64", "Probabilidad de acción tipo intercepción.", "`defensive_responsibility.players[].interception_like_probability`", "Nulo legítimo; no imputar."),
    fila("pressure_like_probability", "float64", "Probabilidad de acción tipo presión.", "`defensive_responsibility.players[].pressure_like_probability`", "Nulo legítimo; no imputar."),
]
notas["defensive_responsibility"] = "Una fila por (evento, jugador). `probability_sum` y `categories` quedan en `eventos`."
tablas["shot_freeze_frame"] = [
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
]
notas["shot_freeze_frame"] = "Adición propuesta (no estaba en la lista de tareas): el plan 7.3.7 pide explotar `shot.freeze_frame`."
for t in ("related_events", "tactics_lineup", "defensive_responsibility", "shot_freeze_frame"):
    produce[t] = PAUX

tablas["frames_360"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("event_uuid", "string", "Evento al que pertenece el frame; se une con `eventos.id`.", "`event_uuid`", "strip. Llave junto con jugador_idx."),
    fila("jugador_idx", "Int64", "Orden del jugador dentro del freeze frame.", "posición en la lista `freeze_frame`", "explode con contador desde 0; el freeze frame no trae ids de jugador."),
    fila("teammate", "boolean", "El jugador visible es compañero de quien ejecuta el evento.", "`freeze_frame[].teammate`", "Sin cambios."),
    fila("actor", "boolean", "El jugador visible es quien ejecuta el evento.", "`freeze_frame[].actor`", "Sin cambios."),
    fila("keeper", "boolean", "El jugador visible es portero.", "`freeze_frame[].keeper`", "Sin cambios."),
    fila("x", "float64", "Coordenada x del jugador visible (yardas, perspectiva del equipo que ejecuta el evento).", "`freeze_frame[].location`", "Se separa [x, y]."),
    fila("y", "float64", "Coordenada y del jugador visible (yardas, perspectiva del equipo que ejecuta el evento).", "`freeze_frame[].location`", "Se separa [x, y]."),
    fila("es_equipo_analizado", "boolean", "El jugador visible pertenece al equipo analizado.", "`freeze_frame[].teammate`, `eventos.team_id`, `partidos.equipo_id`", "Si el equipo del evento es el analizado: teammate; si no: not teammate."),
]
notas["frames_360"] = "Una fila por jugador visible en cada frame. Solo incluye a quienes ve la cámara."
produce["frames_360"] = P02
tablas["frames_360_evento"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("event_uuid", "string", "Evento (unión con `eventos.id`). Llave junto con match_id.", "`event_uuid`", "strip."),
    fila("visible_area", "string", desc_corta("frames_360", "visible_area"), "`visible_area`", "Polígono [x1, y1, x2, y2, ...] guardado como texto JSON."),
    fila("visible_area_yd2", "float64", "Área del polígono visible en yardas cuadradas.", "`visible_area`", "Fórmula del polígono (shoelace) sobre los puntos."),
    fila("n_visibles_equipo", "Int64", "Jugadores visibles del equipo que ejecuta el evento.", "`visible_player_counts[].count`", "count del team_id igual al `eventos.team_id` del evento."),
    fila("n_visibles_rival", "Int64", "Jugadores visibles del equipo rival.", "`visible_player_counts[].count`", "count del team_id distinto al del evento."),
    fila("line_breaking_pass", "boolean", desc_corta("frames_360", "line_breaking_pass"), "`line_breaking_pass`", "Ausente = False."),
    fila("ball_receipt_in_space", "boolean", desc_corta("frames_360", "ball_receipt_in_space"), "`ball_receipt_in_space`", "Ausente = False."),
    fila("num_defenders_on_goal_side_of_actor", "float64", desc_corta("frames_360", "num_defenders_on_goal_side_of_actor"), "`num_defenders_on_goal_side_of_actor`", "Nulo legítimo; no imputar."),
    fila("distance_to_nearest_defender", "float64", desc_corta("frames_360", "distance_to_nearest_defender"), "`distance_to_nearest_defender`", "Nulo legítimo; filtrar por `n_visibles_rival` antes de usarlo."),
    fila("ball_receipt_exceeds_distance", "float64", desc_corta("frames_360", "ball_receipt_exceeds_distance"), "`ball_receipt_exceeds_distance`", "Nulo legítimo; no imputar."),
    fila("distances_from_edge_of_visible_area", "string", desc_corta("frames_360", "distances_from_edge_of_visible_area"), "`distances_from_edge_of_visible_area`", "Lista de {point_id, distance} guardada como texto JSON."),
]
notas["frames_360_evento"] = "Una fila por evento con frame (área visible y métricas 360 a nivel evento)."
produce["frames_360_evento"] = P02

t_p = leer_tabla("partidos")
DROP_P = {"attendance", "home_team.home_team_group", "away_team.away_team_group", "home_team.managers", "away_team.managers"}
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
DERIV_P = {
    "torneo": ("Torneo derivado de la fecha (por ejemplo 'Apertura 2023').", "Derivada de match_date: julio a diciembre = Apertura, enero a junio = Clausura."),
    "fase": ("regular o liguilla.", "regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso."),
    "es_play_in": ("El partido es de la ronda Play-In.", "competition_stage.id = 2."),
    "es_final": ("Uno de los dos partidos de la final del torneo.", "Dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos (calculado sobre toda la liga)."),
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
partidos = []
for c in t_p.column_names:
    if c in DROP_P:
        continue
    n = snake(c, colapsar=True)
    if c in INT_P:
        tipo = "Int64"
    elif c in BOOL_P:
        tipo = "boolean"
    elif c == "match_date":
        tipo = "datetime64[ns]"
    elif c in ("last_updated", "last_updated_360"):
        tipo = "datetime64[ns]"
    elif c in CAT_P:
        tipo = "category"
    else:
        tipo = "string"
    if c in DERIV_P:
        d, regla = DERIV_P[c]
        origen = "`partidos.parquet` (derivada)"
    else:
        d, regla, origen = desc_corta("matches", c), "Sin cambios.", f"`{c}`"
        if c == "match_date":
            regla = "Texto -> fecha."
        if c in ("last_updated", "last_updated_360"):
            regla = "Texto ISO -> fecha y hora."
    partidos.append(fila(n, tipo, d, origen, regla))
tablas["partidos"] = partidos
notas["partidos"] = ("D1: un partido por fila (91 filas). Se descartan attendance, home_team_group y away_team_group (0% de datos) "
                     "y las listas de managers (se resumen en entrenador_*).")
produce["partidos"] = P02

L = lambda col: desc_corta("lineups", col)
tablas["alineaciones"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("team_id", "Int64", "Equipo.", "`team_id`", "Llave junto con player_id."),
    fila("team_name", "string", L("team_name"), "`team_name`", "strip."),
    fila("player_id", "Int64", L("lineup[].player_id"), "`lineup[].player_id`", "explode de `lineup`."),
    fila("player_name", "string", L("lineup[].player_name"), "`lineup[].player_name`", "strip."),
    fila("player_nickname", "string", L("lineup[].player_nickname"), "`lineup[].player_nickname`", "strip; nulo en ~2% de los casos."),
    fila("birth_date", "datetime64[ns]", L("lineup[].birth_date"), "`lineup[].birth_date`", "Texto -> fecha."),
    fila("player_gender", "category", L("lineup[].player_gender"), "`lineup[].player_gender`", "Sin cambios."),
    fila("player_height", "float64", L("lineup[].player_height"), "`lineup[].player_height`", "Sin cambios (cm)."),
    fila("player_weight", "float64", L("lineup[].player_weight"), "`lineup[].player_weight`", "Sin cambios (kg)."),
    fila("jersey_number", "Int64", L("lineup[].jersey_number"), "`lineup[].jersey_number`", "Int64."),
    fila("country_id", "Int64", L("lineup[].country.id"), "`lineup[].country.id`", "Int64."),
    fila("country_name", "category", L("lineup[].country.name"), "`lineup[].country.name`", "strip."),
    fila("stats_goals", "Int64", L("lineup[].stats.goals"), "`lineup[].stats.goals`", "Vacío en ~24% de las filas; se recalcula desde eventos, no se usa como fuente."),
    fila("stats_assists", "Int64", L("lineup[].stats.assists"), "`lineup[].stats.assists`", "Ídem."),
    fila("stats_own_goals", "Int64", L("lineup[].stats.own_goals"), "`lineup[].stats.own_goals`", "Ídem."),
    fila("stats_penalties_scored", "Int64", L("lineup[].stats.penalties_scored"), "`lineup[].stats.penalties_scored`", "Ídem."),
    fila("stats_penalties_missed", "Int64", L("lineup[].stats.penalties_missed"), "`lineup[].stats.penalties_missed`", "Ídem."),
    fila("stats_penalties_saved", "Int64", L("lineup[].stats.penalties_saved"), "`lineup[].stats.penalties_saved`", "Ídem."),
    fila("skills_hops_rating", "float64", L("lineup[].skills.HOPS.rating"), "`lineup[].skills.HOPS.rating`", "Nulo legítimo (~10%); no imputar."),
    fila("skills_hops_raw_rating", "float64", L("lineup[].skills.HOPS.raw_rating"), "`lineup[].skills.HOPS.raw_rating`", "Nulo legítimo; no imputar."),
]
notas["alineaciones"] = "Una fila por (partido, equipo, jugador) de la cédula (titulares y banca)."
produce["alineaciones"] = P02
tablas["posiciones"] = [
    fila("match_id", "Int64", "Partido.", "match_id", "Llave."),
    fila("team_id", "Int64", "Equipo.", "`team_id`", "Llave."),
    fila("player_id", "Int64", "Jugador.", "`lineup[].player_id`", "Llave."),
    fila("posicion_idx", "Int64", "Orden del tramo del jugador en el partido.", "posición en `lineup[].positions`", "explode con contador desde 0."),
    fila("position_id", "Int64", L("lineup[].positions[].position_id"), "`lineup[].positions[].position_id`", "Int64."),
    fila("position", "category", L("lineup[].positions[].position"), "`lineup[].positions[].position`", "strip."),
    fila("from", "string", L("lineup[].positions[].from"), "`lineup[].positions[].from`", "Texto HH:MM:SS.mmm."),
    fila("to", "string", L("lineup[].positions[].to"), "`lineup[].positions[].to`", "Nulo en ~55%: probablemente siguió hasta el final; verificar antes de calcular minutos."),
    fila("from_period", "Int64", L("lineup[].positions[].from_period"), "`lineup[].positions[].from_period`", "Int64."),
    fila("to_period", "Int64", L("lineup[].positions[].to_period"), "`lineup[].positions[].to_period`", "Float con vacíos -> Int64."),
    fila("start_reason", "category", L("lineup[].positions[].start_reason"), "`lineup[].positions[].start_reason`", "strip."),
    fila("end_reason", "category", L("lineup[].positions[].end_reason"), "`lineup[].positions[].end_reason`", "strip; sirve para detectar rojas."),
    fila("counterpart_id", "Int64", L("lineup[].positions[].counterpart_id"), "`lineup[].positions[].counterpart_id`", "Float con vacíos -> Int64."),
    fila("counterpart_name", "string", L("lineup[].positions[].counterpart_name"), "`lineup[].positions[].counterpart_name`", "strip."),
]
notas["posiciones"] = "Una fila por tramo de posición de cada jugador (explode de `lineup[].positions`)."
produce["posiciones"] = P02


def tabla_stats(slug, parquet, extras=()):
    t = leer_tabla(parquet)
    cols = [c for c in t.column_names if c != "account_id"]
    docs_solo_s = [c["columna"] for c in next(e for e in dic["endpoints"] if e["slug"] == slug)["columnas"]
                   if c["estado_cruce"] == "no_devuelto_por_api" and c["columna"] not in cols]
    out = []
    for c in cols + docs_solo_s:
        extra = c in extras
        if c in extras:
            continue
        ta = tipo_pandas_arrow(t.schema.field(c).type) if c in cols else "float"
        regla = "Sin cambios."
        if c == "match_id" or c.endswith("_id"):
            tipo, regla = "Int64", "Int64."
        elif ta == "bool":
            tipo = "boolean"
        elif ta == "str":
            tipo, regla = "string", "strip."
        elif ta == "int":
            tipo = "Int64"
        else:
            tipo = "float64"
        if c in docs_solo_s:
            regla = "No devuelto por la API en estos partidos; se crea como nulo."
        if re.search(r"_ratio|possession|_pct", c) and tipo == "float64":
            regla += " Escala 0 a 1."
        out.append(fila(c, tipo, desc_corta(slug, c), f"`{c}`", regla))
    return out


tablas["team_match_stats"] = tabla_stats("team_match_stats", "team_match_stats")
notas["team_match_stats"] = "Una fila por (partido, equipo). Se descarta account_id."
produce["team_match_stats"] = P02
tablas["player_match_stats"] = tabla_stats("player_match_stats", "player_match_stats")
notas["player_match_stats"] = "Una fila por (partido, jugador). Se descarta account_id."
produce["player_match_stats"] = P02
liga = tabla_stats("team_match_stats", "team_match_stats_liga", extras={"torneo", "fase", "es_play_in", "es_final", "match_date", "match_week"})
liga += [
    fila("torneo", "category", "Torneo del partido (derivado de la fecha).", "`team_match_stats_liga.parquet`", "julio a diciembre = Apertura, enero a junio = Clausura."),
    fila("fase", "category", "regular o liguilla.", "`team_match_stats_liga.parquet`", "regular si competition_stage.id en {1, 42, 44}."),
    fila("es_play_in", "boolean", "El partido es de la ronda Play-In.", "`team_match_stats_liga.parquet`", "competition_stage.id = 2."),
    fila("es_final", "boolean", "Uno de los dos partidos de la final del torneo.", "`team_match_stats_liga.parquet`", "Calculado sobre toda la liga."),
    fila("match_date", "datetime64[ns]", "Fecha del partido.", "`team_match_stats_liga.parquet`", "Texto -> fecha."),
    fila("match_week", "Int64", "Jornada.", "`team_match_stats_liga.parquet`", "Int64."),
]
tablas["team_match_stats_liga"] = liga
notas["team_match_stats_liga"] = ("Línea base: una fila por (partido, equipo) de los 1,364 partidos de las 4 temporadas "
                                  "(available, Complete, Normal). Sirve para comparar al equipo contra la liga.")
produce["team_match_stats_liga"] = P02

ORDEN = ["partidos", "eventos", "frames_360", "frames_360_evento", "alineaciones", "posiciones",
         "team_match_stats", "player_match_stats", "team_match_stats_liga",
         "related_events", "tactics_lineup", "defensive_responsibility", "shot_freeze_frame"]
resumen = {t: len(tablas[t]) for t in ORDEN}

# colisiones de nombre dentro de una tabla
for t in ORDEN:
    nombres = [f["columna"] for f in tablas[t]]
    assert len(nombres) == len(set(nombres)), (t, [n for n in nombres if nombres.count(n) > 1])

viejo = {}
ruta_v0 = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if ruta_v0 and ruta_v0.exists():
    tabla_act = None
    for linea in ruta_v0.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## `(\w+)`", linea)
        if m:
            tabla_act = m.group(1)
        m = re.match(r"^\| `([^`]+)` \| ([^|]+) \|", linea)
        if m and tabla_act:
            viejo[(tabla_act, m.group(1))] = m.group(2).strip()
cambios_tipo, nuevas = [], {}
for t in ORDEN:
    for f in tablas[t]:
        k = (t, f["columna"])
        if viejo and k in viejo and viejo[k] != f["tipo"]:
            cambios_tipo.append((t, f["columna"], viejo[k], f["tipo"]))
        elif viejo and k not in viejo and any(v[0] == t for v in viejo):
            nuevas.setdefault(t, []).append(f["columna"])

DECISIONES = [
    ("Unidad de distancia", "Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m)", "RESUELTA (usuario)", "-"),
    ("Destino unificado `end_x`, `end_y`, `end_z`", "Un solo juego para pass, carry, shot y goalkeeper, interpretado con `type_name`", "RESUELTA (usuario)", "-"),
    ("360 en dos tablas", "`frames_360` (jugador visible) y `frames_360_evento` (área y conteos)", "RESUELTA (usuario)", "-"),
    ("Tabla extra `shot_freeze_frame`", "Se incluye; la produce `02_auxiliares.py`", "Lee", "sáb 17, 20:00"),
    ("Eventos administrativos", "Se conservan en `eventos` con `es_administrativo = True`", "Yordi", "sáb 17, 20:00"),
    ("`match_clock` y `minute_bin`", "No están en v0.1; solo `match_second`", "Lee", "sáb 17, 20:00"),
    ("`defensive_responsibility.categories`", "Texto JSON en `eventos`; no se explota", "Lee", "sáb 17, 20:00"),
    ("Tarjetas y formaciones de lineups", "Sin tabla en v0.1; propuesta `alineaciones_eventos` y `formaciones`", "Yordi y Lee", "sáb 17, 20:00"),
    ("`positions.to` nulo (~55%)", "Se conserva el nulo hasta verificar si significa 'siguió hasta el final'", "Yordi", "sáb 17, 20:00"),
    ("Columnas que no aparecen siempre", "Banderas ausentes se crean con False; stats ausentes, nulas", "Yordi", "sáb 17, 20:00"),
    ("Banderas con nulo legítimo", "Solo `is_transition` e `is_controlled_possession`; el resto False. Validar `out` y `off_camera`", "Lee", "sáb 17, 20:00"),
    ("`category` o `string` en nombres", "`*_name` es category, salvo nombres de personas (string)", "Yordi", "sáb 17, 20:00"),
    ("Penales (periodo 5)", "Se conservan con `period = 5`; las métricas de juego abierto los excluyen", "Lee", "sáb 17, 20:00"),
    ("Eventos sin ubicación (~1%)", "`x` e `y` nulos; se excluyen de los mapas, sin imputar", "Pablo", "sáb 17, 20:00"),
    ("Perspectiva en `frames_360`", "Solo `es_equipo_analizado`; `x` e `y` quedan en la perspectiva del equipo del evento (sin `x_eq`/`y_eq`)", "Pablo", "sáb 17, 20:00"),
    ("Dónde viven los parquet limpios", "`data/interim/` (limpias) y `data/processed/` (agregadas del lunes)", "Yordi", "sáb 17, 20:00"),
]

CAMBIOS = [
    "`fase` pasa de `regular`/`final` a `regular`/`liguilla`; nueva columna `es_play_in` (stage id 2).",
    "`partidos` agrega `entrenador_id`, `equipo_id`, `entrenador_rival_id` y `rival_coentrenador`; se quita la decisión abierta sobre ellos.",
    "Los tipos y los % de nulos se recalcularon con los parquet completos (91 partidos, 317,849 eventos) en lugar de la muestra de 3 a 5 partidos.",
    f"`eventos` tiene 180 columnas de origen con los 91 partidos (170 en la muestra de 5). De las {len(docs_solo)} banderas documentadas que no salieron en la muestra, {len(docs_solo) - len(faltan_en_91)} sí aparecen con los datos completos y {len(faltan_en_91)} siguen sin aparecer (se crean con False).",
    "Las 6 columnas de `team_match_stats` que la API no devolvía en la muestra (tiros libres directos) sí aparecen con los datos completos.",
    "Nueva tabla `team_match_stats_liga` (línea base de la liga).",
    "Perspectiva del equipo analizado: `es_equipo_analizado`, `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq` en `eventos`; `es_equipo_analizado` en `frames_360`.",
    "`match_second` aclara que no es único entre periodos; se ordena por (`period`, `match_second`).",
    "Columna 'produce' en el resumen: `02_limpieza.py` (Yordi) y `02_auxiliares.py` (Lee).",
    "Las decisiones abiertas pasan a tabla con default, responsable y fecha límite; 3 quedan resueltas.",
    "Se corrigen descripciones cortadas y vacías.",
]

md = []
md.append(f"# Contrato de datos {VERSION}\n")
md.append(f"Estado: {VERSION}, {FECHA}. Dueño: Yordi. Es el contrato para que Lee (métricas) y Pablo (gráficas) programen contra los nombres y tipos de las tablas limpias que produce `scripts/02_limpieza.py`. Los tipos y % de nulos salen de los parquet completos de los 91 partidos de Jardine. La versión ejecutable está en `docs/contrato_datos.csv` y `scripts/contrato.py`.\n")
md.append("Este archivo se genera con `python scripts/gen_contrato.py`; no se edita a mano.\n")
md.append("Fuentes: `data/diccionario.json`, `data/raw/parquet/*.parquet` (salida de `scripts/01_descarga.py`) y `Plan_de_trabajo_Kpumas.md` secciones 7.1 a 7.3.\n")
md.append("## Convenciones\n")
for t in [
    "Nombres en snake_case con `_` en lugar de `.` (`pass.length` -> `pass_length`, `shot.statsbomb_xg` -> `shot_statsbomb_xg`). La columna **origen** conserva la ruta con punto del diccionario para trazabilidad.",
    "En `partidos` se quita el prefijo repetido (`home_team.home_team_id` -> `home_team_id`); `50_50.*` pasa a `fifty_fifty_*` (un nombre no puede empezar con dígito).",
    "Tipos pandas: `Int64` (entero con nulos), `float64`, `boolean` (con nulos), `string`, `category`, `datetime64[ns]`. Ningún id queda como float.",
    "Llaves: eventos (`match_id`, `index`); frames_360 (`match_id`, `event_uuid`, `jugador_idx`); frames_360_evento (`match_id`, `event_uuid`); partidos `match_id`. `id` y `event_uuid` son UUID de texto y solo sirven como llave.",
    "Unidad: yardas, cancha 120 x 80, ataque hacia x = 120. Las coordenadas vienen en la perspectiva del equipo que ejecuta el evento (también en 360).",
    "**Perspectiva del equipo analizado.** `x`, `y`, `end_x`, `end_y` están en la perspectiva de `team_id` (el equipo del evento). Para comparar al equipo analizado contra sus rivales en una misma cancha, usar `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq`: igual que `x`/`y` si `es_equipo_analizado`; `120 - x` y `80 - y` si el evento es del rival.",
    "**Orden.** `match_second` no es único entre periodos; ordenar siempre por (`match_id`, `index`) o por (`period`, `match_second`).",
    "Nulo legítimo no se imputa; las banderas que solo aparecen si son verdaderas se rellenan con False (plan 7.3).",
    "`fase` vale `regular` (competition_stage.id en {1, 42, 44}) o `liguilla`; `es_play_in` marca el stage id 2 y `es_final` los dos partidos de la final.",
    "Los parquet limpios se guardan en `data/interim/` con el nombre de la tabla (`data/interim/eventos.parquet`); la muestra de un partido en `data/interim/muestra/`.",
    "Las columnas que no aparecen en algún partido se crean igual (False o nulo) para que el esquema no cambie entre corridas.",
]:
    md.append(f"- {t}")
md.append("")
md.append("## Resumen de tablas\n")
md.append("| tabla | columnas | produce | grano |")
md.append("|---|---|---|---|")
for t in ORDEN:
    md.append(f"| `{t}` | {resumen[t]} | {produce[t]} | {notas[t]} |")
md.append("")
for t in ORDEN:
    md.append(f"## `{t}` ({resumen[t]} columnas)\n")
    md.append(notas[t] + "\n")
    md.append("| columna | tipo | descripción | origen | regla de limpieza |")
    md.append("|---|---|---|---|---|")
    for f in tablas[t]:
        md.append(f"| `{f['columna']}` | {f['tipo']} | {f['descripcion']} | {f['origen']} | {f['regla']} |")
    md.append("")
md.append("## Decisiones abiertas\n")
md.append("| # | decisión | default vigente | quién decide | fecha límite |")
md.append("|---|---|---|---|---|")
for i, (d, dflt, quien, lim) in enumerate(DECISIONES, start=1):
    resuelta = quien.startswith("RESUELTA")
    md.append(f"| {i} | {d} | {dflt} | {quien} | {lim if not resuelta else 'resuelta'} |")
md.append("")
md.append("## Cambios\n")
md.append(f"### {VERSION} ({FECHA}), cambios desde v0\n")
for c in CAMBIOS:
    md.append(f"- {c}")
if cambios_tipo:
    md.append("")
    md.append("Tipos que cambiaron al recalcular con los datos completos:\n")
    md.append("| tabla | columna | v0 | v0.1 |")
    md.append("|---|---|---|---|")
    for t, c, a, b in cambios_tipo:
        md.append(f"| `{t}` | `{c}` | {a} | {b} |")
if nuevas:
    md.append("")
    md.append("Columnas nuevas respecto a v0 (por tabla):\n")
    for t, cs in nuevas.items():
        md.append(f"- `{t}` ({len(cs)}): " + ", ".join(f"`{c}`" for c in cs))
md.append("")
md.append("### v0 (2026-10-17)\n")
md.append("- Primera versión, calculada con la muestra de 3 a 5 partidos.")
md.append("")
(ROOT / "docs" / "contrato_datos.md").write_text("\n".join(md), encoding="utf-8")

filas_csv = []
for t in ORDEN:
    for f in tablas[t]:
        filas_csv.append({"tabla": t, "columna": f["columna"], "tipo": f["tipo"],
                          "origen": f["origen"].replace("`", ""), "regla": f["regla"].replace("`", "")})
pd.DataFrame(filas_csv).to_csv(ROOT / "docs" / "contrato_datos.csv", index=False, encoding="utf-8")
print(json.dumps(resumen))
print("cambios de tipo:", len(cambios_tipo))
for c in cambios_tipo:
    print("  ", c)
print("nuevas:", {k: len(v) for k, v in nuevas.items()})
