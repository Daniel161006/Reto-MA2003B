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
4. Recomendar (terminal) o usar la página web (ver abajo):

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

## Página web

Es la forma pensada para la gente de Interlub: no necesitan terminal ni código.

```bash
uv run streamlit run app/app.py
```

Se abre en el navegador. Ahí se puede:
- **Llenar los datos** de la ficha en un formulario (tipo de producto, NLGI, viscosidad, temperatura, grado alimenticio, etc.).
- **Subir el JSON** que sacó la IA del PDF.
- **Probar con un producto Interlub**: el mismo producto debe salir primero en su propia recomendación.

El resultado son tarjetas con el porcentaje de parecido, el porqué (✓ igual o mejor, ~ algo distinto, ✗ muy distinto), una tabla de comparación y un botón para descargar el CSV.

El catálogo se lee de `data/processed/DATOS_TEC_clean.csv`. Si no existe, la página deja llenar la ficha igual y pide subir el catálogo para comparar.

Para probarla sin los datos reales: `INTERLUB_CSV=tests/datos/interlub_ejemplo.csv uv run streamlit run app/app.py`.

El diseño (colores y letras) está en `.streamlit/config.toml`. Las letras IBM Plex van dentro del proyecto (`app/static/fonts/`, licencia OFL), así que se ven bien aunque no haya internet.

### Publicarla con un link (Streamlit Community Cloud)

1. En <https://share.streamlit.io> crear la app con este repo, rama `main` y archivo principal `app/app.py`.
2. Usa `app/requirements.txt`, que es corto a propósito: el `pyproject.toml` completo trae paquetes pesados (torch, DVC) que no caben en la nube.
3. **Los datos de Interlub no están en el repo** (están cifrados). Decidan con Interlub dónde vive el catálogo: que lo suban en cada sesión desde la barra lateral, o ponerlo en un repo **privado** y la app en modo privado. No lo suban a un repo público.

## Cómo decide el recomendador y cómo afinar los pesos

Todo está en `scripts/recomendador.py`, con constantes arriba del archivo fáciles de cambiar.

- **Se descartan** los que no sirven: otro tipo de producto, que no aguanten la temperatura (tolerancia de 5 °C por arriba y 10 °C por abajo) o, si la ficha es grado alimenticio, los que no tengan NSF.
- **Quedarse corto por arriba en temperatura castiga más que por abajo**: la vida del producto se reduce a la mitad por cada ~10 °C de más. Por eso cada 10 °C faltantes arriba bajan la similitud a la mitad, y por abajo baja linealmente.
- **Propiedades de desempeño** (punto de gota, presión extrema, etc.): si Interlub es igual o mejor cuenta completo; solo castiga si es peor.
- **NLGI, viscosidad y temperatura** además multiplican el puntaje, para que un ✗ en ellas no se compense con lo demás.
- **Producto nuevo**: si ningún producto llega a sustituto directo (75 %), o ninguno pasa los filtros, propone la especificación de un producto a desarrollar: qué debe cumplir, de qué producto Interlub partir, qué cambiarle y qué muestra el catálogo. Solo usa la ficha y el catálogo, no inventa fórmulas. Se puede descargar en TXT.
- **Advertencias** (no cambian el puntaje): si cambia el espesante o el aceite base, avisa que hay que limpiar o probar la compatibilidad. No se usa una tabla fija de compatibilidad porque las tablas publicadas se contradicen entre sí.

Para saber qué pesos importan de verdad, con el catálogo descifrado:

```bash
uv run python scripts/sensibilidad_pesos.py
```

Cambia cada peso (a la mitad y +50 %) y muestra cuánto cambia el top 3. Los que más cambian son los que hay que validar con Interlub.
