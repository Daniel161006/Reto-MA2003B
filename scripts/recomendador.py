"""Recomendador v1.2: dada la ficha de un producto (una fila de fichas_pdf.normalizar), sugiere los productos
Interlub que mejor encajan y explica por qué.

Capas:
1. Filtros (descartan): misma familia; el rango de temperatura de servicio de Interlub cubre el de la ficha
   (con tolerancia de TOL_TEMP); si la ficha es grado alimenticio (NSF/H1), solo productos con registro NSF.
2. Parecido técnico (ordena): cada propiedad que tienen ambos productos aporta una similitud entre 0 y 1 con
   tolerancias técnicas (ver COMPARACIONES); la temperatura también suma. Espesante y aceite base suman si
   coinciden. Los datos faltantes no castigan, pero un producto comparado en pocas propiedades pesa menos
   (cobertura).
3. Propiedades críticas (NLGI, viscosidad, temperatura): además de promediarse, multiplican el puntaje por
   (0.5 + 0.5 × similitud), para que un ✗ en una de ellas no se compense con ✓ en todo lo demás.
   puntaje = parecido × √cobertura × factor_critico
4. Texto (opcional): similitud de embeddings, informativa. Con peso_texto=0 (default) no cambia el orden,
   porque las fichas en texto se parecen demasiado entre sí para distinguir productos.

Las tolerancias son criterio técnico propuesto por el equipo: validarlas con Interlub.

Uso:
    recs, avisos = recomendar(ficha, interlub, k=5)
"""

import fichas_pdf as F
import numpy as np
import pandas as pd

TOL_TEMP = (
    10  # °C: el filtro acepta productos a los que les falte hasta esto en cada extremo
)
FALTA_TEMP_CERO = 20  # °C faltantes (sumando ambos extremos) con los que la similitud de temperatura llega a 0
PESO_TEMPERATURA = 1.5
# properties a substitute cannot get wrong: each multiplies the score by (PISO_CRITICO + (1 - PISO_CRITICO) × sim),
# i.e. ✓ ≈ ×1, ~ ≈ ×0.75, ✗ = ×0.5. Temperature is critical too (see recomendar).
CRITICAS = {"nlgi", "viscosidad_del_aceite_base_a_40c_cst", "viscosidad_a_40c_cst"}
PISO_CRITICO = 0.5
PASO_ISO_VG = 1.5  # razón entre grados ISO VG consecutivos (32, 46, 68, 100, 150, 220, 320, 460, 680...)

# propiedad: (peso, tipo de comparación, tolerancia)
#   "nlgi":       0.5 grados de diferencia ~, 1 grado ✗
#   "viscosidad": ±10 % = mismo grado ISO ✓; un grado ISO de diferencia ~; dos o más ✗
#   "mayor_abs":  propiedad de desempeño en °C; si Interlub es igual o mayor ✓; si es menor, la similitud
#                 baja linealmente y llega a 0 cuando le faltan `tolerancia` °C
#   "mayor_rel":  igual pero relativa (0.4 = le falta un 40 %)
#   "menor_rel":  propiedad donde menos es mejor (desgaste); castiga si Interlub es mayor
COMPARACIONES = {
    "nlgi": (2.0, "nlgi", None),
    "viscosidad_del_aceite_base_a_40c_cst": (1.5, "viscosidad", None),
    "viscosidad_a_40c_cst": (2.0, "viscosidad", None),
    "indice_de_viscosidad": (0.5, "mayor_rel", 0.3),
    "punto_de_gota_c": (1.0, "mayor_abs", 20),  # 10 °C por debajo -> ~
    "punto_de_flama_c": (0.5, "mayor_abs", 40),
    "punto_de_soldadura_cuatro_bolas_kgf": (
        1.0,
        "mayor_rel",
        0.4,
    ),  # un escalón (620 -> 500) -> ~
    "desgaste_cuatro_bolas_mm": (0.5, "menor_rel", 0.5),
    "carga_timken_ok_lb": (0.5, "mayor_rel", 0.4),
}
CATEGORICAS = {"espesante": 1.5, "aceite_base": 1.0}

ETIQUETAS = {
    "nlgi": "NLGI",
    "viscosidad_del_aceite_base_a_40c_cst": "visc. aceite base",
    "viscosidad_a_40c_cst": "visc. 40 °C",
    "indice_de_viscosidad": "índice visc.",
    "punto_de_gota_c": "punto de gota",
    "punto_de_flama_c": "punto de flama",
    "punto_de_soldadura_cuatro_bolas_kgf": "soldadura 4 bolas",
    "desgaste_cuatro_bolas_mm": "desgaste 4 bolas",
    "carga_timken_ok_lb": "Timken",
    "espesante": "espesante",
    "aceite_base": "aceite base",
}


def _con_nlgi(df):
    """NLGI from penetration (tells 00/000 apart), else the declared grade."""
    df = df.reindex(
        columns=df.columns.union(
            ["grado_nlgi_por_penetracion", "grado_nlgi_consistencia"], sort=False
        )
    )
    df["nlgi"] = df["grado_nlgi_por_penetracion"].fillna(df["grado_nlgi_consistencia"])
    return df


