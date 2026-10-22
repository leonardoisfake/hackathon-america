"""Todas las gráficas del América en un solo script.

Uso:
    python graficas_america.py                          # genera todas
    python graficas_america.py radar_posiciones tiros_ataque     # solo las que nombres

Gráficas disponibles (nombre -> archivo que guarda en graficas/<torneo>/):
    actividad_defensiva    1_actividad_defensiva.png
    flujo_pases            2_flujo_pases.png
    mapa_calor_defensivo   3_mapa_calor_defensivo.png
    tiros_ataque           3_tiros_ataque.png
    tiros_defensa          4_tiros_defensa.png
    red_pases              5_red_pases.png
    corners                1_corners_mapa_calor.png
    balon_parado           2_balon_parado_a_favor.png, 3_balon_parado_en_contra.png
    saques_banda           4_saques_banda_a_favor.png, 5_saques_banda_en_contra.png
    mapa_calor_jugadores   mapa_calor_jugadores_<torneo>.png
    radar_posiciones       radar_posiciones_<torneo>.png

Archivos de entrada (junto al script, en la carpeta actual, o en data/interim y data/processed):
    eventos_parquet            obligatorio
    balon_parado_tiros.parquet solo para balon_parado y saques_banda
    player_match_stats.parquet solo para mapa_calor_jugadores y radar_posiciones
    posiciones.parquet         solo para radar_posiciones
Si falta un archivo opcional, esa gráfica se omite y las demás se generan igual.
"""
import sys
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from mplsoccer import Pitch, Radar, VerticalPitch
from scipy.ndimage import gaussian_filter

AQUI = Path(__file__).resolve().parent
EQUIPO_ID = 1229
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = Path(r"C:\Users\pablo\modelo_ame_final\graficas")

BUSCAR_EVENTOS = ["eventos_parquet", "eventos.parquet"]
BUSCAR_TIROS = ["balon_parado_tiros.parquet", "balon_parado_tiros"]
BUSCAR_STATS = ["player_match_stats.parquet", "player_match_stats"]
BUSCAR_POSICIONES = ["posiciones.parquet", "posiciones"]
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "processed", AQUI / "data" / "raw" / "parquet"]

COLUMNAS_EVENTOS = ["match_id", "id", "index", "torneo", "period", "possession", "type_name", "team_name", "player_id",
                    "player_name", "es_equipo_analizado", "x", "y", "x_eq", "y_eq", "end_x", "end_y", "duel_type_name",
                    "pass_type_name", "pass_technique_name", "pass_outcome_name", "pass_completed",
                    "pass_recipient_name", "shot_outcome_name",
                    "shot_statsbomb_xg"]
COLUMNAS_TIROS = ["match_id", "index", "lado", "origen", "set_piece_type", "es_fk_directo", "x", "y", "xg", "gol"]
MINUTOS = "player_match_minutes"


class FaltaDato(Exception):
    pass


def buscar(nombres, descripcion):
    for carpeta in CARPETAS:
        for nombre in nombres:
            ruta = carpeta / nombre
            if ruta.is_file():
                return ruta
    raise FaltaDato(f"No encuentro {descripcion}. Busqué {nombres} en: {[str(c) for c in CARPETAS]}")


def leer(ruta, columnas, descripcion):
    faltan = [c for c in columnas if c not in pq.read_schema(ruta).names]
    if faltan:
        raise FaltaDato(f"A {ruta.name} le faltan columnas: {faltan}. Revisa que sea {descripcion}.")
    return pd.read_parquet(ruta, columns=columnas)


def corto_nombre(n):
    p = str(n).split()
    return p[0] if len(p) == 1 else f"{p[0]} {p[-1]}"


def guardar(fig, torneo, nombre, dpi=150, **kw):
    carpeta = CARPETA_SALIDA / torneo
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_png = carpeta / nombre
    fig.savefig(ruta_png, dpi=dpi, bbox_inches="tight", **kw)
    plt.close(fig)
    print("Guardado:", ruta_png)


def torneos_en(serie):
    presentes = set(serie)
    for t in set(TORNEOS) - presentes:
        print(f"Aviso: no hay datos del torneo '{t}'.")
    lista = [t for t in TORNEOS if t in presentes]
    if not lista:
        raise FaltaDato(f"Ningún torneo coincide. Torneos en los datos: {sorted(presentes)}")
    return lista


# ----------------------------------------------------------------------------- carga común
try:
    ruta_ev = buscar(BUSCAR_EVENTOS, "los eventos")
    eventos = leer(ruta_ev, COLUMNAS_EVENTOS, "la tabla limpia 'eventos', no el parquet crudo")
except FaltaDato as e:
    sys.exit(str(e))
eventos["match_id"] = eventos["match_id"].astype("int64")
eventos["index"] = eventos["index"].astype("int64")
eventos["torneo"] = eventos["torneo"].astype(str)
eventos["es_equipo_analizado"] = eventos["es_equipo_analizado"].fillna(False).astype(bool)
equipo = eventos.loc[eventos["es_equipo_analizado"], "team_name"].iloc[0]
try:
    torneos = torneos_en(eventos["torneo"])
except FaltaDato as e:
    sys.exit(str(e))
por_torneo = {t: eventos[eventos["torneo"] == t] for t in torneos}
mapa_torneo = eventos[["match_id", "torneo"]].drop_duplicates("match_id")
partidos_torneo = eventos.groupby("torneo")["match_id"].nunique()


