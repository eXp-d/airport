"""
СКРАПЕР АЭРОПОРТОВ (selenium + beautifulsoup4 + re)
====================================================

Что делает программа, по шагам:
  1. Открывает в настоящем (невидимом) браузере Chrome страницу страны
     на сайте ourairports.com и собирает список кодов всех аэропортов.
  2. Для КАЖДОГО аэропорта открывает две страницы:
       - главную (там таблица с координатами, высотой, типом...)
       - страницу взлётных полос (/runways.html)
  3. Из HTML вытаскивает нужные значения (bs4 + регулярные выражения).
  4. Сохраняет всё в csv, json, toml и yaml.

Запуск (примеры):
  python scrape_airports.py            -> Россия, все аэропорты
  python scrape_airports.py FI --limit 10   -> Финляндия, первые 10 аэропортов
  python scrape_airports.py RU FI EE   -> сразу три страны
"""

import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import tomli_w                      # запись toml
import yaml                         # запись yaml
from bs4 import BeautifulSoup       # разбор HTML
from selenium import webdriver      # управление браузером
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from timezonefinder import TimezoneFinder  # часовой пояс по координатам

# ----------------------------- НАСТРОЙКИ -----------------------------
SITE = "https://ourairports.com"
PAUSE = 1.0          # пауза после каждой страницы (секунды), чтобы не нагружать сайт
PAGE_SIZE = 50       # сколько аэропортов сайт показывает на одной странице списка
OUT_DIR = Path("output_scraped")   # куда складывать результат


# ------------------------- ЧАСТЬ 1. БРАУЗЕР --------------------------
def make_driver():
    """Запускает Chrome без окна (headless). Selenium сам найдёт драйвер."""
    opts = Options()
    opts.add_argument("--headless=new")      # браузер работает невидимо
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--log-level=3")       # меньше мусора в консоли
    return webdriver.Chrome(options=opts)


def get_html(driver, url):
    """Открывает страницу и возвращает её HTML-код (уже после загрузки JS)."""
    driver.get(url)
    try:
        # ждём до 15 секунд, пока на странице появится заголовок <h1>
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except Exception:
        pass  # если не дождались, всё равно пробуем разобрать то, что есть
    time.sleep(PAUSE)
    return driver.page_source


# --------------- ЧАСТЬ 2. СПИСОК АЭРОПОРТОВ СТРАНЫ -------------------
def collect_idents(driver, country):
    """
    Возвращает список кодов аэропортов страны, например ['UUEE', 'UUDD', ...].
    Код берём из ссылок вида /airports/UUEE/ с помощью регулярного выражения.
    """
    idents, seen = [], set()
    start = 0
    while True:
        url = f"{SITE}/countries/{country}/airports.html"
        if start:
            url += f"?start={start}"          # следующая страница списка
        soup = BeautifulSoup(get_html(driver, url), "html.parser")

        new = []
        for a in soup.find_all("a", href=True):
            m = re.fullmatch(
                r"(?:https://ourairports\.com)?/airports/([A-Za-z0-9-]+)/",
                a["href"],
            )
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                new.append(m.group(1))

        if not new:          # новых аэропортов нет -> список закончился
            break
        idents += new
        print(f"  {country}: найдено {len(idents)} аэропортов...")
        start += PAGE_SIZE
    return idents


# ------------------- ЧАСТЬ 3. РАЗБОР ОДНОГО АЭРОПОРТА ----------------
def parse_facility_table(soup):
    """
    На странице есть таблица «Facility data»: слева название поля,
    справа значение. Превращаем её в словарь {'ICAO code': 'UUEE', ...}.
    """
    data = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            data[label] = value
    return data


def parse_runways(runways_html):
    """
    На странице полос текст выглядит так:
        06C-24C 11,647 x 197 ft (3,550 x 60 m) Surface paved (concrete), lighted.
    Регулярное выражение достаёт: ID полосы, длину в футах, покрытие.
    """
    soup = BeautifulSoup(runways_html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" "))   # убираем переносы строк

    pattern = re.compile(
        r"(\S+)"                       # 1) ID полосы, например 06C-24C
        r"\s+([\d,]+)\s*x\s*[\d,]+\s*ft"   # 2) длина (фут) x ширина (фут)
        r"\s*\([^)]*\)"                # размеры в метрах в скобках - пропускаем
        r"\s*Surface\s+(.+?)"          # 3) покрытие
        r"\s*(?:,\s*(?:un)?lighted)?\s*\."  # ", lighted." в конце
    )
    runways = []
    for m in pattern.finditer(text):
        surface = m.group(3).strip()
        inner = re.search(r"\(([^)]+)\)", surface)   # paved (concrete) -> concrete
        if inner:
            surface = inner.group(1)
        runways.append({
            "id": m.group(1),
            "length_ft": int(m.group(2).replace(",", "")),
            "surface": surface,
        })
    return runways


