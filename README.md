# Reto-MA2003B
Recomendador de productos Interlub: a partir de la ficha técnica (PDF) de una grasa o aceite, por ejemplo de la competencia, sugiere los productos Interlub que mejor encajan y explica por qué.

## Instalación

```bash
uv sync
./scripts/setup_dvc_remote.sh   # credenciales de DagsHub (necesita .env con DVC_DAGSHUB_TOKEN)
dvc pull -r storage
./scripts/dvc_decrypt.sh        # necesita la llave .age/key.txt
```

## Flujo

1. `notebooks/01_limpieza.ipynb`: limpia `DATOS_TEC.xlsx` → `data/processed/DATOS_TEC_clean.csv`.
2. Extrae el PDF con el prompt de `scripts/prompts/extraccion_pdfs.md` y guarda el JSON en `data/processed/`.
3. `notebooks/02_pdfs.ipynb`: normaliza las fichas y calcula los embeddings.
4. Recomendar:

```bash
uv run python scripts/recomendar.py data/processed/ficha.json                     # lista los productos del JSON
uv run python scripts/recomendar.py data/processed/ficha.json -p "ULTRAPLEX MCS 2"
uv run python scripts/recomendar.py data/processed/ficha.json --todos -k 3 --guardar
```

   También se puede usar `notebooks/03_recomendar.ipynb`. La lógica está en `scripts/recomendador.py`.

## Pruebas

```bash
uv run pytest
```

Usan datos ficticios de `tests/datos/`, así que no necesitan los datos cifrados.