def cargar_stats(columnas):
    ruta = buscar(BUSCAR_STATS, "player_match_stats")
    cols = ["match_id", "team_id", "player_id", "player_name", MINUTOS] + list(columnas)
    stats = leer(ruta, cols, "player_match_stats")
    stats = stats[stats["team_id"].astype("Int64") == EQUIPO_ID].copy()
    if stats.empty:
        raise FaltaDato(f"No hay filas del equipo {EQUIPO_ID} en {ruta.name}.")
    stats["player_id"] = stats["player_id"].astype("int64")
    stats["match_id"] = stats["match_id"].astype("int64")
    stats["player_name"] = stats["player_name"].astype(str)
    for c in [MINUTOS] + list(columnas):
        stats[c] = pd.to_numeric(stats[c], errors="coerce").astype(float)
    return stats.merge(mapa_torneo, on="match_id", how="inner")


# ----------------------------------------------------------------------------- 1. actividad defensiva vs rival
def actividad_defensiva():
    tipos = ["Pressure", "Foul Committed", "Interception", "Block"]
    colores = ["#171832", "#323A60", "#45537F", "#7183A3", "#B5C6D5", "#D3DEE4", "#DEDFE0",
               "#F2BAAD", "#F7A18E", "#F17B67", "#E84335", "#E11F19", "#B40B0E"]
    cmap = LinearSegmentedColormap.from_list("statsbomb", colores)
    pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color="black")

    estadisticas = {}
    for t, d in por_torneo.items():
        defensivas = d[(d["period"] < 5) & (
            d["type_name"].isin(tipos)
            | ((d["type_name"] == "Duel") & (d["duel_type_name"] == "Tackle"))
            | ((d["type_name"] == "Pass") & (d["pass_type_name"] == "Interception"))
        )].dropna(subset=["x", "y"])
        propias = defensivas[defensivas["es_equipo_analizado"]]
        rival = defensivas[~defensivas["es_equipo_analizado"]]
        s = pitch.bin_statistic(propias.x, propias.y, statistic="count", bins=(6, 5))
        s_rival = pitch.bin_statistic(rival.x, rival.y, statistic="count", bins=(6, 5))
        s["statistic"] = s["statistic"] / s["statistic"].sum() * 100 - s_rival["statistic"] / s_rival["statistic"].sum() * 100
        estadisticas[t] = s
    # Misma escala de color en los 4 torneos para que se puedan comparar entre sí
    limite = max(np.abs(s["statistic"]).max() for s in estadisticas.values())

    for t in torneos:
        fig, ax = plt.subplots(figsize=(11, 8))
        fig.suptitle(f"¿Dónde defiende {equipo} frente a su rival?", fontsize=20, fontweight="bold")
        pitch.draw(ax=ax)
        hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=cmap, vmin=-limite, vmax=limite, zorder=1)
        pitch.label_heatmap(estadisticas[t], ax=ax, str_format="{:+.1f}", fontsize=13, fontweight="bold", ha="center",
                            va="center", zorder=3, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
        ax.set_title(f"{t}  ({por_torneo[t]['match_id'].nunique()} partidos)", fontsize=15, fontweight="bold")
        cbar = fig.colorbar(hm, ax=ax, shrink=0.7, pad=0.02)
        cbar.set_ticks([-limite, 0, limite])
        cbar.set_ticklabels(["menos que\nel rival", "igual", "más que\nel rival"], fontsize=11)
        fig.text(0.5, 0.02, f"Puntos porcentuales: % de las acciones defensivas de {equipo} en cada zona menos el % del rival.\n"
                 f"{equipo} ataca de izquierda a derecha (su portería es la de la izquierda).", ha="center", fontsize=11)
        guardar(fig, t, "1_actividad_defensiva.png")


# ----------------------------------------------------------------------------- 2. flujo de pases
def flujo_pases():
    pitch = Pitch(pitch_type="statsbomb", pitch_color="#101010", line_color="#8a97a3", line_zorder=3)
    cmap_flujo = LinearSegmentedColormap.from_list("flujo", ["#101010", "#1f3b63", "#2f6f9f", "#4fa3c7"])
    for t in torneos:
        d = por_torneo[t]
        pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"] & d["pass_outcome_name"].isna()]
        pases = pases.dropna(subset=["x", "y", "end_x", "end_y"])

        fig, ax = plt.subplots(figsize=(12, 8.5))
        fig.set_facecolor("#101010")
        fig.suptitle(f"Hacia dónde circula el balón - {equipo}", fontsize=20, fontweight="bold", color="white")
        pitch.draw(ax=ax)
        stat = pitch.bin_statistic(pases.x, pases.y, statistic="count", bins=(8, 6), normalize=True)
        pitch.heatmap(stat, ax=ax, cmap=cmap_flujo, zorder=1)
        pitch.flow(pases.x, pases.y, pases.end_x, pases.end_y, bins=(8, 6), arrow_type="same", arrow_length=8,
                   color="#f4f1de", ax=ax, zorder=4, width=1.4, headwidth=4, headlength=4)
        ax.set_title(f"{t}  ({d['match_id'].nunique()} partidos, {len(pases)} pases completados)", color="white",
                     fontsize=14, pad=8)
        ax.annotate("", xy=(0.62, -0.03), xytext=(0.38, -0.03), xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color="#8a97a3", lw=1.5))
        fig.text(0.5, 0.01, "Cada flecha es la dirección promedio de los pases completados que salen de esa zona;\n"
                 "el azul más claro marca las zonas desde donde salen más pases. Ataque de izquierda a derecha.",
                 ha="center", color="#c8d0d8", fontsize=11)
        guardar(fig, t, "2_flujo_pases.png", facecolor=fig.get_facecolor())