def _fmt(x):
    return f"{x:g}" if isinstance(x, (int, float, np.floating)) else str(x)


def _marca(s):
    return "✓" if s >= 0.8 else ("~" if s >= 0.4 else "✗")


def _similitud(tipo, a, b, tol):
    """Similarity in [0, 1] between the ficha value `a` (float) and the Interlub values `b` (Series)."""
    if tipo == "nlgi":
        sim = 1 - 0.7 * (b - a).abs()
    elif tipo == "viscosidad":
        razon = np.maximum(b, a) / np.minimum(b, a)
        pasos = np.log(razon) / np.log(PASO_ISO_VG)
        sim = (1 - 0.5 * pasos).where(razon > 1.1, 1.0)
    elif tipo == "mayor_abs":
        sim = 1 - (a - b).clip(lower=0) / tol
    elif tipo == "mayor_rel":
        sim = 1 - ((a - b) / abs(a)).clip(lower=0) / tol
    elif tipo == "menor_rel":
        sim = 1 - ((b - a) / abs(a)).clip(lower=0) / tol
    else:
        raise ValueError(tipo)
    return sim.clip(0, 1)


def _filtrar(f, cand):
    avisos = []
    if pd.notna(f.get("familia")):
        cand = cand[cand["familia"] == f["familia"]]

    tmin, tmax = (
        f.get("temperatura_de_servicio_c_min"),
        f.get("temperatura_de_servicio_c_max"),
    )
    if pd.isna(tmin) and pd.isna(tmax):
        avisos.append(
            "La ficha no tiene temperatura de servicio: no se filtró por temperatura."
        )
    else:
        sin_dato = cand["temperatura_de_servicio_c_max"].isna()
        cubre = pd.Series(True, index=cand.index)
        if pd.notna(tmax):
            cubre &= cand["temperatura_de_servicio_c_max"] >= tmax - TOL_TEMP
        if pd.notna(tmin):
            cubre &= cand["temperatura_de_servicio_c_min"] <= tmin + TOL_TEMP
        if sin_dato.any():
            avisos.append(
                f"{sin_dato.sum()} productos Interlub sin temperatura de servicio se conservaron."
            )
        cand = cand[cubre | sin_dato]

    nsf = f.get("tiene_registro_nsf")
    if pd.notna(nsf) and bool(nsf):
        cand = cand[cand["tiene_registro_nsf"].astype(bool)]
        avisos.append(
            "La ficha es grado alimenticio: solo se consideran productos con registro NSF."
        )

    avisos.append(f"Quedan {len(cand)} candidatos después de los filtros.")
    return cand, avisos


def _temperatura(f, cand):
    """Similarity of the service range (1 = fully covers the ficha) and the reason text per product."""
    flo = f.get("temperatura_de_servicio_c_min")
    fhi = f.get("temperatura_de_servicio_c_max")
    lo, hi = (
        cand["temperatura_de_servicio_c_min"],
        cand["temperatura_de_servicio_c_max"],
    )
    falta_arriba = (fhi - hi).clip(lower=0) if pd.notna(fhi) else hi * 0
    falta_abajo = (lo - flo).clip(lower=0) if pd.notna(flo) else lo * 0
    sim = (1 - (falta_arriba + falta_abajo) / FALTA_TEMP_CERO).clip(0, 1)

    razones = {}
    for i in cand.index:
        if pd.isna(hi[i]):
            razones[i] = "temperatura: sin dato en Interlub"
            continue
        if pd.isna(flo) and pd.isna(fhi):
            razones[i] = f"temperatura Interlub {_fmt(lo[i])} a {_fmt(hi[i])} °C"
            continue
        txt = f"temperatura {_fmt(lo[i])} a {_fmt(hi[i])} vs {_fmt(flo)} a {_fmt(fhi)} °C {_marca(sim[i])}"
        faltas = [
            f"le faltan {_fmt(v)} °C {lado}"
            for v, lado in [(falta_abajo[i], "abajo"), (falta_arriba[i], "arriba")]
            if v > 0
        ]
        razones[i] = txt + (f" ({', '.join(faltas)})" if faltas else "")
    return sim, razones


