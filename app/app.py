"""Recomendador Interlub: página web para encontrar el producto Interlub que sustituye a otro.

Correr en tu compu:
    uv run streamlit run app/app.py

El catálogo se lee de data/processed/DATOS_TEC_clean.csv (o de la variable INTERLUB_CSV). Si no existe,
la página pide subir el archivo desde la barra lateral.
"""

import html
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import fichas_pdf as F  # noqa: E402
import recomendador as R  # noqa: E402

CATALOGO = Path(os.environ.get("INTERLUB_CSV", RAIZ / "data/processed/DATOS_TEC_clean.csv"))
NLGI = {"000": -2, "00": -1, "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
NO_SE = "No sé / no aplica"

st.set_page_config(page_title="Recomendador Interlub", page_icon="🛢️", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .chip {display:inline-block; padding:2px 10px; margin:2px 4px 2px 0; border-radius:999px;
             font-size:0.82rem; border:1px solid transparent; white-space:nowrap;}
      .chip.ok  {background:rgba(46,160,67,.14);  border-color:rgba(46,160,67,.45);  color:#1a7f37;}
      .chip.mid {background:rgba(212,160,23,.16); border-color:rgba(212,160,23,.55); color:#8a6100;}
      .chip.bad {background:rgba(207,34,46,.12);  border-color:rgba(207,34,46,.45);  color:#b3261e;}
      .chip.na  {background:rgba(110,118,129,.14); border-color:rgba(110,118,129,.4); color:#57606a;}
      .rank {font-size:2.2rem; font-weight:700; line-height:1; color:#0B5FA5;}
      .codigo {font-size:1.25rem; font-weight:650;}
      .sub {color:#57606a; font-size:0.9rem;}
      .pct {font-size:1.9rem; font-weight:700; line-height:1.1;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ datos

@st.cache_data(show_spinner=False)
def leer_catalogo(origen, firma):
    """origen: ruta o bytes del CSV. `firma` (fecha o tamaño) hace que se relea si el archivo cambia."""
    from io import BytesIO

    return pd.read_csv(BytesIO(origen) if isinstance(origen, bytes) else origen)


def cargar_catalogo():
    """Catálogo Interlub: del archivo local o del que suba la persona."""
    df = None
    if CATALOGO.exists():
        df = leer_catalogo(str(CATALOGO), CATALOGO.stat().st_mtime)
    else:
        st.sidebar.warning("No encontré el catálogo (DATOS_TEC_clean.csv). Súbelo aquí para poder recomendar:")
        archivo = st.sidebar.file_uploader("DATOS_TEC_clean.csv", type="csv")
        if archivo is not None:
            df = leer_catalogo(archivo.getvalue(), archivo.size)
    if df is None:
        return None
    faltan = {"codigoproducto", "familia"} - set(df.columns)
    if faltan:
        st.sidebar.error(f"Al archivo le faltan columnas: {', '.join(sorted(faltan))}")
        return None
    return df


def opciones(df, col):
    """Valores del catálogo; sin catálogo, el vocabulario conocido de espesantes y aceites base."""
    if df is None:
        pares = {"espesante": F.ESPESANTES, "aceite_base": F.ACEITES_BASE}.get(col, [])
        return sorted({v for _, v in pares})
    return sorted(df[col].dropna().astype(str).unique()) if col in df else []


def num(valor):
    return np.nan if valor is None else float(valor)


# ------------------------------------------------------------------ entrada de la ficha

def campo_con_tipo(etiqueta, clave, ayuda=None, paso=1.0):
    """Número opcional + si la ficha lo da como valor exacto, mínimo (>) o máximo (<)."""
    c1, c2 = st.columns([3, 2])
    valor = c1.number_input(etiqueta, value=None, step=paso, help=ayuda, key=f"{clave}_v")
    tipo = c2.selectbox("Dice", ["= exacto", "> al menos", "< menos de"], key=f"{clave}_t", help="Cómo aparece en la ficha")
    return valor, tipo[0]


def formulario(cat):
    """Panel de datos de la ficha. Devuelve la ficha apenas hay algún dato: las recomendaciones salen solas."""
    c1, c2 = st.columns([3, 2])
    nombre = c1.text_input("Nombre del producto a sustituir", placeholder="Ej. Mobilith SHC 460", key="nombre")
    familia = c2.radio("Tipo de producto", ["grasa", "aceite"], horizontal=True, format_func=str.capitalize, key="familia")
    es_grasa = familia == "grasa"

    st.markdown("**Lo básico**")
    a, b, c = st.columns(3)
    espesante = nlgi = NO_SE
    if es_grasa:
        espesante = a.selectbox("Espesante", [NO_SE, *opciones(cat, "espesante")], key="espesante")
        nlgi = c.selectbox("Grado NLGI", [NO_SE, *NLGI], index=0, key="nlgi",
                           help="Dureza de la grasa. 000 es casi líquida y 6 es la más dura.")
    base = b.selectbox("Aceite base", [NO_SE, *opciones(cat, "aceite_base")], key="aceite_base")
    d, e, f = st.columns(3)
    visc = d.number_input("Viscosidad del aceite base a 40 °C (cSt)" if es_grasa else "Viscosidad a 40 °C (cSt)",
                          value=None, min_value=0.0, step=10.0, key="visc")
    tmin = e.number_input("Temperatura mínima de uso (°C)", value=None, step=5.0, key="tmin")
    tmax = f.number_input("Temperatura máxima de uso (°C)", value=None, step=5.0, key="tmax")
    nsf = st.checkbox("Es grado alimenticio (NSF H1)", key="nsf",
                      help="Si lo marcas, solo se recomiendan productos Interlub con registro NSF.")

    with st.expander("Más datos de la ficha (opcional, mejoran la recomendación)"):
        g1, g2 = st.columns(2)
        with g1:
            gota, gota_t = campo_con_tipo("Punto de gota (°C)", "gota", paso=10.0)
            sold, sold_t = campo_con_tipo("Punto de soldadura 4 bolas (kgf)", "sold", paso=10.0)
            timken, timken_t = campo_con_tipo("Carga Timken OK (lb)", "timken", paso=5.0)
        with g2:
            desg, desg_t = campo_con_tipo("Desgaste 4 bolas (mm)", "desg", paso=0.05)
            flama, flama_t = campo_con_tipo("Punto de flama (°C)", "flama", paso=10.0)
            ivis, ivis_t = campo_con_tipo("Índice de viscosidad", "ivis", paso=5.0)

    d = {"nombre_producto": nombre.strip() or "Ficha sin nombre", "familia": familia}
    if espesante != NO_SE:
        d["espesante"] = espesante
    if base != NO_SE:
        d["aceite_base"] = base
    if nlgi != NO_SE:
        d["grado_nlgi_por_penetracion"] = float(NLGI[nlgi])
        d["grado_nlgi_consistencia"] = float(max(NLGI[nlgi], 0))  # 00 y 000 se declaran como 0
    d["viscosidad_del_aceite_base_a_40c_cst" if es_grasa else "viscosidad_a_40c_cst"] = num(visc)
    d["temperatura_de_servicio_c_min"], d["temperatura_de_servicio_c_max"] = num(tmin), num(tmax)
    extras = {
        "punto_de_gota_c": (gota, gota_t), "punto_de_soldadura_cuatro_bolas_kgf": (sold, sold_t),
        "carga_timken_ok_lb": (timken, timken_t), "desgaste_cuatro_bolas_mm": (desg, desg_t),
        "punto_de_flama_c": (flama, flama_t), "indice_de_viscosidad": (ivis, ivis_t),
    }
    for col, (valor, tipo) in extras.items():
        d[col] = num(valor)
        if valor is not None and tipo in "<>":
            d[col + "_tipo"] = tipo
    d["tiene_registro_nsf"] = bool(nsf)

    ficha = pd.Series(d)
    datos = [k for k in ficha.index if k not in ("nombre_producto", "familia", "tiene_registro_nsf")
             and not k.endswith("_tipo") and pd.notna(ficha[k])]
    if not datos and not nsf:
        return None
    return ficha


def subir_json():
    archivo = st.file_uploader("JSON de la ficha técnica", type="json",
                               help="El que devuelve la IA al leer el PDF (ver scripts/prompts/extraccion_pdfs.md)")
    if archivo is None:
        return None
    try:
        registros = json.load(archivo)
        fichas = F.normalizar([registros] if isinstance(registros, dict) else registros)
    except Exception as e:  # noqa: BLE001 - mostrar cualquier problema de formato sin tumbar la página
        st.error(f"No pude leer ese JSON: {e}")
        return None
    fichas = fichas.sort_values("vigente", ascending=False, kind="stable")
    nombre = st.selectbox(
        "Producto de la ficha", fichas["nombre_producto"],
        format_func=lambda n: n + ("" if fichas.set_index("nombre_producto").at[n, "vigente"] else "  (reemplazado)"),
    )
    return fichas.loc[fichas["nombre_producto"] == nombre].iloc[0]


def producto_interlub(cat):
    cod = st.selectbox("Producto Interlub", cat["codigoproducto"].astype(str), key="prueba")
    st.caption("Sirve para probar: el mismo producto debería salir primero en su propia recomendación.")
    ficha = cat.loc[cat["codigoproducto"].astype(str) == cod].iloc[0].copy()
    ficha["nombre_producto"] = f"{cod} (producto Interlub)"
    return ficha


# ------------------------------------------------------------------ resultados

def chip(texto):
    marca = re.findall(r"\s([✓~✗])(?=\s|$)", texto)
    clase = {"✓": "ok", "~": "mid", "✗": "bad"}.get(marca[-1] if marca else "", "na")
    return f'<span class="chip {clase}">{html.escape(texto)}</span>'


def veredicto(p):
    if p >= 0.75:
        return "Muy parecido"
    if p >= 0.5:
        return "Parecido, con diferencias"
    return "Solo como última opción"


def resumen_ficha(f):
    partes = [str(f.get("familia", "")).capitalize()]
    for col, txt in [("espesante", "{}"), ("aceite_base", "base {}")]:
        if pd.notna(f.get(col)):
            partes.append(txt.format(f[col]))
    n = f.get("grado_nlgi_por_penetracion")
    n = n if pd.notna(n) else f.get("grado_nlgi_consistencia")
    if pd.notna(n):
        partes.append("NLGI " + {-2: "000", -1: "00"}.get(n, f"{n:g}"))
    lo, hi = f.get("temperatura_de_servicio_c_min"), f.get("temperatura_de_servicio_c_max")
    if pd.notna(lo) or pd.notna(hi):
        partes.append(f"{'' if pd.isna(lo) else format(lo, 'g')} a {'' if pd.isna(hi) else format(hi, 'g')} °C")
    if f.get("tiene_registro_nsf") in (True, np.True_):
        partes.append("grado alimenticio")
    return " · ".join(partes)


def descripcion_producto(fila):
    partes = []
    for col, txt in [("espesante", "{}"), ("aceite_base", "base {}")]:
        if pd.notna(fila.get(col)):
            partes.append(txt.format(fila[col]))
    n = fila.get("nlgi")
    if pd.notna(n):
        partes.append("NLGI " + {-2: "000", -1: "00"}.get(n, f"{n:g}"))
    lo, hi = fila.get("temperatura_de_servicio_c_min"), fila.get("temperatura_de_servicio_c_max")
    if pd.notna(lo) and pd.notna(hi):
        partes.append(f"{lo:g} a {hi:g} °C")
    if fila.get("tiene_registro_nsf") in (True, np.True_):
        partes.append("NSF")
    return " · ".join(partes)


def tarjeta(pos, fila, cat_nlgi):
    puntaje = float(fila["puntaje"])
    with st.container(border=True):
        a, b, c = st.columns([1, 6, 3], vertical_alignment="center")
        a.markdown(f'<div class="rank">{pos}</div>', unsafe_allow_html=True)
        info = cat_nlgi.loc[fila.name]
        b.markdown(
            f'<div class="codigo">{html.escape(str(fila["codigoproducto"]))}</div>'
            f'<div class="sub">{html.escape(descripcion_producto(info))}</div>',
            unsafe_allow_html=True,
        )
        c.markdown(f'<div class="pct">{puntaje * 100:.0f}%</div><div class="sub">{veredicto(puntaje)}</div>',
                   unsafe_allow_html=True)
        c.progress(min(max(puntaje, 0.0), 1.0))
        st.markdown("".join(chip(t) for t in fila["por_que"].split(" · ")), unsafe_allow_html=True)
        if fila.get("advertencias"):
            st.caption(f"⚠️ {fila['advertencias']}")
        if fila["cobertura"] < 0.6:
            st.caption(f"⚠️ Solo se pudo comparar el {fila['cobertura'] * 100:.0f}% de los datos de la ficha: "
                       "tómalo con cuidado.")


def tabla_comparacion(tabla):
    nombres = {**R.ETIQUETAS, "familia": "familia", "temperatura_de_servicio_c_min": "temperatura mín. (°C)",
               "temperatura_de_servicio_c_max": "temperatura máx. (°C)", "tiene_registro_nsf": "registro NSF"}
    etiquetas = {"nlgi": "NLGI", "viscosidad_del_aceite_base_a_40c_cst": "visc. aceite base 40 °C (cSt)",
                 "viscosidad_a_40c_cst": "visc. 40 °C (cSt)", "punto_de_gota_c": "punto de gota (°C)",
                 "punto_de_flama_c": "punto de flama (°C)", "carga_timken_ok_lb": "Timken OK (lb)",
                 "punto_de_soldadura_cuatro_bolas_kgf": "soldadura 4 bolas (kgf)",
                 "desgaste_cuatro_bolas_mm": "desgaste 4 bolas (mm)"}
    nombres.update(etiquetas)

    def fmt(x):
        if pd.isna(x):
            return "—"
        if isinstance(x, (bool, np.bool_)):
            return "Sí" if x else "No"
        return f"{x:g}" if isinstance(x, (int, float, np.floating, np.integer)) else str(x)

    t = tabla.map(fmt)
    t.index = [nombres.get(i, i) for i in t.index]
    return t


def mostrar(ficha, cat, k):
    recs, avisos = R.recomendar(ficha, cat, k=k)
    st.subheader(f"Sustitutos para: {ficha['nombre_producto']}")
    st.caption(resumen_ficha(ficha))
    for a in avisos:
        st.info(a, icon="ℹ️")
    if recs.empty:
        st.warning("Ningún producto Interlub cumple con los filtros (tipo de producto, temperatura y grado alimenticio). "
                   "Revisa la temperatura de la ficha o consulta con el equipo técnico.")
        return
    st.markdown(
        '<span class="sub">Cada etiqueta compara <b>ficha vs Interlub</b>: '
        '<span class="chip ok">✓ igual o mejor</span><span class="chip mid">~ algo distinto</span>'
        '<span class="chip bad">✗ muy distinto</span></span>', unsafe_allow_html=True)
    cat_nlgi = R._con_nlgi(cat)
    for pos, (_, fila) in enumerate(recs.iterrows(), start=1):
        tarjeta(pos, fila, cat_nlgi)

    with st.expander("Comparación lado a lado", expanded=False):
        st.dataframe(tabla_comparacion(R.comparar(ficha, cat, recs)), width="stretch")
    csv = recs.assign(ficha=ficha["nombre_producto"]).to_csv(index=False).encode("utf-8-sig")
    st.download_button("Descargar recomendaciones (CSV)", csv, file_name="recomendaciones_interlub.csv", mime="text/csv")


# ------------------------------------------------------------------ página

def main():
    st.title("🛢️ Recomendador Interlub")
    st.write("Encuentra el producto Interlub que mejor sustituye a una grasa o aceite, a partir de los datos de su ficha técnica.")

    cat = cargar_catalogo()
    with st.sidebar:
        st.header("Opciones")
        k = st.slider("Cuántas recomendaciones", 1, 10, 5)
        if cat is not None:
            n_g = int((cat["familia"] == "grasa").sum())
            st.caption(f"Catálogo: {len(cat)} productos ({n_g} grasas, {len(cat) - n_g} aceites)")
        with st.expander("¿Cómo se calcula?"):
            st.markdown(
                "1. **Se descartan** los que no sirven: otro tipo de producto, que no aguanten la temperatura "
                "o, si la ficha es grado alimenticio, los que no tengan NSF.\n"
                "2. **Se compara** cada propiedad (NLGI, viscosidad, punto de gota, presión extrema, etc.) con una "
                "tolerancia técnica. Si Interlub es igual o mejor, cuenta completo.\n"
                "3. **Pesan más** NLGI, viscosidad y temperatura: si fallan, el porcentaje baja aunque lo demás coincida.\n"
                "4. Los datos que faltan no castigan, pero si se comparó poco, se avisa.\n\n"
                "Las tolerancias son una propuesta del equipo y deben validarse con Interlub."
            )
    modo = st.radio("¿Cómo quieres dar la ficha?", ["Llenar los datos", "Subir el JSON de la ficha", "Probar con un producto Interlub"],
                    horizontal=True)
    if modo == "Llenar los datos":
        ficha = formulario(cat)
    elif modo == "Subir el JSON de la ficha":
        ficha = subir_json()
    elif cat is not None:
        ficha = producto_interlub(cat)
    else:
        st.info("Para probar con un producto Interlub hace falta el catálogo.")
        ficha = None

    st.divider()
    if ficha is None:
        st.caption("Llena al menos un dato de la ficha (por ejemplo NLGI o temperatura) y aquí aparecen las recomendaciones.")
    elif cat is None:
        st.warning("Ya tengo la ficha, pero falta el catálogo de Interlub para compararla. "
                   "Súbelo en la barra lateral (DATOS_TEC_clean.csv) y las recomendaciones salen solas.")
    else:
        mostrar(ficha, cat, k)


main()