# ----------------------------------------------------------------------------- 3. mapa de calor defensivo
def mapa_calor_defensivo():
    acciones = ["Ball Recovery", "Duel", "Interception", "Clearance", "Block"]
    colores = ["#ffffff", "#fde0c5", "#facba6", "#f59e72", "#f17b50", "#e8553a", "#c8302a", "#8f1d21"]
    cmap = LinearSegmentedColormap.from_list("defensivo", colores)
    pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color="#222222")

    estadisticas, totales = {}, {}
    for t, d in por_torneo.items():
        acc = d[d["type_name"].isin(acciones) & d["es_equipo_analizado"] & (d["period"] < 5)].dropna(subset=["x", "y"])
        estadisticas[t] = pitch.bin_statistic(acc.x, acc.y, statistic="count", bins=(6, 5), normalize=True)
        totales[t] = len(acc)
    vmax = max(s["statistic"].max() for s in estadisticas.values())

    for t in torneos:
        fig, ax = plt.subplots(figsize=(11, 8))
        fig.suptitle(f"Acciones defensivas de {equipo}", fontsize=20, fontweight="bold")
        pitch.draw(ax=ax)
        hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=cmap, vmin=0, vmax=vmax, zorder=1, edgecolors="white")
        pitch.label_heatmap(estadisticas[t], ax=ax, str_format="{:.0%}", fontsize=13, fontweight="bold", ha="center",
                            va="center", zorder=3, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
        ax.set_title(f"{t}  ({por_torneo[t]['match_id'].nunique()} partidos), {totales[t]} acciones", fontsize=15,
                     fontweight="bold")
        cbar = fig.colorbar(hm, ax=ax, shrink=0.7, pad=0.02)
        cbar.set_ticks([0, vmax])
        cbar.set_ticklabels(["menos", "más"], fontsize=12)
        fig.text(0.5, 0.02, "Porcentaje de las acciones defensivas del torneo en cada zona (Ball Recovery, Duel, Interception, Clearance, Block).\n"
                 f"{equipo} ataca de izquierda a derecha (su portería es la de la izquierda).", ha="center", fontsize=11)
        guardar(fig, t, "3_mapa_calor_defensivo.png")


# ----------------------------------------------------------------------------- 3 y 4. tiros a favor / en contra
def mapa_tiros(nombre, etiqueta, propios):
    pitch_t = VerticalPitch(pitch_type="statsbomb", goal_type="box", half=True)
    leyenda = [Line2D([], [], marker="o", ls="", ms=12, mfc="white", mec="black", label="Tiros"),
               Line2D([], [], marker="o", ls="", ms=12, mfc="blue", mec="black", label="Goles")]
    for t in torneos:
        d = por_torneo[t]
        tiros = d[(d["type_name"] == "Shot") & (d["es_equipo_analizado"] == propios) & (d["period"] < 5)].dropna(subset=["x", "y"])
        goles = tiros[tiros["shot_outcome_name"] == "Goal"]
        no_goles = tiros[tiros["shot_outcome_name"] != "Goal"]

        fig, ax = plt.subplots(figsize=(9, 8))
        fig.suptitle(f"{etiqueta} {equipo}", fontsize=20, fontweight="bold")
        pitch_t.draw(ax=ax)
        pitch_t.scatter(no_goles.x, no_goles.y, ax=ax, s=no_goles.shot_statsbomb_xg.fillna(0) * 1000 + 25,
                        alpha=.6, ec="black", color="white", zorder=1)
        pitch_t.scatter(goles.x, goles.y, ax=ax, s=goles.shot_statsbomb_xg.fillna(0) * 1000 + 25,
                        alpha=.9, ec="black", color="blue", zorder=2)
        ax.set_title(f"{t}  ({d['match_id'].nunique()} partidos)", fontsize=15, fontweight="bold")
        ax.text(0.97, 0.03, f"{len(tiros)} tiros\n{len(goles)} goles\n{tiros.shot_statsbomb_xg.sum():.1f} xG",
                transform=ax.transAxes, va="bottom", ha="right", fontsize=13, fontweight="bold",
                bbox=dict(fc="white", ec="black", alpha=.85))
        fig.legend(handles=leyenda, loc="lower center", ncol=2, fontsize=13, shadow=True, edgecolor="black")
        guardar(fig, t, nombre)


def tiros_ataque():
    mapa_tiros("3_tiros_ataque.png", "Ataque", True)


def tiros_defensa():
    mapa_tiros("4_tiros_defensa.png", "Defensa", False)


# ----------------------------------------------------------------------------- 5. red de pases
def red_pases(min_pases_jugador=100, min_pases_enlace=15):
    pitch_r = Pitch(pitch_type="statsbomb", line_color="#555")
    for t in torneos:
        d = por_torneo[t]
        pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"]]
        completados = pases[(pases["pass_completed"].fillna(False).astype(bool)) & pases["pass_recipient_name"].notna()]

        posiciones = completados.groupby("player_name").agg(x=("x_eq", "mean"), y=("y_eq", "mean"), count=("x_eq", "count"))
        posiciones = posiciones[posiciones["count"] >= min_pases_jugador]

        enlaces = (completados.groupby(["player_name", "pass_recipient_name"]).id.count().reset_index()
                   .rename(columns={"player_name": "pasador", "pass_recipient_name": "receptor", "id": "pass_count"}))
        enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="pasador", right_index=True)
        enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="receptor", right_index=True, suffixes=["", "_end"])
        enlaces = enlaces[enlaces["pass_count"] >= min_pases_enlace]

        fig, ax = plt.subplots(figsize=(12, 8.5))
        fig.suptitle(f"Red de pases de {equipo}", fontsize=20, fontweight="bold")
        pitch_r.draw(ax=ax)
        pitch_r.lines(enlaces.x, enlaces.y, enlaces.x_end, enlaces.y_end,
                      lw=enlaces.pass_count / enlaces.pass_count.max() * 7, color="#1f4e9c", alpha=.5, ax=ax, zorder=1)
        pitch_r.scatter(posiciones.x, posiciones.y, s=posiciones["count"] / posiciones["count"].max() * 900 + 60,
                        color="#57920f", edgecolors="black", ax=ax, zorder=2)
        for jugador, r in posiciones.iterrows():
            pitch_r.annotate(jugador.split()[0], xy=(r.x, r.y), ax=ax, ha="center", va="center", fontsize=9, zorder=3)
        ax.set_title(f"{t}  ({d['match_id'].nunique()} partidos)", fontsize=15, fontweight="bold")
        fig.text(0.5, 0.02, f"Posición promedio del torneo. Jugadores con al menos {min_pases_jugador} pases completados y "
                 f"conexiones de al menos {min_pases_enlace} pases.", ha="center", fontsize=11)
        guardar(fig, t, "5_red_pases.png")


