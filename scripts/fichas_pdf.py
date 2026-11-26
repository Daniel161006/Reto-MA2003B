"""Convierte fichas técnicas extraídas de PDF (JSON, ver scripts/prompts/extraccion_pdfs.md) al esquema de
DATOS_TEC_clean.csv, para que cualquier ficha nueva pueda usarse como consulta del recomendador.

Uso:
    registros = json.load(open("../data/processed/competencia_extraccion.json"))
    fichas = normalizar(registros)          # una fila por producto, columnas alineadas con DATOS_TEC
    textos = texto_ficha(fichas)            # misma plantilla de texto que para los productos Interlub
"""

import json
import re
import unicodedata

import numpy as np
import pandas as pd

N_A_KGF = 1 / 9.80665

# NLGI ranges of worked penetration (0.1 mm); 00 -> -1, 000 -> -2 (same coding as 01_limpieza.ipynb)
NLGI_RANGOS = {
    -2: (445, 475),
    -1: (400, 430),
    0: (355, 385),
    1: (310, 340),
    2: (265, 295),
    3: (220, 250),
    4: (175, 205),
    5: (130, 160),
    6: (85, 115),
}
NLGI_CENTROS = pd.Series({g: (lo + hi) / 2 for g, (lo, hi) in NLGI_RANGOS.items()})

# extraction key -> DATOS_TEC column (viscosidad_40c/100c depend on familia, see _columna)
NUMERICAS = {
    "penetracion_trabajada_60": "penetracion_de_cono_a_25c_0_1mm",
    "penetracion_trabajada_10000": "penetracion_a_10_000_estandar",
    "punto_de_gota": "punto_de_gota_c",
    "viscosidad_aceite_base_40c": "viscosidad_del_aceite_base_a_40c_cst",
    "indice_de_viscosidad": "indice_de_viscosidad",
    "punto_de_flama": "punto_de_flama_c",
    "punto_de_fluidez": "punto_de_congelamiento_c",
    "temperatura_servicio_min": "temperatura_de_servicio_c_min",
    "temperatura_servicio_max": "temperatura_de_servicio_c_max",
    "punto_soldadura_4_bolas": "punto_de_soldadura_cuatro_bolas_kgf",
    "desgaste_4_bolas": "desgaste_cuatro_bolas_mm",
    "carga_timken_ok": "carga_timken_ok_lb",
    "lavado_por_agua": "resistencia_al_lavado_por_agua_a_80c_pct",
    "grado_iso_vg": "grado_iso_vg",
    # not in DATOS_TEC, kept because they describe the product
    "rocio_de_agua": "rocio_de_agua_pct",
    "separacion_de_aceite": "separacion_de_aceite_pct",
}

# DATOS_TEC vocabularies (lowercase, no accents)
ESPESANTES = [
    ("sulfonat", "complejo sulfonato de calcio"),
    ("litio", "complejo de litio"),
    ("lithium", "complejo de litio"),
    ("poliurea", "poliurea"),
    ("polyurea", "poliurea"),
    ("bentonit", "bentonita"),
    ("clay", "bentonita"),
    ("arcilla", "bentonita"),
]
ACEITES_BASE = [
    ("semi", "semisintetico"),
    ("white oil", "mineral usp"),
    ("blanco", "mineral usp"),
    ("usp", "mineral usp"),
    ("pao", "pao"),
    ("polialfaolefina", "pao"),
    ("polyalphaolefin", "pao"),
    ("ester", "ester"),
    ("pag", "pag"),
    ("polialquilenglicol", "pag"),
    ("polyglycol", "pag"),
    ("mineral", "mineral"),
]
COLORES = [
    "negro",
    "beige",
    "ambar",
    "incoloro",
    "amarillo",
    "blanco",
    "cristalino",
    "gris",
    "cafe",
    "verde",
    "rojo",
    "cobre",
    "azul",
]
COLOR_EN = {
    "black": "negro",
    "tan": "beige",
    "amber": "ambar",
    "colorless": "incoloro",
    "yellow": "amarillo",
    "white": "blanco",
    "clear": "cristalino",
    "grey": "gris",
    "gray": "gris",
    "brown": "cafe",
    "green": "verde",
    "red": "rojo",
    "copper": "cobre",
    "blue": "azul",
    "light": "claro",
}
TEXTURAS = {
    "suave": "suave",
    "smooth": "suave",
    "adherente": "adherente",
    "pegajosa": "adherente",
    "tacky": "adherente",
    "adhesive": "adherente",
    "fluida": "fluida",
    "fluido": "fluida",
    "fluid": "fluida",
    "viscosa": "viscosa",
    "viscoso": "viscosa",
    "viscous": "viscosa",
}


