"""¿Qué tanto importan los pesos del recomendador?

Usa cada producto del catálogo Interlub como si fuera la ficha de otro producto (se excluye a sí mismo de los
candidatos) y mide dos cosas:

1. Sensibilidad a los pesos: se baja a la mitad y se sube 50 % cada peso, uno por uno, y se compara el top 3 contra
   el original. Si casi no cambia, ese peso da igual y no vale la pena discutirlo. Si cambia mucho, es el que hay que
   validar con Interlub.
2. Robustez a datos faltantes: se le quita 30 % de los datos a la ficha (las fichas en PDF casi nunca traen todo)
   y se revisa si el recomendador sigue encontrando el mismo producto entre los primeros.

Uso (desde la raíz del repo, con el catálogo ya descifrado):
    uv run python scripts/sensibilidad_pesos.py
    uv run python scripts/sensibilidad_pesos.py --max 100 --semilla 7

Guarda la tabla en reports/sensibilidad_pesos.csv.
"""

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import recomendador as R  # noqa: E402

INTERLUB = RAIZ / "data/processed/DATOS_TEC_clean.csv"
K = 3


@contextmanager
def con_peso(nombre, factor):
    """Cambia temporalmente un peso del recomendador y lo restaura al salir."""
    comp, cat = dict(R.COMPARACIONES), dict(R.CATEGORICAS)
    temp, piso = R.PESO_TEMPERATURA, R.PISO_CRITICO
    try:
        if nombre in R.COMPARACIONES:
            peso, tipo, tol = R.COMPARACIONES[nombre]
            R.COMPARACIONES[nombre] = (peso * factor, tipo, tol)
        elif nombre in R.CATEGORICAS:
            R.CATEGORICAS[nombre] *= factor
        elif nombre == "temperatura":
            R.PESO_TEMPERATURA = temp * factor
        elif nombre == "piso_critico":  # qué tanto castiga fallar en NLGI, viscosidad o temperatura
            R.PISO_CRITICO = min(piso * factor, 0.95)
        else:
            raise KeyError(nombre)
        yield
    finally:
        R.COMPARACIONES.clear()
        R.COMPARACIONES.update(comp)
        R.CATEGORICAS.clear()
        R.CATEGORICAS.update(cat)
        R.PESO_TEMPERATURA, R.PISO_CRITICO = temp, piso


def top(ficha, cand, k=K):
    recs, _ = R.recomendar(ficha, cand, k=k)
    return list(recs["codigoproducto"]) if not recs.empty else []


def consultas(interlub, maximo, semilla):
    """Productos que se usarán como ficha (una muestra si el catálogo es grande)."""
    idx = interlub.index.to_numpy()
    if len(idx) > maximo:
        idx = np.random.default_rng(semilla).choice(idx, maximo, replace=False)
    return idx


def sensibilidad(interlub, idx):
    base = {i: top(interlub.loc[i], interlub.drop(index=i)) for i in idx}
    nombres = [*R.COMPARACIONES, *R.CATEGORICAS, "temperatura", "piso_critico"]
    filas = []
    for nombre in nombres:
        fila = {"peso": nombre}
        for etiqueta, factor in [("mitad", 0.5), ("mas50", 1.5)]:
            solapa, igual1 = [], []
            with con_peso(nombre, factor):
                for i in idx:
                    nuevo = top(interlub.loc[i], interlub.drop(index=i))
                    ref = base[i]
                    if ref:
                        solapa.append(len(set(ref) & set(nuevo)) / len(ref))
                        igual1.append(float(bool(nuevo) and nuevo[0] == ref[0]))
            fila[f"top3_igual_{etiqueta}"] = round(float(np.mean(solapa)), 3) if solapa else np.nan
            fila[f"top1_igual_{etiqueta}"] = round(float(np.mean(igual1)), 3) if igual1 else np.nan
        fila["estabilidad"] = min(fila["top3_igual_mitad"], fila["top3_igual_mas50"])
        filas.append(fila)
    return pd.DataFrame(filas).sort_values("estabilidad").reset_index(drop=True)


def robustez(interlub, idx, faltante=0.3, repeticiones=5, semilla=0):
    """Quita al azar `faltante` de los datos de la ficha y revisa si el producto original sigue en el top."""
    rng = np.random.default_rng(semilla)
    columnas = [c for c in [*R.COMPARACIONES, *R.CATEGORICAS, "temperatura_de_servicio_c_min",
                            "temperatura_de_servicio_c_max", "grado_nlgi_por_penetracion",
                            "grado_nlgi_consistencia"] if c in interlub.columns]
    primero, en_top3, total = 0, 0, 0
    for i in idx:
        ficha = interlub.loc[i]
        con_dato = [c for c in columnas if pd.notna(ficha[c])]
        if len(con_dato) < 4:  # con tan pocos datos no tiene sentido quitar más
            continue
        for _ in range(repeticiones):
            quitar = rng.choice(con_dato, int(round(len(con_dato) * faltante)), replace=False)
            variante = ficha.copy()
            variante[list(quitar)] = np.nan
            ranking = top(variante, interlub, k=K)  # aquí el producto original SÍ compite
            total += 1
            primero += bool(ranking) and ranking[0] == ficha["codigoproducto"]
            en_top3 += ficha["codigoproducto"] in ranking
    return {"intentos": total, "sale_primero": primero / total if total else np.nan,
            "sale_en_top3": en_top3 / total if total else np.nan}


def main(argv=None):
    p = argparse.ArgumentParser(description="Sensibilidad de los pesos del recomendador.")
    p.add_argument("--interlub", default=INTERLUB, help="ruta a DATOS_TEC_clean.csv")
    p.add_argument("--max", type=int, default=150, help="máximo de productos a usar como ficha")
    p.add_argument("--semilla", type=int, default=0)
    a = p.parse_args(argv)
    if not Path(a.interlub).exists():
        raise SystemExit(f"No existe {a.interlub}. Descifra los datos o corre 01_limpieza.ipynb.")

    interlub = pd.read_csv(a.interlub)
    idx = consultas(interlub, a.max, a.semilla)
    print(f"Usando {len(idx)} productos como ficha (de {len(interlub)}).\n")

    tabla = sensibilidad(interlub, idx)
    print("1) Sensibilidad a los pesos (1.0 = el top 3 no cambia nada; más bajo = ese peso importa más)")
    print(tabla.to_string(index=False))

    rob = robustez(interlub, idx, semilla=a.semilla)
    print("\n2) Robustez: a la ficha se le quita 30 % de los datos")
    print(f"   El producto original sale primero en {rob['sale_primero']:.0%} de {rob['intentos']} intentos "
          f"y en el top 3 en {rob['sale_en_top3']:.0%}.")

    destino = RAIZ / "reports"
    destino.mkdir(exist_ok=True)
    tabla.to_csv(destino / "sensibilidad_pesos.csv", index=False)
    print(f"\nGuardado en {(destino / 'sensibilidad_pesos.csv').relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