# ----------------------------------------------------------------------------- córners (mapa de calor)
def corners():
    lados = ["Izquierda", "Derecha"]
    paleta = ["white", "#9a9a9a", "#8f8f8f", "#858585", "#7a7a7a", "#707070", "#666666", "#5c5c5c", "#525252", "#484848",
              "#3f3f3f", "#9a1120", "#a2111f", "#aa111e", "#b2111d", "#ba111c", "#c2111b", "#ca111a", "#d11119", "#d91018", "#e21017"]
    cmap = LinearSegmentedColormap.from_list("statsbomb", paleta)
    contorno = [pe.Stroke(linewidth=1.5, foreground="white"), pe.Normal()]

    cs = eventos[(eventos["type_name"] == "Pass") & (eventos["pass_type_name"] == "Corner") & eventos["es_equipo_analizado"]]
    cs = cs.dropna(subset=["x", "y", "end_x", "end_y"]).copy()
    cs["lado"] = np.where(cs["y"] < 40, "Izquierda", "Derecha")
    cs["corto"] = np.where(cs["lado"] == "Izquierda", cs["end_y"] <= 18, cs["end_y"] >= 62)
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, line_color="black", pad_bottom=-5)

    for t in torneos:
        fig, axs = plt.subplots(1, 2, figsize=(15, 6.5))
        fig.suptitle(f"Hacia dónde cobra los córners - {equipo}\n{t} ({partidos_torneo[t]} partidos)", fontsize=18,
                     fontweight="bold")
        fig.subplots_adjust(top=0.80, wspace=0.25)
        for ax, lado in zip(axs, lados):
            todos = cs[(cs["torneo"] == t) & (cs["lado"] == lado)]
            data = todos[~todos["corto"]]
            pitch.draw(ax=ax)
            ax.set_ylim(72, 122)
            cabecera = f"Córners {lado.lower()}"
            if data.empty:
                ax.set_title(f"{cabecera}: sin datos", fontsize=13)
                continue
            stat = pitch.bin_statistic(data["end_x"], data["end_y"], statistic="count", bins=(15, 11), normalize=True)
            pitch.heatmap(stat, edgecolors="white", cmap=cmap, ax=ax, alpha=0.75, zorder=3)
            pitch.label_heatmap(stat, color="black", fontsize=11, fontweight="bold", ax=ax, ha="center", va="center",
                                str_format="{:.0%}", path_effects=contorno, exclude_zeros=True)
            pitch.scatter(data["end_x"], data["end_y"], ax=ax, color="grey", s=10)
            outs = (data["pass_technique_name"] == "Outswinging").mean() * 100
            ins = (data["pass_technique_name"] == "Inswinging").mean() * 100
            cobradores = todos.groupby("player_name").size().sort_values(ascending=False) / len(todos) * 100
            texto = " | ".join(f"{corto_nombre(n)} ({p:.0f}%)" for n, p in cobradores.head(2).items())
            ax.set_title(f"{cabecera}\nAl área: {len(data)} de {len(todos)} | Cobran: {texto}\n"
                         f"Outswinging: {outs:.0f}% | Inswinging: {ins:.0f}%", fontsize=12)
        guardar(fig, t, "1_corners_mapa_calor.png", dpi=130)


# ----------------------------------------------------------------------------- balón parado y saques de banda
TIPOS_PARADO = [("Corner", "Corner", "Córner"), ("Free Kick", "Free Kick", "Tiro libre")]
TIPO_SAQUE = ("Throw In", "Throw-in", "Saque de banda")
COLOR_FLECHA = "#3a5a8c"
COLOR_FALLIDO = "#9aa0a6"
COLOR_TIRO = "#f2a900"
COLOR_GOL = "#d62728"
_cache = {}


def tiros_con_origen():
    # Cada tiro de balón parado con el punto de donde salió el balón parado (córner, tiro libre o saque de banda)
    if "datos" in _cache:
        return _cache["datos"]
    tipos = TIPOS_PARADO + [TIPO_SAQUE]
    tiros = leer(buscar(BUSCAR_TIROS, "la tabla de tiros de balón parado"), COLUMNAS_TIROS, "la tabla de tiros de balón parado")
    tiros["match_id"] = tiros["match_id"].astype("int64")
    tiros["index"] = tiros["index"].astype("int64")
    tiros["gol"] = tiros["gol"].fillna(False).astype(bool)
    tiros["es_fk_directo"] = tiros["es_fk_directo"].fillna(False).astype(bool)
    tiros["set_piece_type"] = tiros["set_piece_type"].astype(str)
    tiros = tiros[(tiros["origen"] == "balon_parado") & tiros["set_piece_type"].isin([t[0] for t in tipos])].copy()
    tiros = tiros.dropna(subset=["x", "y"])

    datos = tiros.merge(eventos[["match_id", "index", "torneo", "possession", "team_name"]], on=["match_id", "index"], how="left")
    sin_evento = datos["torneo"].isna().sum()
    if sin_evento:
        print(f"Aviso: {sin_evento} tiros no se encontraron en los eventos y se omiten.")
        datos = datos.dropna(subset=["torneo"])

    # Origen: el último pase de balón parado del mismo tipo, en la misma posesión, antes del tiro
    datos["pase_tipo"] = datos["set_piece_type"].map({t[0]: t[1] for t in tipos})
    origenes = eventos[eventos["pass_type_name"].isin([t[1] for t in tipos])][
        ["match_id", "index", "possession", "team_name", "pass_type_name", "x", "y"]].rename(
        columns={"index": "idx_origen", "x": "x0", "y": "y0"})
    datos = datos.merge(origenes, left_on=["match_id", "possession", "team_name", "pase_tipo"],
                        right_on=["match_id", "possession", "team_name", "pass_type_name"], how="left")
    datos = datos[datos["idx_origen"].isna() | (datos["idx_origen"] < datos["index"])]
    datos = datos.sort_values("idx_origen").drop_duplicates(["match_id", "index"], keep="last")
    # Tiro libre directo: el origen es el propio punto del tiro
    directo = datos["es_fk_directo"] & datos["x0"].isna()
    datos.loc[directo, ["x0", "y0"]] = datos.loc[directo, ["x", "y"]].to_numpy()
    datos["sin_origen"] = datos["x0"].isna()
    datos["directo"] = directo
    _cache["datos"] = datos
    return datos


