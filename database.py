"""
Módulo de base de datos — SQLite local (fácil migrar a PostgreSQL en la nube)
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from unidecode import unidecode
import os

DB_FILE = os.environ.get("DB_PATH", "apuestas.db")


def normalizar(texto: str) -> str:
    texto = unidecode(texto.lower())
    eliminar = ["xolos de caliente", "xolos de", "de caliente", "xolos",
                 "caliente", "fc", "club", "cf", "cd", "de", "los",
                 "atletico", "atletico", "futbol"]
    for w in eliminar:
        texto = texto.replace(w, " ")
    while "  " in texto:
        texto = texto.replace("  ", " ")
    return texto.strip()


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self._crear_tablas()

    def _crear_tablas(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                casa TEXT NOT NULL,
                partido TEXT NOT NULL,
                partido_norm TEXT NOT NULL,
                cuota_local REAL,
                cuota_empate REAL,
                cuota_visitante REAL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                porcentaje REAL NOT NULL,
                activa INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_odds_norm ON odds(partido_norm);
            CREATE INDEX IF NOT EXISTS idx_odds_fecha ON odds(fecha);
        """)
        self.conn.commit()

    def guardar_datos(self, filas: list):
        """
        Guarda lista de registros.
        Cada fila: [casa, partido, partido_norm, local, empate, visitante, fecha, hora]
        """
        if not filas:
            return
        cur = self.conn.cursor()
        cur.executemany("""
            INSERT INTO odds (casa, partido, partido_norm, cuota_local, cuota_empate, cuota_visitante, fecha, hora)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, filas)
        self.conn.commit()

    def get_partidos_recientes(self) -> list:
        """Retorna partidos únicos de las últimas 24 horas."""
        hace_24h = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT partido, partido_norm
            FROM odds
            WHERE created_at >= ?
            ORDER BY partido
        """, (hace_24h,))
        return [{"partido": r[0], "partido_norm": r[1]} for r in cur.fetchall()]

    def buscar_partido(self, busqueda: str) -> dict | None:
        """Busca un partido por nombre aproximado."""
        busqueda_norm = normalizar(busqueda)
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT partido_norm, partido FROM odds
            WHERE partido_norm LIKE ?
            ORDER BY created_at DESC LIMIT 1
        """, (f"%{busqueda_norm}%",))
        row = cur.fetchone()
        if not row:
            return None
        return self.get_partido_por_norm(row[0])

    def get_partido_por_norm(self, partido_norm: str) -> dict | None:
        """Obtiene las cuotas actuales de cada casa para un partido."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT casa, partido, cuota_local, cuota_empate, cuota_visitante, hora
            FROM odds
            WHERE partido_norm = ?
            ORDER BY created_at DESC
        """, (partido_norm,))
        rows = cur.fetchall()
        if not rows:
            return None

        # Obtener la cuota más reciente por casa
        casas_vistas = set()
        casas = []
        for r in rows:
            if r[0] not in casas_vistas:
                casas_vistas.add(r[0])
                casas.append({
                    "casa": r[0],
                    "local": r[2] or 0,
                    "empate": r[3] or 0,
                    "visitante": r[4] or 0,
                })

        return {
            "partido": rows[0][1],
            "partido_norm": partido_norm,
            "hora": rows[0][5],
            "casas": casas
        }

    def get_variaciones(self, busqueda: str) -> list:
        busqueda_norm = normalizar(busqueda)
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT partido_norm FROM odds WHERE partido_norm LIKE ? LIMIT 1
        """, (f"%{busqueda_norm}%",))
        row = cur.fetchone()
        if not row:
            return []
        return self.get_variaciones_por_norm(row[0])

    def get_variaciones_por_norm(self, partido_norm: str) -> list:
        """Calcula variación porcentual primera vs última cuota por casa."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT casa, partido, cuota_local, cuota_empate, cuota_visitante, created_at
            FROM odds
            WHERE partido_norm = ?
            ORDER BY created_at
        """, (partido_norm,))
        rows = cur.fetchall()
        if not rows:
            return []

        df = pd.DataFrame(rows, columns=["casa", "partido", "local", "empate", "visitante", "created_at"])
        resultado = []

        for casa in df["casa"].unique():
            sub = df[df["casa"] == casa]
            if len(sub) < 2:
                continue
            primera = sub.iloc[0]
            ultima = sub.iloc[-1]

            def var_pct(ini, fin):
                try:
                    return ((fin - ini) / ini) * 100 if ini else 0
                except:
                    return 0

            resultado.append({
                "partido": sub.iloc[0]["partido"],
                "casa": casa,
                "local_actual": ultima["local"],
                "empate_actual": ultima["empate"],
                "visitante_actual": ultima["visitante"],
                "var_local": var_pct(primera["local"], ultima["local"]),
                "var_empate": var_pct(primera["empate"], ultima["empate"]),
                "var_visitante": var_pct(primera["visitante"], ultima["visitante"]),
            })

        return resultado

    def detectar_arbitraje(self, umbral_margen: float = 0) -> list:
        """
        Detecta oportunidades de arbitraje.
        Arbitraje: suma de (1/cuota) para los mejores resultados < 1
        """
        partidos = self.get_partidos_recientes()
        oportunidades = []

        for p in partidos:
            datos = self.get_partido_por_norm(p["partido_norm"])
            if not datos or not datos["casas"]:
                continue

            casas = datos["casas"]
            mejor_local = max(casas, key=lambda x: x["local"])
            mejor_empate = max(casas, key=lambda x: x["empate"])
            mejor_visitante = max(casas, key=lambda x: x["visitante"])

            try:
                suma = (1 / mejor_local["local"]) + (1 / mejor_empate["empate"]) + (1 / mejor_visitante["visitante"])
                if suma < 1:
                    margen = (1 - suma) * 100
                    if margen > umbral_margen:
                        oportunidades.append({
                            "partido": datos["partido"],
                            "mejor_local": mejor_local["local"],
                            "casa_local": mejor_local["casa"],
                            "mejor_empate": mejor_empate["empate"],
                            "casa_empate": mejor_empate["casa"],
                            "mejor_visitante": mejor_visitante["visitante"],
                            "casa_visitante": mejor_visitante["casa"],
                            "margen": margen,
                        })
            except (ZeroDivisionError, TypeError):
                continue

        return sorted(oportunidades, key=lambda x: x["margen"], reverse=True)

    def activar_alerta(self, user_id: int, tipo: str, porcentaje: float):
        cur = self.conn.cursor()
        # Desactivar alertas previas del usuario
        cur.execute("UPDATE alertas SET activa = 0 WHERE user_id = ?", (user_id,))
        cur.execute(
            "INSERT INTO alertas (user_id, tipo, porcentaje) VALUES (?, ?, ?)",
            (user_id, tipo, porcentaje)
        )
        self.conn.commit()

    def desactivar_alertas(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE alertas SET activa = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_alertas_activas(self) -> list:
        """
        Revisa si alguna cuota cambió más del umbral para usuarios con alertas activas.
        Retorna alertas a disparar.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT user_id, tipo, porcentaje FROM alertas WHERE activa = 1")
        alertas = cur.fetchall()

        disparadas = []
        partidos = self.get_partidos_recientes()

        for partido in partidos:
            variaciones = self.get_variaciones_por_norm(partido["partido_norm"])
            for v in variaciones:
                for alerta in alertas:
                    user_id, tipo, pct = alerta
                    for campo, var_val, val_actual in [
                        ("Local", v["var_local"], v["local_actual"]),
                        ("Empate", v["var_empate"], v["empate_actual"]),
                        ("Visitante", v["var_visitante"], v["visitante_actual"]),
                    ]:
                        cond_sube = tipo == "sube" and var_val >= pct
                        cond_baja = tipo == "baja" and var_val <= -pct
                        if cond_sube or cond_baja:
                            disparadas.append({
                                "user_id": user_id,
                                "partido": v["partido"],
                                "tipo": campo,
                                "direccion": tipo,
                                "variacion": abs(var_val),
                                "valor_nuevo": val_actual,
                                "disparada": True,
                            })

        return disparadas


db = Database()
