# Ghana Climate Atlas - Backend API

FastAPI backend serving climate projection data for Ghana districts.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```


```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Endpoints

### Districts
- `GET /api/districts` - All districts as GeoJSON
- `GET /api/districts/list` - District list (no geometry)
- `GET /api/districts/regions` - List of regions
- `GET /api/districts/{id}` - Single district
- `GET /api/districts/{id}/climate` - District climate data

### Climate
- `GET /api/climate/variables` - Available climate variables
- `GET /api/climate/{variable}` - Climate data by variable
- `GET /api/climate/{variable}/compare` - Baseline vs future comparison
- `GET /api/climate/{variable}/range` - Min/max for color scale

## Query Parameters

| Parameter | Values | Default |
|-----------|--------|---------|
| period | baseline, 2030, 2050, 2080 | baseline |
| scenario | historical, rcp45, rcp85 | rcp45 |

## Example Queries

```bash
# Get all districts
curl http://localhost:8000/api/districts

# Get annual max temperature for 2050 under RCP8.5
curl "http://localhost:8000/api/climate/annual_max_temp?period=2050&scenario=rcp85"

# Compare baseline to 2050
curl "http://localhost:8000/api/climate/annual_max_temp/compare?period=2050&scenario=rcp85"
```

## Data Source

Currently using mock data based on CORDEX-Africa projections.
Replace with real KAPy/GMet Climate Atlas data when available.
