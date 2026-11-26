"""Pruebas del análisis de sensibilidad de pesos (con el catálogo ficticio)."""

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import recomendador as R  # noqa: E402
import sensibilidad_pesos as S  # noqa: E402

CATALOGO = Path(__file__).parent / "datos" / "interlub_ejemplo.csv"


def test_con_peso_restaura():
    antes = (dict(R.COMPARACIONES), dict(R.CATEGORICAS), R.PESO_TEMPERATURA, R.PISO_CRITICO)
    for nombre in ["nlgi", "espesante", "temperatura", "piso_critico"]:
        with S.con_peso(nombre, 0.5):
            pass
    assert (dict(R.COMPARACIONES), dict(R.CATEGORICAS), R.PESO_TEMPERATURA, R.PISO_CRITICO) == antes


def test_sensibilidad_y_robustez():
    interlub = pd.read_csv(CATALOGO)
    idx = S.consultas(interlub, 100, 0)
    tabla = S.sensibilidad(interlub, idx)
    assert {"peso", "estabilidad"} <= set(tabla.columns)
    assert tabla["estabilidad"].between(0, 1).all()
    assert "piso_critico" in set(tabla["peso"])
    rob = S.robustez(interlub, idx)
    assert 0 <= rob["sale_primero"] <= rob["sale_en_top3"] <= 1