def balon_parado():
    datos = tiros_con_origen()
    datos = datos[datos["set_piece_type"].isin([t[0] for t in TIPOS_PARADO])]
    torneos_bp = torneos_en(datos["torneo"])
    pitch = VerticalPitch(pitch_type="statsbomb", line_color="#555555", line_zorder=1)

    def figura(torneo, lado, titulo, nombre):
        d_t = datos[(datos["torneo"] == torneo) & (datos["lado"] == lado)]
        partidos = partidos_torneo[torneo]
        fig, axs = plt.subplots(1, len(TIPOS_PARADO), figsize=(13, 7.6))
        fig.suptitle(f"{titulo}", fontsize=22, fontweight="bold", y=1.0)
        fig.subplots_adjust(top=0.84, bottom=0.12, wspace=0.08)
        fig.text(0.5, 0.915, f"{torneo} ({partidos} partidos) - origen del balón parado y lugar del tiro", ha="center", fontsize=14)
        for ax, (clave, _, etiqueta) in zip(axs, TIPOS_PARADO):
            d = d_t[d_t["set_piece_type"] == clave]
            pitch.draw(ax=ax)
            ax.set_ylim(45, 122)
            con = d[~d["sin_origen"] & ~d["directo"]]
            pitch.arrows(con.x0, con.y0, con.x, con.y, ax=ax, color=COLOR_FLECHA, alpha=0.35, width=1.2,
                         headwidth=4, headlength=4, zorder=2)
            pitch.arrows(con[con["gol"]].x0, con[con["gol"]].y0, con[con["gol"]].x, con[con["gol"]].y, ax=ax,
                         color=COLOR_GOL, alpha=0.9, width=1.8, headwidth=4, headlength=4, zorder=3)
            pitch.scatter(con.x0, con.y0, ax=ax, s=18, color=COLOR_FLECHA, alpha=0.6, zorder=2)
            no_gol = d[~d["gol"]]
            gol = d[d["gol"]]
            pitch.scatter(no_gol.x, no_gol.y, ax=ax, s=no_gol.xg.fillna(0) * 900 + 25, color="white", edgecolors="black",
                          alpha=0.85, zorder=4)
            pitch.scatter(gol.x, gol.y, ax=ax, s=gol.xg.fillna(0) * 900 + 40, color=COLOR_GOL, edgecolors="black",
                          alpha=0.95, zorder=5)
            dire = d[d["directo"]]
            if len(dire):
                pitch.scatter(dire.x0, dire.y0, ax=ax, s=70, marker="D", color="#f2c14e", edgecolors="black", zorder=3)
            ax.set_title(f"{etiqueta}: {len(d)} tiros, {int(d['gol'].sum())} {'gol' if int(d['gol'].sum()) == 1 else 'goles'}, {d['xg'].sum():.1f} xG",
                         fontsize=13, fontweight="bold")
        leyenda = [Line2D([], [], color=COLOR_FLECHA, lw=2, label="Origen → tiro"),
                   Line2D([], [], marker="o", ls="", ms=10, mfc="white", mec="black", label="Tiro (tamaño = xG)"),
                   Line2D([], [], marker="o", ls="", ms=10, mfc=COLOR_GOL, mec="black", label="Gol"),
                   Line2D([], [], marker="D", ls="", ms=8, mfc="#f2c14e", mec="black", label="Tiro libre directo (sin pase)")]
        fig.legend(handles=leyenda, loc="lower center", ncol=4, fontsize=12, frameon=False)
        guardar(fig, torneo, nombre, dpi=140)

    for t in torneos_bp:
        figura(t, "a_favor", f"Balón parado a favor de {equipo}", "2_balon_parado_a_favor.png")
        figura(t, "en_contra", f"Balón parado en contra de {equipo}", "3_balon_parado_en_contra.png")


