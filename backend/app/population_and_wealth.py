import math
import os
import time
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Solar Market Reality API")

# Enable CORS so your React frontend (localhost:5173) can communicate freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HDX_RWI_RESOURCE_ID = "de2f953e-940c-43bb-b1f8-4d02d28124b5"
HDX_API_KEY = os.getenv("HDX_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJZaGRYaWJ3UTh1N2NMYlVZdk1pWmE0TVp2SDBOUGIzYU1qeXJPREV5VFpFIiwiaWF0IjoxNzkxMzExOTE5LCJleHAiOjE3OTU2MzE5MTl9.uM_IR0C7NYsRkK8H9NNZ5lAlEA60vCL-j6_EjKWlEJQ")
RWANDA_GIS_BASE = (
    "https://moegis.environment.gov.rw/server/rest/services/Hosted/"
    "Administrative_boundaries/FeatureServer"
)


def get_geometry_center(coords):
    flat = []

    def flatten(elem):
        if isinstance(elem, list):
            if len(elem) == 2 and all(isinstance(x, (int, float)) for x in elem):
                flat.append(elem)
            else:
                for item in elem:
                    flatten(item)

    flatten(coords)
    if not flat:
        return 0.0, 0.0
    lon = sum(c[0] for c in flat) / len(flat)
    lat = sum(c[1] for c in flat) / len(flat)
    return lon, lat


def resolve_location(raw_query: str):
    clean_query = raw_query.strip()

    # 1. Strategy A: Nominatim Geocoding
    try:
        nom_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": clean_query,
            "format": "geojson",
            "polygon_geojson": "1",
            "addressdetails": "1",
            "limit": "10",
        }
        headers = {"User-Agent": "SolarMarketRealityApp/1.0"}
        res = requests.get(nom_url, params=params, headers=headers, timeout=10)
        if res.ok:
            data = res.json()
            features = data.get("features", [])
            if features:
                # Rank by importance
                sorted_features = sorted(
                    features,
                    key=lambda x: x.get("properties", {}).get("importance", 0),
                    reverse=True,
                )
                feat = sorted_features[0]
                geom = feat.get("geometry", {})
                bbox = feat.get("bbox")
                props = feat.get("properties", {})

                if props.get("lat") and props.get("lon"):
                    lat = float(props["lat"])
                    lon = float(props["lon"])
                elif bbox:
                    lon = (bbox[0] + bbox[2]) / 2
                    lat = (bbox[1] + bbox[3]) / 2
                else:
                    lon, lat = get_geometry_center(geom.get("coordinates", []))

                return {
                    "place_name": props.get("display_name", clean_query),
                    "lat": lat,
                    "lon": lon,
                    "geometry": geom,
                }
    except Exception as e:
        print(f"Nominatim lookup failed: {e}")

    # 2. Strategy B: Rwanda Administrative GIS Boundary (Cells & Villages)
    search_name = clean_query.lower().replace("rwanda", "").split(",")[0].strip()
    escaped_name = search_name.replace("'", "''")

    layers = [(2, "cell"), (3, "village")]
    for layer_id, field in layers:
        try:
            where_clause = f"UPPER({field}) LIKE UPPER('%{escaped_name}%')"
            params = {
                "where": where_clause,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultRecordCount": "5",
            }
            url = f"{RWANDA_GIS_BASE}/{layer_id}/query"
            res = requests.get(url, params=params, timeout=10)
            if res.ok:
                data = res.json()
                features = data.get("features", [])
                if features:
                    feat = features[0]
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    lon, lat = get_geometry_center(geom.get("coordinates", []))

                    hierarchy = ", ".join(
                        filter(
                            None,
                            [
                                props.get("village"),
                                props.get("cell"),
                                props.get("sector"),
                                props.get("district"),
                                props.get("province"),
                                "Rwanda",
                            ],
                        )
                    )
                    return {
                        "place_name": hierarchy,
                        "lat": lat,
                        "lon": lon,
                        "geometry": geom,
                    }
        except Exception as e:
            print(f"Rwanda GIS lookup error: {e}")

    # 3. Strategy C: Open-Meteo Global Gazetteer fallback
    try:
        primary_name = clean_query.split(",")[0].strip()
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={primary_name}&count=1&language=en&format=json"
        res = requests.get(geo_url, timeout=10)
        if res.ok:
            data = res.json()
            results = data.get("results", [])
            if results:
                item = results[0]
                details = ", ".join(
                    filter(
                        None,
                        [
                            item.get("name"),
                            item.get("admin2"),
                            item.get("admin1"),
                            item.get("country"),
                        ],
                    )
                )
                return {
                    "place_name": details,
                    "lat": float(item["latitude"]),
                    "lon": float(item["longitude"]),
                    "geometry": None,
                }
    except Exception as e:
        print(f"Open-Meteo lookup error: {e}")

    raise HTTPException(status_code=404, detail="Location not found.")


