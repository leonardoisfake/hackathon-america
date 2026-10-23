"""Reporte en PDF (fase 5): imprime el HTML del reporte con Chrome sin interfaz, con el mismo formato.

Uso:
    python scripts/06_reporte_pdf.py              # reporte/reporte_jardine_america.html -> .pdf
    python scripts/06_reporte_pdf.py --entrega    # ademas copia el HTML y el PDF a entrega/
    python scripts/06_reporte_pdf.py --chrome "C:/ruta/a/chrome.exe"

Va despues de 05_reporte_html.py. Las paginas miden lo que dice el CSS de impresion del HTML (@page, 1280 x 1810
px: ancho de escritorio con proporcion A4), asi que el PDF se ve como el HTML en pantalla. Chrome imprime una copia
temporal del HTML sin carga diferida de imagenes, para que entren todas, y espera a que carguen las fuentes de
Google Fonts. Al final dice cuantas paginas tiene el PDF, cuanto pesa y si los titulos salieron con Big Shoulders
Display (si no, con la fuente de respaldo, y lo avisa).

Codigos de salida: 0 si escribio el PDF; 1 si falta el HTML, no encuentra Chrome o Chrome no genero el PDF.
"""
import argparse
import base64
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HTML = "reporte/reporte_jardine_america.html"
ENTREGA = "entrega"
ESPERA_MS = 20000  # tiempo virtual para que carguen fuentes e imagenes antes de imprimir
FUENTE_TITULOS = b"Big-Shoulders-Display"  # asi nombra Chrome la fuente de los titulos dentro del PDF
CALIDAD_JPEG = 82  # solo en el PDF: Chrome guarda los WebP sin perdida y el PDF pasaria de 30 MB
DATA_WEBP = re.compile(r"data:image/webp;base64,([A-Za-z0-9+/=]+)")
CHROME_RUTAS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def ruta_repo(valor):
    # Ruta absoluta tal cual; relativa, desde la raiz del repo.
    p = Path(valor)
    return p if p.is_absolute() else (ROOT / p).resolve()


def buscar_chrome(dada):
    if dada:
        return Path(dada) if Path(dada).is_file() else None
    en_path = shutil.which("chrome") or shutil.which("google-chrome")
    candidatas = ([en_path] if en_path else []) + CHROME_RUTAS
    return next((Path(c) for c in candidatas if c and Path(c).is_file()), None)


def a_jpeg(m):
    # Imagen opaca de WebP a JPEG, que Chrome pasa al PDF tal cual; con transparencia (logos, foto) se queda igual.
    datos = base64.b64decode(m.group(1))
    with Image.open(io.BytesIO(datos)) as im:
        if im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getextrema()[3][0] < 255:
            return m.group(0)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=CALIDAD_JPEG, optimize=True)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def copia_para_imprimir(html, carpeta):
    # Copia del HTML para imprimir: sin loading="lazy" (una imagen diferida puede no cargar) y figuras en JPEG.
    texto = html.read_text(encoding="utf-8").replace(' loading="lazy"', "")
    tmp = carpeta / "reporte_para_pdf.html"
    tmp.write_text(DATA_WEBP.sub(a_jpeg, texto), encoding="utf-8")
    return tmp


def imprimir(chrome, html, pdf, perfil):
    args = ["--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer", "--hide-scrollbars",
            f"--virtual-time-budget={ESPERA_MS}", "--run-all-compositor-stages-before-draw",
            f"--user-data-dir={perfil}", f"--print-to-pdf={pdf}", html.as_uri()]
    if os.name == "nt":
        # en Windows, Chrome lanzado desde Python no escribe el PDF; con Start-Process de PowerShell si
        lista = ",".join("'" + ('"' + a + '"').replace("'", "''") + "'" for a in args)
        orden = ["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath '{chrome}' -ArgumentList {lista} -Wait"]
    else:
        orden = [str(chrome)] + args
    res = subprocess.run(orden, capture_output=True, text=True, timeout=300)
    for _ in range(90):  # Chrome puede regresar antes de terminar de escribir
        if pdf.exists() and pdf.stat().st_size > 0:
            time.sleep(1)
            break
        time.sleep(1)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--html", default=HTML, help=f"HTML del reporte (por defecto {HTML})")
    p.add_argument("--salida", default=None, help="PDF de salida (por defecto, el HTML con extension .pdf)")
    p.add_argument("--chrome", default=None, help="ruta a chrome.exe (por defecto la busca en las rutas habituales)")
    p.add_argument("--entrega", action="store_true", help=f"copia el HTML y el PDF a {ENTREGA}/ en la raiz del repo")
    args = p.parse_args()

    html = ruta_repo(args.html)
    pdf = ruta_repo(args.salida) if args.salida else html.with_suffix(".pdf")
    if not html.is_file():
        print(f"ERROR: no existe {html}; corre antes scripts/05_reporte_html.py.", file=sys.stderr)
        return 1
    chrome = buscar_chrome(args.chrome)
    if chrome is None:
        print("ERROR: no se encontro Chrome; pasa la ruta con --chrome.", file=sys.stderr)
        return 1

    inicio = time.perf_counter()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    nuevo = pdf.with_name(pdf.stem + ".tmp.pdf")
    nuevo.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tmp_06_pdf_", dir=html.parent) as carpeta:
        carpeta = Path(carpeta)
        res = imprimir(chrome, copia_para_imprimir(html, carpeta), nuevo, carpeta / "perfil")
        if not nuevo.exists() or nuevo.stat().st_size == 0:
            print(f"ERROR: Chrome no genero el PDF (codigo {res.returncode}).\n{res.stderr[-1500:]}", file=sys.stderr)
            return 1
        time.sleep(1)  # Chrome suelta el perfil antes de borrar la carpeta temporal
    os.replace(nuevo, pdf)

    datos = pdf.read_bytes()
    paginas = len(re.findall(rb"/Type\s*/Page(?![s\w])", datos))
    try:
        mostrar = pdf.relative_to(ROOT).as_posix()
    except ValueError:
        mostrar = str(pdf)
    print(f"Escrito en {mostrar}: {paginas} paginas, {len(datos) / 1024 ** 2:.2f} MB. "
          f"{time.perf_counter() - inicio:.1f} s")
    if FUENTE_TITULOS in datos:
        print("[OK] los titulos salieron con Big Shoulders Display")
    else:
        print("AVISO: el PDF no trae Big Shoulders Display (sin internet salen con la fuente de respaldo)")

    if args.entrega:
        destino = ROOT / ENTREGA
        destino.mkdir(exist_ok=True)
        for f in (html, pdf):
            shutil.copy2(f, destino / f.name)
        print(f"Copiados a {ENTREGA}/: {html.name} ({html.stat().st_size / 1024 ** 2:.2f} MB) y {pdf.name} "
              f"({pdf.stat().st_size / 1024 ** 2:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