def norm_texto(s):
    """lowercase, no accents, single spaces (same as 01_limpieza.ipynb)."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s.replace("®", "")).strip()


_NUM = r"[-+]?\d+(?:\.\d+)?"


def parse_valor(valor, unidad=None):
    """Literal value -> (float, tipo) with tipo in {'=', '>', '<', '~', 'rango'}, as in DATOS_TEC_clean.

    Handles decimal commas, '177(350)' (°C(°F): keeps °C), 'Approx.'/'c.'/'ISO VG' (~), '> x', '< x',
    'a to b' / 'a - b' (midpoint), 'x +/- d' (rango) and newtons -> kgf.
    """
    if valor is None:
        return np.nan, None
    v = re.sub(r"(\d),(\d)", r"\1.\2", str(valor)).strip()
    v = re.sub(r"\(.*?\)", "", v).split(";")[0].strip()  # drop (°F) and 2nd reading
    v_low = v.lower()
    tipo, x = None, None
    if m := re.search(rf"({_NUM})\D*?(?:\+/-|±)\s*({_NUM})", v):
        x, tipo = float(m[1]), "rango"
    elif m := re.search(rf"({_NUM})\s*(?:-|–|to|a)\s*({_NUM})", v):
        x, tipo = (float(m[1]) + float(m[2])) / 2, "rango"
    elif m := re.search(rf"([<>])\s*=?\s*({_NUM})", v):
        x, tipo = float(m[2]), m[1]
    elif m := re.search(_NUM, v):
        x = float(m[0])
        tipo = "~" if re.search(r"approx|aprox|\bc\.|ca\.|iso vg", v_low) else "="
    if x is None:
        return np.nan, None
    if unidad and re.fullmatch(r"\s*N\s*", unidad):
        x = round(x * N_A_KGF, 1)  # 1 decimal: the N value already carries rounding
    return x, tipo


def _columna(clave, familia):
    if clave == "viscosidad_40c":
        return (
            "viscosidad_del_aceite_base_a_40c_cst"
            if familia == "grasa"
            else "viscosidad_a_40c_cst"
        )
    if clave == "viscosidad_100c":
        return (
            "viscosidad_aceite_base_a_100c_cst"
            if familia == "grasa"
            else "viscosidad_a_100c_cst"
        )
    return NUMERICAS.get(clave)


def _vocab(texto, pares):
    t = norm_texto(texto)
    if not t:
        return None
    return next((v for k, v in pares if re.search(rf"\b{k}", t)), None)


def _color(texto):
    t = norm_texto(texto)
    if not t:
        return None
    words = [COLOR_EN.get(w, w) for w in re.findall(r"[a-z]+", t)]
    base = next((w for w in words if w in COLORES), None)
    return None if base is None else base + (" claro" if "claro" in words else "")


def _valor(props, clave):
    return (props.get(clave) or {}).get("valor")


def nlgi_por_penetracion(pen):
    return NLGI_CENTROS.sub(pen).abs().idxmin() if pd.notna(pen) else np.nan


def normalizar(registros):
    """List of extraction records -> DataFrame aligned with DATOS_TEC_clean (plus metadata and texts)."""
    filas = []
    for r in registros:
        props = r.get("propiedades") or {}
        fam = norm_texto(r.get("familia"))
        f = {
            "nombre_producto": r["nombre_producto"],
            "marca": r.get("marca"),
            "archivo_fuente": r.get("archivo_fuente"),
            "numero_producto": r.get("numero_producto"),
            "fecha_documento": r.get("fecha_documento"),
            "reemplaza_a": r.get("reemplaza_a"),
            "familia": fam,
        }
        for clave, prop in props.items():
            col = _columna(clave, fam)
            if col is None or prop is None:
                continue
            x, tipo = parse_valor(prop.get("valor"), prop.get("unidad"))
            f[col], f[col + "_tipo"] = x, tipo

        nlgi_txt = norm_texto(_valor(props, "grado_nlgi"))
        # declared grade coded like DATOS_TEC (00/000 -> 0); derived grade from penetration, else from 00/000
        f["grado_nlgi_consistencia"] = parse_valor(nlgi_txt)[0] if nlgi_txt else np.nan
        derivado = nlgi_por_penetracion(
            f.get("penetracion_de_cono_a_25c_0_1mm", np.nan)
        )
        f["grado_nlgi_por_penetracion"] = (
            derivado
            if pd.notna(derivado)
            else {"00": -1, "000": -2}.get(nlgi_txt, f["grado_nlgi_consistencia"])
        )
        f["espesante"] = (
            _vocab(_valor(props, "espesante"), ESPESANTES)
            or (norm_texto(_valor(props, "espesante")) or "").removeprefix("espesante ")
            or None
        )
        f["espesante_en_vocabulario"] = (
            f["espesante"] in {v for _, v in ESPESANTES} if f["espesante"] else None
        )
        f["aceite_base"] = _vocab(_valor(props, "aceite_base"), ACEITES_BASE)
        f["color"] = _color(_valor(props, "color"))
        cu = re.search(r"\b1[ab]\b", norm_texto(_valor(props, "corrosion_cobre")) or "")
        f["corrosion_al_cobre"] = cu[0] if cu else None
        tex = [
            TEXTURAS[w]
            for w in re.findall(r"[a-z]+", norm_texto(_valor(props, "textura")) or "")
            if w in TEXTURAS
        ]
        for t in ["suave", "adherente", "fluida", "viscosa"]:
            f["textura_" + t] = (t in tex) if _valor(props, "textura") else pd.NA
        f["tiene_registro_nsf"] = bool(
            re.search(r"\bnsf\b|\bh1\b", norm_texto(r.get("certificaciones")) or "")
        )
        for k in [
            "descripcion",
            "aplicaciones",
            "beneficios_caracteristicas",
            "certificaciones",
        ]:
            f[k] = r.get(k)
        f["otras_propiedades"] = json.dumps(
            r.get("otras_propiedades") or [], ensure_ascii=False
        )
        filas.append(f)

    df = pd.DataFrame(filas)
    # a product is superseded when a newer sheet says it replaces it ("antes: ...")
    base = df["nombre_producto"].map(
        lambda n: norm_texto(re.sub(r"\s+(000|00|0|1|2|3)$", "", n))
    )
    reemplazados = {
        n.strip()
        for t in df["reemplaza_a"].dropna()
        for n in re.split(r",| y | and ", norm_texto(t))
    }
    df.insert(
        df.columns.get_loc("reemplaza_a") + 1, "vigente", ~base.isin(reemplazados)
    )
    # drop *_tipo columns that only say "=" (same convention as DATOS_TEC_clean)
    tipos = [c for c in df if c.endswith("_tipo") and set(df[c].dropna()) <= {"="}]
    df = df.drop(columns=tipos)
    for c in [c for c in df if c.startswith("textura_")]:
        df[c] = df[c].astype("boolean")
    return df


def _fmt(x):
    return f"{x:g}"


def _si(x):
    return pd.notna(x) and bool(x)


def texto_ficha(df):
    """Same textual template for Interlub and PDF products, so their embeddings are comparable."""
    nlgi_txt = {-2: "000", -1: "00"}

    def una(r):
        g = r.get
        partes = [g("familia")]
        if pd.notna(g("espesante")):
            partes.append(f"espesante {g('espesante')}")
        if pd.notna(g("aceite_base")):
            partes.append(f"aceite base {g('aceite_base')}")
        n = g("grado_nlgi_por_penetracion")
        n = n if pd.notna(n) else g("grado_nlgi_consistencia")
        if pd.notna(n):
            partes.append(f"grado NLGI {nlgi_txt.get(n, _fmt(n))}")
        if pd.notna(g("grado_iso_vg")):
            partes.append(f"ISO VG {_fmt(g('grado_iso_vg'))}")
        if pd.notna(g("color")):
            partes.append(f"color {g('color')}")
        tex = [
            t
            for t in ["suave", "adherente", "fluida", "viscosa"]
            if _si(g("textura_" + t))
        ]
        if tex:
            partes.append("textura " + " y ".join(tex))
        lo, hi = g("temperatura_de_servicio_c_min"), g("temperatura_de_servicio_c_max")
        if pd.notna(lo) and pd.notna(hi):
            partes.append(f"temperatura de servicio de {_fmt(lo)} a {_fmt(hi)} grados")
        for col, txt in [
            ("punto_de_gota_c", "punto de gota {} grados"),
            (
                "viscosidad_del_aceite_base_a_40c_cst",
                "viscosidad del aceite base {} cSt",
            ),
            ("viscosidad_a_40c_cst", "viscosidad {} cSt a 40 grados"),
            (
                "punto_de_soldadura_cuatro_bolas_kgf",
                "extrema presión, soldadura cuatro bolas {} kgf",
            ),
        ]:
            if pd.notna(g(col)):
                partes.append(txt.format(_fmt(round(g(col)))))
        if _si(g("tiene_registro_nsf")):
            partes.append("grado alimenticio, registro NSF H1")
        return ", ".join(p for p in partes if isinstance(p, str))

    return df.apply(lambda r: una(r.to_dict()), axis=1)


def texto_libre(df):
    """Free text of a PDF product (description, applications, benefits, certifications) for embeddings."""
    cols = [
        "descripcion",
        "aplicaciones",
        "beneficios_caracteristicas",
        "certificaciones",
    ]
    return df[cols].apply(
        lambda r: " ".join(x for x in r if isinstance(x, str)), axis=1
    )


def fragmentos(df, min_palabras=3):
    """Split each product's free text into sentences (the model reads ~128 tokens, so long fields get cut and
    averaging dilutes key phrases). Returns one row per fragment: product index, field and text.
    A query scores each product by its best-matching fragment."""
    campos = [
        "descripcion",
        "aplicaciones",
        "beneficios_caracteristicas",
        "certificaciones",
    ]
    filas = [
        (i, c, s)
        for i, r in df.iterrows()
        for c in campos
        if isinstance(r[c], str)
        for s in re.split(r"(?<=[.;:])\s+|\s+[—-]\s+", r[c])
        if len(s.split()) >= min_palabras
    ]
    return pd.DataFrame(filas, columns=["producto", "campo", "texto"])