def fetch_wealth_index(lat: float, lon: float):
    try:
        delta = 0.15
        min_lat, max_lat = round(lat - delta, 5), round(lat + delta, 5)
        min_lon, max_lon = round(lon - delta, 5), round(lon + delta, 5)

        sql = (
            f'SELECT latitude, longitude, rwi, error FROM "{HDX_RWI_RESOURCE_ID}" '
            f"WHERE latitude BETWEEN {min_lat} AND {max_lat} "
            f"AND longitude BETWEEN {min_lon} AND {max_lon} LIMIT 100"
        )
        hdx_url = "https://data.humdata.org/api/3/action/datastore_search_sql"
        headers = {"Authorization": HDX_API_KEY}
        res = requests.get(hdx_url, params={"sql": sql}, headers=headers, timeout=10)

        if not res.ok:
            return None

        records = res.json().get("result", {}).get("records", [])
        if not records:
            return None

        # Distance calculation
        closest = min(
            records,
            key=lambda r: math.hypot(
                float(r["latitude"]) - lat, float(r["longitude"]) - lon
            ),
        )
        score = float(closest["rwi"])

        if score < -0.4:
            return {
                "rwi": f"{score:.2f}",
                "tier": "Subsidy / Grant Dependent",
                "level": "Low Purchasing Power",
                "recommendation": "Entry-level pico-lanterns ($5–$15) or Results-Based Financing (RBF) grants.",
                "meterWidth": "25%",
                "color": "bg-rose-500",
            }
        elif score < 0.2:
            return {
                "rwi": f"{score:.2f}",
                "tier": "Core PAYGo Market",
                "level": "Moderate Purchasing Power",
                "recommendation": "Multi-light Solar Home Systems (SHS) with mobile money installment plans.",
                "meterWidth": "60%",
                "color": "bg-amber-500",
            }
        else:
            return {
                "rwi": f"{score:.2f}",
                "tier": "Commercially Viable",
                "level": "High Purchasing Power",
                "recommendation": "Large Tier 2+ Solar Home Systems, Solar TVs, Refrigeration, and Productive Use (water pumps).",
                "meterWidth": "90%",
                "color": "bg-emerald-500",
            }
    except Exception as e:
        print(f"RWI calculation error: {e}")
        return None


@app.get("/api/lookup")
def lookup_population_and_wealth(query: str = Query(..., min_length=1)):
    # 1. Geocode
    location = resolve_location(query)
    lat = location["lat"]
    lon = location["lon"]
    geom = location["geometry"]

    # 2. Polygon fallback if Point or absent
    if not geom or geom.get("type") not in ["Polygon", "MultiPolygon"]:
        d = 0.01
        geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon - d, lat - d],
                    [lon + d, lat - d],
                    [lon + d, lat + d],
                    [lon - d, lat + d],
                    [lon - d, lat - d],
                ]
            ],
        }

    # 3. Query WorldPop Population Task
    pop_url = "https://api.worldpop.org/v2/population"
    body = {"geojson": geom, "year": 2020, "resolution": "100m"}
    init_res = requests.post(pop_url, json=body, timeout=15)

    if not init_res.ok or not init_res.json().get("task_id"):
        raise HTTPException(
            status_code=500, detail="WorldPop failed to initiate population task."
        )

    task_id = init_res.json()["task_id"]
    pop_result = None

    for _ in range(30):
        time.sleep(2)
        task_res = requests.get(
            f"https://api.worldpop.org/v2/tasks/{task_id}", timeout=10
        )
        if task_res.ok:
            data = task_res.json()
            if data.get("status") == "success":
                pop_result = data.get("result")
                break
            if data.get("status") == "failure":
                raise HTTPException(
                    status_code=500, detail="WorldPop calculation failed."
                )

    if not pop_result:
        raise HTTPException(status_code=504, detail="WorldPop calculation timed out.")

    # 4. Query Meta RWI
    wealth = fetch_wealth_index(lat, lon)

    return {
        "placeName": location["place_name"],
        "population": round(pop_result["total_population"]),
        "geometryType": geom["type"],
        "wealth": wealth,
    }