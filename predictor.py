"""
Módulo de predicción ML — Decision Tree adaptado a datos reales de odds.
Si no hay datos históricos de partidos, usa las cuotas implícitas como features.
"""

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import LabelEncoder
import logging

logger = logging.getLogger(__name__)


class Predictor:
    def __init__(self):
        self.model = None
        self.encoder = LabelEncoder()
        self._entrenar_modelo_base()

    def _entrenar_modelo_base(self):
        """
        Modelo base entrenado con datos de ejemplo de Liga MX.
        En producción, reemplazar con datos históricos reales de la temporada.
        Cuanto más datos históricos tengas en la BD, mejor será el modelo.
        """
        data = {
            "prob_impl_local": [0.55, 0.48, 0.35, 0.62, 0.28, 0.50, 0.40, 0.60, 0.32, 0.25,
                                 0.58, 0.44, 0.38, 0.65, 0.30, 0.52, 0.42, 0.61, 0.29, 0.47],
            "prob_impl_empate": [0.28, 0.30, 0.31, 0.25, 0.29, 0.30, 0.30, 0.26, 0.30, 0.28,
                                  0.27, 0.29, 0.31, 0.24, 0.30, 0.29, 0.30, 0.25, 0.30, 0.29],
            "prob_impl_visitante": [0.17, 0.22, 0.34, 0.13, 0.43, 0.20, 0.30, 0.14, 0.38, 0.47,
                                     0.15, 0.27, 0.31, 0.11, 0.40, 0.19, 0.28, 0.14, 0.41, 0.24],
            "resultado": ["H", "H", "A", "H", "A", "H", "A", "H", "A", "A",
                          "H", "D", "A", "H", "A", "H", "D", "H", "A", "D"]
        }

        df = pd.DataFrame(data)
        X = df[["prob_impl_local", "prob_impl_empate", "prob_impl_visitante"]]
        y = df["resultado"]

        self.encoder.fit(["A", "D", "H"])
        y_enc = self.encoder.transform(y)

        self.model = DecisionTreeClassifier(max_depth=4, random_state=42)
        self.model.fit(X, y_enc)
        logger.info("Modelo ML entrenado correctamente.")

    def predecir(self, datos_partido: dict) -> dict:
        """
        Usa las probabilidades implícitas de las cuotas para predecir.
        Probabilidad implícita = 1 / cuota_decimal
        """
        casas = datos_partido.get("casas", [])
        if not casas:
            return self._prediccion_vacia()

        # Usar las mejores cuotas disponibles
        try:
            mejor_local = max(c["local"] for c in casas if c["local"] > 0)
            mejor_empate = max(c["empate"] for c in casas if c["empate"] > 0)
            mejor_visitante = max(c["visitante"] for c in casas if c["visitante"] > 0)
        except (ValueError, TypeError):
            return self._prediccion_vacia()

        # Probabilidades implícitas
        p_local = 1 / mejor_local
        p_empate = 1 / mejor_empate
        p_visitante = 1 / mejor_visitante
        total = p_local + p_empate + p_visitante

        # Normalizar (quitar margen de la casa)
        p_local /= total
        p_empate /= total
        p_visitante /= total

        # Predicción
        X = np.array([[p_local, p_empate, p_visitante]])
        pred_enc = self.model.predict(X)[0]
        proba = self.model.predict_proba(X)[0]

        resultado = self.encoder.inverse_transform([pred_enc])[0]

        # Mapear probabilidades a clases
        clases = self.encoder.classes_  # ['A', 'D', 'H']
        proba_dict = {c: p for c, p in zip(clases, proba)}

        return {
            "resultado": resultado,
            "prob_local": proba_dict.get("H", p_local),
            "prob_empate": proba_dict.get("D", p_empate),
            "prob_visitante": proba_dict.get("A", p_visitante),
            "prob_impl_local": p_local,
            "prob_impl_empate": p_empate,
            "prob_impl_visitante": p_visitante,
        }

    def _prediccion_vacia(self) -> dict:
        return {
            "resultado": "?",
            "prob_local": 0.33,
            "prob_empate": 0.33,
            "prob_visitante": 0.33,
        }

    def reentrenar(self, df_historico: pd.DataFrame):
        """
        Reentrena el modelo con datos históricos reales de tu BD.
        Llama esto periódicamente cuando tengas suficientes datos.
        
        df_historico debe tener columnas:
        - cuota_local, cuota_empate, cuota_visitante, resultado (H/D/A)
        """
        if len(df_historico) < 20:
            logger.warning("Pocos datos para reentrenar. Se mantiene modelo base.")
            return

        df_historico = df_historico.dropna(subset=["cuota_local", "cuota_empate", "cuota_visitante", "resultado"])
        df_historico["p_local"] = 1 / df_historico["cuota_local"]
        df_historico["p_empate"] = 1 / df_historico["cuota_empate"]
        df_historico["p_visitante"] = 1 / df_historico["cuota_visitante"]
        total = df_historico["p_local"] + df_historico["p_empate"] + df_historico["p_visitante"]
        df_historico["p_local"] /= total
        df_historico["p_empate"] /= total
        df_historico["p_visitante"] /= total

        X = df_historico[["p_local", "p_empate", "p_visitante"]]
        y = self.encoder.transform(df_historico["resultado"])

        self.model.fit(X, y)
        logger.info(f"Modelo reentrenado con {len(df_historico)} registros históricos.")
