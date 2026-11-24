"""Adaptador de Telegram mediante long polling (requests) con menús y teclados interactivos."""
from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from agente import Agente
from flujo_guiado import procesar_flujo, obtener_sesion, KEYBOARD_MENU, _norm, _menu_principal_texto

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
ADMINS_RAW = os.getenv("TELEGRAM_ADMINS", "").strip()
ADMINS = {
    int(item.strip()) for item in ADMINS_RAW.split(",")
    if item.strip().lstrip("-").isdigit()
}
PUBLICO = os.getenv("TELEGRAM_PUBLICO", "true").strip().lower() in ("true", "1", "si", "yes")


def _peticion(method: str, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, timeout: int = 35) -> dict[str, Any]:
    respuesta = requests.post(
        f"{BASE_URL}/{method}",
        params=params,
        json=json_body,
        timeout=timeout,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def enviar(chat_id: str, texto: str, max_caracteres: int = 1500, reply_markup: dict[str, Any] | None = None) -> None:
    texto = (texto or "")[:max_caracteres]
    cuerpo: dict[str, Any] = {"chat_id": chat_id, "text": texto}
    if reply_markup:
        cuerpo["reply_markup"] = reply_markup
    try:
        _peticion(
            "sendMessage",
            json_body=cuerpo,
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"No se pudo enviar mensaje a Telegram: {exc}")


def ejecutar_telegram(agente: Agente, limitador: Any) -> None:
    if not TOKEN:
        print("Falta TELEGRAM_TOKEN en el archivo .env.")
        return

    modo = "PÚBLICO (cualquier usuario puede interactuar)" if PUBLICO else "PRIVADO (solo lista blanca)"
    print(f"Telegram iniciado (long polling). Modo: {modo}")
    print(f"Administrador(es) configurado(s): {ADMINS if ADMINS else 'Ninguno'}")
    print("Esperando mensajes en Telegram...")

    offset = 0
    while True:
        try:
            datos = _peticion(
                "getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                timeout=35,
            )
        except requests.RequestException as exc:
            print(f"Error en long polling: {exc}. Reintentando en 3 s...")
            time.sleep(3)
            continue

        for actualizacion in datos.get("result", []):
            offset = max(offset, int(actualizacion.get("update_id", 0)) + 1)
            mensaje = actualizacion.get("message") or {}
            usuario = mensaje.get("from") or {}
            uid = usuario.get("id")
            chat_id = str((mensaje.get("chat") or {}).get("id", uid))
            texto = (mensaje.get("text") or "").strip()
            nombre_usuario = usuario.get("first_name", "Usuario")
            es_admin = uid in ADMINS

            if not PUBLICO and not es_admin:
                print(f"[Telegram] Acceso denegado a {nombre_usuario} (@{usuario.get('username')}, ID: {uid})")
                enviar(
                    chat_id,
                    f"Usuario no autorizado.\nTu ID de Telegram es: {uid}\nEl bot se encuentra en modo privado.",
                    limitador.max_caracteres,
                )
                continue

            if not texto:
                continue

            tag = "ADMIN" if es_admin else "USUARIO"
            print(f"[Telegram] [{tag}] Mensaje de {nombre_usuario} (ID {uid}): {texto}")

            # Comando para administradores: /admin o /stats
            if texto.lower() in {"/admin", "/stats", "/estado"}:
                if es_admin:
                    try:
                        with agente.memoria._conectar() as conexion:
                            total_msgs = conexion.execute("SELECT count(*) FROM mensajes").fetchone()[0]
                            total_chats = conexion.execute("SELECT count(DISTINCT chat_id) FROM mensajes").fetchone()[0]
                    except Exception:
                        total_msgs, total_chats = 0, 0
                    cerebro_actual = os.getenv("CEREBRO", "reglas")
                    panel = (
                        "🛡️ Panel de Administración\n\n"
                        f"• Administrador: {nombre_usuario} (ID {uid})\n"
                        f"• Modo de acceso: {'Público (abierto a todos)' if PUBLICO else 'Privado'}\n"
                        f"• Motor activo (CEREBRO): {cerebro_actual}\n"
                        f"• Chats únicos en BD: {total_chats}\n"
                        f"• Total de interacciones: {total_msgs}\n\n"
                        "Comandos disponibles:\n"
                        "- /admin : Ver este panel\n"
                        "- /reset : Borrar memoria de este chat\n"
                        "- /menu : Ver menú clínico interactivo"
                    )
                    enviar(chat_id, panel, limitador.max_caracteres, reply_markup=KEYBOARD_MENU)
                else:
                    enviar(chat_id, "⚠️ El comando /admin es exclusivo para el administrador del sistema.", limitador.max_caracteres)
                continue

            permitido, motivo = limitador.permitir(chat_id)
            if not permitido:
                enviar(chat_id, motivo, limitador.max_caracteres)
                continue
            permitido, motivo = limitador.validar_texto(texto)
            if not permitido:
                enviar(chat_id, motivo, limitador.max_caracteres)
                continue

            sesion = obtener_sesion(chat_id)
            t_norm = _norm(texto)

            # Si el usuario solicita el menú o inicia sesión:
            if texto.lower() in {"/start", "/menu", "start", "menu"} or (sesion.estado == "MENU" and not sesion.opcion and t_norm in ("hola", "inicio", "volver")):
                sesion.estado = "MENU"
                sesion.opcion = ""
                menu_texto = _menu_principal_texto(nombre_usuario)
                enviar(chat_id, menu_texto, limitador.max_caracteres, reply_markup=KEYBOARD_MENU)
                continue

            es_accion_menu = (
                any(k in t_norm for k in (
                    "triaje", "dosis", "dosificacion", "fluido", "fluidoterapia",
                    "termico", "calor", "paciente", "reset", "menu", "start", "volver",
                    "1", "2", "3", "4"
                ))
                or texto.strip().startswith("/")
            )

            # Si el usuario está dentro de un flujo guiado (ficha, triaje, etc.) o eligió una opción de menú:
            if sesion.estado != "MENU" or es_accion_menu:
                respuesta, teclado = procesar_flujo(chat_id, texto, nombre_usuario)
                enviar(chat_id, respuesta, limitador.max_caracteres, reply_markup=teclado)
                print(f"[Telegram] [{tag}] Respuesta de flujo enviada a {nombre_usuario}")
                continue

            # Si escribió una consulta clínica libre directamente en el menú:
            try:
                respuesta = agente.procesar(chat_id, texto)
            except Exception as exc:
                respuesta = f"Error interno: {exc}"

            enviar(chat_id, respuesta, limitador.max_caracteres, reply_markup=KEYBOARD_MENU)
            print(f"[Telegram] [{tag}] Respuesta libre enviada a {nombre_usuario}")
