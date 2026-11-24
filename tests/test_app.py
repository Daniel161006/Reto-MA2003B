"""Pruebas de la página web (app/app.py) simulando a una persona, con el catálogo ficticio de tests/datos/."""

import os
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = str(Path(__file__).parent / "datos" / "interlub_ejemplo.csv")


@pytest.fixture(autouse=True)
def catalogo_de_prueba(monkeypatch):
    monkeypatch.setenv("INTERLUB_CSV", CATALOGO)


def abrir():
    return AppTest.from_file(str(RAIZ / "app" / "app.py"), default_timeout=30).run()


def codigos(at):
    return [m.value.split("</div>")[0].split(">")[-1] for m in at.markdown if 'class="codigo"' in m.value]


def test_abre_sin_errores():
    at = abrir()
    assert not at.exception
    assert any("Recomendador Interlub" in t.value for t in at.title)


def test_recomienda_solo_al_llenar_datos():
    at = abrir()
    assert not codigos(at)  # sin datos no recomienda
    at.selectbox(key="espesante").set_value("complejo de litio")
    at.selectbox(key="nlgi").set_value("2")
    at.number_input(key="visc").set_value(220.0)
    at.number_input(key="tmin").set_value(-20.0)
    at.number_input(key="tmax").set_value(150.0)
    at.text_input(key="nombre").set_value("Mi grasa")
    at.run()  # sin botón: con solo cambiar los datos ya recomienda
    assert not at.exception and not at.error
    assert codigos(at)[0] == "G-LITIO-2"
    assert any("Mi grasa" in s.value for s in at.subheader)


def test_se_actualiza_al_cambiar_un_dato():
    at = abrir()
    at.selectbox(key="nlgi").set_value("2")
    at.number_input(key="tmax").set_value(150.0)
    at.run()
    antes = codigos(at)
    at.selectbox(key="nlgi").set_value("1").run()
    assert codigos(at)[0] == "G-LITIO-1" and codigos(at) != antes


def test_aceite_oculta_campos_de_grasa():
    at = abrir()
    assert any(s.key == "nlgi" for s in at.selectbox)
    at.radio(key="familia").set_value("aceite").run()
    assert not any(s.key in ("nlgi", "espesante") for s in at.selectbox)
    assert not at.exception


def test_sin_datos_no_recomienda():
    at = abrir()
    assert not at.exception and not codigos(at)
    assert any("Llena al menos un dato" in c.value for c in at.caption)


def test_grado_alimenticio_solo_nsf():
    at = abrir()
    at.number_input(key="tmax").set_value(150.0)
    at.checkbox(key="nsf").set_value(True).run()
    assert codigos(at) == ["G-ALIM-2"]


def test_sin_resultados_explica():
    at = abrir()
    at.number_input(key="tmax").set_value(900.0).run()
    assert not at.exception
    assert any("Ningún producto" in w.value for w in at.warning)


def test_producto_interlub_sale_primero():
    at = abrir()
    at.radio[0].set_value("Probar con un producto Interlub").run()
    at.selectbox(key="prueba").set_value("G-SULF-2").run()
    assert not at.exception
    assert codigos(at)[0] == "G-SULF-2"


def test_sin_catalogo_el_panel_sigue_visible(monkeypatch):
    monkeypatch.setenv("INTERLUB_CSV", str(Path(__file__).parent / "datos" / "no_existe.csv"))
    at = abrir()
    assert not at.exception
    assert any(s.key == "espesante" for s in at.selectbox)  # el panel está, con opciones por defecto
    at.number_input(key="tmax").set_value(150.0).run()
    assert not at.exception
    assert any("falta el catálogo" in w.value for w in at.warning)
