"""
Bot de Telegram - Comparador de Apuestas Liga MX
Requiere: python-telegram-bot, pandas, scikit-learn, sqlalchemy, apscheduler
"""

import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import db
from scraper import ScraperManager
from predictor import Predictor

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")

scraper = ScraperManager()
predictor = Predictor()

# ─────────────────── COMANDOS ───────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "⚽ *Bot Comparador de Apuestas - Liga MX*\n\n"
        "Comandos disponibles:\n"
        "• /partidos — Ver partidos del día\n"
        "• /odds — Comparar cuotas entre casas\n"
        "• /prediccion — Predicción ML del partido\n"
        "• /variacion — Movimiento histórico de cuotas\n"
        "• /arbitraje — Detectar apuestas sin riesgo\n"
        "• /alertas — Configurar alertas de cuotas\n"
        "• /ayuda — Ver más información\n\n"
        "💡 Los datos se actualizan cada 30 minutos automáticamente."
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_partidos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra los partidos disponibles con botones interactivos."""
    partidos = db.get_partidos_recientes()

    if not partidos:
        await update.message.reply_text(
            "⚠️ No hay partidos disponibles en este momento.\n"
            "Los datos se actualizan cada 30 minutos."
        )
        return

    keyboard = []
    for p in partidos:
        keyboard.append([
            InlineKeyboardButton(
                f"⚽ {p['partido']}",
                callback_data=f"partido_{p['partido_norm']}"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"📋 *Partidos disponibles* ({len(partidos)} encontrados)\n"
        "Selecciona uno para ver las cuotas:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def cmd_odds(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra tabla comparativa de odds."""
    if ctx.args:
        partido_busqueda = " ".join(ctx.args)
        resultado = db.buscar_partido(partido_busqueda)
        if resultado:
            texto = _formatear_odds(resultado)
            await update.message.reply_text(texto, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"❌ No encontré el partido: *{partido_busqueda}*\n"
                "Usa /partidos para ver los disponibles.",
                parse_mode="Markdown"
            )
    else:
        await cmd_partidos(update, ctx)


