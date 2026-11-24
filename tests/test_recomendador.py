"""Pruebas del recomendador con datos ficticios (tests/datos/), para no depender de los datos cifrados.

Correr desde la raíz del repo:
    uv run pytest
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import fichas_pdf as F  # noqa: E402
import recomendador as R  # noqa: E402
import recomendar as CLI  # noqa: E402

DATOS = Path(__file__).parent / "datos"
JSON = DATOS / "ficha_ejemplo.json"


@pytest.fixture
def interlub():
    return pd.read_csv(DATOS / "interlub_ejemplo.csv")


@pytest.fixture
def fichas():
    return CLI.cargar_fichas(JSON)


def ficha(fichas, nombre):
    return fichas.loc[fichas["nombre_producto"] == nombre].iloc[0]


# --- normalización de la ficha -------------------------------------------------------------------------------


def test_parse_valor():
    assert F.parse_valor("> 260") == (260.0, ">")
    assert F.parse_valor("265-295") == (280.0, "rango")
    assert F.parse_valor("0,45") == (0.45, "=")
    x, tipo = F.parse_valor("3923", "N")  # newtons -> kgf
    assert tipo == "=" and x == pytest.approx(400, abs=0.1)


def test_normalizar(fichas):
    f = ficha(fichas, "FICTIGRASA EP 2")
    assert f["familia"] == "grasa"
    assert f["espesante"] == "complejo de litio"  # "Lithium complex" -> vocabulario Interlub
    assert f["aceite_base"] == "mineral"
    assert f["grado_nlgi_por_penetracion"] == 2  # 265-295 -> NLGI 2
    assert f["viscosidad_del_aceite_base_a_40c_cst"] == 220  # en grasa, viscosidad 40 °C = del aceite base
    assert bool(ficha(fichas, "FICTIFOOD 2")["tiene_registro_nsf"])


def test_reemplazado_no_vigente(fichas):
    # "reemplaza_a: Fictigrasa Vieja" marca como no vigente a FICTIGRASA VIEJA 2
    assert not ficha(fichas, "FICTIGRASA VIEJA 2")["vigente"]
    assert ficha(fichas, "FICTIGRASA EP 2")["vigente"]


# --- filtros ---------------------------------------------------------------------------------------------------


def test_filtra_familia(fichas, interlub):
    recs, _ = R.recomendar(ficha(fichas, "FICTIGRASA EP 2"), interlub, k=10)
    assert "A-ENGR-220" not in set(recs["codigoproducto"])  # aceite, la ficha es grasa


def test_filtra_temperatura(fichas, interlub):
    # la ficha pide hasta 150 °C; G-FRIA-2 llega a 100 (le faltan 50 > tolerancia de 10)
    recs, _ = R.recomendar(ficha(fichas, "FICTIGRASA EP 2"), interlub, k=10)
    assert "G-FRIA-2" not in set(recs["codigoproducto"])


def test_grado_alimenticio_solo_nsf(fichas, interlub):
    recs, avisos = R.recomendar(ficha(fichas, "FICTIFOOD 2"), interlub, k=10)
    assert set(recs["codigoproducto"]) == {"G-ALIM-2"}
    assert any("grado alimenticio" in a for a in avisos)


# --- orden ---------------------------------------------------------------------------------------------------------


def test_el_mas_parecido_gana(fichas, interlub):
    # misma familia, espesante, aceite, NLGI y viscosidad: G-LITIO-2 debe quedar primero
    recs, _ = R.recomendar(ficha(fichas, "FICTIGRASA EP 2"), interlub, k=5)
    assert recs.iloc[0]["codigoproducto"] == "G-LITIO-2"
    assert recs["puntaje"].is_monotonic_decreasing
    assert recs["puntaje"].between(0, 1).all()


def test_critica_penaliza(fichas, interlub):
    # G-LITIO-1 es NLGI 1 y otra viscosidad: el factor crítico debe bajar
    recs, _ = R.recomendar(ficha(fichas, "FICTIGRASA EP 2"), interlub, k=10)
    fac = recs.set_index("codigoproducto")["factor_critico"]
    assert fac["G-LITIO-2"] > fac["G-LITIO-1"]


def test_sin_datos_no_truena(interlub):
    vacia = pd.Series({"nombre_producto": "VACIA", "familia": "grasa"})
    recs, avisos = R.recomendar(vacia, interlub, k=3)
    assert len(recs) == 3
    assert any("no tiene temperatura" in a for a in avisos)


def test_ninguno_pasa_filtros(interlub):
    extrema = pd.Series({"nombre_producto": "X", "familia": "grasa", "temperatura_de_servicio_c_max": 900.0})
    recs, _ = R.recomendar(extrema, interlub)
    assert recs.empty


def test_comparar(fichas, interlub):
    f = ficha(fichas, "FICTIGRASA EP 2")
    recs, _ = R.recomendar(f, interlub, k=2)
    tabla = R.comparar(f, interlub, recs)
    assert list(tabla.columns) == ["FICTIGRASA EP 2", *recs["codigoproducto"]]
    assert "nlgi" in tabla.index


# --- comando de terminal -----------------------------------------------------------------------------------


def test_cli_un_producto(capsys):
    assert CLI.main([str(JSON), "-p", "fictigrasa ep 2", "--interlub", str(DATOS / "interlub_ejemplo.csv")]) == 0
    salida = capsys.readouterr().out
    assert "G-LITIO-2" in salida and "Por qué" in salida


def test_cli_lista_si_hay_varios(capsys):
    assert CLI.main([str(JSON), "--interlub", str(DATOS / "interlub_ejemplo.csv")]) == 1
    assert "(reemplazado)" in capsys.readouterr().out


def test_cli_producto_inexistente():
    with pytest.raises(SystemExit):
        CLI.main([str(JSON), "-p", "NO EXISTE", "--interlub", str(DATOS / "interlub_ejemplo.csv")])
