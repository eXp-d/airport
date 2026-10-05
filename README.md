# Аэропорты мира

Датасет аэропортов: ICAO, координаты, статус, тип, страна, высота (фут),
часовой пояс, количество и параметры взлётных полос.

## Файлы
- `scrape_airports.py` - скрапер на selenium + beautifulsoup4 + re (основной)
- `build_dataset.py` - быстрый вариант: скачивает готовые CSV OurAirports

## Запуск
    pip install -r requirements.txt
    python scrape_airports.py FI --limit 10

Нужен установленный Google Chrome. Результат появится в `output_scraped/`
в форматах csv, json, toml, yaml.

Источник данных: ourairports.com (общественное достояние).
