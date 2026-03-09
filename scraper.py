"""
Módulo de scraping — versión async para correr en servidor sin pantalla.
Usa Selenium en modo headless (sin interfaz gráfica).
"""

import time
import asyncio
from datetime import datetime
from unidecode import unidecode
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

logger = logging.getLogger(__name__)


def normalizar(p: str) -> str:
    p = unidecode(p.lower())
    eliminar = ["xolos de caliente", "xolos de", "de caliente", "xolos", "caliente",
                 "fc", "club", "cf", "cd", "de", "los", "atletico", "futbol"]
    for w in eliminar:
        p = p.replace(w, " ")
    while "  " in p:
        p = p.replace("  ", " ")
    return p.strip()


def american_a_decimal(m) -> float | None:
    try:
        m = int(str(m).replace("+", ""))
        return round((m / 100 + 1) if m > 0 else (100 / abs(m) + 1), 2)
    except:
        return None


def crear_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless")          # ← SIN pantalla (clave para servidor)
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=opts)


def _extraer_caliente(driver) -> list:
    logger.info("Scrapeando Caliente.mx...")
    driver.get("https://sports.caliente.mx/es_MX/Liga-MX")
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.seln-name"))
        )
        time.sleep(2)
    except:
        logger.warning("No se cargaron partidos en Caliente.mx")
        return []

    filas = driver.find_elements(By.CSS_SELECTOR, "tr.mkt") or driver.find_elements(By.CSS_SELECTOR, "div.mkt")
    datos = []
    ahora = datetime.now()

    for f in filas:
        try:
            equipos = f.find_elements(By.CSS_SELECTOR, "span.seln-name")
            cuotas = f.find_elements(By.CSS_SELECTOR, "button.price")
            if len(equipos) == 2 and len(cuotas) >= 3:
                el, ev = (e.text.strip() for e in equipos)
                m_loc = cuotas[0].text.split("\n")[-1].replace("+", "")
                m_emp = cuotas[1].text.split("\n")[-1].replace("+", "")
                m_vis = cuotas[2].text.split("\n")[-1].replace("+", "")
                partido = f"{el} vs {ev}"
                datos.append([
                    "Caliente",
                    partido,
                    normalizar(partido),
                    american_a_decimal(m_loc),
                    american_a_decimal(m_emp),
                    american_a_decimal(m_vis),
                    ahora.strftime("%Y-%m-%d"),
                    ahora.strftime("%H:%M:%S"),
                ])
        except Exception as e:
            logger.error(f"Error Caliente fila: {e}")

    logger.info(f"Caliente: {len(datos)} partidos extraídos.")
    return datos


def _extraer_codere(driver) -> list:
    logger.info("Scrapeando Codere.mx...")
    driver.get("https://apuestas.codere.mx/es_MX/t/45349/LigaMX")
    try:
        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.mkt"))
        )
        time.sleep(4)
    except:
        logger.warning("No se cargaron partidos en Codere.mx")
        return []

    datos = []
    ahora = datetime.now()

    for f in driver.find_elements(By.CSS_SELECTOR, "tr.mkt"):
        try:
            equipos = f.find_elements(By.CSS_SELECTOR, "span.seln-name")
            cuotas = f.find_elements(By.CSS_SELECTOR, "button.price")
            if len(equipos) == 2 and len(cuotas) >= 3:
                el, ev = (e.text.strip() for e in equipos)
                m_loc = cuotas[0].text.split("\n")[-1].replace("+", "")
                m_emp = cuotas[1].text.split("\n")[-1].replace("+", "")
                m_vis = cuotas[2].text.split("\n")[-1].replace("+", "")
                partido = f"{el} vs {ev}"
                datos.append([
                    "Codere",
                    partido,
                    normalizar(partido),
                    american_a_decimal(m_loc),
                    american_a_decimal(m_emp),
                    american_a_decimal(m_vis),
                    ahora.strftime("%Y-%m-%d"),
                    ahora.strftime("%H:%M:%S"),
                ])
        except Exception as e:
            logger.error(f"Error Codere fila: {e}")

    logger.info(f"Codere: {len(datos)} partidos extraídos.")
    return datos


class ScraperManager:
    async def extraer_todos(self) -> list:
        """
        Corre el scraper en un thread separado para no bloquear el event loop de asyncio.
        """
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, self._scrape_sync)
        return resultado

    def _scrape_sync(self) -> list:
        driver = crear_driver()
        try:
            cal = _extraer_caliente(driver)
            cod = _extraer_codere(driver)
            return cal + cod
        finally:
            driver.quit()