def saques_banda():
    datos = tiros_con_origen()
    # Todos los saques de banda (pases con pass_type_name = Throw-in)
    saques = eventos[(eventos["type_name"] == "Pass") & (eventos["pass_type_name"] == TIPO_SAQUE[1])].dropna(
        subset=["x", "y", "end_x", "end_y"]).copy()
    saques["completado"] = saques["pass_outcome_name"].isna()

    # Saques que terminaron en tiro: el origen de cada tiro de la tabla
    con_tiro = datos[~datos["sin_origen"] & (datos["set_piece_type"] == TIPO_SAQUE[0])][
        ["match_id", "idx_origen", "gol", "xg"]].rename(columns={"idx_origen": "index"})
    con_tiro = con_tiro.groupby(["match_id", "index"], as_index=False).agg(gol=("gol", "max"), xg=("xg", "sum"))
    saques = saques.merge(con_tiro, on=["match_id", "index"], how="left")
    saques["tiro"] = saques["xg"].notna()
    saques["gol"] = saques["gol"].fillna(False).astype(bool)
    torneos_sb = torneos_en(saques["torneo"])
    pitch = Pitch(pitch_type="statsbomb", line_color="#555555", line_zorder=1)

    def figura(torneo, propios, titulo, nombre):
        d = saques[(saques["torneo"] == torneo) & (saques["es_equipo_analizado"] == propios)]
        fig, ax = plt.subplots(figsize=(14, 9.5))
        pitch.draw(ax=ax)
        fig.suptitle(titulo, fontsize=22, fontweight="bold", y=0.97)
        ax.set_title(f"{torneo} ({partidos_torneo[torneo]} partidos): {len(d)} saques de banda, {int(d['tiro'].sum())} con tiro, "
                     f"{int(d['gol'].sum())} {'gol' if int(d['gol'].sum()) == 1 else 'goles'}", fontsize=14)
        for sel, color, alpha, ancho, z in [(~d["completado"], COLOR_FALLIDO, 0.35, 1.4, 2),
                                            (d["completado"] & ~d["tiro"], COLOR_FLECHA, 0.45, 1.4, 3),
                                            (d["tiro"] & ~d["gol"], COLOR_TIRO, 0.95, 2.2, 4),
                                            (d["gol"], COLOR_GOL, 1.0, 2.6, 5)]:
            p = d[sel]
            pitch.arrows(p.x, p.y, p.end_x, p.end_y, ax=ax, color=color, alpha=alpha, width=ancho,
                         headwidth=4, headlength=4, zorder=z)
        leyenda = [Line2D([], [], color=COLOR_FLECHA, lw=3, label="Saque completado"),
                   Line2D([], [], color=COLOR_FALLIDO, lw=3, label="Saque perdido"),
                   Line2D([], [], color=COLOR_TIRO, lw=3, label="Saque que terminó en tiro"),
                   Line2D([], [], color=COLOR_GOL, lw=3, label="Saque que terminó en gol")]
        fig.legend(handles=leyenda, loc="lower center", ncol=4, fontsize=12, frameon=False)
        fig.text(0.5, 0.075, "Cada flecha va de donde se sacó la banda a donde cayó el balón. Ataca de izquierda a derecha.",
                 ha="center", fontsize=11)
        guardar(fig, torneo, nombre, dpi=140)

    for t in torneos_sb:
        figura(t, True, f"Saques de banda de {equipo}", "4_saques_banda_a_favor.png")
        figura(t, False, f"Saques de banda del rival de {equipo}", "5_saques_banda_en_contra.png")


# ----------------------------------------------------------------------------- mapa de calor por jugador
def mapa_calor_jugadores(n_jugadores=11):
    sin_posicion = ["Starting XI", "Half Start", "Half End", "Substitution", "Tactical Shift", "Injury Stoppage",
                    "Referee Ball-Drop", "Player Off", "Player On", "Bad Behaviour", "Own Goal For", "Own Goal Against"]
    cmap = LinearSegmentedColormap.from_list("zona", ["#ffffff", "#ffe3d6", "#f9b79c", "#ef7b5c", "#d9382f", "#9e1220"])
    ev = eventos[eventos["es_equipo_analizado"] & (eventos["period"] < 5) & ~eventos["type_name"].isin(sin_posicion)]
    ev = ev.dropna(subset=["x", "y", "player_id"]).copy()
    ev["player_id"] = ev["player_id"].astype("int64")

    stats = cargar_stats([])
    torneos_j = torneos_en(stats["torneo"])
    pitch = Pitch(pitch_type="statsbomb", line_color="#444444", line_zorder=3, pad_top=2, pad_bottom=2)

    for t in torneos_j:
        s = stats[stats["torneo"] == t]
        minutos = s.groupby("player_id")[MINUTOS].sum().sort_values(ascending=False).head(n_jugadores)
        nombres = s.groupby("player_id")["player_name"].agg(lambda x: x.iloc[0])
        partidos = s.groupby("player_id")["match_id"].nunique()
        ev_t = ev[ev["torneo"] == t]

        fig, axs = plt.subplots(3, 4, figsize=(20, 12.5))
        fig.suptitle(f"{equipo} - {t}", fontsize=26, fontweight="bold", y=1.0)
        fig.subplots_adjust(top=0.88)
        fig.text(0.5, 0.935, f"Zonas donde estuvo cada uno de los {len(minutos)} jugadores con más minutos "
                 "(posición de sus acciones con balón y sin balón)", ha="center", fontsize=14)
        plano = axs.flatten()

        for ax, (pid, mins) in zip(plano, minutos.items()):
            d = ev_t[ev_t["player_id"] == pid]
            pitch.draw(ax=ax)
            if len(d) >= 5:
                stat = pitch.bin_statistic(d.x, d.y, statistic="count", bins=(48, 32))
                suave = gaussian_filter(stat["statistic"], 2.2)
                suave = np.where(suave < suave.max() * 0.06, np.nan, suave)
                stat["statistic"] = suave
                pitch.heatmap(stat, ax=ax, cmap=cmap, zorder=1, alpha=0.9)
                pitch.scatter(d.x.mean(), d.y.mean(), ax=ax, s=90, color="white", edgecolors="black", linewidth=1.5, zorder=4)
            ax.set_title(f"{corto_nombre(nombres[pid])}\n{int(partidos[pid])} partidos, {int(mins)} min, {len(d)} acciones",
                         fontsize=12, fontweight="bold")

        for ax in plano[len(minutos):]:
            ax.axis("off")
        if len(minutos) < len(plano):
            plano[len(minutos)].text(0.0, 0.5, "Cuanto más oscuro el rojo, más\nacciones del jugador en esa zona\n"
                                     "(cada mapa se mide contra el\npropio jugador).\n\nEl punto blanco es su posición\npromedio.\n\n"
                                     "América ataca de izquierda a derecha.", fontsize=11.5, va="center", ha="left")
        guardar(fig, t, f"mapa_calor_jugadores_{t.replace(' ', '_')}.png", dpi=120)


