"""Las métricas de contexto del América (posesión, xG, PPDA, altura de recuperación) dibujadas en la cancha.

Uso:  python contexto_cancha.py

Por cada torneo guarda 3 imágenes en CARPETA_SALIDA/<torneo>/ (las mismas carpetas de las demás gráficas):
    contexto_cancha_marcador.png   perdiendo / empatando / ganando
    contexto_cancha_localia.png    local / visitante   (necesita partidos.parquet con es_local)
    contexto_cancha_rival.png      rivales difíciles / intermedios / fáciles (por su posición en la tabla)

Cada imagen tiene 3 filas de canchas, el América ataca de izquierda a derecha:
    1. Territorio: % de los pases de cada zona que son del América (azul = domina el América, dorado = el rival)
    2. Peligro: tiros de ambos equipos, tamaño = xG (los del rival se ven en la portería del América)
    3. Presión: mapa de calor de sus acciones defensivas y una línea con la altura media de recuperación

Entradas (junto al script, en la carpeta actual, o en data/interim y data/processed):
    eventos_parquet    tabla limpia 'eventos' (obligatoria)
    partidos.parquet   tabla 'partidos' con match_id y es_local (si falta, se omite la imagen de localía)
    team_match_stats_liga.parquet  resultados de toda la liga; arma la tabla de posiciones para clasificar a los rivales
                                   (si falta, los rivales se agrupan por la diferencia de xG del América contra ellos)
"""
import sys
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from mplsoccer import Pitch

AQUI = Path(__file__).resolve().parent
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = Path(r"C:\Users\pablo\modelo_ame_final\graficas")
BUSCAR_EVENTOS = ["eventos_parquet", "eventos.parquet"]
BUSCAR_LIGA = ["team_match_stats_liga.parquet", "team_match_stats_liga", "team_match_stats_liga_1.parquet"]
BUSCAR_PARTIDOS = ["partidos.parquet", "partidos", "analitica_partidos.parquet"]
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "processed", AQUI / "data" / "raw" / "parquet"]

COLUMNAS_EVENTOS = ["match_id", "torneo", "period", "minute", "second", "type_name", "team_name", "es_equipo_analizado",
                    "x_eq", "y_eq", "duel_type_name", "shot_outcome_name", "shot_statsbomb_xg"]
ZONA_PRESION = 48  # x_eq >= 48: el 60% de campo más cercano a la portería del rival
ACCIONES_PRESION = ["Pressure", "Interception", "Foul Committed"]
ACCIONES_CALOR = ACCIONES_PRESION + ["Ball Recovery", "Duel"]
BINS = (3, 1)

# Para fijar tú los niveles de rival, llena este diccionario: {"Tigres UANL": "Fuertes", "Atlas": "Medios", ...}
# Las columnas salen en el orden en que aparecen los niveles. Si está vacío, los niveles se calculan solos.
NIVELES_MANUAL = {}

AZUL, ORO, ROJO = "#0F2A52", "#B8912B", "#d62728"
CMAP_TERRITORIO = LinearSegmentedColormap.from_list("territorio", [ORO, "#f4f1de", AZUL])
CMAP_CALOR = LinearSegmentedColormap.from_list("calor", ["#ffffff", "#fde0c5", "#f59e72", "#e8553a", "#c8302a", "#8f1d21"])


def buscar(nombres, obligatorio=True):
    for carpeta in CARPETAS:
        for nombre in nombres:
            ruta = carpeta / nombre
            if ruta.is_file():
                return ruta
    if obligatorio:
        sys.exit(f"No encuentro {nombres} en: {[str(c) for c in CARPETAS]}")
    return None


def leer_eventos():
    ruta = buscar(BUSCAR_EVENTOS)
    faltan = [c for c in COLUMNAS_EVENTOS if c not in pq.read_schema(ruta).names]
    if faltan:
        sys.exit(f"A {ruta.name} le faltan columnas: {faltan}. Este script espera la tabla limpia 'eventos'.")
    e = pd.read_parquet(ruta, columns=COLUMNAS_EVENTOS)
    e["match_id"] = e["match_id"].astype("int64")
    e["torneo"] = e["torneo"].astype(str)
    e["es_equipo_analizado"] = e["es_equipo_analizado"].fillna(False).astype(bool)
    return e


