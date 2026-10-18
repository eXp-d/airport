"""
ПРОВЕРКА МАГАЗИНОВ: пускает ли сайт автоматический браузер и видны ли цены.

Запуск (в кавычках - по ссылке на страницу товара из каждого магазина):
  python check_store.py "https://site1.ru/product/..." "https://site2.ru/product/..."
  python check_store.py --yandex "https://site1.ru/..."     (через Яндекс Браузер)
"""
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# фразы, по которым видно, что сайт отказал в доступе
BLOCK_WORDS = ["403", "forbidden", "captcha", "капча", "доступ запрещ",
               "доступ ограничен", "access denied", "вы не робот", "подозрительн",
               "проблемы со связью", "проверьте настройки интернета", "vpn",
               "блокировк"]


YANDEX_PATHS = [
    r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
    r"C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe"),
]
# берём первый путь, по которому реально лежит браузер
YANDEX_BROWSER = next((p for p in YANDEX_PATHS if os.path.exists(p)), YANDEX_PATHS[0])
YANDEX_DRIVER = Path("yandexdriver.exe")


def main():
    use_yandex = "--yandex" in sys.argv          # проверка через Яндекс Браузер
    urls = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not urls:
        print('Укажите ссылки: python check_store.py "ссылка1" "ссылка2"')
        return

    opts = Options()
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--lang=ru-RU")
    if use_yandex:
        opts.binary_location = YANDEX_BROWSER
        driver = webdriver.Chrome(service=Service(str(YANDEX_DRIVER)), options=opts)
    else:
        driver = webdriver.Chrome(options=opts)

    try:
        for url in urls:
            driver.get(url)
            time.sleep(6)                                  # даём странице загрузиться
            title = driver.title.lower()
            body = driver.find_element(By.TAG_NAME, "body").text[:1500].lower()

            blocked = [w for w in BLOCK_WORDS if w in title or w in body]
            has_price = "₽" in body or "руб" in body or "₽" in driver.page_source

            if blocked:
                verdict = f"БЛОК (признаки: {', '.join(blocked)})"
            elif has_price:
                verdict = "ПУСТИЛ, цены видны"
            else:
                verdict = "ПУСТИЛ, но цен не видно (возможно, нужно выбрать магазин/город)"
            print(f"\n{url}\n  -> {verdict}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