async def cmd_prediccion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Predicción ML para un partido."""
    if not ctx.args:
        await update.message.reply_text(
            "Uso: /prediccion [nombre del partido]\n"
            "Ejemplo: /prediccion america chivas"
        )
        return

    partido_busqueda = " ".join(ctx.args)
    datos = db.buscar_partido(partido_busqueda)

    if not datos:
        await update.message.reply_text(f"❌ No encontré: {partido_busqueda}")
        return

    pred = predictor.predecir(datos)
    texto = _formatear_prediccion(datos['partido'], pred)
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_variacion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra movimiento histórico de cuotas."""
    if not ctx.args:
        await update.message.reply_text(
            "Uso: /variacion [nombre del partido]\n"
            "Ejemplo: /variacion america guadalajara"
        )
        return

    partido_busqueda = " ".join(ctx.args)
    variaciones = db.get_variaciones(partido_busqueda)

    if not variaciones:
        await update.message.reply_text(
            f"❌ Sin datos históricos para: {partido_busqueda}"
        )
        return

    texto = _formatear_variaciones(variaciones)
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_arbitraje(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Detecta oportunidades de arbitraje entre casas."""
    oportunidades = db.detectar_arbitraje()

    if not oportunidades:
        await update.message.reply_text(
            "📊 No se detectaron oportunidades de arbitraje en este momento.\n"
            "El arbitraje ocurre cuando la suma de probabilidades implícitas < 100%."
        )
        return

    texto = "🎯 *Oportunidades de Arbitraje Detectadas*\n\n"
    for op in oportunidades:
        margen = op['margen']
        texto += (
            f"⚽ *{op['partido']}*\n"
            f"  Local: {op['mejor_local']:.2f} ({op['casa_local']})\n"
            f"  Empate: {op['mejor_empate']:.2f} ({op['casa_empate']})\n"
            f"  Visitante: {op['mejor_visitante']:.2f} ({op['casa_visitante']})\n"
            f"  💰 Margen de ganancia: *{margen:.2f}%*\n\n"
        )

    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_alertas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Configura alertas de cambio de cuota."""
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📈 Alerta cuando cuota SUBA 5%", callback_data="alerta_sube_5")],
        [InlineKeyboardButton("📉 Alerta cuando cuota BAJE 5%", callback_data="alerta_baja_5")],
        [InlineKeyboardButton("🔔 Alerta cuando cuota SUBA 10%", callback_data="alerta_sube_10")],
        [InlineKeyboardButton("❌ Desactivar mis alertas", callback_data="alerta_off")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔔 *Configuración de Alertas*\n\n"
        "Te avisaré cuando las cuotas cambien significativamente:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "📚 *Guía del Bot de Apuestas*\n\n"
        "*¿Cómo leer las cuotas?*\n"
        "Las cuotas en formato decimal indican cuánto ganas por cada peso apostado.\n"
        "Ej: cuota 2.50 → apostas $100, ganas $250 (ganancia neta: $150)\n\n"
        "*¿Qué es el arbitraje?*\n"
        "Cuando las cuotas de diferentes casas permiten apostar a todos los resultados "
        "y garantizar ganancia sin importar el resultado.\n\n"
        "*¿Cómo funciona la predicción ML?*\n"
        "Usa un modelo entrenado con datos históricos de puntos y goles promedio "
        "para estimar probabilidades de cada resultado.\n\n"
        "*Frecuencia de actualización:* Cada 30 minutos ⏱\n"
        "*Casas incluidas:* Caliente.mx, Codere.mx"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


# ─────────────────── CALLBACKS ───────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("partido_"):
        partido_norm = data.replace("partido_", "")
        resultado = db.get_partido_por_norm(partido_norm)
        if resultado:
            texto = _formatear_odds(resultado)
            keyboard = [[
                InlineKeyboardButton("🤖 Ver Predicción ML", callback_data=f"pred_{partido_norm}"),
                InlineKeyboardButton("📈 Ver Variación", callback_data=f"var_{partido_norm}"),
            ]]
            await query.edit_message_text(
                texto,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

    elif data.startswith("pred_"):
        partido_norm = data.replace("pred_", "")
        datos = db.get_partido_por_norm(partido_norm)
        if datos:
            pred = predictor.predecir(datos)
            texto = _formatear_prediccion(datos['partido'], pred)
            await query.edit_message_text(texto, parse_mode="Markdown")

    elif data.startswith("var_"):
        partido_norm = data.replace("var_", "")
        variaciones = db.get_variaciones_por_norm(partido_norm)
        if variaciones:
            texto = _formatear_variaciones(variaciones)
            await query.edit_message_text(texto, parse_mode="Markdown")

    elif data.startswith("alerta_"):
        accion = data.replace("alerta_", "")
        user_id = query.from_user.id
        if accion == "off":
            db.desactivar_alertas(user_id)
            await query.edit_message_text("✅ Alertas desactivadas.")
        else:
            tipo, pct = accion.split("_")
            db.activar_alerta(user_id, tipo, int(pct))
            await query.edit_message_text(
                f"✅ Alerta activada: te avisaré cuando una cuota {'suba' if tipo=='sube' else 'baje'} un {pct}%."
            )


# ─────────────────── FORMATTERS ───────────────────

def _formatear_odds(datos: dict) -> str:
    partido = datos['partido']
    casas = datos['casas']

    texto = f"⚽ *{partido}*\n"
    texto += f"🕐 Actualizado: {datos.get('hora', 'N/A')}\n\n"
    texto += "```\n"
    texto += f"{'Casa':<12} {'Local':>7} {'Empate':>7} {'Visit':>7}\n"
    texto += "-" * 37 + "\n"

    for c in casas:
        texto += f"{c['casa']:<12} {c['local']:>7.2f} {c['empate']:>7.2f} {c['visitante']:>7.2f}\n"

    texto += "```\n"

    # Mejores cuotas
    mejor_local = max(casas, key=lambda x: x['local'])
    mejor_empate = max(casas, key=lambda x: x['empate'])
    mejor_visitante = max(casas, key=lambda x: x['visitante'])

    texto += "\n🏆 *Mejores cuotas:*\n"
    texto += f"  Local: *{mejor_local['local']:.2f}* ({mejor_local['casa']})\n"
    texto += f"  Empate: *{mejor_empate['empate']:.2f}* ({mejor_empate['casa']})\n"
    texto += f"  Visitante: *{mejor_visitante['visitante']:.2f}* ({mejor_visitante['casa']})\n"

    return texto


def _formatear_prediccion(partido: str, pred: dict) -> str:
    prob_local = pred['prob_local'] * 100
    prob_empate = pred['prob_empate'] * 100
    prob_visitante = pred['prob_visitante'] * 100

    barra_local = "█" * int(prob_local / 10) + "░" * (10 - int(prob_local / 10))
    barra_empate = "█" * int(prob_empate / 10) + "░" * (10 - int(prob_empate / 10))
    barra_visitante = "█" * int(prob_visitante / 10) + "░" * (10 - int(prob_visitante / 10))

    resultado_pred = pred['resultado']
    emoji = "🏠" if resultado_pred == "H" else ("🤝" if resultado_pred == "D" else "✈️")

    texto = (
        f"🤖 *Predicción ML — {partido}*\n\n"
        f"Resultado más probable: {emoji} *{'Local' if resultado_pred == 'H' else ('Empate' if resultado_pred == 'D' else 'Visitante')}*\n\n"
        f"📊 *Probabilidades:*\n"
        f"Local    {barra_local} {prob_local:.1f}%\n"
        f"Empate   {barra_empate} {prob_empate:.1f}%\n"
        f"Visitante {barra_visitante} {prob_visitante:.1f}%\n\n"
        f"⚠️ _Esto es una estimación estadística, no una garantía._"
    )
    return texto


def _formatear_variaciones(variaciones: list) -> str:
    if not variaciones:
        return "❌ Sin datos históricos suficientes."

    partido = variaciones[0]['partido']
    texto = f"📈 *Variación de cuotas — {partido}*\n\n"

    for v in variaciones:
        flecha_l = "📈" if v['var_local'] > 0 else ("📉" if v['var_local'] < 0 else "➡️")
        flecha_e = "📈" if v['var_empate'] > 0 else ("📉" if v['var_empate'] < 0 else "➡️")
        flecha_v = "📈" if v['var_visitante'] > 0 else ("📉" if v['var_visitante'] < 0 else "➡️")

        texto += (
            f"🏢 *{v['casa']}*\n"
            f"  {flecha_l} Local: {v['local_actual']:.2f} ({v['var_local']:+.2f}%)\n"
            f"  {flecha_e} Empate: {v['empate_actual']:.2f} ({v['var_empate']:+.2f}%)\n"
            f"  {flecha_v} Visitante: {v['visitante_actual']:.2f} ({v['var_visitante']:+.2f}%)\n\n"
        )

    return texto


# ─────────────────── SCHEDULER (actualización automática) ───────────────────

async def actualizar_datos_automatico(app):
    """Corre el scraper y actualiza la BD cada 30 minutos."""
    logger.info("⏰ Actualizando datos automáticamente...")
    try:
        datos = await scraper.extraer_todos()
        db.guardar_datos(datos)

        # Verificar alertas activas
        alertas = db.get_alertas_activas()
        for alerta in alertas:
            if alerta['disparada']:
                try:
                    await app.bot.send_message(
                        chat_id=alerta['user_id'],
                        text=(
                            f"🔔 *Alerta de cuota!*\n"
                            f"⚽ {alerta['partido']}\n"
                            f"La cuota {alerta['tipo']} {'subió' if alerta['direccion'] == 'sube' else 'bajó'} "
                            f"un {alerta['variacion']:.1f}%\n"
                            f"Nuevo valor: *{alerta['valor_nuevo']:.2f}*"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Error enviando alerta: {e}")

        logger.info(f"✅ Datos actualizados: {len(datos)} registros.")
    except Exception as e:
        logger.error(f"❌ Error en actualización automática: {e}")


# ─────────────────── MAIN ───────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("partidos", cmd_partidos))
    app.add_handler(CommandHandler("odds", cmd_odds))
    app.add_handler(CommandHandler("prediccion", cmd_prediccion))
    app.add_handler(CommandHandler("variacion", cmd_variacion))
    app.add_handler(CommandHandler("arbitraje", cmd_arbitraje))
    app.add_handler(CommandHandler("alertas", cmd_alertas))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Scheduler cada 30 minutos
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: app.create_task(actualizar_datos_automatico(app)),
        "interval",
        minutes=30,
        id="update_odds"
    )
    scheduler.start()

    logger.info("🤖 Bot iniciado y escuchando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
