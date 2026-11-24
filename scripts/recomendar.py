"""Recomendador Interlub desde la terminal.

Recibe el JSON que devolvió la IA al extraer una ficha técnica en PDF (ver scripts/prompts/extraccion_pdfs.md)
y muestra los productos Interlub que mejor encajan, con el porqué y una tabla de comparación.

Uso (desde la raíz del repo):
    uv run python scripts/recomendar.py data/processed/ficha.json                  # lista los productos del JSON
    uv run python scripts/recomendar.py data/processed/ficha.json -p "ULTRAPLEX MCS 2"
    uv run python scripts/recomendar.py data/processed/ficha.json --todos -k 3     # todos los productos vigentes
    uv run python scripts/recomendar.py ficha.json -p "X" --texto --guardar        # + embeddings, guarda CSV

Opciones:
    -p / --producto   nombre_producto a usar como consulta (si no se da y hay uno solo, usa ese)
    --todos           recomienda para todos los productos vigentes del JSON
    -k                cuántas recomendaciones (default 5)
    --interlub        ruta a DATOS_TEC_clean.csv (default data/processed/DATOS_TEC_clean.csv)
    --texto           agrega la similitud de texto (necesita data/processed/embeddings.npz de 02_pdfs.ipynb)
    --peso-texto      peso de la similitud de texto en el puntaje (default 0: solo informativa)
    --guardar         guarda las recomendaciones en reports/recomendaciones_<producto>.csv
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import fichas_pdf as F  # noqa: E402
import recomendador as R  # noqa: E402

INTERLUB = RAIZ / "data/processed/DATOS_TEC_clean.csv"
EMB = RAIZ / "data/processed/embeddings.npz"
REPORTES = RAIZ / "reports"


def cargar_fichas(ruta_json):
    """Lee el JSON de la IA (lista de objetos o un solo objeto) y lo normaliza al esquema de DATOS_TEC."""
    with open(ruta_json, encoding="utf-8") as f:
        registros = json.load(f)
    if isinstance(registros, dict):  # la IA a veces devuelve un solo objeto en vez de una lista
        registros = [registros]
    return F.normalizar(registros)


def elegir(fichas, producto=None, todos=False):
    """Fichas a usar como consulta: la indicada, todas las vigentes o la única que haya."""
    if todos:
        return fichas[fichas["vigente"]]
    if producto is None:
        if len(fichas) == 1:
            return fichas
        return None
    sel = fichas[fichas["nombre_producto"].str.casefold() == producto.casefold()]
    if sel.empty:
        raise SystemExit(
            f"No encontré '{producto}' en el JSON. Productos disponibles:\n  "
            + "\n  ".join(fichas["nombre_producto"])
        )
    return sel


def preparar_texto(interlub):
    """Carga el modelo y los embeddings de Interlub (solo si se pide --texto)."""
    import numpy as np
    from sentence_transformers import SentenceTransformer

    if not EMB.exists():
        raise SystemExit(f"No existe {EMB}: corre primero notebooks/02_pdfs.ipynb.")
    emb = np.load(EMB, allow_pickle=True)
    if not (emb["interlub_id"] == interlub["codigoproducto"].to_numpy()).all():
        raise SystemExit("embeddings.npz no coincide con DATOS_TEC_clean.csv: re-corre 02_pdfs.ipynb.")
    return SentenceTransformer(str(emb["modelo"])), emb["interlub_ficha"]


def recomendar_ficha(ficha, interlub, k=5, texto=None, peso_texto=0.0):
    """Recomendaciones + avisos + tabla comparativa para una ficha."""
    sim = None
    if texto is not None:
        modelo, emb_interlub = texto
        sim = R.similitud_texto(ficha, interlub, modelo, emb_interlub)
    recs, avisos = R.recomendar(ficha, interlub, k=k, sim_texto=sim, peso_texto=peso_texto)
    tabla = R.comparar(ficha, interlub, recs) if not recs.empty else pd.DataFrame()
    return recs, avisos, tabla


def imprimir(ficha, recs, avisos, tabla):
    nombre = ficha["nombre_producto"]
    marca = ficha.get("marca")
    print("=" * 100)
    print(f"Ficha: {nombre}" + (f" ({marca})" if isinstance(marca, str) else ""))
    print("=" * 100)
    for a in avisos:
        print("•", a)
    if recs.empty:
        print("\nNingún producto Interlub pasa los filtros.")
        return
    print("\nRecomendaciones:")
    cols = [c for c in recs.columns if c not in ("por_que", "advertencias")]
    print(recs[cols].to_string(index=False))
    print("\nPor qué:")
    for _, r in recs.iterrows():
        print(f"  {r['codigoproducto']}: {r['por_que']}")
        if r["advertencias"]:
            print(f"      ⚠ {r['advertencias']}")
    print("\nComparación lado a lado:")
    print(tabla.to_string())
    print()


def nombre_archivo(nombre):
    return re.sub(r"[^a-z0-9]+", "_", F.norm_texto(nombre)).strip("_")


def main(argv=None):
    p = argparse.ArgumentParser(description="Recomienda productos Interlub a partir de una ficha técnica.")
    p.add_argument("json", help="JSON de la extracción del PDF")
    p.add_argument("-p", "--producto", help="nombre_producto a usar como consulta")
    p.add_argument("--todos", action="store_true", help="recomendar para todos los productos vigentes")
    p.add_argument("-k", type=int, default=5, help="número de recomendaciones")
    p.add_argument("--interlub", default=INTERLUB, help="ruta a DATOS_TEC_clean.csv")
    p.add_argument("--texto", action="store_true", help="agregar similitud de embeddings")
    p.add_argument("--peso-texto", type=float, default=0.0, help="peso del texto en el puntaje (0 a 1)")
    p.add_argument("--guardar", action="store_true", help="guardar CSV en reports/")
    a = p.parse_args(argv)

    if not 0 <= a.peso_texto <= 1:
        raise SystemExit("--peso-texto debe estar entre 0 y 1.")
    if a.peso_texto > 0 and not a.texto:
        raise SystemExit("--peso-texto necesita --texto.")
    if not Path(a.interlub).exists():
        raise SystemExit(
            f"No existe {a.interlub}. Descifra los datos (scripts/dvc_decrypt.sh) o corre 01_limpieza.ipynb."
        )

    interlub = pd.read_csv(a.interlub)
    fichas = cargar_fichas(a.json)
    consulta = elegir(fichas, a.producto, a.todos)
    if consulta is None:
        print("El JSON tiene varios productos; elige uno con -p o usa --todos:")
        for _, f in fichas.iterrows():
            print(f"  - {f['nombre_producto']}" + ("" if f["vigente"] else "  (reemplazado)"))
        return 1

    texto = preparar_texto(interlub) if a.texto else None
    for _, ficha in consulta.iterrows():
        recs, avisos, tabla = recomendar_ficha(ficha, interlub, a.k, texto, a.peso_texto)
        imprimir(ficha, recs, avisos, tabla)
        if a.guardar and not recs.empty:
            REPORTES.mkdir(exist_ok=True)
            ruta = REPORTES / f"recomendaciones_{nombre_archivo(ficha['nombre_producto'])}.csv"
            recs.assign(ficha=ficha["nombre_producto"]).to_csv(ruta, index=False)
            print(f"Guardado en {ruta.relative_to(RAIZ)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
