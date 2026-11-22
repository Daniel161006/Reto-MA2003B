# Prompt: extracción de fichas técnicas (PDF) a JSON

El prompt listo para copiar está al final de este archivo.

## Cómo analizar un PDF nuevo

1. Guarda el PDF en `data/raw/pdfs/`.
2. Abre Claude (u otra IA que lea PDFs), pega el prompt de abajo y adjunta el PDF.
3. Revisa el JSON contra el PDF (sobre todo que haya un objeto por grado y que los valores sean literales).
4. Agrega los objetos a la lista de `data/processed/competencia_extraccion.json`.
5. Corre `notebooks/02_pdfs.ipynb`: normaliza al esquema de `DATOS_TEC` (`scripts/fichas_pdf.py`), muestra avisos de
   validación y recalcula los embeddings.

## Cambios respecto al prompt base de la Actividad 1 y por qué

- **Un registro por producto/grado**, no por PDF: una ficha suele tabular varios grados NLGI o versiones.
- **JSON en vez de tabla/CSV**: las fichas usan coma decimal (`0,43`), que rompe un CSV.
- **Valor literal + unidad + método por separado**: la conversión de unidades (N → kgf, °F → °C) y el parseo
  de `>`, `≈`, rangos se hace después en `scripts/fichas_pdf.py`, de forma reproducible y revisable.
- **Claves fijas alineadas con `DATOS_TEC`** para poder comparar ambas tablas, y una regla explícita para no
  juntar pruebas distintas (water washout ≠ water spray-off).

## Prompt

```text
Actúa como analista de datos técnicos de lubricantes. Te compartiré la ficha técnica (PDF) de uno o varios
productos de un fabricante. Extrae la información y responde SOLO con una lista JSON, siguiendo estas reglas:

1. Un objeto por producto. Si la ficha tabula varios grados o versiones (p. ej. NLGI 00, 0, 1, 2, o con/sin
   MoS2), cada columna es un producto distinto con su nombre completo (p. ej. "Starplex EP 2 M3").
2. Copia los valores literalmente: mismo número, signo o aproximación (>, <, ±, "c.", "approx."), rango,
   coma o punto decimal, unidad e idioma originales. No conviertas unidades, no redondees, no traduzcas.
3. Si un dato no aparece o dice "n/a", "-" o "—", usa null. No infieras ni completes con conocimiento externo.
4. Cada propiedad técnica va en "propiedades" como {"valor", "unidad", "metodo", "nombre_en_pdf"}; "metodo" es
   la norma (ASTM/DIN/ISO/IP) si aparece. Si un mismo texto da mínimo y máximo (p. ej. "-20 a 180 °C"),
   sepáralos en las dos claves correspondientes.
5. Usa estas claves cuando la propiedad corresponda, aunque en el PDF tenga otro nombre o idioma:
   grado_nlgi, grado_iso_vg, espesante, aceite_base, penetracion_trabajada_60, penetracion_trabajada_10000,
   punto_de_gota, viscosidad_aceite_base_40c, viscosidad_40c, viscosidad_100c, indice_de_viscosidad,
   punto_de_flama, punto_de_fluidez, temperatura_servicio_min, temperatura_servicio_max,
   punto_soldadura_4_bolas, desgaste_4_bolas, carga_timken_ok, lavado_por_agua, rocio_de_agua (spray-off),
   corrosion_cobre, separacion_de_aceite, color, textura.
   No juntes pruebas distintas bajo una misma clave (p. ej. water washout ≠ water spray-off).
6. Cualquier otra propiedad va en "otras_propiedades" (lista de {"nombre_en_pdf", "valor", "unidad", "metodo"}).
7. Campos de texto literal, sin resumir ni traducir: "descripcion", "aplicaciones",
   "beneficios_caracteristicas", "certificaciones" (NSF, H1, Halal, NLGI GC-LB, especificaciones de OEM).
8. Metadatos: "marca", "fabricante", "nombre_producto", "familia" (grasa o aceite, solo si la ficha lo dice),
   "numero_producto", "fecha_documento", "reemplaza_a" (si dice "antes:" o "formerly"), "archivo_fuente".

Formato de cada objeto:
{
  "archivo_fuente": "...", "marca": "...", "fabricante": "...", "nombre_producto": "...", "familia": "grasa",
  "numero_producto": null, "fecha_documento": null, "reemplaza_a": null,
  "propiedades": {
    "punto_de_gota": {"valor": "> 300", "unidad": "°C", "metodo": "ASTM D-566", "nombre_en_pdf": "Punto de gota"}
  },
  "otras_propiedades": [
    {"nombre_en_pdf": "Ensayo corrosión niebla salina", "valor": "> 1000", "unidad": "horas", "metodo": "ASTM B-117"}
  ],
  "descripcion": "...", "aplicaciones": "...", "beneficios_caracteristicas": "...", "certificaciones": "..."
}
```
