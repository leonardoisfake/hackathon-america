"""Todas las gráficas del América en un solo script.

Uso:
    python graficas_america.py                          # genera todas
    python graficas_america.py radar_posiciones tiros_ataque     # solo las que nombres
    python graficas_america.py tiros_ataque --salida otra/carpeta   # guarda en otra carpeta

Gráficas disponibles (nombre -> archivo que guarda en figuras/<torneo>/ en la raíz del repo):
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
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgb
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, PercentFormatter
from mplsoccer import Pitch, Radar, VerticalPitch
from scipy.ndimage import gaussian_filter

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parent
EQUIPO_ID = 1229
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = ROOT / "figuras"

BUSCAR_EVENTOS = ["eventos_parquet", "eventos.parquet"]
BUSCAR_TIROS = ["balon_parado_tiros.parquet", "balon_parado_tiros"]
BUSCAR_STATS = ["player_match_stats.parquet", "player_match_stats"]
BUSCAR_POSICIONES = ["posiciones.parquet", "posiciones"]
BUSCAR_ALINEACIONES = ["alineaciones.parquet", "alineaciones"]
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "processed", AQUI / "data" / "raw" / "parquet",
            ROOT / "data" / "interim", ROOT / "data" / "processed"]

COLUMNAS_EVENTOS = ["match_id", "id", "index", "torneo", "period", "possession", "type_name", "team_name", "player_id",
                    "player_name", "es_equipo_analizado", "x", "y", "x_eq", "y_eq", "end_x", "end_y", "duel_type_name",
                    "pass_type_name", "pass_technique_name", "pass_outcome_name", "pass_completed",
                    "pass_recipient_name", "shot_outcome_name", "shot_type_name",
                    "shot_statsbomb_xg"]
COLUMNAS_TIROS = ["match_id", "index", "lado", "origen", "set_piece_type", "es_fk_directo", "x", "y", "xg", "gol"]
MINUTOS = "player_match_minutes"


# ----------------------------------------------------------------------------- estilo común
# Paleta del reporte (diseno_html/DESIGN.md): el América siempre en marino y el rival en gris cálido
TINTA = "#0F1A2E"
TINTA_SUAVE = "#4A5568"
FONDO = "#FFFFFF"
LINEA_CANCHA = "#B8C2D1"
MARINO = "#0A1F44"
AMARILLO = "#FFD23F"  # solo como acento encima de una marca marina, nunca como texto ni suelto sobre blanco
RIVAL = "#7D746A"
GRIS_TIRO = "#7A8494"
NEUTRO = "#F3F3F2"
RAMPA_MARINO = ["#EEF1F6", "#C9D3E6", "#93A6C8", "#5C76A3", "#2E4A7A", MARINO]  # de claro a oscuro
RAMPA_RIVAL = ["#EFEDEA", "#D6D1CB", "#B5ADA4", "#8F867C", "#6B635A", "#4A433C"]
CMAP_MARINO = LinearSegmentedColormap.from_list("marino", RAMPA_MARINO)
# Divergente: gris cálido (rival) a la izquierda, neutro claro al centro, marino (América) a la derecha
CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rival_america", RAMPA_RIVAL[:0:-1] + [NEUTRO] + RAMPA_MARINO[1:])
FUENTES = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def aplicar_estilo():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": FUENTES,
        "text.color": TINTA, "axes.labelcolor": TINTA, "xtick.color": TINTA_SUAVE, "ytick.color": TINTA_SUAVE,
        "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
        "legend.frameon": False, "legend.fontsize": 11,
    })


def luminancia(color):
    canal = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in to_rgb(color)]
    return 0.2126 * canal[0] + 0.7152 * canal[1] + 0.0722 * canal[2]


def texto_sobre(color):
    # Blanco o tinta, el que contraste más con el color de fondo
    lum = luminancia(color)
    return FONDO if 1.05 / (lum + 0.05) >= (lum + 0.05) / (luminancia(TINTA) + 0.05) else TINTA


def ficha(ax, texto):
    # Una sola línea chica con la n, arriba a la izquierda de la cancha
    ax.text(0, 1.01, texto, transform=ax.transAxes, ha="left", va="bottom", fontsize=11, color=TINTA_SUAVE)


def ficha_figura(fig, texto, y=0.99, tamano=12):
    # La misma ficha para las figuras de varios paneles, arriba a la izquierda de la figura
    fig.text(0.01, y, texto, ha="left", va="top", fontsize=tamano, color=TINTA_SUAVE, linespacing=1.4)


def rotulo_panel(ax, nombre, detalle="", tamano=12, separacion=4):
    # Lo que identifica a cada panel (jugador, lado, tipo de jugada): nombre en tinta y detalle en tinta suave
    alto = 0
    if detalle:
        ax.annotate(detalle, xy=(0.5, 1), xycoords="axes fraction", xytext=(0, separacion), textcoords="offset points",
                    ha="center", va="bottom", fontsize=tamano - 1.5, color=TINTA_SUAVE, linespacing=1.3)
        alto = (detalle.count("\n") + 1) * (tamano - 1.5) * 1.4
    ax.set_title(nombre, fontsize=tamano, fontweight="bold", color=TINTA, pad=separacion + alto + 4)


def colores_equipo(propios):
    # Color fuerte, color medio y borde del gol: el América en marino con borde amarillo, el rival en gris cálido
    if propios:
        return MARINO, RAMPA_MARINO[3], AMARILLO
    return RIVAL, RAMPA_RIVAL[3], FONDO


def flecha_ataque(ax, y=-0.035):
    ax.annotate("", xy=(0.57, y), xytext=(0.45, y), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=TINTA_SUAVE, lw=1.5, mutation_scale=14))
    ax.text(0.44, y, "Ataque", transform=ax.transAxes, ha="right", va="center", fontsize=11, color=TINTA_SUAVE)


def porterias(ax, izquierda=None, derecha="Portería del rival", tamano=10.5):
    # Rótulo de cada portería en una cancha horizontal, girado junto a la línea de meta
    izquierda = izquierda or f"Portería del {equipo}"
    ax.text(-1.5, 40, izquierda, rotation=90, ha="right", va="center", fontsize=tamano, color=TINTA_SUAVE)
    ax.text(121.5, 40, derecha, rotation=270, ha="left", va="center", fontsize=tamano, color=TINTA_SUAVE)


def porteria_arriba(ax, texto, tamano=10.5):
    # Rótulo de la portería de una cancha vertical, a un lado del arco y sobre la línea de meta
    ax.annotate(texto, xy=(46, 120), xytext=(0, 3), textcoords="offset points", ha="left", va="bottom",
                fontsize=tamano, color=TINTA_SUAVE)


def con_signo(valor):
    valor = round(float(valor), 1)
    return "0.0" if valor == 0 else f"{valor:+.1f}".replace("-", "−")


def rotular_celdas(pitch, ax, stat, cmap, norma, formato, **kw):
    # Valor en cada celda con el color de texto que mejor contrasta con la celda
    for x, y, v in zip(stat["cx"].ravel(), stat["cy"].ravel(), stat["statistic"].ravel()):
        if np.isnan(v):
            continue
        pitch.annotate(formato(v), xy=(x, y), ax=ax, ha="center", va="center", zorder=3,
                       color=texto_sobre(cmap(norma(v))), **kw)


def valor_celda(stat, x, y):
    # Valor de la celda cuyo centro queda más cerca del punto
    i = np.argmin((stat["cx"] - x) ** 2 + (stat["cy"] - y) ** 2)
    return stat["statistic"].ravel()[i]


def barra_color(fig, ax, mapeable, y=-0.12, ancho=0.34):
    cax = ax.inset_axes([(1 - ancho) / 2, y, ancho, 0.025])
    barra = fig.colorbar(mapeable, cax=cax, orientation="horizontal")
    barra.outline.set_visible(False)
    barra.ax.tick_params(length=0, labelsize=10, labelcolor=TINTA_SUAVE, pad=4)
    return barra


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


def cargar_apodos():
    # Mapa player_id -> nombre deportivo; si falta el parquet o la columna, se sigue con corto_nombre
    try:
        al = leer(buscar(BUSCAR_ALINEACIONES, "las alineaciones"), ["player_id", "player_name", "player_nickname"],
                  "la tabla de alineaciones")
    except FaltaDato as e:
        print(f"Aviso: sin apodos, uso el nombre corto. {e}")
        return {}
    al = al.dropna(subset=["player_id", "player_nickname"])
    al = al[al["player_nickname"].astype(str).str.strip() != ""]
    return dict(zip(al["player_id"].astype("int64"), al["player_nickname"].astype(str).str.strip()))


APODOS = cargar_apodos()


def nombre_jugador(player_id, player_name):
    # Apodo deportivo si existe; si no, primer nombre + último apellido
    apodo = APODOS.get(int(player_id)) if pd.notna(player_id) else None
    return apodo or corto_nombre(player_name)


def nombre_corto(player_id, player_name):
    # Apodo sin el primer nombre cuando tiene dos palabras o más (para etiquetas apretadas)
    palabras = nombre_jugador(player_id, player_name).split()
    return " ".join(palabras[1:]) if len(palabras) > 1 else palabras[0]


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
    aplicar_estilo()
    tipos = ["Pressure", "Foul Committed", "Interception", "Block"]
    pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color=LINEA_CANCHA)

    estadisticas, totales = {}, {}
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
        totales[t] = (len(propias), len(rival))
    # Misma escala de color en los 4 torneos para que se puedan comparar entre sí
    limite = max(np.abs(s["statistic"]).max() for s in estadisticas.values())
    norma = Normalize(-limite, limite)

    for t in torneos:
        fig, ax = plt.subplots(figsize=(11, 8))
        pitch.draw(ax=ax)
        hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=CMAP_DIVERGENTE, norm=norma, zorder=1, edgecolors=FONDO, linewidth=1)
        rotular_celdas(pitch, ax, estadisticas[t], CMAP_DIVERGENTE, norma, con_signo, fontsize=13, fontweight="bold")
        n_propias, n_rival = totales[t]
        ficha(ax, f"{t} · {por_torneo[t]['match_id'].nunique()} partidos · {n_propias:,} acciones defensivas del {equipo} "
                  f"y {n_rival:,} del rival · diferencia en puntos porcentuales\n"
                  f"El {equipo} y el rival aparecen con la portería que defienden a la izquierda")
        porterias(ax, "Portería que defiende cada equipo", "Portería que ataca")
        flecha_ataque(ax)
        barra = barra_color(fig, ax, hm)
        barra.set_ticks([-limite, 0, limite])
        barra.set_ticklabels([con_signo(-limite), "0", con_signo(limite)])
        barra.ax.text(-0.03, 0.5, "Más peso en la defensa del rival", transform=barra.ax.transAxes, ha="right",
                      va="center", fontsize=11, color=TINTA)
        barra.ax.text(1.03, 0.5, f"Más peso en la defensa del {equipo}", transform=barra.ax.transAxes, ha="left",
                      va="center", fontsize=11, color=TINTA)
        guardar(fig, t, "1_actividad_defensiva.png")


# ----------------------------------------------------------------------------- 2. flujo de pases
def flujo_pases():
    aplicar_estilo()
    pitch = Pitch(pitch_type="statsbomb", line_color=LINEA_CANCHA, line_zorder=3)
    pases_t, estadisticas = {}, {}
    for t in torneos:
        d = por_torneo[t]
        pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"] & d["pass_outcome_name"].isna()]
        pases_t[t] = pases.dropna(subset=["x", "y", "end_x", "end_y"])
        estadisticas[t] = pitch.bin_statistic(pases_t[t].x, pases_t[t].y, statistic="count", bins=(8, 6), normalize=True)
    # Misma escala de color en los 4 torneos para que se puedan comparar entre sí
    norma = Normalize(0, max(s["statistic"].max() for s in estadisticas.values()))

    for t in torneos:
        pases, stat = pases_t[t], estadisticas[t]
        fig, ax = plt.subplots(figsize=(12, 8.5))
        pitch.draw(ax=ax)
        hm = pitch.heatmap(stat, ax=ax, cmap=CMAP_MARINO, norm=norma, zorder=1, edgecolors=FONDO, linewidth=1)
        flechas = pitch.flow(pases.x, pases.y, pases.end_x, pases.end_y, bins=(8, 6), arrow_type="same", arrow_length=8,
                             color=TINTA, ax=ax, zorder=4, width=1.4, headwidth=4, headlength=4)
        # Cada flecha va en blanco o en tinta según el color de la celda donde empieza
        flechas.set_color([texto_sobre(CMAP_MARINO(norma(valor_celda(stat, x, y)))) for x, y in zip(flechas.X, flechas.Y)])
        ficha(ax, f"{t} · {por_torneo[t]['match_id'].nunique()} partidos · {len(pases):,} pases completados")
        porterias(ax)
        flecha_ataque(ax)
        barra = barra_color(fig, ax, hm)
        barra.ax.xaxis.set_major_locator(MultipleLocator(0.01))
        barra.ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        barra.set_label("% de los pases completados del torneo que salen de cada zona", fontsize=11, color=TINTA,
                        labelpad=6)
        barra.ax.xaxis.set_label_position("top")
        ax.legend(handles=[Line2D([], [], ls="", marker=r"$\rightarrow$", ms=16, color=TINTA,
                                  label="Dirección promedio de los pases que salen de la zona (en blanco sobre las zonas oscuras)")],
                  loc="upper center", bbox_to_anchor=(0.5, -0.17), fontsize=11, handletextpad=0.3)
        guardar(fig, t, "2_flujo_pases.png")


# ----------------------------------------------------------------------------- 3. mapa de calor defensivo
def mapa_calor_defensivo():
    aplicar_estilo()
    acciones = ["Ball Recovery", "Duel", "Interception", "Clearance", "Block"]
    pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color=LINEA_CANCHA)

    estadisticas, totales = {}, {}
    for t, d in por_torneo.items():
        acc = d[d["type_name"].isin(acciones) & d["es_equipo_analizado"] & (d["period"] < 5)].dropna(subset=["x", "y"])
        estadisticas[t] = pitch.bin_statistic(acc.x, acc.y, statistic="count", bins=(6, 5), normalize=True)
        totales[t] = len(acc)
    vmax = max(s["statistic"].max() for s in estadisticas.values())
    norma = Normalize(0, vmax)

    for t in torneos:
        fig, ax = plt.subplots(figsize=(11, 8))
        pitch.draw(ax=ax)
        hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=CMAP_MARINO, norm=norma, zorder=1, edgecolors=FONDO, linewidth=1)
        rotular_celdas(pitch, ax, estadisticas[t], CMAP_MARINO, norma, lambda v: f"{v:.0%}", fontsize=13,
                       fontweight="bold")
        ficha(ax, f"{t} · {por_torneo[t]['match_id'].nunique()} partidos · {totales[t]:,} acciones defensivas del {equipo}")
        porterias(ax)
        flecha_ataque(ax)
        barra = barra_color(fig, ax, hm)
        barra.ax.xaxis.set_major_locator(MultipleLocator(0.05))
        barra.ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        barra.set_label("% de las acciones defensivas del torneo en cada zona", fontsize=11, color=TINTA, labelpad=6)
        barra.ax.xaxis.set_label_position("top")
        guardar(fig, t, "3_mapa_calor_defensivo.png")


# ----------------------------------------------------------------------------- 3 y 4. tiros a favor / en contra
def area_xg(xg):
    # Área del punto proporcional al xG del tiro
    return np.nan_to_num(np.asarray(xg, dtype=float)) * 1000 + 25


def mapa_tiros(nombre, propios):
    aplicar_estilo()
    pitch_t = VerticalPitch(pitch_type="statsbomb", goal_type="box", half=True, line_color=LINEA_CANCHA)
    relleno_gol, _, borde_gol = colores_equipo(propios)
    leyenda = ([Line2D([], [], marker="o", ls="", ms=11, mfc=relleno_gol, mec=borde_gol, mew=1.5, label="Gol"),
                Line2D([], [], marker="o", ls="", ms=11, mfc="none", mec=GRIS_TIRO, label="Sin gol")]
               + [Line2D([], [], marker="o", ls="", ms=np.sqrt(area_xg(v)), mfc="none", mec=GRIS_TIRO, label=f"{v} xG")
                  for v in (0.05, 0.2, 0.5)])
    for t in torneos:
        d = por_torneo[t]
        # Sin penales, igual que el xG del reporte
        tiros = d[(d["type_name"] == "Shot") & (d["es_equipo_analizado"] == propios) & (d["period"] < 5)
                  & (d["shot_type_name"] != "Penalty")].dropna(subset=["x", "y"])
        goles = tiros[tiros["shot_outcome_name"] == "Goal"]
        no_goles = tiros[tiros["shot_outcome_name"] != "Goal"]

        fig, ax = plt.subplots(figsize=(9, 8))
        pitch_t.draw(ax=ax)
        pitch_t.scatter(no_goles.x, no_goles.y, ax=ax, s=area_xg(no_goles.shot_statsbomb_xg), facecolors="none",
                        edgecolors=GRIS_TIRO, linewidths=0.9, zorder=2)
        pitch_t.scatter(goles.x, goles.y, ax=ax, s=area_xg(goles.shot_statsbomb_xg), color=relleno_gol,
                        edgecolors=borde_gol, linewidths=1.5, zorder=3)
        ficha(ax, f"{t} · {d['match_id'].nunique()} partidos · {len(tiros):,} tiros · {len(goles):,} goles · "
                  f"{tiros.shot_statsbomb_xg.sum():.1f} xG")
        porteria_arriba(ax, "Portería del rival" if propios else f"Portería del {equipo}")
        ax.legend(handles=leyenda, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=5, fontsize=11,
                  handletextpad=0.4, columnspacing=1.6)
        guardar(fig, t, nombre)


def tiros_ataque():
    mapa_tiros("3_tiros_ataque.png", True)


def tiros_defensa():
    mapa_tiros("4_tiros_defensa.png", False)


# ----------------------------------------------------------------------------- 5. red de pases
def red_pases(min_pases_jugador=100, min_pases_enlace=15):
    aplicar_estilo()
    pitch_r = Pitch(pitch_type="statsbomb", line_color=LINEA_CANCHA)
    for t in torneos:
        d = por_torneo[t]
        pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"]]
        completados = pases[(pases["pass_completed"].fillna(False).astype(bool)) & pases["pass_recipient_name"].notna()]

        posiciones = completados.groupby("player_name").agg(x=("x_eq", "mean"), y=("y_eq", "mean"), count=("x_eq", "count"),
                                                            pid=("player_id", "first"))
        posiciones = posiciones[posiciones["count"] >= min_pases_jugador]
        etiquetas = {j: nombre_corto(r.pid, j) for j, r in posiciones.iterrows()}
        repetidas = {e for e in etiquetas.values() if list(etiquetas.values()).count(e) > 1}
        for j in etiquetas:
            if etiquetas[j] in repetidas:
                etiquetas[j] = nombre_jugador(posiciones.at[j, "pid"], j)

        enlaces = (completados.groupby(["player_name", "pass_recipient_name"]).id.count().reset_index()
                   .rename(columns={"player_name": "pasador", "pass_recipient_name": "receptor", "id": "pass_count"}))
        enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="pasador", right_index=True)
        enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="receptor", right_index=True, suffixes=["", "_end"])
        enlaces = enlaces[enlaces["pass_count"] >= min_pases_enlace]

        fig, ax = plt.subplots(figsize=(12, 8.5))
        pitch_r.draw(ax=ax)
        max_enlace = enlaces.pass_count.max()
        pitch_r.lines(enlaces.x, enlaces.y, enlaces.x_end, enlaces.y_end,
                      lw=enlaces.pass_count / max_enlace * 7, color=RAMPA_MARINO[3], alpha=.55, ax=ax, zorder=1)
        max_nodo = posiciones["count"].max()
        tamanos = posiciones["count"] / max_nodo * 900 + 60
        pitch_r.scatter(posiciones.x, posiciones.y, s=tamanos, color=MARINO, edgecolors=FONDO, linewidths=1.5, ax=ax,
                        zorder=2)
        colocar_nombres(fig, ax, posiciones.x, posiciones.y, np.sqrt(tamanos) / 2,
                        [etiquetas[j] for j in posiciones.index])
        ficha(ax, f"{t} · {d['match_id'].nunique()} partidos · {len(posiciones)} jugadores con {min_pases_jugador} pases "
                  f"completados o más · {len(enlaces)} conexiones de {min_pases_enlace} pases o más")
        porterias(ax)
        flecha_ataque(ax)
        # Leyendas de tamaño del punto y grosor de la línea con valores redondos del propio torneo
        nodos = redondos(min_pases_jugador, max_nodo)
        lineas = redondos(min_pases_enlace, max_enlace)
        ley_nodos = ax.legend(handles=[Line2D([], [], ls="", marker="o", ms=np.sqrt(v / max_nodo * 900 + 60), mfc=MARINO,
                                              mec=FONDO, label=f"{v:,}") for v in nodos],
                              title="Pases completados del jugador", loc="upper left", bbox_to_anchor=(0.02, -0.07),
                              ncol=len(nodos), fontsize=11, title_fontsize=11, columnspacing=1.2, handletextpad=0.5,
                              handleheight=2.6)
        ley_nodos._legend_box.align = "left"
        ax.add_artist(ley_nodos)
        ley_lineas = ax.legend(handles=[Line2D([], [], color=RAMPA_MARINO[3], alpha=.55, lw=v / max_enlace * 7,
                                               label=f"{v:,}") for v in lineas],
                               title="Pases entre los dos jugadores", loc="upper right", bbox_to_anchor=(0.98, -0.07),
                               ncol=len(lineas), fontsize=11, title_fontsize=11, columnspacing=1.2, handlelength=2.5)
        ley_lineas._legend_box.align = "left"
        guardar(fig, t, "5_red_pases.png")


def redondos(minimo, maximo):
    # Tres valores redondos entre el mínimo del filtro y el máximo observado, para las leyendas de tamaño
    paso = 10 ** max(int(np.log10(max(maximo, 1))) - 1, 0) * 5
    medio = max(round((minimo + maximo) / 2 / paso) * paso, minimo)
    alto = max(int(maximo // paso) * paso, medio)
    return sorted({int(minimo), int(medio), int(alto)})


def colocar_nombres(fig, ax, xs, ys, radios, textos, tamano=11):
    # Cada nombre prueba abajo, arriba, derecha e izquierda de su punto y se queda con el lugar que menos choca
    # con los puntos y con los nombres ya puestos
    xs, ys, radios = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), np.asarray(radios, dtype=float)
    fig.canvas.draw()
    render = fig.canvas.get_renderer()
    escala = fig.dpi / 72
    centros = ax.transData.transform(np.column_stack([xs, ys]))
    ocupado = [(cx - r * escala, cy - r * escala, cx + r * escala, cy + r * escala)
               for (cx, cy), r in zip(centros, radios)]
    halo = [pe.withStroke(linewidth=3, foreground="white")]

    def choque(caja):
        return sum(choque_con(caja, b) for b in ocupado)

    orden = np.argsort(-radios)
    for i in orden:
        r = radios[i] + 3
        mejor = None
        for dx, dy, ha, va in [(0, -r, "center", "top"), (0, r, "center", "bottom"), (r, 0, "left", "center"),
                               (-r, 0, "right", "center")]:
            texto = ax.annotate(textos[i], xy=(xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                                ha=ha, va=va, fontsize=tamano, color=TINTA, zorder=3, path_effects=halo)
            b = texto.get_window_extent(render)
            caja = (b.x0, b.y0, b.x1, b.y1)
            # Se descuenta el choque con su propio punto, que siempre toca por estar pegado a él
            costo = choque(caja) - choque_con(caja, ocupado[i])
            if mejor is None or costo < mejor[0]:
                if mejor is not None:
                    mejor[1].remove()
                mejor = (costo, texto, caja)
            else:
                texto.remove()
            if costo == 0:
                break
        ocupado.append(mejor[2])


def choque_con(caja, otra):
    # Área en que se enciman dos cajas (x0, y0, x1, y1) en pixeles
    return (max(0, min(caja[2], otra[2]) - max(caja[0], otra[0]))
            * max(0, min(caja[3], otra[3]) - max(caja[1], otra[1])))


# ----------------------------------------------------------------------------- córners (mapa de calor)
def corners():
    aplicar_estilo()
    lados = ["Izquierda", "Derecha"]

    cs = eventos[(eventos["type_name"] == "Pass") & (eventos["pass_type_name"] == "Corner") & eventos["es_equipo_analizado"]]
    cs = cs.dropna(subset=["x", "y", "end_x", "end_y"]).copy()
    cs["lado"] = np.where(cs["y"] < 40, "Izquierda", "Derecha")
    cs["corto"] = np.where(cs["lado"] == "Izquierda", cs["end_y"] <= 18, cs["end_y"] >= 62)
    # Solo la zona del área: la cancha se recorta desde x = 85 (el córner largo más corto de los 4 torneos cae en 86.9)
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, line_color=LINEA_CANCHA, line_zorder=2, pad_bottom=-25,
                          pad_top=3)

    for t in torneos:
        fig, axs = plt.subplots(1, 2, figsize=(15, 4.9))
        fig.subplots_adjust(top=0.7, bottom=0.02, left=0.01, right=0.99, wspace=0.06)
        ficha_figura(fig, f"{t} · {partidos_torneo[t]} partidos · {(cs['torneo'] == t).sum():,} córners del {equipo}\n"
                          "Cada número es el % de los córners de ese lado (sin los cortos) que cae en la zona · "
                          "cada punto gris es un córner", y=1.0)
        for ax, lado in zip(axs, lados):
            todos = cs[(cs["torneo"] == t) & (cs["lado"] == lado)]
            data = todos[~todos["corto"]]
            pitch.draw(ax=ax)
            porteria_arriba(ax, "Portería del rival", tamano=11)
            cabecera = f"Desde la {lado.lower()}"
            if data.empty:
                rotulo_panel(ax, cabecera, "todos en corto")
                continue
            stat = pitch.bin_statistic(data["end_x"], data["end_y"], statistic="count", bins=(15, 11), normalize=True)
            norma = Normalize(0, stat["statistic"].max())
            # Las zonas sin córners quedan en blanco
            visible = dict(stat, statistic=np.where(stat["statistic"] > 0, stat["statistic"], np.nan))
            pitch.heatmap(visible, edgecolors=FONDO, linewidth=1, cmap=CMAP_MARINO, norm=norma, ax=ax, zorder=1)
            pitch.scatter(data["end_x"], data["end_y"], ax=ax, color=GRIS_TIRO, s=8, alpha=0.6, zorder=2.5)
            rotular_celdas(pitch, ax, visible, CMAP_MARINO, norma, lambda v: f"{v:.0%}", fontsize=13, fontweight="bold")
            outs = (data["pass_technique_name"] == "Outswinging").mean() * 100
            ins = (data["pass_technique_name"] == "Inswinging").mean() * 100
            cobradores = todos.groupby("player_name").size().sort_values(ascending=False) / len(todos) * 100
            ids_cobro = todos.groupby("player_name")["player_id"].first()
            texto = " y ".join(f"{nombre_jugador(ids_cobro[n], n)} ({p:.0f}%)" for n, p in cobradores.head(2).items())
            rotulo_panel(ax, cabecera, f"{len(data)} de {len(todos)} sin jugar en corto · cobran {texto}\n"
                                       f"abiertos {outs:.0f}% · cerrados {ins:.0f}%", tamano=13)
        guardar(fig, t, "1_corners_mapa_calor.png", dpi=130)


# ----------------------------------------------------------------------------- balón parado y saques de banda
TIPOS_PARADO = [("Corner", "Corner", "Córner"), ("Free Kick", "Free Kick", "Tiro libre")]
TIPO_SAQUE = ("Throw In", "Throw-in", "Saque de banda")
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
    aplicar_estilo()
    datos = tiros_con_origen()
    datos = datos[datos["set_piece_type"].isin([t[0] for t in TIPOS_PARADO])]
    torneos_bp = torneos_en(datos["torneo"])
    pitch = VerticalPitch(pitch_type="statsbomb", line_color=LINEA_CANCHA, line_zorder=1)

    def figura(torneo, lado, nombre):
        fuerte, medio, borde_gol = colores_equipo(lado == "a_favor")
        d_t = datos[(datos["torneo"] == torneo) & (datos["lado"] == lado)]
        fig, axs = plt.subplots(1, len(TIPOS_PARADO), figsize=(13, 7.6))
        fig.subplots_adjust(top=0.9, bottom=0.12, wspace=0.08)
        ficha_figura(fig, f"{torneo} · {partidos_torneo[torneo]} partidos · {len(d_t):,} tiros de córner o tiro libre · "
                          f"{int(d_t['gol'].sum()):,} goles · {d_t['xg'].sum():.1f} xG", y=1.0)
        for ax, (clave, _, etiqueta) in zip(axs, TIPOS_PARADO):
            d = d_t[d_t["set_piece_type"] == clave]
            pitch.draw(ax=ax)
            ax.set_ylim(45, 122)
            porteria_arriba(ax, "Portería del rival" if lado == "a_favor" else f"Portería del {equipo}")
            con = d[~d["sin_origen"] & ~d["directo"]]
            pitch.arrows(con.x0, con.y0, con.x, con.y, ax=ax, color=medio, alpha=0.4, width=1.2,
                         headwidth=4, headlength=4, zorder=2)
            pitch.arrows(con[con["gol"]].x0, con[con["gol"]].y0, con[con["gol"]].x, con[con["gol"]].y, ax=ax,
                         color=fuerte, alpha=0.95, width=1.8, headwidth=4, headlength=4, zorder=3)
            pitch.scatter(con.x0, con.y0, ax=ax, s=18, color=medio, alpha=0.7, zorder=2)
            no_gol = d[~d["gol"]]
            gol = d[d["gol"]]
            pitch.scatter(no_gol.x, no_gol.y, ax=ax, s=no_gol.xg.fillna(0) * 900 + 25, facecolors=FONDO,
                          edgecolors=GRIS_TIRO, linewidths=0.9, zorder=4)
            pitch.scatter(gol.x, gol.y, ax=ax, s=gol.xg.fillna(0) * 900 + 40, color=fuerte, edgecolors=borde_gol,
                          linewidths=1.5, zorder=5)
            dire = d[d["directo"]]
            if len(dire):
                pitch.scatter(dire.x0, dire.y0, ax=ax, s=60, marker="D", facecolors="none", edgecolors=fuerte,
                              linewidths=1.3, zorder=6)
            goles = int(d["gol"].sum())
            rotulo_panel(ax, etiqueta, f"{len(d):,} tiros · {goles} {'gol' if goles == 1 else 'goles'} · "
                                       f"{d['xg'].sum():.1f} xG")
        leyenda = [Line2D([], [], color=medio, lw=2, label="Del saque al tiro"),
                   Line2D([], [], marker="o", ls="", ms=10, mfc="none", mec=GRIS_TIRO, label="Tiro (tamaño = xG)"),
                   Line2D([], [], marker="o", ls="", ms=10, mfc=fuerte, mec=borde_gol, mew=1.5, label="Gol"),
                   Line2D([], [], marker="D", ls="", ms=8, mfc="none", mec=fuerte, label="Tiro libre directo")]
        # La leyenda va justo debajo de las canchas, que el aspecto fijo deja más bajas que su eje
        axs[0].apply_aspect()
        fig.legend(handles=leyenda, loc="upper center", bbox_to_anchor=(0.5, axs[0].get_position().y0 - 0.01), ncol=4,
                   fontsize=12)
        guardar(fig, torneo, nombre, dpi=140)

    for t in torneos_bp:
        figura(t, "a_favor", "2_balon_parado_a_favor.png")
        figura(t, "en_contra", "3_balon_parado_en_contra.png")


def saques_banda():
    aplicar_estilo()
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
    pitch = Pitch(pitch_type="statsbomb", line_color=LINEA_CANCHA, line_zorder=1)

    def figura(torneo, propios, nombre):
        fuerte, medio, borde_gol = colores_equipo(propios)
        d = saques[(saques["torneo"] == torneo) & (saques["es_equipo_analizado"] == propios)]
        fig, ax = plt.subplots(figsize=(14, 9.5))
        pitch.draw(ax=ax)
        goles = int(d["gol"].sum())
        ficha(ax, f"{torneo} · {partidos_torneo[torneo]} partidos · {len(d):,} saques de banda · "
                  f"{int(d['tiro'].sum())} con tiro · {goles} {'gol' if goles == 1 else 'goles'}")
        # La masa de saques va tenue y delgada; solo resaltan los que terminaron en tiro o gol
        for sel, color, alpha, ancho, z in [(~d["completado"], GRIS_TIRO, 0.25, 0.9, 2),
                                            (d["completado"] & ~d["tiro"], medio, 0.3, 0.9, 3),
                                            (d["tiro"], fuerte, 1.0, 2.8, 4)]:
            p = d[sel]
            pitch.arrows(p.x, p.y, p.end_x, p.end_y, ax=ax, color=color, alpha=alpha, width=ancho,
                         headwidth=4, headlength=4, zorder=z)
        # La jugada que acabó en tiro se cierra con un círculo: hueco si no fue gol, relleno si fue gol
        tiro, gol = d[d["tiro"] & ~d["gol"]], d[d["gol"]]
        pitch.scatter(tiro.end_x, tiro.end_y, ax=ax, s=110, facecolors=FONDO, edgecolors=fuerte, linewidths=2, zorder=5)
        pitch.scatter(gol.end_x, gol.end_y, ax=ax, s=140, color=fuerte, edgecolors=borde_gol, linewidths=2, zorder=6)
        if propios:
            porterias(ax, f"Portería del {equipo}", "Portería del rival", tamano=11)
        else:
            porterias(ax, "Portería del rival", f"Portería del {equipo}", tamano=11)
        flecha_ataque(ax, y=-0.03)
        leyenda = [Line2D([], [], color=medio, lw=1.5, alpha=0.5, label="Saque completado"),
                   Line2D([], [], color=GRIS_TIRO, lw=1.5, alpha=0.5, label="Saque perdido"),
                   Line2D([], [], color=fuerte, lw=3, marker="o", ms=10, mfc=FONDO, mec=fuerte, mew=2,
                          label="La jugada terminó en tiro"),
                   Line2D([], [], color=fuerte, lw=3, marker="o", ms=11, mfc=fuerte, mec=borde_gol, mew=2,
                          label="La jugada terminó en gol")]
        ax.legend(handles=leyenda, loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=4, fontsize=12)
        guardar(fig, torneo, nombre, dpi=140)

    for t in torneos_sb:
        figura(t, True, "4_saques_banda_a_favor.png")
        figura(t, False, "5_saques_banda_en_contra.png")


# ----------------------------------------------------------------------------- mapa de calor por jugador
def mapa_calor_jugadores(n_jugadores=11):
    sin_posicion = ["Starting XI", "Half Start", "Half End", "Substitution", "Tactical Shift", "Injury Stoppage",
                    "Referee Ball-Drop", "Player Off", "Player On", "Bad Behaviour", "Own Goal For", "Own Goal Against"]
    aplicar_estilo()
    ev = eventos[eventos["es_equipo_analizado"] & (eventos["period"] < 5) & ~eventos["type_name"].isin(sin_posicion)]
    ev = ev.dropna(subset=["x", "y", "player_id"]).copy()
    ev["player_id"] = ev["player_id"].astype("int64")

    stats = cargar_stats([])
    torneos_j = torneos_en(stats["torneo"])
    pitch = Pitch(pitch_type="statsbomb", line_color=LINEA_CANCHA, line_zorder=3, pad_top=2, pad_bottom=2)

    for t in torneos_j:
        s = stats[stats["torneo"] == t]
        minutos = s.groupby("player_id")[MINUTOS].sum().sort_values(ascending=False).head(n_jugadores)
        nombres = s.groupby("player_id")["player_name"].agg(lambda x: x.iloc[0])
        partidos = s.groupby("player_id")["match_id"].nunique()
        ev_t = ev[ev["torneo"] == t]

        # 3 columnas para que cada cancha se lea al ancho del reporte
        fig, axs = plt.subplots(4, 3, figsize=(15, 17))
        fig.subplots_adjust(top=0.93, bottom=0.01, left=0.03, right=0.97, hspace=0.42, wspace=0.12)
        ficha_figura(fig, f"{t} · {partidos_torneo[t]} partidos · los {len(minutos)} jugadores con más minutos",
                     y=0.995, tamano=13)
        plano = axs.flatten()

        for ax, (pid, mins) in zip(plano, minutos.items()):
            d = ev_t[ev_t["player_id"] == pid]
            pitch.draw(ax=ax)
            if len(d) >= 5:
                stat = pitch.bin_statistic(d.x, d.y, statistic="count", bins=(48, 32))
                suave = gaussian_filter(stat["statistic"], 2.2)
                suave = np.where(suave < suave.max() * 0.06, np.nan, suave)
                stat["statistic"] = suave
                pitch.heatmap(stat, ax=ax, cmap=CMAP_MARINO, zorder=1)
                pitch.scatter(d.x.mean(), d.y.mean(), ax=ax, s=110, color=FONDO, edgecolors=TINTA, linewidth=1.5, zorder=4)
            porterias(ax, f"Portería del {equipo}", "Portería del rival", tamano=11)
            rotulo_panel(ax, nombre_jugador(pid, nombres[pid]),
                         f"{int(partidos[pid])} partidos · {int(mins):,} min · {len(d):,} acciones", tamano=15)

        for ax in plano[len(minutos):]:
            ax.axis("off")
        if len(minutos) < len(plano):
            # Leyenda en el hueco que queda: escala de color, posición promedio y dirección de ataque
            hueco = plano[len(minutos)]
            barra = fig.colorbar(plt.cm.ScalarMappable(cmap=CMAP_MARINO), cax=hueco.inset_axes([0.08, 0.72, 0.8, 0.07]),
                                 orientation="horizontal", ticks=[0, 1])
            barra.outline.set_visible(False)
            barra.ax.set_xticklabels(["menos", "más"])
            barra.ax.tick_params(length=0, labelsize=13, labelcolor=TINTA_SUAVE)
            barra.set_label("Acciones del jugador en la zona", fontsize=14, color=TINTA, labelpad=6)
            barra.ax.xaxis.set_label_position("top")
            hueco.scatter([0.1], [0.42], s=110, color=FONDO, edgecolors=TINTA, linewidth=1.5, transform=hueco.transAxes,
                          clip_on=False)
            hueco.text(0.17, 0.42, "Posición promedio", transform=hueco.transAxes, va="center", fontsize=14, color=TINTA)
            hueco.annotate("", xy=(0.62, 0.16), xytext=(0.38, 0.16), xycoords="axes fraction",
                           arrowprops=dict(arrowstyle="-|>", color=TINTA_SUAVE, lw=1.8, mutation_scale=16))
            hueco.text(0.36, 0.16, "Ataque", transform=hueco.transAxes, ha="right", va="center", fontsize=14,
                       color=TINTA_SUAVE)
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


def radar_posiciones(n_jugadores=11, min_minutos_escala=300):
    aplicar_estilo()
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
    nombres = pd.Series({pid: nombre_jugador(pid, n) for pid, n in
                         stats.groupby("player_id")["player_name"].agg(lambda s: s.iloc[0]).items()})
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
        # 3 columnas para que cada radar se lea al ancho del reporte
        fig, axs = plt.subplots(4, 3, figsize=(15, 22))
        fig.subplots_adjust(top=0.92, bottom=0.01, left=0.06, right=0.94, hspace=0.42, wspace=0.42)
        ficha_figura(fig, f"{t} · {partidos_torneo[t]} partidos · los {n} jugadores con más minutos\n"
                          f"Cada eje va de 0 (o del mínimo) al máximo de los jugadores de la misma posición con "
                          f"{min_minutos_escala} min o más en los cuatro torneos · el número es el valor del jugador",
                     y=0.995, tamano=13)
        plano = axs.flatten()

        for ax, (_, fila) in zip(plano, d.iterrows()):
            rol = fila["rol"]
            ms = METRICAS[rol]
            radar = radares[rol]
            valores = []
            for c, _, _ in ms:
                lo, hi = limites[(rol, c)]
                v = fila[c] if pd.notna(fila[c]) else lo
                valores.append(min(max(v, lo), hi))
            radar.setup_axis(ax=ax)
            radar.draw_circles(ax=ax, facecolor="#F4F6F9", edgecolor="#D5DBE5")
            res = radar.draw_radar(valores, ax=ax, kwargs_radar={"facecolor": MARINO, "alpha": 0.55},
                                   kwargs_rings={"facecolor": MARINO, "alpha": 0.08})
            radar.draw_param_labels(ax=ax, fontsize=12, color=TINTA_SUAVE)
            for (x, y), (c, _, tipo) in zip(res[2], ms):
                ax.text(x, y, formato(fila[c], tipo), fontsize=12, ha="center", va="center", fontweight="bold",
                        color=TINTA, bbox=dict(boxstyle="round,pad=0.2", fc=FONDO, ec=MARINO, lw=0.6))
            rotulo_panel(ax, fila["nombre"], f"{rol} · {int(fila['partidos'])} partidos · {int(fila['minutos']):,} min",
                         tamano=15, separacion=26)

        for ax in plano[n:]:
            ax.axis("off")
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
    global CARPETA_SALIDA
    # Sin argumentos genera todas. Los argumentos que no sean nombres de gráfica se ignoran
    # (así no estorban los que meten algunos editores al ejecutar).
    argumentos = sys.argv[1:]
    if "--salida" in argumentos:
        i = argumentos.index("--salida")
        if i + 1 >= len(argumentos):
            sys.exit("Falta la carpeta después de --salida.")
        CARPETA_SALIDA = Path(argumentos[i + 1]).resolve()
        del argumentos[i:i + 2]
    elegidas = [a for a in argumentos if a in GRAFICAS] or list(GRAFICAS)
    omitidas = []
    for nombre in elegidas:
        print(f"\n== {nombre} ==")
        try:
            # El estilo que fije cada gráfica no pasa a la siguiente
            with plt.rc_context():
                GRAFICAS[nombre]()
        except FaltaDato as e:
            print("Omitida:", e)
            omitidas.append(nombre)
    print(f"\nListo: {len(elegidas) - len(omitidas)} de {len(elegidas)} gráficas generadas en {CARPETA_SALIDA}")
    if omitidas:
        print("Omitidas por falta de datos:", ", ".join(omitidas))


if __name__ == "__main__":
    main()