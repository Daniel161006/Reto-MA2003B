"""Pruebas de la página web (app/app.py) simulando a una persona, con el catálogo ficticio de tests/datos/."""

import re
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
    return [c for m in at.markdown for c in re.findall(r'<div class="codigo">([^<]+)</div>', m.value)]


def texto(at):
    return " ".join(m.value for m in at.markdown)


def test_abre_sin_errores():
    at = abrir()
    assert not at.exception
    assert "Recomendador de sustitutos" in texto(at)
    assert "Aquí aparecen los sustitutos" in texto(at)


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
    assert "Sustitutos para Mi grasa" in texto(at)
    assert "Te recomendamos" in texto(at)


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
    at.button_group(key="familia").set_value("aceite").run()
    assert not any(s.key in ("nlgi", "espesante") for s in at.selectbox)
    assert not at.exception


def test_sin_datos_no_recomienda():
    at = abrir()
    assert not at.exception and not codigos(at)
    assert "Llena al menos un dato" in texto(at)


def test_grado_alimenticio_solo_nsf():
    at = abrir()
    at.number_input(key="tmax").set_value(150.0)
    at.checkbox(key="nsf").set_value(True).run()
    assert codigos(at) == ["G-ALIM-2"]


def test_sin_resultados_explica():
    at = abrir()
    at.number_input(key="tmax").set_value(900.0).run()
    assert not at.exception
    assert "Ningún producto Interlub cumple" in texto(at)


def test_producto_interlub_sale_primero():
    at = abrir()
    at.button_group(key="modo").set_value("Autoprueba").run()
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
    assert "Falta el catálogo de Interlub" in texto(at)
    assert not codigos(at)


def test_subir_json_de_ficha():
    at = abrir()
    at.button_group(key="modo").set_value("Subir JSON").run()
    assert not at.exception
    assert "Sube el JSON" in texto(at)


def test_avisa_cambio_de_espesante():
    at = abrir()
    at.selectbox(key="espesante").set_value("poliurea")
    at.number_input(key="tmax").set_value(150.0)
    at.run()
    assert not at.exception
    assert "Cambia el espesante" in texto(at)


def test_propone_producto_nuevo_si_nadie_cumple():
    at = abrir()
    at.selectbox(key="nlgi").set_value("2")
    at.number_input(key="tmax").set_value(230.0)
    at.run()
    assert not at.exception
    assert "Especificación para sustituir" in texto(at)
    assert "De qué producto partir" in texto(at)
    assert any("especificación" in b.label.lower() for b in at.get("download_button"))


def test_no_propone_nuevo_si_hay_sustituto_directo():
    at = abrir()
    at.selectbox(key="espesante").set_value("complejo de litio")
    at.selectbox(key="nlgi").set_value("2")
    at.number_input(key="visc").set_value(220.0)
    at.number_input(key="tmax").set_value(150.0)
    at.run()
    assert "Especificación para sustituir" not in texto(at)


def test_ejemplo_de_un_clic():
    at = abrir()
    at.button(key="ej_0").click().run()  # grasa EP para rodamientos
    assert not at.exception
    assert at.number_input(key="tmax").value == 150.0
    assert "Sustitutos para Grasa EP para rodamientos" in texto(at)
    assert codigos(at)[0] == "G-LITIO-2"


def test_ejemplo_de_aceite_cambia_el_tipo():
    at = abrir()
    at.button(key="ej_2").click().run()  # aceite para engranes
    assert not at.exception
    assert at.button_group(key="familia").value == "aceite"
    assert codigos(at)[0] == "A-ENGR-220"


def test_limpiar_borra_la_ficha():
    at = abrir()
    at.button(key="ej_0").click().run()
    assert codigos(at)
    at.button(key="limpiar").click().run()
    assert not at.exception and not codigos(at)
    assert at.number_input(key="tmax").value is None


def test_confianza_segun_datos_clave():
    at = abrir()
    at.number_input(key="tmax").set_value(150.0).run()
    assert "Confianza de la comparación: <b>baja</b>" in texto(at)
    at.selectbox(key="nlgi").set_value("2")
    at.number_input(key="visc").set_value(220.0)
    at.run()
    assert "Confianza de la comparación: <b>alta</b>" in texto(at)