def leer_liga():
    # Resultados de todos los equipos de la liga: sirve para armar la tabla de posiciones de cada torneo
    ruta = buscar(BUSCAR_LIGA, obligatorio=False)
    cols = ["match_id", "team_name", "torneo", "fase", "team_match_gd"]
    if ruta is None or [c for c in cols if c not in pq.read_schema(ruta).names]:
        print("Aviso: no encontré team_match_stats_liga con torneo, fase y team_match_gd; los rivales se agruparán por "
              "la diferencia de xG del América contra ellos.")
        return None
    l = pd.read_parquet(ruta, columns=cols)
    l["torneo"] = l["torneo"].astype(str)
    return l[l["fase"].astype(str) == "regular"]


def tabla_posiciones(liga, torneo):
    # Tabla de la fase regular: 3 puntos por victoria, 1 por empate; desempata la diferencia de goles
    d = liga[liga["torneo"] == torneo].copy()
    d["pts"] = np.where(d["team_match_gd"] > 0, 3, np.where(d["team_match_gd"] == 0, 1, 0))
    t = d.groupby("team_name").agg(pts=("pts", "sum"), dg=("team_match_gd", "sum"))
    t = t.sort_values(["pts", "dg"], ascending=False)
    t["pos"] = np.arange(1, len(t) + 1)
    return t


def leer_localia():
    ruta = buscar(BUSCAR_PARTIDOS, obligatorio=False)
    if ruta is None or "es_local" not in pq.read_schema(ruta).names:
        print("Aviso: no encontré una tabla de partidos con 'es_local'; se omite la imagen de localía.")
        return None
    p = pd.read_parquet(ruta, columns=["match_id", "es_local"])
    p["match_id"] = p["match_id"].astype("int64")
    return p.drop_duplicates("match_id").set_index("match_id")["es_local"].astype(bool)


def preparar(eventos):
    # Eventos de tiempo reglamentario con el estado del marcador (-1 perdiendo, 0 empatando, 1 ganando) y los
    # segundos que cada partido pasa en cada estado
    e = eventos[eventos["period"].isin([1, 2])].copy()
    e["t"] = e["minute"] * 60 + e["second"]
    fin_p1 = e[e["period"] == 1].groupby("match_id")["t"].max()
    e["t"] = np.where(e["period"] == 1, e["t"], e["t"] - 45 * 60 + e["match_id"].map(fin_p1).fillna(45 * 60))
    duracion = e.groupby("match_id")["t"].max()
    gol = ((e["type_name"] == "Shot") & (e["shot_outcome_name"] == "Goal")) | (e["type_name"] == "Own Goal For")
    e["gol_am"] = gol & e["es_equipo_analizado"]
    e["gol_rv"] = gol & ~e["es_equipo_analizado"]
    e["estado"] = 0
    expo = []
    for m, idx in e.groupby("match_id").indices.items():
        sub = e.iloc[idx]
        goles = sub[sub["gol_am"] | sub["gol_rv"]].sort_values("t")
        gt = goles["t"].to_numpy()
        previo = np.concatenate([[0], np.cumsum(np.where(goles["gol_am"], 1, -1))])
        e.iloc[idx, e.columns.get_loc("estado")] = np.sign(previo[np.searchsorted(gt, sub["t"].to_numpy(), side="left")])
        for estado, seg in zip(np.sign(previo), np.diff(np.concatenate([[0], gt, [duracion[m]]]))):
            expo.append((m, int(estado), seg))
    expo = pd.DataFrame(expo, columns=["match_id", "estado", "seg"]).groupby(["match_id", "estado"], as_index=False).sum()
    rival = e[~e["es_equipo_analizado"]].dropna(subset=["team_name"]).groupby("match_id")["team_name"].first()
    return e, expo, rival


