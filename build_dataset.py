import csv
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

BASE = "https://davidmegginson.github.io/ourairports-data/"
DATA_DIR = Path("data")
OUT_DIR = Path("output")


def read_csv(name):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / name
    if not path.exists():
        print(f"Скачиваю {name} ...")
        urllib.request.urlretrieve(BASE + name, path)
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value):
    f = to_float(value)
    return None if f is None else int(round(f))


def main():
    airports_raw = read_csv("airports.csv")
    runways_raw = read_csv("runways.csv")
    countries = {r["code"]: r["name"] for r in read_csv("countries.csv")}

    tf = TimezoneFinder()
    now = datetime.now()

    runways_by_airport = {}
    for r in runways_raw:
        runways_by_airport.setdefault(r["airport_ident"], []).append({
            "id": "/".join(x for x in (r.get("le_ident"), r.get("he_ident")) if x),
            "length_ft": to_int(r.get("length_ft")),
            "surface": r.get("surface") or None,
        })

    airports = []
    runway_rows = []
    for a in airports_raw:
        lat = to_float(a["latitude_deg"])
        lon = to_float(a["longitude_deg"])
        if lat is None or lon is None:
            continue

        # ICAO: отдельная колонка, иначе gps_code, иначе внутренний ident
        icao = a.get("icao_code") or a.get("gps_code") or a["ident"]

        # Часовой пояс: целое смещение от UTC, например +3
        tz_name = tf.timezone_at(lat=lat, lng=lon)
        tz = None
        if tz_name:
            offset = ZoneInfo(tz_name).utcoffset(now).total_seconds() / 3600
            tz = int(round(offset))

        runways = runways_by_airport.get(a["ident"], [])
        airports.append({
            "icao": icao,
            "latitude": lat,
            "longitude": lon,
            "status": "close" if a["type"] == "closed" else "open",
            "type": a["type"],
            "country": countries.get(a["iso_country"], a["iso_country"]),
            "elevation_ft": to_int(a["elevation_ft"]),
            "timezone": f"{tz:+d}" if tz is not None else None,
            "runways": runways,
        })
        for rw in runways:
            runway_rows.append({"icao": icao, **rw})

    OUT_DIR.mkdir(exist_ok=True)

    with open(OUT_DIR / "airports.json", "w", encoding="utf-8") as f:
        json.dump(airports, f, ensure_ascii=False, indent=2)

    cols = ["icao", "latitude", "longitude", "status", "type",
            "country", "elevation_ft", "timezone"]
    with open(OUT_DIR / "airports.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(airports)

    with open(OUT_DIR / "runways.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["icao", "id", "length_ft", "surface"])
        w.writeheader()
        w.writerows(runway_rows)

    print(f"Готово: {len(airports)} аэропортов, {len(runway_rows)} ВПП -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
