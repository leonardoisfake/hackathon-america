"""Las métricas de contexto del América dibujadas en la cancha: con los 91 partidos juntos y por torneo.

Uso:
    python scripts/Cambio_Partidos.py                                   # guarda en figuras/ en la raíz del repo
    python scripts/Cambio_Partidos.py --salida "../Local/ARCHIVOS_YORDI/figuras_pablo"   # guarda en otra carpeta

Guarda 3 imágenes con los 91 partidos en la raíz de la carpeta de salida y las mismas 3 de cada torneo en
<salida>/<torneo>/ (las carpetas que usa graficas.py):
    contexto_cancha_marcador.png   Perdiendo / Empatando / Ganando
    contexto_cancha_localia.png    Local / Visitante
    contexto_cancha_rival.png      Rival débil / Rival medio / Rival fuerte
Un nivel con menos de MIN_PARTIDOS partidos o MIN_MINUTOS minutos en un torneo no se dibuja: su columna dice
«Pocos datos». La línea punteada de la fila 3 es siempre el promedio de los 91 partidos, para comparar torneos.

Los contextos usan las mismas definiciones que el resto del reporte:
    marcador  score_state de data/processed/contexto_eventos.parquet (marcador antes de cada evento) y los minutos
              de cada estado de contexto_partidos.parquet
    localía   is_home de data/processed/contexto_partidos.parquet
    rival     rival_strength_tercil de data/processed/contexto_partidos.parquet (tercil de la diferencia de xG sin
              penales del rival dentro de su torneo)

Cada imagen tiene 3 filas de canchas, una columna por nivel del contexto y el América atacando de izquierda a derecha:
    1. Territorio: % de los pases de cada tercio de cancha que son del América contra los del rival
    2. Peligro: tiros de ambos equipos sin penales, tamaño = xG, y xG por 90 minutos a favor y en contra
    3. Presión: calor de las acciones defensivas del América y línea con la altura media de sus recuperaciones

Entradas (junto al script, en la carpeta actual, o en data/interim y data/processed):
    eventos.parquet            tabla limpia 'eventos'
    contexto_eventos.parquet   score_state por evento
    contexto_partidos.parquet  is_home, rival_strength_tercil y minutos ganando, empatando y perdiendo por partido
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
from mplsoccer import Pitch

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parent
CARPETA_SALIDA = ROOT / "figuras"
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "processed",
            ROOT / "data" / "interim", ROOT / "data" / "processed"]
BUSCAR_EVENTOS = ["eventos_parquet", "eventos.parquet"]
BUSCAR_CONTEXTO_EVENTOS = ["contexto_eventos.parquet"]
BUSCAR_CONTEXTO_PARTIDOS = ["contexto_partidos.parquet"]

COLUMNAS_EVENTOS = ["match_id", "index", "period", "type_name", "team_name", "es_equipo_analizado", "x_eq", "y_eq",
                    "shot_outcome_name", "shot_type_name", "shot_statsbomb_xg"]
COLUMNAS_PARTIDOS = ["match_id", "torneo", "is_home", "rival_strength_tercil", "minutos_perdiendo", "minutos_empatando",
                     "minutos_ganando"]
ACCIONES_CALOR = ["Pressure", "Interception", "Foul Committed", "Ball Recovery", "Duel"]
ACCIONES_RECUPERA = ["Ball Recovery", "Interception"]
BINS_TERRITORIO = (3, 1)
BINS_CALOR = (6, 5)
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
MIN_PARTIDOS = 5  # por debajo de esto un nivel no se dibuja
MIN_MINUTOS = 90

# Paleta del reporte, la misma de graficas.py (no se importa porque graficas.py carga los datos al importarse)
TINTA = "#0F1A2E"
TINTA_SUAVE = "#4A5568"
FONDO = "#FFFFFF"
LINEA_CANCHA = "#B8C2D1"
MARINO = "#0A1F44"
AMARILLO = "#FFD23F"  # solo como acento encima de una marca marina, nunca como texto ni suelto sobre blanco
RIVAL = "#7D746A"
NEUTRO = "#F3F3F2"
RAMPA_MARINO = ["#EEF1F6", "#C9D3E6", "#93A6C8", "#5C76A3", "#2E4A7A", MARINO]
RAMPA_RIVAL = ["#EFEDEA", "#D6D1CB", "#B5ADA4", "#8F867C", "#6B635A", "#4A433C"]
CMAP_MARINO = LinearSegmentedColormap.from_list("marino", RAMPA_MARINO)
CMAP_DIVERGENTE = LinearSegmentedColormap.from_list("rival_america", RAMPA_RIVAL[:0:-1] + [NEUTRO] + RAMPA_MARINO[1:])
HALO = [pe.withStroke(linewidth=5.5, foreground=FONDO)]  # borde blanco para que la línea se lea sobre el calor
FUENTES = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def aplicar_estilo():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": FUENTES,
        "text.color": TINTA, "axes.labelcolor": TINTA, "xtick.color": TINTA_SUAVE, "ytick.color": TINTA_SUAVE,
        "figure.facecolor": FONDO, "axes.facecolor": FONDO, "savefig.facecolor": FONDO,
        "legend.frameon": False,
    })


def luminancia(color):
    canal = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in to_rgb(color)]
    return 0.2126 * canal[0] + 0.7152 * canal[1] + 0.0722 * canal[2]


def texto_sobre(color):
    # Blanco o tinta, el que contraste más con el color de fondo
    lum = luminancia(color)
    return FONDO if 1.05 / (lum + 0.05) >= (lum + 0.05) / (luminancia(TINTA) + 0.05) else TINTA


def area_xg(xg):
    # Área del punto proporcional al xG del tiro, a la escala de estas canchas chicas
    return np.nan_to_num(np.asarray(xg, dtype=float)) * 300 + 8


def buscar(nombres):
    for carpeta in CARPETAS:
        for nombre in nombres:
            ruta = carpeta / nombre
            if ruta.is_file():
                return ruta
    sys.exit(f"No encuentro {nombres} en: {[str(c) for c in CARPETAS]}")


def leer(nombres, columnas):
    ruta = buscar(nombres)
    faltan = [c for c in columnas if c not in pq.read_schema(ruta).names]
    if faltan:
        sys.exit(f"A {ruta.name} le faltan columnas: {faltan}.")
    return pd.read_parquet(ruta, columns=columnas)


def leer_datos():
    # Eventos con su score_state y partidos con localía, tercil del rival y minutos por estado del marcador
    e = leer(BUSCAR_EVENTOS, COLUMNAS_EVENTOS)
    ctx = leer(BUSCAR_CONTEXTO_EVENTOS, ["match_id", "index", "score_state"])
    partidos = leer(BUSCAR_CONTEXTO_PARTIDOS, COLUMNAS_PARTIDOS)
    for tabla in (e, ctx, partidos):
        tabla["match_id"] = tabla["match_id"].astype("int64")
    for tabla in (e, ctx):
        tabla["index"] = tabla["index"].astype("int64")
    e["es_equipo_analizado"] = e["es_equipo_analizado"].fillna(False).astype(bool)
    e = e.merge(ctx, on=["match_id", "index"], how="left", validate="one_to_one")
    # Sin la tanda de penales (score_state nulo) y sin tiros de penal, igual que el xG del reporte
    e = e[e["period"] < 5]
    e = e[~((e["type_name"] == "Shot") & (e["shot_type_name"] == "Penalty"))]
    e["score_state"] = e["score_state"].astype(str)
    partidos = partidos.drop_duplicates("match_id").set_index("match_id")
    partidos["minutos"] = partidos[["minutos_perdiendo", "minutos_empatando", "minutos_ganando"]].sum(axis=1)
    faltan = set(e["match_id"]) - set(partidos.index)
    if faltan:
        sys.exit(f"Hay {len(faltan)} partidos en los eventos que no están en contexto_partidos.")
    return e, partidos


def metricas(E, minutos):
    am = E["es_equipo_analizado"]
    pase = E["type_name"] == "Pass"
    tiro = E["type_name"] == "Shot"
    xg = E["shot_statsbomb_xg"].fillna(0)
    recupera = E["type_name"].isin(ACCIONES_RECUPERA) & am & E["x_eq"].notna()
    d90 = minutos / 90
    return {
        "pases_am": (pase & am).sum() / pase.sum() if pase.sum() else np.nan,
        "xg_favor": xg[tiro & am].sum() / d90 if d90 > 0 else np.nan,
        "xg_contra": xg[tiro & ~am].sum() / d90 if d90 > 0 else np.nan,
        "altura": E.loc[recupera, "x_eq"].mean(),
    }


def territorio(E, pitch):
    # Parte de los pases de cada tercio de cancha que son del América
    p = E[E["type_name"] == "Pass"].dropna(subset=["x_eq", "y_eq"])
    propio = p["es_equipo_analizado"]
    s_am = pitch.bin_statistic(p.loc[propio, "x_eq"], p.loc[propio, "y_eq"], statistic="count", bins=BINS_TERRITORIO)
    total = pitch.bin_statistic(p["x_eq"], p["y_eq"], statistic="count", bins=BINS_TERRITORIO)["statistic"]
    s_am["statistic"] = np.where(total > 0, s_am["statistic"] / np.where(total > 0, total, 1), np.nan)
    return s_am


def calor(E, pitch):
    # Parte de las acciones defensivas del América (en ese nivel) que cae en cada zona
    d = E[E["es_equipo_analizado"] & E["type_name"].isin(ACCIONES_CALOR)].dropna(subset=["x_eq", "y_eq"])
    return pitch.bin_statistic(d["x_eq"], d["y_eq"], statistic="count", bins=BINS_CALOR, normalize=True)


def caja(ax, x, y, titulo, valor, color):
    ax.text(x, y, f"{titulo}\n{valor}", ha="center", va="center", fontsize=13, fontweight="bold", color=FONDO,
            zorder=6, linespacing=1.25, bbox=dict(boxstyle="round,pad=0.4", fc=color, ec="none", alpha=0.95))


def porterias(ax):
    ax.text(-1.5, 40, "Portería del América", rotation=90, ha="right", va="center", fontsize=12.5, color=TINTA_SUAVE)
    ax.text(121.5, 40, "Portería del rival", rotation=270, ha="left", va="center", fontsize=12.5, color=TINTA_SUAVE)


def titulo_panel(ax, texto):
    ax.set_title(texto, fontsize=14, color=TINTA, pad=6)


def dibujar_columna(axs, pitch, E, minutos, ref_altura, norma_calor):
    m = metricas(E, minutos)
    ax1, ax2, ax3 = axs
    for ax in axs:
        pitch.draw(ax=ax)
        porterias(ax)

    # 1. Territorio
    t = territorio(E, pitch)
    norma = Normalize(0.2, 0.8)
    pitch.heatmap(t, ax=ax1, cmap=CMAP_DIVERGENTE, norm=norma, edgecolors=FONDO, linewidth=2, zorder=1)
    for cx, cy, v in zip(t["cx"].ravel(), t["cy"].ravel(), t["statistic"].ravel()):
        if not np.isnan(v):
            ax1.text(cx, cy, f"{v:.0%}", ha="center", va="center", fontsize=22, fontweight="bold", zorder=3,
                     color=texto_sobre(CMAP_DIVERGENTE(norma(v))))
    titulo_panel(ax1, f"El América da el {m['pases_am']:.0%} de los pases")

    # 2. Peligro: cada equipo con su color; el gol relleno y con borde, como en 3_tiros_ataque y 4_tiros_defensa
    tiros = E[E["type_name"] == "Shot"].dropna(subset=["x_eq", "y_eq"])
    for propio, color, borde_gol in ((False, RIVAL, FONDO), (True, MARINO, AMARILLO)):
        s = tiros[tiros["es_equipo_analizado"] == propio]
        gol = s["shot_outcome_name"] == "Goal"
        pitch.scatter(s.loc[~gol, "x_eq"], s.loc[~gol, "y_eq"], s=area_xg(s.loc[~gol, "shot_statsbomb_xg"]),
                      facecolors="none", edgecolors=color, linewidths=0.7, alpha=0.5, ax=ax2, zorder=2)
        pitch.scatter(s.loc[gol, "x_eq"], s.loc[gol, "y_eq"], s=area_xg(s.loc[gol, "shot_statsbomb_xg"]),
                      color=color, edgecolors=borde_gol, linewidths=1, ax=ax2, zorder=4)
    caja(ax2, 42, 40, "en contra", f"{m['xg_contra']:.2f}", RIVAL)
    caja(ax2, 78, 40, "a favor", f"{m['xg_favor']:.2f}", MARINO)
    titulo_panel(ax2, "xG por 90 minutos")

    # 3. Presión: calor de acciones defensivas y altura media de recuperación
    pitch.heatmap(calor(E, pitch), ax=ax3, cmap=CMAP_MARINO, norm=norma_calor, edgecolors=FONDO, linewidth=1,
                  zorder=1)
    ax3.plot([ref_altura, ref_altura], [0, 80], color=TINTA_SUAVE, ls=":", lw=2.4, zorder=6)
    ax3.plot([m["altura"], m["altura"]], [0, 80], color=MARINO, lw=2.8, zorder=5, path_effects=HALO)
    titulo_panel(ax3, f"Recupera a {m['altura']:.0f} yardas de su portería")


def columna_sin_datos(axs, pitch, n_partidos, minutos):
    # Cancha vacía con el aviso, para no dibujar un nivel con muy pocos datos
    for ax in axs:
        pitch.draw(ax=ax)
        ax.text(60, 40, f"Pocos datos\n{n_partidos} partidos · {minutos:,.0f} min", ha="center", va="center",
                fontsize=15, color=TINTA_SUAVE, linespacing=1.5, zorder=6,
                bbox=dict(boxstyle="round,pad=0.6", fc=NEUTRO, ec="none"))
    titulo_panel(axs[0], f"No se dibuja: pide {MIN_PARTIDOS} partidos y {MIN_MINUTOS} min")


def leyendas(fig, axs_leyenda, norma_calor, texto_ref):
    # Una columna a la derecha explica cada fila: qué mide, colores, tamaños y líneas
    texto = dict(fontsize=13, color=TINTA, ha="left", va="top", linespacing=1.35)
    titulo = dict(fontsize=14.5, fontweight="bold", color=TINTA, ha="left", va="top")
    a1, a2, a3 = axs_leyenda
    for ax in axs_leyenda:
        ax.axis("off")

    a1.text(0, 1, "1. Territorio", transform=a1.transAxes, **titulo)
    a1.text(0, 0.87, "% de los pases dados en\ncada tercio que son\ndel América", transform=a1.transAxes, **texto)
    barra = fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0.2, 0.8), cmap=CMAP_DIVERGENTE),
                         cax=a1.inset_axes([0, 0.3, 0.9, 0.08]), orientation="horizontal", ticks=[0.2, 0.5, 0.8])
    barra.outline.set_visible(False)
    barra.ax.set_xticklabels(["20%", "50%", "80%"])
    barra.ax.tick_params(length=0, labelsize=13, labelcolor=TINTA_SUAVE)
    a1.text(0, 0.16, "Más del rival", transform=a1.transAxes, fontsize=13, color=TINTA, ha="left", va="top")
    a1.text(0.9, 0.05, "Más del América", transform=a1.transAxes, fontsize=13, color=TINTA, ha="right", va="top")

    a2.text(0, 1, "2. Peligro", transform=a2.transAxes, **titulo)
    a2.text(0, 0.87, "Tiros;\ntamaño = xG", transform=a2.transAxes, **texto)
    marcas = [Line2D([], [], marker="o", ls="", ms=10, mfc="none", mec=MARINO, label="Tiro del América"),
              Line2D([], [], marker="o", ls="", ms=10, mfc=MARINO, mec=AMARILLO, mew=1.5, label="Gol del América"),
              Line2D([], [], marker="o", ls="", ms=10, mfc="none", mec=RIVAL, label="Tiro del rival"),
              Line2D([], [], marker="o", ls="", ms=10, mfc=RIVAL, mec=FONDO, mew=1.5, label="Gol del rival")]
    marcas += [Line2D([], [], marker="o", ls="", ms=np.sqrt(area_xg(v)), mfc="none", mec=TINTA_SUAVE,
                      label=f"{v} xG") for v in (0.05, 0.3, 0.6)]
    a2.legend(handles=marcas, loc="upper left", bbox_to_anchor=(-0.04, 0.66), fontsize=13, ncol=1,
              handletextpad=0.4, labelspacing=0.45, borderaxespad=0)

    a3.text(0, 1, "3. Presión", transform=a3.transAxes, **titulo)
    a3.text(0, 0.87, "% de las acciones\ndefensivas del América\nen cada zona", transform=a3.transAxes, **texto)
    barra = fig.colorbar(plt.cm.ScalarMappable(norm=norma_calor, cmap=CMAP_MARINO),
                         cax=a3.inset_axes([0, 0.47, 0.9, 0.08]), orientation="horizontal")
    barra.outline.set_visible(False)
    barra.ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    barra.ax.locator_params(nbins=3)
    barra.ax.tick_params(length=0, labelsize=13, labelcolor=TINTA_SUAVE)
    lineas = [Line2D([], [], color=MARINO, lw=2.8, label="Altura media donde\nrecupera el balón"),
              Line2D([], [], color=TINTA_SUAVE, lw=2.4, ls=":", label=texto_ref)]
    a3.legend(handles=lineas, loc="upper left", bbox_to_anchor=(-0.04, 0.3), fontsize=13, handlelength=1.8,
              labelspacing=0.7, borderaxespad=0)


def suficiente(n_partidos, minutos):
    return n_partidos >= MIN_PARTIDOS and minutos >= MIN_MINUTOS


def figura(columnas, titulo_figura, subtitulo, carpeta, nombre, ref_altura, texto_ref):
    # columnas: lista de (nombre, detalle, eventos, minutos, partidos)
    aplicar_estilo()
    pitch = Pitch(pitch_type="statsbomb", line_color=LINEA_CANCHA, line_zorder=2, pad_left=6, pad_right=6)
    n = len(columnas)
    # Misma escala del calor en todas las columnas dibujadas de la figura
    norma_calor = Normalize(0, max(np.nanmax(calor(E, pitch)["statistic"]) for _, _, E, minutos, n_p in columnas
                                   if suficiente(n_p, minutos)))
    fig, axs = plt.subplots(3, n + 1, figsize=(4.9 * n + 2.9, 13.6), squeeze=False,
                            gridspec_kw={"width_ratios": [1] * n + [0.56]})
    fig.subplots_adjust(top=0.83, bottom=0.01, left=0.01, right=0.99, hspace=0.3, wspace=0.12)
    fig.text(0.01, 0.995, titulo_figura, ha="left", va="top", fontsize=19, fontweight="bold", color=TINTA)
    fig.text(0.01, 0.955, subtitulo, ha="left", va="top", fontsize=13, color=TINTA_SUAVE, linespacing=1.4)
    for j, (nombre_col, detalle, E, minutos, n_partidos) in enumerate(columnas):
        if suficiente(n_partidos, minutos):
            dibujar_columna(axs[:, j], pitch, E, minutos, ref_altura, norma_calor)
        else:
            columna_sin_datos(axs[:, j], pitch, n_partidos, minutos)
        axs[0, j].annotate(detalle, xy=(0.5, 1), xycoords="axes fraction", xytext=(0, 30), textcoords="offset points",
                           ha="center", va="bottom", fontsize=13, color=TINTA_SUAVE)
        axs[0, j].annotate(nombre_col, xy=(0.5, 1), xycoords="axes fraction", xytext=(0, 48),
                           textcoords="offset points", ha="center", va="bottom", fontsize=17, fontweight="bold",
                           color=TINTA)
    leyendas(fig, axs[:, n], norma_calor, texto_ref)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    fig.savefig(ruta, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Guardado:", ruta)


def figuras_contexto(e, partidos, carpeta, torneo, base, ref, texto_ref):
    # Las 3 figuras de un conjunto de partidos: los 91 (torneo = None) o los de un torneo
    sufijo = f" · {torneo}" if torneo else ""
    etiqueta = torneo or "91 partidos"

    # Marcador: cada columna usa solo los eventos y los minutos jugados con ese marcador
    cols = []
    for estado, nombre in (("perdiendo", "Perdiendo"), ("empatando", "Empatando"), ("ganando", "Ganando")):
        minutos = partidos[f"minutos_{estado}"]
        n_p = int((minutos > 0).sum())
        cols.append((nombre, f"{minutos.sum():,.0f} min en {n_p} partidos", e[e["score_state"] == estado],
                     minutos.sum(), n_p))
        print(f"{etiqueta} · marcador {estado}: {n_p} partidos, {minutos.sum():,.0f} min")
    figura(cols, f"El América según el marcador{sufijo}",
           f"{base}\nCada columna usa solo los minutos jugados con ese marcador (el marcador antes de cada jugada)",
           carpeta, "contexto_cancha_marcador.png", ref, texto_ref)

    # Localía
    cols = []
    for es_local, nombre in ((True, "Local"), (False, "Visitante")):
        ms = partidos.index[partidos["is_home"].astype(bool) == es_local]
        minutos = partidos.loc[ms, "minutos"].sum()
        cols.append((nombre, f"{len(ms)} partidos · {minutos:,.0f} min", e[e["match_id"].isin(ms)], minutos, len(ms)))
        print(f"{etiqueta} · localía {nombre}: {len(ms)} partidos, {minutos:,.0f} min")
    figura(cols, f"El América de local y de visitante{sufijo}", f"{base}\nPartidos completos",
           carpeta, "contexto_cancha_localia.png", ref, texto_ref)

    # Rival
    cols = []
    for tercil in ("débil", "medio", "fuerte"):
        ms = partidos.index[partidos["rival_strength_tercil"].astype(str) == tercil]
        minutos = partidos.loc[ms, "minutos"].sum()
        cols.append((f"Rival {tercil}", f"{len(ms)} partidos · {minutos:,.0f} min", e[e["match_id"].isin(ms)],
                     minutos, len(ms)))
        print(f"{etiqueta} · rival {tercil}: {len(ms)} partidos, {minutos:,.0f} min")
    figura(cols, f"El América según la fuerza del rival{sufijo}",
           f"{base}\nFuerza del rival: tercio de su torneo según su diferencia de xG por partido",
           carpeta, "contexto_cancha_rival.png", ref, texto_ref)


def main():
    global CARPETA_SALIDA
    argumentos = sys.argv[1:]
    if "--salida" in argumentos:
        i = argumentos.index("--salida")
        if i + 1 >= len(argumentos):
            sys.exit("Falta la carpeta después de --salida.")
        CARPETA_SALIDA = Path(argumentos[i + 1]).resolve()

    e, partidos = leer_datos()
    # La referencia de la fila 3 es siempre la de los 91 partidos, también en las figuras por torneo
    ref = metricas(e, partidos["minutos"].sum())["altura"]
    ataque = "El América ataca de izquierda a derecha"

    figuras_contexto(e, partidos, CARPETA_SALIDA, None,
                     f"{e['match_id'].nunique()} partidos (Apertura 2023 a Clausura 2025) · {ataque}", ref,
                     f"Promedio de los\n91 partidos ({ref:.0f} yd)")
    for torneo in TORNEOS:
        p_t = partidos[partidos["torneo"].astype(str) == torneo]
        if p_t.empty:
            print(f"Aviso: no hay partidos del torneo '{torneo}'.")
            continue
        figuras_contexto(e[e["match_id"].isin(p_t.index)], p_t, CARPETA_SALIDA / torneo, torneo,
                         f"{torneo} · {len(p_t)} partidos · {ataque}", ref,
                         f"Promedio de los 91\npartidos, no solo\nde este torneo ({ref:.0f} yd)")


if __name__ == "__main__":
    main()
