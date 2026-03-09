# 🤖 Bot Comparador de Apuestas — Liga MX

## Archivos del proyecto

```
bot_apuestas/
├── bot.py          ← Núcleo del bot (comandos, callbacks, scheduler)
├── database.py     ← BD SQLite + todas las consultas
├── scraper.py      ← Extracción de Caliente.mx y Codere.mx
├── predictor.py    ← Modelo ML Decision Tree
└── requirements.txt
```

---

## ⚙️ Instalación local (para pruebas)

```bash
pip install -r requirements.txt

# Obtén tu token en @BotFather en Telegram
export TELEGRAM_TOKEN="tu_token_aqui"

python bot.py
```

---

## ☁️ Despliegue en la nube (RECOMENDADO)

### Opción 1 — Railway.app (gratis para empezar)
1. Crea cuenta en https://railway.app
2. Conecta tu repositorio de GitHub con estos archivos
3. Agrega variable de entorno: `TELEGRAM_TOKEN=tu_token`
4. Railway instala dependencias y corre `python bot.py` automáticamente
5. Instala ChromeDriver en el buildpack (agrega `Aptfile` con `google-chrome-stable`)

### Opción 2 — VPS (DigitalOcean / Linode ~$6 USD/mes)
```bash
# En el servidor:
sudo apt update && sudo apt install -y python3-pip google-chrome-stable
pip install -r requirements.txt
export TELEGRAM_TOKEN="tu_token"

# Correr en background con screen o systemd:
screen -S bot
python bot.py
# Ctrl+A, D para dejar corriendo
```

### Aptfile (necesario para Railway/Render)
```
google-chrome-stable
```

---

## 🔔 Comandos del bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida y lista de comandos |
| `/partidos` | Lista de partidos del día con botones |
| `/odds america chivas` | Comparativa de cuotas para ese partido |
| `/prediccion america chivas` | Predicción ML + probabilidades |
| `/variacion america chivas` | Movimiento histórico de cuotas |
| `/arbitraje` | Detecta oportunidades sin riesgo |
| `/alertas` | Configura alertas de cambio de cuota |
| `/ayuda` | Guía de uso |

---

## 💡 Ideas para expandir el bot

1. **Más casas de apuestas**: Agregar BetMGM, 1xBet, Betway
2. **Más ligas**: Champions, Premier League, NFL
3. **Modo premium**: Cobra suscripción mensual con Stripe/PayPal
4. **Canal de Telegram**: Publica las mejores cuotas automáticamente cada día
5. **Historial de resultados**: Guarda resultados reales para mejorar el modelo ML
6. **Estadísticas de equipos**: Integrar API de fútbol (football-data.org es gratuita)

---

## 🔄 Flujo de datos

```
Cada 30 min:
Caliente.mx ─┐
              ├── ScraperManager ── SQLite DB ── Bot Telegram ── Usuarios
Codere.mx   ─┘                        │
                                       └── Alertas automáticas
```

---

## ⚠️ Notas importantes

- El scraper usa **Selenium headless** (sin ventana gráfica), compatible con servidores Linux
- La BD es **SQLite** por simplicidad; para escalar a 1000+ usuarios migra a **PostgreSQL**
- El modelo ML mejora automáticamente mientras más datos históricos acumules
- Revisa los **Términos de Uso** de Caliente y Codere antes de hacer scraping comercial