def parse_airport(ident, main_html, runways_html, tf, now):
    """Собирает одну запись об аэропорте из двух HTML-страниц."""
    facts = parse_facility_table(BeautifulSoup(main_html, "html.parser"))

    # ICAO. Если у аэропорта нет кода, берём внутренний идентификатор сайта
    icao = facts.get("ICAO code") or ident

    # Тип аэропорта: large_airport, small_airport, closed ...
    kind = facts.get("Facility type", "")

    # Координаты: '55.977486,37.386677'
    lat = lon = None
    m = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", facts.get("Coordinates", ""))
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))

    # Высота: '622 ft / 190 m MSL' -> 622
    elevation = None
    m = re.search(r"(-?[\d,]+)\s*ft", facts.get("Field elevation", ""))
    if m:
        elevation = int(m.group(1).replace(",", ""))

    # Страна: 'Moscow, Moscow Oblast, RUSSIA' -> последнее слово после запятой
    country = facts.get("Location", "").split(",")[-1].strip().title()

    # Часовой пояс на сайте не указан, считаем по координатам (+3, -5 ...)
    timezone = None
    if lat is not None:
        tz_name = tf.timezone_at(lat=lat, lng=lon)
        if tz_name:
            hours = ZoneInfo(tz_name).utcoffset(now).total_seconds() / 3600
            timezone = f"{int(round(hours)):+d}"

    runways = parse_runways(runways_html)

    return {
        "icao": icao,
        "latitude": lat,
        "longitude": lon,
        "status": "close" if "closed" in kind else "open",
        "type": kind,
        "country": country,
        "elevation_ft": elevation,
        "timezone": timezone,
        "runways_count": len(runways),
        "runways": runways,
    }


# ------------------------ ЧАСТЬ 4. СОХРАНЕНИЕ ------------------------
def drop_none(obj):
    """toml не умеет хранить пустые значения, поэтому убираем None."""
    if isinstance(obj, dict):
        return {k: drop_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [drop_none(v) for v in obj]
    return obj


def save_all(airports):
    """Записывает результат во все четыре формата."""
    OUT_DIR.mkdir(exist_ok=True)

    # JSON
    with open(OUT_DIR / "airports.json", "w", encoding="utf-8") as f:
        json.dump(airports, f, ensure_ascii=False, indent=2)

    # YAML
    with open(OUT_DIR / "airports.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"airports": airports}, f, allow_unicode=True, sort_keys=False)

    # TOML
    with open(OUT_DIR / "airports.toml", "wb") as f:
        tomli_w.dump({"airports": drop_none(airports)}, f)

    # CSV: две таблицы - аэропорты и полосы (связаны по icao)
    cols = ["icao", "latitude", "longitude", "status", "type",
            "country", "elevation_ft", "timezone", "runways_count"]
    with open(OUT_DIR / "airports.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(airports)

    with open(OUT_DIR / "runways.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["icao", "id", "length_ft", "surface"])
        w.writeheader()
        for a in airports:
            for r in a["runways"]:
                w.writerow({"icao": a["icao"], **r})


# --------------------------- ГЛАВНАЯ ЧАСТЬ ---------------------------
def main():
    parser = argparse.ArgumentParser(description="Скрапер аэропортов OurAirports")
    parser.add_argument("countries", nargs="*", default=["RU"],
                        help="коды стран из 2 букв, например RU FI US")
    parser.add_argument("--limit", type=int, default=None,
                        help="максимум аэропортов на страну (для теста)")
    args = parser.parse_args()

    tf = TimezoneFinder()
    now = datetime.now()
    driver = make_driver()
    airports = []

    try:
        for country in args.countries:
            print(f"Страна {country}: собираю список аэропортов...")
            idents = collect_idents(driver, country.upper())
            if args.limit:
                idents = idents[: args.limit]

            for i, ident in enumerate(idents, 1):
                try:
                    main_html = get_html(driver, f"{SITE}/airports/{ident}/")
                    rw_html = get_html(driver, f"{SITE}/airports/{ident}/runways.html")
                    airports.append(parse_airport(ident, main_html, rw_html, tf, now))
                    print(f"[{country}] {i}/{len(idents)} {ident} готово")
                except Exception as err:      # один сбой не должен ломать всё
                    print(f"[{country}] {i}/{len(idents)} {ident} ОШИБКА: {err}")
    finally:
        driver.quit()
        save_all(airports)    # сохраняем даже если нажали Ctrl+C
        print(f"Сохранено {len(airports)} аэропортов в папку {OUT_DIR}/")


if __name__ == "__main__":
    main()
