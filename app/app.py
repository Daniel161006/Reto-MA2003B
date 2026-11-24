"""Recomendador Interlub: página web para encontrar el producto Interlub que sustituye a otra grasa o aceite.

Correr en tu compu (desde la raíz del repo):
    uv run streamlit run app/app.py

El catálogo se lee de data/processed/DATOS_TEC_clean.csv (o de la variable INTERLUB_CSV). Si no existe, la
página deja llenar la ficha igual y pide subir el catálogo para poder comparar.

Diseño: colores y letras en .streamlit/config.toml; el resto de estilos en CSS (abajo).
"""

import html
import json
import math
import os
import sys
from io import BytesIO
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
NO_SE = "No lo dice la ficha"
MODOS = ["Llenar datos", "Subir JSON", "Autoprueba"]
CAMPOS = ["nombre", "nlgi", "espesante", "aceite_base", "visc", "tmin", "tmax", "nsf",
          *[f"{c}_{s}" for c in ["gota", "sold", "desg", "timken", "flama", "ivis"] for s in "vt"]]

# Paleta de lubricantes: petróleo profundo, ámbar aceite, miel, acero y grafito
PETROLEO, AMBAR, PIZARRA = "#0D2C36", "#D4920F", "#1A242C"
MIEL, ACEITE_OSC, ACERO = "#EAB54E", "#7A4A06", "#E8ECEF"
VERDE, AMBAR_OSC, ROJO = "#2E7D4F", "#9A6200", "#B3362F"

# Ejemplos de un clic para probar la página sin tener una ficha a la mano
EJEMPLOS = {
    "Grasa EP para rodamientos": {
        "desc": "NLGI 2, aceite de 220 cSt, de -20 a 150 °C",
        "valores": {"familia": "grasa", "nombre": "Grasa EP para rodamientos", "nlgi": "2", "visc": 220.0,
                    "tmin": -20.0, "tmax": 150.0}},
    "Grasa grado alimenticio": {
        "desc": "NLGI 2, de -20 a 120 °C, con registro NSF H1",
        "valores": {"familia": "grasa", "nombre": "Grasa grado alimenticio", "nlgi": "2", "tmin": -20.0,
                    "tmax": 120.0, "nsf": True}},
    "Aceite para engranes": {
        "desc": "ISO VG 220, de -10 a 100 °C",
        "valores": {"familia": "aceite", "nombre": "Aceite para engranes ISO 220", "visc": 220.0, "tmin": -10.0,
                    "tmax": 100.0}},
    "Grasa de muy alta temperatura": {
        "desc": "NLGI 2, aceite de 460 cSt, hasta 260 °C",
        "valores": {"familia": "grasa", "nombre": "Grasa para hornos", "nlgi": "2", "visc": 460.0, "tmax": 260.0}},
}

st.set_page_config(page_title="Recomendador Interlub", page_icon="🛢️", layout="wide",
                   initial_sidebar_state="collapsed")

