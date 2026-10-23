# Análisis táctico de André Jardine en el Club América

Análisis táctico de André Jardine como entrenador del Club América, del Apertura 2023 al Clausura 2025. Cubre 91 partidos (66 de fase regular y 25 de liguilla) con datos de eventos y 360 de Hudl StatsBomb. Es la entrega del equipo al Hackathon ITAM + Club América.

La pregunta del reto: ¿qué principios definen al equipo en ofensiva y en defensa, cómo se mantienen a lo largo del tiempo y cómo ajusta Jardine según el rival, el marcador, la localía o el minuto?

## Contenido

- [Resultado](#resultado)
- [Estructura del repo](#estructura-del-repo)
- [Cómo correr el pipeline](#cómo-correr-el-pipeline)
- [Datos](#datos)
- [Equipo y licencia](#equipo-y-licencia)

## Resultado

El reporte está en la carpeta `entrega/`:

- `entrega/reporte_jardine_america.html`: versión interactiva, con pestañas por temporada. También se puede abrir en línea: https://leonardoisfake.github.io/hackathon-america/entrega/reporte_jardine_america.html
- `entrega/reporte_jardine_america.pdf`: versión en PDF.

## Estructura del repo

| Ruta | Qué hay |
| :--- | :--- |
| `sb_api.py` | Acceso a la API de StatsBomb con caché local. |
| `scripts/` | Los scripts del pipeline, numerados por fase (`01_descarga.py` a `06_reporte_pdf.py`), más `graficas.py`, `Cambio_Partidos.py`, `contrato.py`, `gen_contrato.py`, `control_calidad.py` y `gen_reporte_nulos.py`. |
| `scripts/*.md` | Framework analítico: `README.md`, `01_definiciones_y_supuestos.md`, `02_restricciones_y_riesgos.md`, `03_decisiones_de_limpieza.md`, `04_jugadores.md` y `05_metricas_finales.md`. |
| `docs/contrato/` | Contrato de datos: columnas, tipos y reglas de cada tabla. |
| `docs/` | Especificaciones por fase (`spec_01`, `spec_03_contexto`, `spec_03_defensa`, `spec_03_tabla_analitica`, `spec_04_contexto`, `spec_05_reporte_html`), `reporte_textos/` e `inventario_descarga.md`. |
| `especificaciones_metricas/` | Fichas de las métricas. |
| `AGENTS.md` | Contexto del repo, reglas de trabajo y detalle de cada script. |
| `requirements.txt` | Dependencias de Python. |
| `LICENSE` | Licencia MIT. |

## Cómo correr el pipeline

Corre todo desde la raíz del repo. El detalle de argumentos, salidas y códigos de salida de cada fase está en `AGENTS.md`, sección «Cómo correr el pipeline».

1. Instala las dependencias:

   ```
   pip install -r requirements.txt
   ```

2. Crea un archivo `.env` en la raíz con tus credenciales de StatsBomb. No se sube al repo.

   ```
   SB_USER=...
   SB_PASS=...
   ```

3. Descarga y limpieza:

   ```
   python scripts/01_descarga.py
   python scripts/02_limpieza.py
   python scripts/02_auxiliares.py
   ```

4. Contexto y métricas. Los tres scripts `03_` de ataque, defensa y jugadores van en cualquier orden entre ellos:

   ```
   python scripts/03_contexto.py
   python scripts/03_ataque.py
   python scripts/03_defensa.py
   python scripts/03_jugadores.py
   python scripts/03_tabla_analitica.py
   python scripts/04_contexto.py
   python scripts/04_patrones.py
   ```

5. Gráficas. `--salida` indica la carpeta donde se guardan las figuras:

   ```
   python scripts/graficas.py --salida <carpeta>
   python scripts/Cambio_Partidos.py --salida <carpeta>
   ```

6. Reporte. `--figuras` apunta a la carpeta del paso anterior. El PDF se imprime del HTML con Chrome, y `--entrega` copia los dos a `entrega/`. El detalle de este paso está en `docs/spec_05_reporte_html.md`.

   ```
   python scripts/05_reporte_html.py --figuras <carpeta>
   python scripts/06_reporte_pdf.py --entrega
   ```

## Datos

Los datos de StatsBomb no se publican y no están en el repo: `data/` está en `.gitignore`. Para reproducir el análisis hacen falta credenciales propias de StatsBomb. Al repo y al reporte solo llegan resultados agregados.

## Equipo y licencia

Facultad de Ingeniería, UNAM:

- Leonardo Alan Lee Robles
- Patricio Alfaro Domínguez
- Pablo Abad Gonzalez
- Yordi Josue Jiménez Ayala

Licencia MIT. Ver `LICENSE`.
