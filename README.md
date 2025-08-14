# ByLaws-IQ MVP (Verified Synthesis Only)

Single-screen Streamlit app that returns zoning by-law metrics with live citations for a US address.

## Quickstart

1) Create and activate a virtual environment
```bash
python3 -m venv .venv && source .venv/bin/activate
```

2) Install dependencies
```bash
pip install -r requirements.txt
```

3) Create `.env` at project root with keys
```
OPENROUTER_API_KEY=...
TAVILY_API_KEY=...
MAPBOX_TOKEN=...   # or GEOAPIFY_KEY=...
```

4) Make the package importable (root-level `bylaws_iq/`)
   - No `src` path hacks needed. Streamlit imports `bylaws_iq` directly.

5) Run the app
```bash
streamlit run app/main.py
```

## Structure
```
app/
  main.py                 # Streamlit UI
  components.py           # Small UI helpers
bylaws_iq/
  __init__.py
  models.py             # Pydantic models for IO schema
  pipeline.py           # Orchestration (synthesis only)
  logging_config.py
  services/
    geocode.py          # Mapbox/Geoapify/Nominatim
    search.py           # Tavily with allowlist + scraping
    scrape.py           # Requests/BS4 + PDF text extraction
    llm.py              # OpenRouter synthesis
    zoning.py           # Discovery + heuristic helpers
```

## Notes
- Strict metrics only: carParking90Deg, officesParkingRatio, drivewayWidth, minLotArea, minFrontSetback, minSideSetback, minRearSetback, minLotFrontage, minLotWidth.
- Mode is `synthesis` only; verification pass disabled.