CSS = f"""
<style>
/* =====================================================================  base */
.stApp {{ background: #EEF1F3; color: {PIZARRA}; }}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebarCollapsedControl"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ padding-top: 0; padding-bottom: 2.5rem; max-width: 1320px; }}
.stApp label p {{ font-size: .85rem; font-weight: 500; color: #42525C; }}

/* =====================================================================  cabecera de lado a lado */
.hero {{ margin: -1rem calc(50% - 50vw) 1.6rem; padding: 2.4rem max(1.25rem, calc(50vw - 580px)) 4.6rem;
        background:
          radial-gradient(55% 120% at 82% 20%, rgba(234,181,78,.20) 0%, rgba(234,181,78,0) 62%),
          radial-gradient(90% 140% at 8% 120%, #134454 0%, rgba(19,68,84,0) 60%),
          linear-gradient(180deg, #0B2630 0%, {PETROLEO} 100%);
        color: #fff; position: relative; overflow: hidden; }}
.hero .capas {{ position: absolute; left: 0; right: 0; bottom: -1px; width: 100%; height: 58px; display: block; }}
.hero-texto {{ position: relative; max-width: 640px; }}
.hero h1 {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; font-size: 2.6rem;
           line-height: 1.06; letter-spacing: -0.015em; margin: 0 0 .55rem; color: #fff; padding: 0; }}
.hero p {{ margin: 0; max-width: 46ch; color: #B7CBD2; font-size: 1.05rem; line-height: 1.55; }}
.logo {{ display: inline-flex; align-items: center; gap: .9rem; margin-bottom: 1.6rem; }}
.logo .emblema {{ width: 60px; height: 60px; flex: none; filter: drop-shadow(0 10px 18px rgba(0,0,0,.4)); }}
.logo-nombre {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; font-size: 2.15rem;
               letter-spacing: .17em; line-height: 1; color: #fff; text-shadow: 0 2px 12px rgba(0,0,0,.35);
               padding-right: .2rem; }}
.logo-nombre i {{ display: block; height: 3px; margin-top: .5rem; border-radius: 3px;
                 background: linear-gradient(90deg, {MIEL}, {AMBAR} 55%, rgba(212,146,15,0)); }}
.ondas {{ position: absolute; right: max(.5rem, calc(50vw - 640px)); top: 46%; width: 560px; height: auto;
         transform: translateY(-50%); pointer-events: none; }}
@media (max-width: 1000px) {{ .ondas {{ display: none; }} }}

/* =====================================================================  paneles */
.st-key-panel_ficha, .st-key-panel_catalogo {{ background: #fff; border: 1px solid #E1E7EB !important;
  border-radius: 18px; padding: 1.35rem 1.35rem 1.4rem !important;
  box-shadow: 0 1px 2px rgba(13,44,54,.04), 0 18px 40px -28px rgba(13,44,54,.35); }}
@media (min-width: 1100px) and (min-height: 820px) {{
  .st-key-panel_ficha {{ position: sticky; top: 1rem; }}
}}
.panel-titulo {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; font-size: 1.4rem;
                color: {PETROLEO}; margin: 0; letter-spacing: -.005em; }}
.panel-sub {{ color: #5B6B76; font-size: .9rem; margin: 0 0 .4rem; line-height: 1.45; }}
.grupo {{ display: flex; align-items: center; gap: .5rem; font-weight: 600; font-size: .95rem; color: {PETROLEO};
         border-top: 1px solid #EDF1F3; padding-top: .95rem; margin: .7rem 0 .1rem; }}
.grupo .g-gota {{ display: inline-grid; place-items: center; width: 1.35rem; height: 1.35rem; border-radius: 50%;
                 background: #FBF1DC; color: {AMBAR}; }}
.grupo .g-gota svg {{ width: 8px; height: 11px; }}

/* campos de captura */
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-baseweb="select"] > div {{
  background: #F7F9FA !important; border: 1px solid #D6DEE3 !important; border-radius: 10px !important;
  min-height: 2.8rem; transition: border-color .15s ease, box-shadow .15s ease, background-color .15s ease; }}
[data-testid="stTextInputRootElement"] *, [data-testid="stNumberInputContainer"] * {{ background: transparent !important;
  border: none !important; }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-baseweb="select"] > div:focus-within {{ border-color: {AMBAR} !important; background: #fff !important;
  box-shadow: 0 0 0 3px rgba(212,146,15,.18) !important; }}
[data-testid="stNumberInputContainer"] button:hover {{ color: {AMBAR} !important; }}
input::placeholder {{ color: #9AA8B1 !important; }}

/* interruptores (pestañas) */
div[data-testid="stButtonGroup"] [role="radiogroup"] {{ background: #EDF1F3; border: 1px solid #DDE4E8;
  border-radius: 12px; padding: 3px; gap: 3px; }}
div[data-testid="stButtonGroup"] button {{ border: none !important; background: transparent !important;
  border-radius: 9px !important; min-height: 2.3rem; color: #4A5A64 !important; box-shadow: none !important;
  margin: 0 !important; }}
div[data-testid="stButtonGroup"] button:hover {{ color: {PETROLEO} !important; background: rgba(255,255,255,.55) !important; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: #fff !important;
  box-shadow: 0 1px 2px rgba(13,44,54,.14), 0 4px 10px -4px rgba(13,44,54,.22) !important; }}
div[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: {PETROLEO} !important; font-weight: 600; }}
.st-key-modo [role="radiogroup"] button, .st-key-familia [role="radiogroup"] button {{ flex: 1 1 0; }}
.st-key-k {{ display: flex; justify-content: flex-end; }}

/* casilla y expansores */
[data-testid="stCheckbox"] label p {{ color: {PIZARRA}; }}
[data-testid="stExpander"] details {{ background: #fff; border: 1px solid #DFE6EA; border-radius: 12px; }}
[data-testid="stExpander"] summary {{ font-weight: 500; }}
[data-testid="stExpander"] summary:hover {{ color: {PETROLEO}; }}

/* confianza de la comparación */
.confianza {{ background: linear-gradient(180deg, #F8FAFB, #F2F5F7); border: 1px solid #E3E9EC; border-radius: 12px;
             padding: .85rem 1rem; margin-top: .8rem; }}
.conf-top {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; font-size: .88rem;
            color: #42525C; }}
.conf-top b {{ font-weight: 700; color: {PIZARRA}; text-transform: capitalize; }}
.conf-barra {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: .55rem 0 .6rem; }}
.conf-barra span {{ height: 7px; border-radius: 4px; background: #DCE3E7; }}
.conf-barra span.on {{ background: linear-gradient(90deg, {MIEL}, {AMBAR}); }}
.conf-barra.alta span.on {{ background: linear-gradient(90deg, #4BB37E, {VERDE}); }}
.conf-items {{ display: flex; flex-wrap: wrap; gap: .35rem; font-size: .8rem; }}
.conf-items span {{ border-radius: 999px; padding: .1rem .6rem; border: 1px solid; }}
.conf-items .si {{ color: {VERDE}; background: #EAF5EE; border-color: #C5E3D0; }}
.conf-items .no {{ color: #6B7A85; background: #fff; border-color: #D9E0E5; border-style: dashed; }}
.conf-items .si::before {{ content: "✓ "; font-weight: 700; }}

/* =====================================================================  resultados */
.res-titulo {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; font-size: 1.4rem;
              color: {PETROLEO}; margin: 0; line-height: 1.2; letter-spacing: -.005em; }}
.res-ficha {{ color: #5B6B76; font-size: .92rem; margin: .3rem 0 .1rem; }}
.etq {{ display: inline-block; background: #fff; border: 1px solid #D9E0E5; color: #34434D;
       border-radius: 999px; padding: 1px 10px; margin: 2px 4px 2px 0; font-size: .79rem; }}
.etq.nsf {{ background: #EAF5EE; border-color: #C5E3D0; color: {VERDE}; }}

/* mejor opción: tablero oscuro */
.mejor {{ background:
          radial-gradient(70% 90% at 0% 0%, rgba(234,181,78,.14), rgba(234,181,78,0) 60%),
          linear-gradient(160deg, #123B48 0%, {PETROLEO} 45%, #081E26 100%);
         color: #E8F0F2; border-radius: 20px; position: relative; overflow: hidden;
         box-shadow: 0 2px 4px rgba(13,44,54,.12), 0 24px 48px -24px rgba(8,30,38,.65);
         padding: 1.5rem 1.6rem 1.35rem; margin: .7rem 0 1.4rem; }}
.mejor::before {{ content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px;
                  background: linear-gradient(90deg, {MIEL}, {AMBAR} 50%, {ACEITE_OSC}); }}
.mejor-top {{ display: flex; gap: 1.6rem; align-items: center; flex-wrap: wrap; }}
.mejor-info {{ flex: 1 1 260px; min-width: 0; }}
.lugar {{ color: {AMBAR_OSC}; font-weight: 600; font-size: .9rem; margin-bottom: .15rem; }}
.mejor .lugar {{ color: {MIEL}; }}
.codigo {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; color: {PIZARRA};
          font-size: 1.9rem; line-height: 1.08; word-break: break-word; letter-spacing: -.01em; }}
.mejor .codigo {{ color: #fff; font-size: 2.3rem; margin-bottom: .35rem; }}
.mejor .etq {{ background: rgba(255,255,255,.07); border-color: rgba(255,255,255,.16); color: #D3E0E5; }}
.mejor .etq.nsf {{ background: rgba(69,196,134,.14); border-color: rgba(69,196,134,.4); color: #8FE0B6; }}
.veredicto {{ font-weight: 600; }}
.mejor .veredicto {{ display: inline-flex; align-items: center; gap: .4rem; font-size: .95rem; margin-top: .55rem;
                    padding: .25rem .75rem; border-radius: 999px; background: rgba(255,255,255,.08); }}
.mejor table.props {{ margin-top: 1.1rem; }}
.mejor table.props th {{ background: rgba(255,255,255,.05); color: #9DB3BB; border-bottom-color: rgba(255,255,255,.1); }}
.mejor table.props td {{ color: #E8F0F2; border-bottom-color: rgba(255,255,255,.07); }}
.mejor table.props .nota {{ color: #9DB3BB; }}
.mejor .dot.ok {{ color: #5FD39A; }} .mejor .dot.mid {{ color: #F2B441; }} .mejor .dot.bad {{ color: #F48C80; }}
.mejor .aviso.ambar {{ background: rgba(242,180,65,.1); border-color: rgba(242,180,65,.35); color: #F7D79B; }}
.mejor .aviso.info {{ background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.16); color: #CFE0E5; }}

/* otras opciones */
.otros-titulo {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; color: {PETROLEO};
                font-size: 1.1rem; margin: .3rem 0 .6rem; }}
.fila {{ background: #fff; border: 1px solid #E1E7EB; border-radius: 14px; padding: .95rem 1.2rem .85rem;
        margin-bottom: .65rem; box-shadow: 0 1px 2px rgba(13,44,54,.04), 0 10px 24px -22px rgba(13,44,54,.4); }}
.fila-top {{ display: grid; grid-template-columns: 2.1rem minmax(0, 1fr) 220px; gap: 1rem; align-items: center; }}
.fila .num {{ display: grid; place-items: center; width: 2.1rem; height: 2.1rem; border-radius: 50%;
             background: #EEF2F4; color: {PETROLEO}; font-family: 'IBM Plex Sans Condensed', sans-serif;
             font-weight: 700; font-size: 1rem; }}
.fila .codigo {{ font-size: 1.25rem; margin-bottom: .2rem; }}
.medidor {{ display: grid; gap: .35rem; }}
.medidor-top {{ display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; }}
.medidor .pct {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; font-size: 1.3rem;
                font-variant-numeric: tabular-nums; color: {PIZARRA}; }}
.medidor .veredicto {{ font-size: .8rem; }}
.pista {{ position: relative; height: 10px; border-radius: 999px; background: #E6EBEE; overflow: hidden;
         box-shadow: inset 0 1px 2px rgba(13,44,54,.08); }}
.pista > span {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px;
                background-image: linear-gradient(180deg, rgba(255,255,255,.25), rgba(255,255,255,0)) !important; }}
.pista::after {{ content: ""; position: absolute; left: 75%; top: 0; bottom: 0; width: 2px; background: rgba(13,44,54,.4); }}
details.mas summary {{ cursor: pointer; color: {PETROLEO}; font-size: .85rem; font-weight: 600; margin-top: .6rem;
                      list-style-position: inside; width: fit-content; }}
details.mas summary:hover {{ color: {AMBAR_OSC}; }}
details.ayuda summary {{ list-style: none; color: #5B6B76; font-weight: 500; font-size: .82rem; margin-top: .25rem; }}
details.ayuda summary::-webkit-details-marker {{ display: none; }}
details.ayuda summary::before {{ content: "?"; display: inline-grid; place-items: center; width: 1.1rem; height: 1.1rem;
  border-radius: 50%; background: #E6EBEE; color: {PETROLEO}; font-size: .7rem; font-weight: 700; margin-right: .45rem; }}
details.ayuda summary:hover::before {{ background: #FBF1DC; color: {AMBAR_OSC}; }}
details.ayuda p {{ margin: .35rem 0 0; max-width: 62ch; }}
.mejor details.mas summary {{ color: {MIEL}; margin-top: 1.05rem; }}
.mejor details.mas summary:hover {{ color: #fff; }}
.mejor details.mas table.props {{ margin-top: .7rem; }}
.nuevo details.mas summary {{ margin-top: 1.05rem; font-size: .93rem; }}
.nuevo details.ayuda summary {{ margin-top: .3rem; font-size: .82rem; }}
details.mas summary:focus-visible {{ outline: 2px solid {AMBAR}; outline-offset: 2px; border-radius: 3px; }}

/* tablas: quitar los bordes por defecto de Streamlit */
.stApp table.props th, .stApp table.props td, .stApp table.req th, .stApp table.req td,
.stApp table.comp th, .stApp table.comp td {{ border-top: 0; border-left: 0; border-right: 0; }}
.stApp table.props, .stApp table.comp {{ border: 0; }}

/* tabla de propiedades */
table.props {{ width: 100%; border-collapse: separate; border-spacing: 0; margin-top: .85rem; font-size: .9rem;
              border-radius: 10px; overflow: hidden; }}
table.props th {{ text-align: left; font-weight: 600; color: #5B6B76; font-size: .78rem; background: #F4F7F8;
                 border-bottom: 1px solid #E1E7EB; padding: .45rem .6rem; }}
table.props td {{ padding: .5rem .6rem; border-bottom: 1px solid #EEF2F4; vertical-align: top; }}
table.props tr:last-child td {{ border-bottom: none; }}
table.props td.v {{ font-variant-numeric: tabular-nums; }}
table.props .nota {{ display: block; color: #7A8A95; font-size: .8rem; }}
.dot {{ display: inline-flex; align-items: center; gap: .4rem; font-weight: 600; font-size: .82rem; white-space: nowrap; }}
.dot::before {{ content: ""; width: .55rem; height: .55rem; border-radius: 50%; background: currentColor;
               box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 18%, transparent); }}
.dot.ok {{ color: {VERDE}; }} .dot.mid {{ color: {AMBAR_OSC}; }} .dot.bad {{ color: {ROJO}; }}

.aviso {{ border-radius: 10px; padding: .7rem .95rem; font-size: .9rem; margin: .6rem 0 0; line-height: 1.45;
         border: 1px solid; }}
.aviso.ambar {{ background: #FCF5E6; border-color: #EED7A6; color: #5E3F00; }}
.aviso.info {{ background: #EDF4F6; border-color: #CCDDE2; color: {PETROLEO}; }}
.aviso.rojo {{ background: #FCEEEC; border-color: #EFC7C2; color: #8A2620; }}
.resumen {{ color: #6B7A85; font-size: .84rem; margin: .5rem 0 .4rem; }}

/* estado vacío */
.st-key-vacio {{ border: 1.5px dashed #C3CED5; border-radius: 18px; padding: 1.6rem 1.5rem 1.4rem;
                 background: linear-gradient(180deg, rgba(255,255,255,.75), rgba(255,255,255,.4)); }}
.vacio-cabeza {{ display: flex; gap: 1rem; align-items: center; margin-bottom: .4rem; }}
.vacio-cabeza svg {{ flex: none; filter: drop-shadow(0 6px 10px rgba(212,146,15,.35)); }}
.vacio b {{ display: block; color: {PETROLEO}; font-family: 'IBM Plex Sans Condensed', sans-serif;
           font-size: 1.4rem; font-weight: 600; }}
.vacio p {{ color: #5B6B76; margin: .15rem 0 0; font-size: .93rem; }}
.st-key-vacio button {{ background: #fff; border: 1px solid #DDE4E8; border-radius: 14px; min-height: 4.6rem;
                       padding: .8rem 1rem; justify-content: flex-start;
                       box-shadow: 0 1px 2px rgba(13,44,54,.04); transition: border-color .15s ease, box-shadow .15s ease; }}
.st-key-vacio button > div, .st-key-vacio button > div > span {{ display: flex; justify-content: flex-start; width: 100%; }}
.st-key-vacio button [data-testid="stMarkdownContainer"] {{ overflow: visible; text-align: left; width: 100%; }}
.st-key-vacio button p {{ font-size: .86rem; text-align: left; white-space: normal; color: #5B6B76; line-height: 1.45; }}
.st-key-vacio button p strong {{ color: {PETROLEO}; font-size: .96rem; }}
.st-key-vacio button:hover {{ border-color: {AMBAR}; box-shadow: 0 0 0 3px rgba(212,146,15,.14); }}

/* producto nuevo: ficha de desarrollo */
.nuevo {{ background: repeating-linear-gradient(135deg, #FFFDF8 0 14px, #FFF9EC 14px 28px);
         border: 1.5px dashed {AMBAR}; border-radius: 18px; padding: 1.4rem 1.5rem 1.3rem; margin: .7rem 0 .9rem; }}
.nuevo-tag {{ display: inline-flex; align-items: center; gap: .35rem; background: {AMBAR}; color: #fff;
             border-radius: 999px; padding: .15rem .7rem; font-size: .78rem; font-weight: 600; margin-bottom: .5rem; }}
.nuevo h3 {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600; font-size: 1.55rem;
            color: {PIZARRA}; margin: 0 0 .3rem; padding: 0; }}
.nuevo .intro {{ color: #3D4B55; font-size: .93rem; margin: 0 0 .5rem; max-width: 70ch; }}
.nuevo h4 {{ font-size: .93rem; font-weight: 600; color: {PETROLEO}; margin: 1.1rem 0 .4rem; padding: 0; }}
.nuevo ul {{ margin: 0; padding-left: 1.15rem; }} .nuevo li {{ margin: .25rem 0; font-size: .92rem; }}
.nuevo li::marker {{ color: {AMBAR}; }}
table.req {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: .9rem; background: #fff;
            border: 1px solid #EEDDB8; border-radius: 10px; overflow: hidden; }}
table.req th {{ text-align: left; font-weight: 500; color: #5B6B76; width: 45%; padding: .42rem .65rem;
               border-bottom: 1px solid #F3E8D0; vertical-align: top; }}
table.req td {{ padding: .42rem .65rem; border-bottom: 1px solid #F3E8D0; }}
table.req tr:last-child th, table.req tr:last-child td {{ border-bottom: none; }}
.base {{ display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; }}
.base .codigo-base {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; font-size: 1.3rem; }}

/* comparación lado a lado */
table.comp {{ width: 100%; border-collapse: collapse; font-size: .86rem; background: #fff; }}
table.comp th, table.comp td {{ padding: .5rem .7rem; border-bottom: 1px solid #EDF1F3; text-align: left; }}
table.comp thead th {{ white-space: nowrap; font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 600;
                       color: {PIZARRA}; font-size: .98rem; border-bottom: 2px solid #D3DCE1; }}
table.comp tbody th {{ font-weight: 500; color: #5B6B76; }}
table.comp .ficha {{ background: #FCF5E6; }}
table.comp thead th.ficha {{ color: {AMBAR_OSC}; }}
table.comp tbody tr:hover td, table.comp tbody tr:hover th {{ background: #F5F8F9; }}
table.comp tbody tr:hover td.ficha {{ background: #F8ECD2; }}
.comp-wrap {{ overflow-x: auto; }}

/* manómetro */
.gauge {{ flex: none; text-align: center; }}
.gauge svg {{ display: block; margin: 0 auto; overflow: visible; }}
.gauge .g-num {{ font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; font-size: 2.4rem;
                line-height: 1; color: {PIZARRA}; margin-top: .2rem; font-variant-numeric: tabular-nums; }}
.gauge .g-txt {{ color: #5B6B76; font-size: .8rem; }}
.mejor .gauge .g-num {{ color: #fff; }} .mejor .gauge .g-txt {{ color: #9DB3BB; }}
.gauge .needle {{ transform-origin: 60px 62px; transform: rotate(var(--rot));
                  animation: barrido .8s cubic-bezier(.2,.8,.25,1); }}
@keyframes barrido {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(var(--rot)); }} }}
@media (prefers-reduced-motion: reduce) {{ .gauge .needle {{ animation: none; }} }}

/* botones */
.stDownloadButton button {{ background: {PETROLEO}; color: #fff; border: none; border-radius: 10px;
                           min-height: 2.6rem; padding: 0 1.1rem; box-shadow: 0 6px 14px -8px rgba(13,44,54,.6); }}
.stDownloadButton button:hover {{ background: #144252; color: #fff; }}
.stDownloadButton button p {{ color: #fff; font-weight: 600; }}
.st-key-limpiar button {{ color: #5B6B76; justify-content: flex-end; }}
.st-key-limpiar button:hover {{ color: {AMBAR_OSC}; }}
.st-key-cabeza_panel [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap; align-items: center; }}
.st-key-cabeza_panel [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; flex: 1 1 auto; }}
[data-testid="stRadioOption"]:not(:has(input:checked)) > div > div:first-child {{
  box-shadow: inset 0 0 0 1.5px #8C9AA4; border-radius: 50%; }}

/* pie */
.pie {{ display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; color: #7A8A95;
       font-size: .8rem; border-top: 1px solid #D9E0E5; margin-top: 1.6rem; padding-top: 1rem; }}

/* =====================================================================  ritmo editorial y estados */
:focus-visible {{ outline: 2px solid {AMBAR} !important; outline-offset: 2px; }}

/* otras opciones: listado con líneas finas, no tarjetas iguales */
.otros-titulo {{ margin: 1.6rem 0 0; padding-bottom: .55rem; border-bottom: 2px solid {PETROLEO}; }}
.fila {{ background: transparent; border: 0; border-bottom: 1px solid #D3DCE1; border-radius: 0; box-shadow: none;
        padding: 1rem .5rem .9rem; margin: 0; transition: background-color .15s ease; }}
.fila:hover {{ background: rgba(255,255,255,.7); }}
.fila-top {{ grid-template-columns: 2.4rem minmax(0, 1fr) 230px; }}
.fila .num {{ background: none; width: auto; height: auto; border-radius: 0; justify-content: start;
             font-size: 1.7rem; font-weight: 600; color: #A3B1BA; line-height: 1; }}
.fila:hover .num {{ color: {AMBAR}; }}
.fila .codigo {{ font-size: 1.3rem; }}
.medidor .pct {{ font-size: 1.45rem; }}

/* ejemplos del estado vacío: lista vertical */
.st-key-vacio [data-testid="stHorizontalBlock"] {{ flex-direction: column !important; flex-wrap: nowrap !important; gap: .5rem !important; }}
.st-key-vacio [data-testid="stColumn"] {{ width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important; }}
.st-key-vacio button {{ min-height: 3.6rem; border-radius: 10px; border-left: 4px solid #D6DEE3; box-shadow: none;
                       padding: .65rem 1rem; transition: border-color .15s ease, background-color .15s ease; }}
.st-key-vacio button:hover {{ border-color: #DDE4E8; border-left-color: {AMBAR}; background: #FFFDF8; box-shadow: none; }}
.st-key-vacio button:active {{ background: #FBF1DC; }}

/* avisos: barra lateral de color */
.aviso {{ border-width: 0 0 0 4px; border-radius: 4px 10px 10px 4px; padding: .7rem 1rem; }}
.aviso.ambar {{ border-color: {AMBAR}; }} .aviso.info {{ border-color: #7FA3AF; }} .aviso.rojo {{ border-color: {ROJO}; }}
.mejor .aviso.ambar {{ border-color: {MIEL}; }} .mejor .aviso.info {{ border-color: rgba(255,255,255,.4); }}

/* paneles: sombra más discreta, el tablero oscuro es el que manda */
.st-key-panel_ficha, .st-key-panel_catalogo {{ box-shadow: 0 1px 2px rgba(13,44,54,.05); }}

/* botones y desplegables: estados */
.stDownloadButton button {{ transition: background-color .15s ease, transform .1s ease; }}
.stDownloadButton button:active {{ transform: translateY(1px); }}
details.mas summary {{ transition: color .15s ease; }}
[data-testid="stExpander"] summary:hover {{ color: {AMBAR_OSC}; }}

@media (max-width: 640px) {{
  .hero {{ padding: 1.6rem 1.25rem 3.5rem; }} .hero h1 {{ font-size: 1.9rem; }}
  .logo {{ margin-bottom: 1.1rem; }} .logo .emblema {{ width: 46px; height: 46px; }}
  .logo-nombre {{ font-size: 1.6rem; }} .hero p {{ font-size: .98rem; }}
  .codigo {{ font-size: 1.45rem; }} .mejor .codigo {{ font-size: 1.8rem; }}
  .mejor {{ padding: 1.2rem 1.1rem 1.1rem; }}
  .fila-top {{ grid-template-columns: 2rem minmax(0, 1fr); }}
  .fila-top .medidor {{ grid-column: 1 / -1; }}
  .st-key-panel_ficha, .st-key-panel_catalogo {{ padding: 1rem .9rem 1.1rem !important; }}
  div[data-testid="stButtonGroup"] button {{ padding: 0 .35rem !important; }}
  div[data-testid="stButtonGroup"] button p {{ font-size: .8rem !important; }}
}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ utilidades

def e(x):
    return html.escape(str(x))


def nota(texto, tipo="info"):
    st.markdown(f'<div class="aviso {tipo}">{texto}</div>', unsafe_allow_html=True)


def color_puntaje(p):
    return VERDE if p >= 0.75 else (AMBAR if p >= 0.5 else ROJO)


def color_claro(p):
    """Mismos cortes que color_puntaje, en tonos que se leen sobre el tablero oscuro."""
    return "#5FD39A" if p >= 0.75 else ("#F2B441" if p >= 0.5 else "#F48C80")


def veredicto(p):
    if p >= 0.75:
        return "Sustituto directo"
    if p >= 0.5:
        return "Sustituto con ajustes"
    return "Revisar antes de usarlo"


def titular(p):
    if p >= 0.75:
        return "Te recomendamos"
    if p >= 0.5:
        return "La opción más cercana"
    return "Lo más parecido, con reservas"


def _punto(cx, cy, r, frac):
    """Punto del arco (0 = izquierda, 1 = derecha) a radio r."""
    ang = math.pi * (1 - frac)
    return cx + r * math.cos(ang), cy - r * math.sin(ang)


def manometro(p, ancho=170, oscuro=False):
    """Medidor semicircular del parecido (0 a 100 %) estilo manómetro: bisel de acero, escala cada 10 % y
    marca en 75 % (desde ahí es sustituto directo). `oscuro` lo dibuja para el tablero de la mejor opción."""
    pct = int(round(max(0.0, min(1.0, p)) * 100))
    col = color_claro(p) if oscuro else color_puntaje(p)
    pista = "rgba(255,255,255,.1)" if oscuro else "#E3E8EB"
    tick = "rgba(255,255,255,.45)" if oscuro else "#8D9BA5"
    aguja = "#FFFFFF" if oscuro else PIZARRA
    marca75 = "#5FD39A" if oscuro else VERDE
    arco = "M14 62 A46 46 0 0 1 106 62"
    escala = ""
    for n in range(0, 11):
        frac = n / 10
        largo = 7 if n in (0, 5, 10) else 4
        x1, y1 = _punto(60, 62, 35, frac)
        x2, y2 = _punto(60, 62, 35 - largo, frac)
        escala += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{tick}" '
                   f'stroke-width="{1.6 if largo == 7 else 1}" stroke-linecap="round"/>')
    x1, y1 = _punto(60, 62, 35, 0.75)
    x2, y2 = _punto(60, 62, 27, 0.75)
    escala += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{marca75}" stroke-width="2"/>'
    gid = "acero-o" if oscuro else "acero"
    acero = (('<stop offset="0" stop-color="#4A6873"/><stop offset=".5" stop-color="#C9D6DB"/>'
              '<stop offset="1" stop-color="#3D5964"/>') if oscuro else
             ('<stop offset="0" stop-color="#B9C3CA"/><stop offset=".5" stop-color="#EEF2F4"/>'
              '<stop offset="1" stop-color="#9AA7B0"/>'))
    brillo = (f'<path d="{arco}" fill="none" stroke="{col}" stroke-width="16" pathLength="100" opacity=".18" '
              f'stroke-dasharray="{max(pct, 0.5)} 100" filter="url(#difuso)"/>') if oscuro else ""
    difuso = ('<filter id="difuso" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/>'
              '</filter>') if oscuro else ""
    return (
        f'<div class="gauge"><svg viewBox="0 0 120 70" width="{ancho}" role="img" '
        f'aria-label="{pct} por ciento de parecido">'
        f'<defs><linearGradient id="{gid}" x1="0" x2="1">{acero}</linearGradient>{difuso}</defs>'
        f'<path d="M4 62 A56 56 0 0 1 116 62" fill="none" stroke="url(#{gid})" stroke-width="3.5" stroke-linecap="round"/>'
        f'<path d="{arco}" fill="none" stroke="{pista}" stroke-width="9" pathLength="100"/>{brillo}'
        f'<path d="{arco}" fill="none" stroke="{col}" stroke-width="9" pathLength="100" '
        f'stroke-dasharray="{max(pct, 0.5)} 100"/>{escala}'
        f'<g class="needle" style="--rot:{pct * 1.8:.1f}deg"><path d="M60 59.6 L24 62 L60 64.4 Z" fill="{aguja}"/></g>'
        f'<circle cx="60" cy="62" r="6" fill="{aguja}"/><circle cx="60" cy="62" r="2.6" fill="{AMBAR}"/>'
        f'</svg><div class="g-num">{pct}%</div><div class="g-txt">de parecido</div></div>'
    )


def medidor_barra(p):
    """Barra horizontal del parecido; la rayita marca el 75 % (sustituto directo)."""
    pct = int(round(max(0.0, min(1.0, p)) * 100))
    col = color_puntaje(p)
    return (f'<div class="medidor" role="img" aria-label="{pct} por ciento de parecido">'
            f'<div class="medidor-top"><span class="pct">{pct}%</span>'
            f'<span class="veredicto" style="color:{col}">{veredicto(p)}</span></div>'
            f'<div class="pista"><span style="width:{max(pct, 1)}%;background:{col}"></span></div></div>')


def etiquetas_producto(fila):
    """Etiquetas cortas con lo que identifica a un producto (espesante, base, NLGI, viscosidad, temperatura, NSF)."""
    out = []
    if pd.notna(fila.get("espesante")):
        out.append(str(fila["espesante"]))
    if pd.notna(fila.get("aceite_base")):
        out.append(f"base {fila['aceite_base']}")
    n = fila.get("nlgi")
    if pd.isna(n):
        n = fila.get("grado_nlgi_por_penetracion")
    if pd.isna(n):
        n = fila.get("grado_nlgi_consistencia")
    if pd.notna(n):
        out.append("NLGI " + {-2: "000", -1: "00"}.get(n, f"{n:g}"))
    visc = fila.get("viscosidad_a_40c_cst")
    if pd.isna(visc):
        visc = fila.get("viscosidad_del_aceite_base_a_40c_cst")
    if pd.notna(visc):
        out.append(f"{visc:g} cSt")
    lo, hi = fila.get("temperatura_de_servicio_c_min"), fila.get("temperatura_de_servicio_c_max")
    if pd.notna(lo) or pd.notna(hi):
        out.append(R._rango(lo, hi))
    html_ = "".join(f'<span class="etq">{e(t)}</span>' for t in out)
    if fila.get("tiene_registro_nsf") in (True, np.True_):
        html_ += '<span class="etq nsf">grado alimenticio NSF</span>'
    return html_


def tabla_props(detalle):
    clase = {"✓": ("ok", "Igual o mejor"), "~": ("mid", "Algo distinto"), "✗": ("bad", "Muy distinto")}
    filas = ""
    for d in detalle:
        c, txt = clase.get(d["marca"], ("mid", d["marca"]))
        extra = f'<span class="nota">{e(d["nota"])}</span>' if d.get("nota") else ""
        prop = str(d["propiedad"])
        filas += (f'<tr><td>{e(prop[:1].upper() + prop[1:])}</td><td class="v">{e(d["ficha"])}</td>'
                  f'<td class="v">{e(d["interlub"])}{extra}</td><td><span class="dot {c}">{txt}</span></td></tr>')
    if not filas:
        return '<p class="panel-sub">No hubo propiedades en común para comparar.</p>'
    return ('<table class="props"><thead><tr><th>Propiedad</th><th>Tu ficha</th><th>Interlub</th><th>Resultado</th>'
            f'</tr></thead><tbody>{filas}</tbody></table>')


def avisos_producto(fila):
    out = ""
    if fila.get("advertencias"):
        out += f'<div class="aviso ambar">{e(fila["advertencias"])}</div>'
    if fila["cobertura"] < 0.6:
        out += (f'<div class="aviso info">Solo se pudo comparar el {fila["cobertura"] * 100:.0f}% de los datos de '
                'tu ficha. Confírmalo con la ficha completa del producto.</div>')
    return out


# ------------------------------------------------------------------ datos

@st.cache_data(show_spinner=False)
def leer_catalogo(origen, firma):
    """origen: ruta o bytes del CSV. `firma` hace que se relea si el archivo cambia."""
    return pd.read_csv(BytesIO(origen) if isinstance(origen, bytes) else origen)


def catalogo_local():
    if CATALOGO.exists():
        return leer_catalogo(str(CATALOGO), CATALOGO.stat().st_mtime)
    return None


def catalogo_subido():
    archivo = st.file_uploader("Catálogo de productos Interlub (DATOS_TEC_clean.csv)", type="csv", key="catalogo")
    if archivo is None:
        return None
    df = leer_catalogo(archivo.getvalue(), archivo.size)
    faltan = {"codigoproducto", "familia"} - set(df.columns)
    if faltan:
        nota(f"A ese archivo le faltan las columnas {', '.join(sorted(faltan))}. Sube DATOS_TEC_clean.csv, "
             "el que sale de notebooks/01_limpieza.ipynb.", "rojo")
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


# ------------------------------------------------------------------ estado: ejemplos y limpiar

def limpiar():
    for k in CAMPOS:
        st.session_state.pop(k, None)


def cargar_ejemplo(nombre):
    limpiar()
    st.session_state["modo"] = MODOS[0]
    for k, v in EJEMPLOS[nombre]["valores"].items():
        st.session_state[k] = v


# ------------------------------------------------------------------ entrada de la ficha

GOTA_SVG = ('<svg viewBox="0 0 12 16" aria-hidden="true"><path d="M6 1C8.2 4.2 11 7 11 10a5 5 0 0 1-10 0C1 7 '
            '3.8 4.2 6 1z" fill="currentColor"/></svg>')


def ayuda(titulo, texto):
    """Explicación que queda plegada hasta que alguien la pide."""
    return f'<details class="mas ayuda"><summary>{titulo}</summary><p class="panel-sub">{texto}</p></details>'


def grupo(texto):
    st.markdown(f'<div class="grupo"><span class="g-gota">{GOTA_SVG}</span>{texto}</div>', unsafe_allow_html=True)


def numero(etiqueta, clave, paso, **kw):
    return st.number_input(etiqueta, value=None, step=paso, key=clave, placeholder="Vacío", format="%g", **kw)


def campo_con_tipo(etiqueta, clave, paso=1.0):
    """Número opcional + si la ficha lo da como valor exacto, mínimo (>) o máximo (<)."""
    c1, c2 = st.columns([3, 2])
    with c1:
        valor = numero(etiqueta, f"{clave}_v", paso)
    tipo = c2.selectbox("Cómo lo dice", ["Exacto", "Al menos (>)", "Menos de (<)"], key=f"{clave}_t")
    return valor, {"Exacto": "=", "Al menos (>)": ">", "Menos de (<)": "<"}[tipo]


def confianza(ficha, es_grasa):
    """Qué tan confiable será la comparación según los datos clave que trae la ficha."""
    claves = [("Temperatura", pd.notna(ficha.get("temperatura_de_servicio_c_max"))
               or pd.notna(ficha.get("temperatura_de_servicio_c_min"))),
              ("Viscosidad", pd.notna(ficha.get("viscosidad_del_aceite_base_a_40c_cst"))
               or pd.notna(ficha.get("viscosidad_a_40c_cst")))]
    if es_grasa:
        claves.insert(0, ("NLGI", pd.notna(ficha.get("grado_nlgi_por_penetracion"))))
    n = sum(ok for _, ok in claves)
    total = len(claves)
    nivel = "alta" if n == total else ("media" if n >= total - 1 and n > 0 else "baja")
    encendidas = {"alta": 3, "media": 2, "baja": 1 if n else 0}[nivel]
    barra = "".join(f'<span class="{"on" if i < encendidas else ""}"></span>' for i in range(3))
    items = "".join(f'<span class="{"si" if ok else "no"}">{e(nombre)}</span>' for nombre, ok in claves)
    consejo = {"alta": "Tienes los datos clave.",
               "media": "Agrega el dato que falta para afinar el resultado.",
               "baja": "Con pocos datos el resultado es solo orientativo."}[nivel]
    return (f'<div class="confianza" title="{consejo}"><div class="conf-top"><span>Confianza de la comparación: <b>{nivel}</b></span>'
            f'</div><div class="conf-barra {nivel}">{barra}</div><div class="conf-items">{items}</div></div>')


def formulario(cat):
    """Panel de datos. Devuelve la ficha apenas hay algún dato técnico: las recomendaciones salen solas."""
    nombre = st.text_input("Producto que quieres sustituir", placeholder="Ej. Mobilith SHC 460", key="nombre")
    if st.session_state.get("familia") not in ("grasa", "aceite"):
        st.session_state["familia"] = "grasa"
    familia = st.segmented_control("Tipo de producto", ["grasa", "aceite"], key="familia",
                                   format_func=str.capitalize, width="stretch") or "grasa"
    es_grasa = familia == "grasa"

    espesante = nlgi = NO_SE
    if es_grasa:
        grupo("Consistencia y composición")
        a, b = st.columns(2)
        nlgi = a.selectbox("Grado NLGI", [NO_SE, *NLGI], key="nlgi",
                           help="Qué tan dura es la grasa: 000 es casi líquida y 6 es la más dura.")
        espesante = b.selectbox("Espesante", [NO_SE, *opciones(cat, "espesante")], key="espesante")
    else:
        grupo("Composición")
    a, b = st.columns(2)
    base = a.selectbox("Aceite base", [NO_SE, *opciones(cat, "aceite_base")], key="aceite_base")
    with b:
        visc = numero("Viscosidad a 40 °C (cSt)", "visc", 10.0, min_value=0.0, help="En grasas, la del aceite base.")

    grupo("Temperatura de uso")
    a, b = st.columns(2)
    with a:
        tmin = numero("Mínima (°C)", "tmin", 5.0)
    with b:
        tmax = numero("Máxima (°C)", "tmax", 5.0)
    nsf = st.checkbox("Es grado alimenticio (NSF H1)", key="nsf",
                      help="Solo se recomiendan productos Interlub con registro NSF.")

    with st.expander("Pruebas de desempeño (opcional)", icon=":material/science:"):
        gota, gota_t = campo_con_tipo("Punto de gota (°C)", "gota", paso=10.0)
        sold, sold_t = campo_con_tipo("Soldadura 4 bolas (kgf)", "sold", paso=10.0)
        desg, desg_t = campo_con_tipo("Desgaste 4 bolas (mm)", "desg", paso=0.05)
        timken, timken_t = campo_con_tipo("Carga Timken OK (lb)", "timken", paso=5.0)
        flama, flama_t = campo_con_tipo("Punto de flama (°C)", "flama", paso=10.0)
        ivis, ivis_t = campo_con_tipo("Índice de viscosidad", "ivis", paso=5.0)

    d = {"nombre_producto": nombre.strip() or "tu ficha", "familia": familia}
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
    hay = bool(datos or nsf)
    if hay:
        st.markdown(confianza(ficha, es_grasa), unsafe_allow_html=True)
    return ficha if hay else None


def subir_json():
    archivo = st.file_uploader("JSON de la ficha técnica", type="json", key="json",
                               help="El que devuelve la IA al leer el PDF con el prompt de scripts/prompts/extraccion_pdfs.md")
    if archivo is None:
        st.markdown(ayuda("¿Qué archivo subo?", "Sube el JSON que sacó la IA del PDF. Si trae varios productos, "
                          "eliges cuál comparar."), unsafe_allow_html=True)
        return None
    try:
        registros = json.load(archivo)
        fichas = F.normalizar([registros] if isinstance(registros, dict) else registros)
    except Exception as err:  # noqa: BLE001 - cualquier problema de formato se explica sin tumbar la página
        nota(f"Ese archivo no tiene el formato esperado ({e(err)}). Revisa que sea la lista JSON que devolvió "
             "la IA, sin texto antes ni después.", "rojo")
        return None
    fichas = fichas.sort_values("vigente", ascending=False, kind="stable").reset_index(drop=True)
    vigente = dict(zip(fichas["nombre_producto"], fichas["vigente"]))
    nombre = st.selectbox("Producto de la ficha", fichas["nombre_producto"], key="json_producto",
                          format_func=lambda n: n + ("" if vigente[n] else " (reemplazado)"))
    return fichas.loc[fichas["nombre_producto"] == nombre].iloc[0]


def producto_interlub(cat):
    if cat is None:
        st.markdown('<p class="panel-sub">Para la autoprueba hace falta el catálogo de Interlub.</p>',
                    unsafe_allow_html=True)
        return None
    cod = st.selectbox("Producto Interlub", cat["codigoproducto"].astype(str), key="prueba")
    st.markdown(ayuda("¿Para qué sirve?", "Sirve para revisar el recomendador: el mismo producto debe salir en "
                      "primer lugar."), unsafe_allow_html=True)
    ficha = cat.loc[cat["codigoproducto"].astype(str) == cod].iloc[0].copy()
    ficha["nombre_producto"] = cod
    return ficha


# ------------------------------------------------------------------ resultados

def tarjeta_mejor(fila, info):
    p = float(fila["puntaje"])
    return (
        '<div class="mejor"><div class="mejor-top">'
        f'{manometro(p, 190, oscuro=True)}'
        f'<div class="mejor-info"><div class="lugar">{titular(p)}</div>'
        f'<div class="codigo">{e(fila["codigoproducto"])}</div>'
        f'<div>{etiquetas_producto(info)}</div>'
        f'<div class="veredicto" style="color:{color_claro(p)}">{veredicto(p)}</div></div></div>'
        f'{avisos_producto(fila)}<details class="mas"><summary>Ver comparación</summary>'
        f'{tabla_props(fila["detalle"])}</details></div>'
    )


def tarjeta_fila(pos, fila, info):
    return (
        '<div class="fila"><div class="fila-top">'
        f'<div class="num">{pos}</div>'
        f'<div><div class="codigo">{e(fila["codigoproducto"])}</div><div>{etiquetas_producto(info)}</div></div>'
        f'{medidor_barra(float(fila["puntaje"]))}</div>'
        f'<details class="mas"><summary>Ver comparación</summary>{tabla_props(fila["detalle"])}'
        f'{avisos_producto(fila)}</details></div>'
    )


def tarjeta_nuevo(ficha, prop, hay_recs):
    intro = ("Ningún producto Interlub cumple con lo que pide la ficha. Esta es la especificación de un producto "
             "nuevo que sí lo haría, para revisarla con el equipo de desarrollo." if not hay_recs else
             "Ningún producto Interlub es un sustituto directo. Si conviene tener uno, esta es la especificación de "
             "un producto nuevo, para revisarla con el equipo de desarrollo.")
    req = "".join(f'<tr><th scope="row">{e(r["propiedad"])}</th><td>{e(r["valor"])}</td></tr>' for r in prop["requisitos"])
    html_ = ('<div class="nuevo"><span class="nuevo-tag">Producto nuevo</span>'
             f'<h3>Especificación para sustituir a {e(ficha["nombre_producto"])}</h3>{ayuda("¿Por qué un producto nuevo?", intro)}'
             f'<h4>Lo que debe cumplir</h4><table class="req"><tbody>{req}</tbody></table>')
    if prop["base"] is not None:
        parecido = (f'<span class="panel-sub">hoy se parece {prop["base_puntaje"] * 100:.0f}%</span>'
                    if prop["base_puntaje"] is not None else "")
        html_ += (f'<h4>De qué producto partir</h4><div class="base"><span class="codigo-base">{e(prop["base"])}</span>'
                  f'{parecido}</div>' + ayuda("¿Por qué este?", "Es el producto Interlub más cercano en lo demás, "
                                                   "así que su fórmula es el mejor punto de partida."))
        if prop["cambios"]:
            html_ += "<h4>Qué hay que cambiarle</h4><ul>" + "".join(f"<li>{e(c)}</li>" for c in prop["cambios"]) + "</ul>"
    if prop["pistas"]:
        html_ += ('<details class="mas"><summary>Qué muestra el catálogo</summary><ul>'
                  + "".join(f"<li>{e(c)}</li>" for c in prop["pistas"]) + "</ul></details>")
    return html_ + "</div>"


def texto_especificacion(ficha, prop):
    """La misma propuesta en texto, para descargarla y compartirla."""
    lineas = [f"Especificación de producto nuevo para sustituir a {ficha['nombre_producto']}", "",
              "Lo que debe cumplir:"]
    lineas += [f"- {r['propiedad']}: {r['valor']}" for r in prop["requisitos"]]
    if prop["base"] is not None:
        lineas += ["", f"Producto Interlub de partida: {prop['base']}"]
        if prop["cambios"]:
            lineas += ["", "Qué hay que cambiarle:"] + [f"- {c}" for c in prop["cambios"]]
    if prop["pistas"]:
        lineas += ["", "Qué muestra el catálogo:"] + [f"- {c}" for c in prop["pistas"]]
    lineas += ["", "Generado por el Recomendador Interlub (reto MA2003B). Validar con el equipo técnico."]
    return "\n".join(lineas)


def mostrar_nuevo(ficha, cat, recs):
    prop = R.propuesta_nuevo(ficha, cat, recs)
    st.markdown(tarjeta_nuevo(ficha, prop, not recs.empty), unsafe_allow_html=True)
    st.download_button("Descargar especificación", texto_especificacion(ficha, prop).encode("utf-8"),
                       file_name="especificacion_producto_nuevo.txt", mime="text/plain", key="desc_nuevo",
                       icon=":material/download:")


def tabla_comparacion(tabla):
    nombres = {
        "familia": "Tipo", "espesante": "Espesante", "aceite_base": "Aceite base", "nlgi": "NLGI",
        "temperatura_de_servicio_c_min": "Temperatura mínima (°C)", "temperatura_de_servicio_c_max": "Temperatura máxima (°C)",
        "viscosidad_del_aceite_base_a_40c_cst": "Viscosidad aceite base 40 °C (cSt)",
        "viscosidad_a_40c_cst": "Viscosidad 40 °C (cSt)", "indice_de_viscosidad": "Índice de viscosidad",
        "punto_de_gota_c": "Punto de gota (°C)", "punto_de_flama_c": "Punto de flama (°C)",
        "punto_de_soldadura_cuatro_bolas_kgf": "Soldadura 4 bolas (kgf)", "desgaste_cuatro_bolas_mm": "Desgaste 4 bolas (mm)",
        "carga_timken_ok_lb": "Timken OK (lb)", "tiene_registro_nsf": "Registro NSF",
    }

    def fmt(x):
        if isinstance(x, (bool, np.bool_)):
            return "Sí" if x else "No"
        if pd.isna(x):
            return "—"
        if isinstance(x, (int, float, np.floating, np.integer)):
            return {-2.0: "000", -1.0: "00"}.get(float(x), f"{x:g}")
        return str(x)

    cols = list(tabla.columns)
    cab = '<th scope="col"></th>' + "".join(
        f'<th scope="col" class="{"ficha" if i == 0 else ""}">{e("Tu ficha" if i == 0 else c)}</th>'
        for i, c in enumerate(cols))
    cuerpo = ""
    for idx, fila in tabla.iterrows():
        celdas = "".join(f'<td class="{"ficha" if i == 0 else ""}">{e(fmt(v))}</td>' for i, v in enumerate(fila))
        cuerpo += f'<tr><th scope="row">{e(nombres.get(idx, idx))}</th>{celdas}</tr>'
    return f'<div class="comp-wrap"><table class="comp"><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table></div>'


def mostrar(ficha, cat):
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    c1.markdown(
        f'<p class="res-titulo">Sustitutos para {e(ficha["nombre_producto"])}</p>'
        f'<div class="res-ficha">{etiquetas_producto(R._con_nlgi(ficha.to_frame().T).iloc[0])}</div>',
        unsafe_allow_html=True,
    )
    with c2:
        k = st.segmented_control("Cuántas opciones ver", [3, 5, 10], default=5, key="k",
                                 format_func=lambda n: f"Top {n}", label_visibility="collapsed") or 5
    recs, avisos = R.recomendar(ficha, cat, k=k)
    n_cand = next((a for a in avisos if a.startswith("Quedan")), "")
    otros = [a for a in avisos if not a.startswith("Quedan")]
    for a in otros:
        nota(e(a), "info")

    if recs.empty:
        nota("Ningún producto Interlub cumple con el tipo de producto, la temperatura de uso y, si aplica, el "
             "grado alimenticio. Abajo está la especificación de un producto nuevo que sí cumpliría.", "ambar")
        mostrar_nuevo(ficha, cat, recs)
        return
    nuevo = R.necesita_nuevo(recs)
    if nuevo:
        nota("Ningún producto es un sustituto directo. Abajo de las opciones está la especificación de un "
             "producto nuevo que sí cumpliría.", "ambar")

    info = R._con_nlgi(cat)
    filas = list(recs.iterrows())
    i0, mejor = filas[0]
    st.markdown(tarjeta_mejor(mejor, info.loc[i0]), unsafe_allow_html=True)
    if len(filas) > 1:
        st.markdown('<div class="otros-titulo">Otras opciones</div>'
                    + "".join(tarjeta_fila(pos, f, info.loc[i]) for pos, (i, f) in enumerate(filas[1:], start=2)),
                    unsafe_allow_html=True)
    if n_cand:
        total = int(n_cand.split()[1])
        txt = (f"Estos son los {total} productos Interlub que pasaron los filtros." if total <= len(recs) else
               f"{total} productos Interlub pasaron los filtros; aquí están los {len(recs)} más parecidos.")
        st.markdown(ayuda("Sobre estos resultados", f"{txt} La rayita de cada barra marca el 75 %, desde donde "
                          "un producto es sustituto directo."), unsafe_allow_html=True)

    if nuevo:
        mostrar_nuevo(ficha, cat, recs)

    with st.expander("Comparar todo lado a lado", icon=":material/table_view:"):
        st.markdown(tabla_comparacion(R.comparar(ficha, cat, recs)), unsafe_allow_html=True)
    csv = (recs.drop(columns="detalle").assign(ficha=ficha["nombre_producto"])
           .to_csv(index=False).encode("utf-8-sig"))
    st.download_button("Descargar recomendaciones (CSV)", csv, file_name="recomendaciones_interlub.csv",
                       mime="text/csv", icon=":material/download:")


def estado_vacio():
    with st.container(key="vacio"):
        st.markdown(
            '<div class="vacio"><div class="vacio-cabeza">'
            f'<svg width="34" height="45" viewBox="0 0 12 16" aria-hidden="true"><path d="M6 1C8.2 4.2 11 7 11 10a5 5 0 '
            f'0 1-10 0C1 7 3.8 4.2 6 1z" fill="{AMBAR}"/></svg>'
            '<div><b>Aquí aparecen los sustitutos</b><p>Llena al menos un dato de la ficha o empieza con un ejemplo:'
            '</p></div></div></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, (nombre, ej) in enumerate(EJEMPLOS.items()):
            cols[i % 2].button(f"**{nombre}**  \n{ej['desc']}", key=f"ej_{i}", on_click=cargar_ejemplo,
                               args=(nombre,), width="stretch")


# ------------------------------------------------------------------ página

# capas de aceite al fondo de la cabecera (tres viscosidades: miel, ámbar y aceite usado)
CAPAS_ACEITE = (
    '<svg class="capas" viewBox="0 0 1440 58" preserveAspectRatio="none" aria-hidden="true">'
    f'<path d="M0 16 C 220 0, 430 32, 680 16 S 1130 2, 1440 18 L1440 58 L0 58 Z" fill="{MIEL}" opacity=".45"/>'
    f'<path d="M0 24 C 260 10, 500 40, 760 24 S 1190 10, 1440 27 L1440 58 L0 58 Z" fill="{AMBAR}" opacity=".9"/>'
    f'<path d="M0 33 C 300 22, 560 46, 820 33 S 1230 22, 1440 36 L1440 58 L0 58 Z" fill="{ACEITE_OSC}"/>'
    '<path d="M0 44 C 320 34, 600 56, 880 44 S 1260 34, 1440 46 L1440 58 L0 58 Z" fill="#EEF1F3"/>'
    '</svg>'
)


EMBLEMA = (
    '<svg class="emblema" viewBox="0 0 64 64" aria-hidden="true"><defs>'
    '<linearGradient id="lgT" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1D5A6E"/>'
    '<stop offset="1" stop-color="#07202A"/></linearGradient>'
    f'<linearGradient id="lgG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{MIEL}"/>'
    f'<stop offset=".55" stop-color="{AMBAR}"/><stop offset="1" stop-color="{ACEITE_OSC}"/></linearGradient>'
    '<clipPath id="lgC"><path d="M32 9C39.5 20 49 28.5 49 39.5a17 17 0 0 1-34 0C15 28.5 24.5 20 32 9z"/></clipPath>'
    '</defs>'
    '<rect x="1.5" y="1.5" width="61" height="61" rx="17" fill="url(#lgT)" stroke="rgba(234,181,78,.6)" '
    'stroke-width="1.5"/>'
    '<path d="M32 9C39.5 20 49 28.5 49 39.5a17 17 0 0 1-34 0C15 28.5 24.5 20 32 9z" fill="url(#lgG)"/>'
    '<g clip-path="url(#lgC)">'
    f'<path d="M10 41C18 34 24 48 32 41S46 34 54 41V62H10z" fill="{ACEITE_OSC}" opacity=".5"/>'
    '<path d="M10 48C18 42 24 55 32 48S46 42 54 48V62H10z" fill="#3A2202" opacity=".45"/></g>'
    '<path d="M24.5 27.5C21.5 32 21 37 22.5 41" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="2.4" '
    'stroke-linecap="round"/></svg>'
)

# ondas de una gota que cae en aceite (adorno de la cabecera)
ONDAS = (
    '<svg class="ondas" viewBox="0 0 560 260" aria-hidden="true">'
    + "".join(
        f'<ellipse cx="280" cy="170" rx="{rx}" ry="{ry}" fill="none" stroke="{MIEL}" stroke-opacity="{op}" '
        'stroke-width="1.6"/>'
        for rx, ry, op in ((46, 11, .55), (92, 22, .4), (142, 34, .28), (196, 47, .18), (254, 61, .09)))
    + f'<path d="M280 62C286 72 294 79 294 88a14 14 0 0 1-28 0C266 79 274 72 280 62z" fill="{MIEL}" opacity=".85"/>'
    '<path d="M274 76C272 80 271.5 84 272.5 87" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="2" '
    'stroke-linecap="round"/></svg>'
)


def cabecera():
    st.markdown(
        '<div class="hero"><div class="hero-texto">'
        f'<div class="logo" role="img" aria-label="Interlub">{EMBLEMA}<span class="logo-nombre">INTERLUB<i></i></span></div>'
        '<h1>Recomendador de sustitutos</h1>'
        '<p>Compara una grasa o aceite con el catálogo de Interlub y encuentra el producto más parecido.</p></div>'
        f'{ONDAS}{CAPAS_ACEITE}</div>',
        unsafe_allow_html=True,
    )


def main():
    cabecera()
    cat = catalogo_local()
    izq, der = st.columns([5, 7], gap="large")

    with izq:
        with st.container(border=True, key="panel_ficha"):
            with st.container(key="cabeza_panel"):
                c1, c2 = st.columns([3, 2], vertical_alignment="center")
                c1.markdown('<p class="panel-titulo">Datos de la ficha</p>', unsafe_allow_html=True)
                c2.button("Limpiar", key="limpiar", on_click=limpiar, icon=":material/restart_alt:", type="tertiary",
                          width="stretch")
            if st.session_state.get("modo") not in MODOS:
                st.session_state["modo"] = MODOS[0]
            modo = st.segmented_control("Cómo quieres dar la ficha", MODOS, key="modo",
                                        label_visibility="collapsed", width="stretch") or MODOS[0]
            if modo == MODOS[0]:
                ficha = formulario(cat)
            elif modo == MODOS[1]:
                ficha = subir_json()
            else:
                ficha = producto_interlub(cat)

    with der:
        if cat is None:
            with st.container(border=True, key="panel_catalogo"):
                st.markdown('<p class="panel-titulo">Falta el catálogo de Interlub</p>'
                            '<p class="panel-sub">Sin él puedes llenar la ficha, pero no hay con qué compararla. '
                            'Súbelo aquí o ponlo en data/processed/ para que se cargue solo.</p>',
                            unsafe_allow_html=True)
                cat = catalogo_subido()
                if cat is not None:
                    st.rerun()

        if ficha is None:
            estado_vacio()
        elif cat is not None:
            mostrar(ficha, cat)

    with st.expander("¿Cómo decide el recomendador?", icon=":material/info:"):
        st.markdown(
            "1. **Descarta** lo que no sirve: otro tipo de producto, los que no aguantan la temperatura de uso "
            "(se toleran 5 °C por arriba y 10 °C por abajo) y, si la ficha es grado alimenticio, los que no tienen NSF.\n"
            "2. **Compara** cada propiedad con una tolerancia técnica. En pruebas de desempeño (punto de gota, "
            "soldadura, desgaste) si Interlub es igual o mejor cuenta completo.\n"
            "3. **Pesan más** el grado NLGI, la viscosidad y la temperatura: si fallan, el parecido baja aunque lo "
            "demás coincida. Quedarse corto en la temperatura máxima castiga más que en la mínima.\n"
            "4. **Avisa** si cambia el espesante o el aceite base, porque mezclar productos distintos puede requerir "
            "limpieza o una prueba de compatibilidad.\n"
            "5. **Propone un producto nuevo** si ninguno llega a sustituto directo (75 %): qué debe cumplir, de qué "
            "producto Interlub partir, qué cambiarle y qué muestra el catálogo. Solo usa la ficha y el catálogo, no "
            "inventa fórmulas.\n\n"
            "Los datos que la ficha no trae no restan, pero si se comparó poco la página lo dice. Las tolerancias "
            "son una propuesta del equipo y deben validarse con Interlub."
        )
    st.markdown('<div class="pie"><span>Proyecto del reto MA2003B para Interlub.</span>'
                '<span>Recomendaciones orientativas: confírmalas con el equipo técnico antes de cambiar de producto.'
                '</span></div>', unsafe_allow_html=True)


main()