def metricas(E, segundos):
    # Mismas definiciones que en contexto_partido.py
    am = E["es_equipo_analizado"]
    pase = E["type_name"] == "Pass"
    tiro = E["type_name"] == "Shot"
    xg = E["shot_statsbomb_xg"].fillna(0)
    accion = E["type_name"].isin(ACCIONES_PRESION) | ((E["type_name"] == "Duel") & (E["duel_type_name"] == "Tackle"))
    en_zona = E["x_eq"] >= ZONA_PRESION
    recupera = E["type_name"].isin(["Ball Recovery", "Interception"]) & am & E["x_eq"].notna()
    d90 = segundos / 5400
    n_pases = pase.sum()
    pres = (accion & am & en_zona).sum()
    return {
        "posesion": (pase & am).sum() / n_pases * 100 if n_pases else np.nan,
        "xg_favor": xg[tiro & am].sum() / d90 if d90 > 0 else np.nan,
        "xg_contra": xg[tiro & ~am].sum() / d90 if d90 > 0 else np.nan,
        "ppda": (pase & ~am & en_zona).sum() / pres if pres else np.nan,
        "altura": E.loc[recupera, "x_eq"].mean(),
        "n_tiros": int((tiro & am).sum()), "n_goles": int((tiro & am & (E["shot_outcome_name"] == "Goal")).sum()),
    }


def territorio(E, pitch):
    # % de los pases de cada tercio de cancha que son del América
    p = E[(E["type_name"] == "Pass")].dropna(subset=["x_eq", "y_eq"])
    propio = p["es_equipo_analizado"]
    s_am = pitch.bin_statistic(p.loc[propio, "x_eq"], p.loc[propio, "y_eq"], statistic="count", bins=BINS)
    s_todo = pitch.bin_statistic(p["x_eq"], p["y_eq"], statistic="count", bins=BINS)
    total = s_todo["statistic"]
    s_am["statistic"] = np.where(total > 0, s_am["statistic"] / np.where(total > 0, total, 1), np.nan)
    return s_am


def caja(ax, x, y, titulo, valor, color):
    ax.text(x, y, f"{titulo}\n{valor}", ha="center", va="center", fontsize=15, fontweight="bold", color="white",
            zorder=6, bbox=dict(boxstyle="round,pad=0.45", fc=color, ec="none", alpha=0.95))


def dibujar_columna(axs, pitch, E, segundos, titulo, n_partidos, ref_altura):
    m = metricas(E, segundos)
    ax1, ax2, ax3 = axs
    for ax in axs:
        pitch.draw(ax=ax)
    if E.empty:
        for ax in axs:
            ax.text(60, 40, "sin datos", ha="center", va="center", fontsize=14, color="#777777")
        ax1.set_title(f"{titulo}\nsin datos", fontsize=13, fontweight="bold")
        return

    # 1. ¿Quién tiene el balón? (por tercios de cancha)
    t = territorio(E, pitch)
    pitch.heatmap(t, ax=ax1, cmap=CMAP_TERRITORIO, norm=TwoSlopeNorm(vcenter=0.5, vmin=0.2, vmax=0.8), edgecolors="white",
                  zorder=1, alpha=0.9)
    for cx, cy, v in zip(t["cx"].ravel(), t["cy"].ravel(), t["statistic"].ravel()):
        if not np.isnan(v):
            color = "white" if v > 0.68 else "black"
            ax1.text(cx, cy - 4, f"{v:.0%}", ha="center", va="center", fontsize=24, fontweight="bold", zorder=3,
                     color=color)
            ax1.text(cx, cy + 11, "de cada 100 pases\nen esta zona,\nson del América", ha="center", va="center",
                     fontsize=10, zorder=3, color=color)
    ax1.set_title(f"{titulo}\n{n_partidos} partidos\n¿Quién tiene el balón? América: {m['posesion']:.0f}%",
                  fontsize=13, fontweight="bold")

    # 2. ¿Cuánto peligro hay? (xG por 90 minutos)
    tiros = E[E["type_name"] == "Shot"].dropna(subset=["x_eq", "y_eq"])
    for propio, color in ((False, ORO), (True, AZUL)):
        s = tiros[tiros["es_equipo_analizado"] == propio]
        gol = s["shot_outcome_name"] == "Goal"
        pitch.scatter(s.loc[~gol, "x_eq"], s.loc[~gol, "y_eq"], s=22, color=color, alpha=0.3, ax=ax2, zorder=2)
        pitch.scatter(s.loc[gol, "x_eq"], s.loc[gol, "y_eq"], s=260, color=ROJO, edgecolors="black", marker="*",
                      ax=ax2, zorder=4)
    caja(ax2, 38, 40, "xG en contra", f"{m['xg_contra']:.2f}", ORO)
    caja(ax2, 82, 40, "xG a favor", f"{m['xg_favor']:.2f}", AZUL)
    ax2.set_title("¿Cuánto peligro hay? (xG por 90 min)", fontsize=13, fontweight="bold")

    # 3. ¿Dónde recupera el balón? (línea) y cuánto presiona (PPDA)
    ax3.fill_between([0, m["altura"]], [0, 0], [80, 80], color="#f3dcd8", alpha=0.8, zorder=0)
    ax3.axvline(ref_altura, color="#777777", ls=":", lw=2.2, zorder=3)
    ax3.axvline(m["altura"], color=AZUL, ls="--", lw=3.4, zorder=4)
    ax3.annotate("", xy=(m["altura"] + 14, 14), xytext=(m["altura"], 14), zorder=5,
                 arrowprops=dict(arrowstyle="-|>", color=AZUL, lw=2.5))
    ax3.text(m["altura"] + 2, 6, f"{m['altura']:.0f} yardas", fontsize=15, fontweight="bold", color=AZUL, va="center", zorder=6)
    caja(ax3, 96, 40, "PPDA", f"{m['ppda']:.1f}", AZUL)
    ax3.text(96, 55, "menos = presiona más", ha="center", va="center", fontsize=11, color="#333333", zorder=6)
    ax3.set_title(f"¿Dónde recupera el balón?\nA {m['altura']:.0f} yardas de su portería", fontsize=13, fontweight="bold")