def recomendar(ficha, interlub, k=5, sim_texto=None, peso_texto=0.0):
    """ficha: Series (one row of fichas_pdf.normalizar). interlub: DataFrame of DATOS_TEC_clean.csv.
    sim_texto: optional Series (index = interlub.index) with text similarity; shown as a column and
    mixed into the score with weight peso_texto (0 by default).
    Returns (DataFrame of the top k with score and reasons, list of warnings)."""
    f = _con_nlgi(ficha.to_frame().T).iloc[0]
    cand, avisos = _filtrar(f, _con_nlgi(interlub))
    if cand.empty:
        return pd.DataFrame(), avisos

    num = pd.Series(0.0, index=cand.index)  # weighted sum of similarities
    den = pd.Series(0.0, index=cand.index)  # weight of the properties actually compared
    posible = 0.0  # weight of every property the ficha has
    razones = {i: [] for i in cand.index}
    factor = pd.Series(1.0, index=cand.index)  # product of the critical penalties

    def critica(sim):
        """Multiply the score by the critical penalty; missing values (NaN) do not penalize."""
        factor.update(factor * (PISO_CRITICO + (1 - PISO_CRITICO) * sim.dropna()))

    # temperature: also a score, not only a filter (covering the full range beats covering it "almost")
    sim_t, razon_t = _temperatura(f, cand)
    if pd.notna(f.get("temperatura_de_servicio_c_max")) or pd.notna(
        f.get("temperatura_de_servicio_c_min")
    ):
        posible += PESO_TEMPERATURA
        hay = sim_t.notna()
        num[hay] += PESO_TEMPERATURA * sim_t[hay]
        den[hay] += PESO_TEMPERATURA
        critica(sim_t)

    for col, (peso, tipo_cmp, tol) in COMPARACIONES.items():
        a = f.get(col)
        if pd.isna(a) or col not in cand:
            continue
        a = float(a)
        posible += peso
        b = cand[col]
        sim = _similitud(tipo_cmp, a, b, tol)
        # ">"/"<" in the ficha (e.g. "punto de gota > 300") means at least / at most that value
        tipo = f.get(col + "_tipo")
        if tipo == ">":
            sim = sim.where(b < a, 1.0)
        elif tipo == "<":
            sim = sim.where(b > a, 1.0)
        hay = b.notna()
        num[hay] += peso * sim[hay]
        den[hay] += peso
        if col in CRITICAS:
            critica(sim)
        signo = tipo if tipo in (">", "<", "~") else ""
        for i in cand.index[hay]:
            razones[i].append(
                f"{ETIQUETAS[col]} {signo}{_fmt(a)} vs {_fmt(b[i])} {_marca(sim[i])}"
            )

    vocab_espesante = {v for _, v in F.ESPESANTES}
    for col, peso in CATEGORICAS.items():
        a = f.get(col)
        if pd.isna(a):
            continue
        if col == "espesante" and a not in vocab_espesante:
            avisos.append(
                f"Espesante '{a}' no existe en Interlub: no se usa para comparar."
            )
            continue
        posible += peso
        hay = cand[col].notna()
        igual = (cand[col] == a).astype(float)
        num[hay] += peso * igual[hay]
        den[hay] += peso
        for i in cand.index[hay]:
            razones[i].append(
                f"{ETIQUETAS[col]} " + ("✓" if igual[i] else f"✗ ({cand.at[i, col]})")
            )

    media = (num / den).fillna(0.0)
    cobertura = (den / posible) if posible else den * 0
    puntaje = media * np.sqrt(cobertura) * factor
    if sim_texto is not None:
        puntaje = (1 - peso_texto) * puntaje + peso_texto * sim_texto.loc[cand.index]

    out = pd.DataFrame(
        {
            "codigoproducto": cand["codigoproducto"],
            "puntaje": puntaje.round(3),
            "parecido_tecnico": media.round(3),
            "cobertura": cobertura.round(2),
            "factor_critico": factor.round(2),
            "por_que": [" · ".join([razon_t[i], *razones[i]]) for i in cand.index],
        }
    )
    if sim_texto is not None:
        out.insert(2, "sim_texto", sim_texto.loc[cand.index].round(3))
    return out.sort_values("puntaje", ascending=False).head(k), avisos


def similitud_texto(ficha, interlub, modelo, emb_interlub):
    """Cosine similarity between the ficha's text template and every Interlub product's template.
    emb_interlub: rows aligned with interlub (embeddings.npz -> interlub_ficha)."""
    texto = F.texto_ficha(ficha.to_frame().T).iloc[0]
    q = modelo.encode([texto], normalize_embeddings=True)[0]
    return pd.Series(emb_interlub @ q, index=interlub.index)


def comparar(ficha, interlub, recs):
    """Side-by-side table: the ficha vs each recommended product, on the columns the recommender uses."""
    cols = [
        "familia",
        "espesante",
        "aceite_base",
        "nlgi",
        "temperatura_de_servicio_c_min",
        "temperatura_de_servicio_c_max",
        *[c for c in COMPARACIONES if c != "nlgi"],
        "tiene_registro_nsf",
    ]
    f = _con_nlgi(ficha.to_frame().T).iloc[0]
    top = _con_nlgi(interlub.loc[recs.index])
    tabla = pd.concat(
        [
            # a PDF only has the columns its sheet reports: missing ones show as empty
            f.reindex(cols).rename(f.get("nombre_producto", "ficha")),
            top.set_index("codigoproducto").reindex(columns=cols).T,
        ],
        axis=1,
    )
    return tabla.loc[tabla.notna().any(axis=1)]