# ----------------------------------------------------------------------------- radar por posición
ROL_POR_POSITION_ID = {
    1: "Portero",
    3: "Defensa central", 4: "Defensa central", 5: "Defensa central",
    2: "Lateral / Carrilero", 6: "Lateral / Carrilero", 7: "Lateral / Carrilero", 8: "Lateral / Carrilero",
    9: "Pivote", 10: "Pivote", 11: "Pivote",
    12: "Interior / Ofensivo", 13: "Interior / Ofensivo", 14: "Interior / Ofensivo", 15: "Interior / Ofensivo",
    16: "Interior / Ofensivo", 18: "Interior / Ofensivo", 19: "Interior / Ofensivo", 20: "Interior / Ofensivo",
    17: "Extremo / Delantero", 21: "Extremo / Delantero", 22: "Extremo / Delantero",
    23: "Extremo / Delantero", 24: "Extremo / Delantero", 25: "Extremo / Delantero",
}
# (columna, etiqueta, tipo)  tipo: "p90" = suma / minutos * 90, "ratio" = media ponderada por minutos,
# "vallas" = % de partidos con 0 goles recibidos
METRICAS = {
    "Portero": [
        ("player_match_save_ratio", "% paradas", "ratio"),
        ("player_match_gsaa", "Goles evitados\n(PSxG) por 90", "p90"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_claim_success", "% balones\natrapados", "ratio"),
        ("player_match_goals_conceded", "Vallas\ninvictas (% PJ)", "vallas"),
    ],
    "Defensa central": [
        ("player_match_successful_aerials", "Duelos aéreos\nganados por 90", "p90"),
        ("player_match_clearances", "Despejes\npor 90", "p90"),
        ("player_match_interceptions", "Intercepciones\npor 90", "p90"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_challenge_ratio", "% duelos\ndefensivos ganados", "ratio"),
    ],
    "Lateral / Carrilero": [
        ("player_match_crosses_into_box", "Centros al\nárea por 90", "p90"),
        ("player_match_successful_crosses", "Centros\nexitosos por 90", "p90"),
        ("player_match_dribbles", "Regates\ncompletados por 90", "p90"),
        ("player_match_ball_recoveries", "Recuperaciones\npor 90", "p90"),
        ("player_match_key_passes", "Pases clave\npor 90", "p90"),
    ],
    "Pivote": [
        ("player_match_lbp_completed", "Pases que rompen\nlíneas por 90", "p90"),
        ("player_match_ball_recoveries", "Recuperaciones\npor 90", "p90"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_tackles", "Entradas con\néxito por 90", "p90"),
        ("player_match_challenge_ratio", "% duelos\nganados", "ratio"),
    ],
    "Interior / Ofensivo": [
        ("player_match_assists", "Asistencias\npor 90", "p90"),
        ("player_match_key_passes", "Pases clave\npor 90", "p90"),
        ("player_match_op_f3_passes", "Pases último\ntercio por 90", "p90"),
        ("player_match_deep_progressions", "Progresiones\nprofundas por 90", "p90"),
        ("player_match_xa", "xA (ocasiones\ngeneradas) por 90", "p90"),
    ],
    "Extremo / Delantero": [
        ("player_match_goals", "Goles\npor 90", "p90"),
        ("player_match_np_xg", "xG (sin penales)\npor 90", "p90"),
        ("player_match_np_shots_on_target", "Remates a\npuerta por 90", "p90"),
        ("player_match_dribbles", "Regates con\néxito por 90", "p90"),
        ("player_match_touches_inside_box", "Toques en el\nárea por 90", "p90"),
    ],
}
COLOR_ROL = {"Portero": "#7a5195", "Defensa central": "#0F2A52", "Lateral / Carrilero": "#2a7f62",
             "Pivote": "#b5651d", "Interior / Ofensivo": "#B8912B", "Extremo / Delantero": "#B40B0E"}


def radar_posiciones(n_jugadores=11, min_minutos_escala=300):
    columnas_usadas = sorted({c for ms in METRICAS.values() for c, _, _ in ms})
    stats = cargar_stats(columnas_usadas)

    pos = leer(buscar(BUSCAR_POSICIONES, "posiciones"), ["match_id", "team_id", "player_id", "position_id", "from", "to"],
               "la tabla de posiciones")
    pos = pos[pos["team_id"].astype("Int64") == EQUIPO_ID].dropna(subset=["position_id"]).copy()
    pos["match_id"] = pos["match_id"].astype("int64")
    pos["player_id"] = pos["player_id"].astype("int64")
    pos["rol"] = pos["position_id"].astype(int).map(ROL_POR_POSITION_ID)
    pos = pos.dropna(subset=["rol"])
    inicio = pd.to_timedelta(pos["from"], errors="coerce").dt.total_seconds()
    fin = pd.to_timedelta(pos["to"], errors="coerce").dt.total_seconds()
    pos["segundos"] = (fin.fillna(95 * 60) - inicio).clip(lower=0)
    pos = pos.merge(mapa_torneo, on="match_id", how="left").dropna(subset=["torneo"])
    rol_principal = (pos.groupby(["torneo", "player_id", "rol"])["segundos"].sum().reset_index()
                     .sort_values("segundos", ascending=False).drop_duplicates(["torneo", "player_id"])
                     .set_index(["torneo", "player_id"])["rol"])

    def agregar(d):
        minutos = d[MINUTOS].sum()
        fila = {"minutos": minutos, "partidos": d["match_id"].nunique()}
        for rol, ms in METRICAS.items():
            for col, _, tipo in ms:
                if tipo == "p90":
                    fila[col] = d[col].sum() / minutos * 90 if minutos > 0 else np.nan
                elif tipo == "ratio":
                    v = d[col]
                    peso = d.loc[v.notna(), MINUTOS]
                    fila[col] = (v.dropna() * peso).sum() / peso.sum() if peso.sum() > 0 else np.nan
                else:
                    v = d[col].dropna()
                    fila[col] = (v == 0).mean() if len(v) else np.nan
        return pd.Series(fila)

    tabla = stats.groupby(["torneo", "player_id"]).apply(agregar, include_groups=False).reset_index()
    nombres = stats.groupby("player_id")["player_name"].agg(lambda s: s.iloc[0]).map(corto_nombre)
    tabla["nombre"] = tabla["player_id"].map(nombres)
    tabla["rol"] = [rol_principal.get((t, p)) for t, p in zip(tabla["torneo"], tabla["player_id"])]
    torneos_r = torneos_en(tabla["torneo"])

    limites = {}
    pool = tabla[(tabla["minutos"] >= min_minutos_escala) & tabla["rol"].notna()]
    for rol, ms in METRICAS.items():
        sub = pool[pool["rol"] == rol]
        for col, _, tipo in ms:
            v = sub[col].dropna()
            if v.empty:
                limites[(rol, col)] = (0.0, 1.0)
                continue
            lo = 0.0 if tipo in ("p90", "vallas") else float(v.min())
            if col == "player_match_gsaa":
                lo = min(0.0, float(v.min()))
            hi = float(v.max())
            pad = (hi - lo) * 0.08 or 0.1
            limites[(rol, col)] = (lo - (pad if lo < 0 or tipo == "ratio" else 0), hi + pad)

    radares = {}
    for rol, ms in METRICAS.items():
        lo = [limites[(rol, c)][0] for c, _, _ in ms]
        hi = [limites[(rol, c)][1] for c, _, _ in ms]
        radares[rol] = Radar([e for _, e, _ in ms], lo, hi, round_int=[False] * len(ms),
                             num_rings=4, ring_width=1, center_circle_radius=1)

    def formato(valor, tipo):
        if pd.isna(valor):
            return "s/d"
        return f"{valor:.0%}" if tipo in ("ratio", "vallas") else f"{valor:.2f}"

    for t in torneos_r:
        d = tabla[tabla["torneo"] == t].sort_values("minutos", ascending=False).head(n_jugadores)
        d = d[d["rol"].notna()]
        n = len(d)
        fig, axs = plt.subplots(3, 4, figsize=(18, 15.5))
        fig.suptitle(f"América - {t}", fontsize=26, fontweight="bold", y=0.985)
        fig.text(0.5, 0.947, f"Los {n} jugadores con más minutos, con las métricas de su posición principal", ha="center", fontsize=14)
        plano = axs.flatten()

        for ax, (_, fila) in zip(plano, d.iterrows()):
            rol = fila["rol"]
            ms = METRICAS[rol]
            radar = radares[rol]
            color = COLOR_ROL[rol]
            valores = []
            for c, _, _ in ms:
                lo, hi = limites[(rol, c)]
                v = fila[c] if pd.notna(fila[c]) else lo
                valores.append(min(max(v, lo), hi))
            radar.setup_axis(ax=ax)
            radar.draw_circles(ax=ax, facecolor="#f2f2f2", edgecolor="#cccccc")
            res = radar.draw_radar(valores, ax=ax, kwargs_radar={"facecolor": color, "alpha": 0.6},
                                   kwargs_rings={"facecolor": color, "alpha": 0.1})
            radar.draw_param_labels(ax=ax, fontsize=8)
            for (x, y), (c, _, tipo) in zip(res[2], ms):
                ax.text(x, y, formato(fila[c], tipo), fontsize=8, ha="center", va="center", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, lw=0.6, alpha=0.9))
            ax.set_title(f"{fila['nombre']}\n{rol}\n{int(fila['partidos'])} partidos, {int(fila['minutos'])} min",
                         fontsize=11.5, fontweight="bold", y=1.07)

        for ax in plano[n:]:
            ax.axis("off")
        if n < len(plano):
            plano[n].text(0.0, 0.5, "Cada jugador se mide en la posición\nque más minutos jugó en el torneo.\n\n"
                          "Los conteos son por 90 minutos y los\nporcentajes están ponderados por minutos.\n\n"
                          "La escala es la misma para los 4 torneos\ny se calcula con los jugadores de esa\nposición con al menos "
                          f"{min_minutos_escala} min en un torneo.", fontsize=10.5, va="center", ha="left")
        guardar(fig, t, f"radar_posiciones_{t.replace(' ', '_')}.png", dpi=130)


# ----------------------------------------------------------------------------- ejecución
GRAFICAS = {
    "actividad_defensiva": actividad_defensiva,
    "flujo_pases": flujo_pases,
    "mapa_calor_defensivo": mapa_calor_defensivo,
    "tiros_ataque": tiros_ataque,
    "tiros_defensa": tiros_defensa,
    "red_pases": red_pases,
    "corners": corners,
    "balon_parado": balon_parado,
    "saques_banda": saques_banda,
    "mapa_calor_jugadores": mapa_calor_jugadores,
    "radar_posiciones": radar_posiciones,
}


def main():
    # Sin argumentos genera todas. Los argumentos que no sean nombres de gráfica se ignoran
    # (así no estorban los que meten algunos editores al ejecutar).
    elegidas = [a for a in sys.argv[1:] if a in GRAFICAS] or list(GRAFICAS)
    omitidas = []
    for nombre in elegidas:
        print(f"\n== {nombre} ==")
        try:
            GRAFICAS[nombre]()
        except FaltaDato as e:
            print("Omitida:", e)
            omitidas.append(nombre)
    print(f"\nListo: {len(elegidas) - len(omitidas)} de {len(elegidas)} gráficas generadas en {CARPETA_SALIDA}")
    if omitidas:
        print("Omitidas por falta de datos:", ", ".join(omitidas))


if __name__ == "__main__":
    main()