def figura(columnas, titulo_figura, subtitulo, ruta_torneo, nombre, ref_altura, pie_columnas=None):
    # columnas: lista de (titulo, eventos, segundos, n_partidos)
    pitch = Pitch(pitch_type="statsbomb", line_color="#555555", line_zorder=2)
    fig, axs = plt.subplots(3, len(columnas), figsize=(6.4 * len(columnas) + 0.6, 15), squeeze=False)
    fig.subplots_adjust(top=0.865, bottom=0.09, hspace=0.32, wspace=0.08, left=0.02, right=0.98)
    fig.suptitle(titulo_figura, fontsize=22, fontweight="bold", y=0.985)
    fig.text(0.5, 0.935, subtitulo, ha="center", fontsize=12.5)
    for j, (titulo, E, segundos, n) in enumerate(columnas):
        dibujar_columna(axs[:, j], pitch, E, segundos, titulo, n, ref_altura)
        if pie_columnas and pie_columnas[j]:
            axs[2, j].text(0.5, -0.06, textwrap.fill(pie_columnas[j], 52), transform=axs[2, j].transAxes, ha="center",
                           va="top", fontsize=9, color="#555555")
    fig.text(0.5, 0.035,
             "Fila 1: de cada 100 pases dados en esa zona, cuántos son del América (azul = más del América, dorado = más del rival).   "
             "Fila 2: puntos = tiros (azul América, dorado rival), estrella = gol.\n"
             "Fila 3: línea azul = altura donde recupera el balón; línea gris punteada = promedio del torneo; "
             "zona rosa = campo que deja atrás. PPDA = pases del rival por cada acción de presión del América.",
             ha="center", va="center", fontsize=10.5, color="#444444")
    carpeta = CARPETA_SALIDA / ruta_torneo
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    fig.savefig(ruta, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Guardado:", ruta)


def segundos_de(expo, partidos, estado=None):
    d = expo[expo["match_id"].isin(partidos)]
    if estado is not None:
        d = d[d["estado"] == estado]
    return d["seg"].sum()


def niveles_rival(e, expo, rival, partidos, torneo, liga):
    # Devuelve ([(nombre del nivel, rivales, etiquetas)], explicación)
    rivales_torneo = sorted(set(rival.reindex(list(partidos)).dropna()))
    if NIVELES_MANUAL:
        niveles = list(dict.fromkeys(NIVELES_MANUAL.values()))
        return ([(n, [r for r, v in NIVELES_MANUAL.items() if v == n and r in rivales_torneo],
                  [r for r, v in NIVELES_MANUAL.items() if v == n and r in rivales_torneo]) for n in niveles],
                "Niveles de rival definidos a mano.")
    if liga is not None:
        tabla = tabla_posiciones(liga, torneo)
        orden = [r for r in tabla.index if r in rivales_torneo]  # de la parte alta a la baja de la tabla
        partes = [list(x) for x in np.array_split(orden, 3)]
        nombres = ["Rivales difíciles (parte alta de la tabla)", "Rivales intermedios (media tabla)",
                   "Rivales fáciles (parte baja de la tabla)"]
        return ([(n, rs, [f"{r} ({tabla.loc[r, 'pos']}°)" for r in rs]) for n, rs in zip(nombres, partes)],
                "Rivales agrupados por su posición en la tabla de la fase regular del torneo (entre paréntesis): "
                "el tercio de arriba son los difíciles y el de abajo los fáciles.")
    filas = []
    rs = rival.reindex(list(partidos)).dropna()
    for r, ms in rs.groupby(rs):
        sub = e[e["match_id"].isin(ms.index)]
        mt = metricas(sub, segundos_de(expo, ms.index))
        filas.append((r, mt["xg_favor"] - mt["xg_contra"]))
    orden = [r for r, _ in sorted(filas, key=lambda f: f[1])]
    nombres = ["Los que más le complican", "Intermedios", "Los que menos le complican"]
    return ([(n, list(x), list(x)) for n, x in zip(nombres, np.array_split(orden, 3))],
            "Rivales agrupados por la diferencia de xG que logra el América contra ellos; cada grupo es un tercio.")


def main():
    eventos = leer_eventos()
    equipo = eventos.loc[eventos["es_equipo_analizado"], "team_name"].iloc[0]
    local = leer_localia()
    liga = leer_liga()
    e, expo, rival = preparar(eventos)
    torneo_de = eventos.drop_duplicates("match_id").set_index("match_id")["torneo"]
    presentes = set(torneo_de)
    for t in set(TORNEOS) - presentes:
        print(f"Aviso: el torneo '{t}' no está en el archivo (encontrados: {sorted(presentes)})")
    torneos = [t for t in TORNEOS if t in presentes]
    if not torneos:
        sys.exit("Ningún torneo de la lista coincide con la columna torneo.")

    for t in torneos:
        partidos = torneo_de.index[torneo_de == t]
        et = e[e["match_id"].isin(partidos)]
        n = len(partidos)
        ref = metricas(et, segundos_de(expo, partidos))["altura"]

        # marcador
        cols = []
        for estado, nombre in ((-1, "Perdiendo"), (0, "Empatando"), (1, "Ganando")):
            sub = et[et["estado"] == estado]
            seg = segundos_de(expo, partidos, estado)
            n_est = expo[(expo["match_id"].isin(partidos)) & (expo["estado"] == estado) & (expo["seg"] > 0)]["match_id"].nunique()
            cols.append((f"{nombre} ({seg / 60 / n:.0f} min por partido)", sub, seg, n_est))
        figura(cols, f"{equipo} según el marcador - {t}",
               f"{n} partidos, tiempo reglamentario. Cada columna usa solo los minutos jugados en ese marcador. "
               "El América ataca de izquierda a derecha.", t, "contexto_cancha_marcador.png", ref)

        # localía
        if local is not None:
            cols = []
            for es_local, nombre in ((True, "Local"), (False, "Visitante")):
                ms = [m for m in partidos if m in local.index and bool(local[m]) == es_local]
                sub = et[et["match_id"].isin(ms)]
                cols.append((nombre, sub, segundos_de(expo, ms), len(ms)))
            figura(cols, f"{equipo} de local y de visitante - {t}",
                   f"{n} partidos, tiempo reglamentario. El América ataca de izquierda a derecha.", t,
                   "contexto_cancha_localia.png", ref)

        # rival
        cols, pies = [], []
        niveles, explicacion = niveles_rival(e, expo, rival, partidos, t, liga)
        for nombre, rivales, etiquetas in niveles:
            ms = [m for m in partidos if rival.get(m) in rivales]
            sub = et[et["match_id"].isin(ms)]
            cols.append((nombre, sub, segundos_de(expo, ms), len(ms)))
            pies.append(", ".join(etiquetas))
        figura(cols, f"{equipo} según el rival - {t}", f"{n} partidos. {explicacion}", t,
               "contexto_cancha_rival.png", ref, pies)


if __name__ == "__main__":
    main()