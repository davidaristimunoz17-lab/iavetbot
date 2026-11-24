"""Punto de entrada: consola o Telegram."""
from __future__ import annotations

import argparse
import os
import time
from collections import deque
from threading import Lock

from dotenv import load_dotenv

from agente import Agente


class Limitador:
    """Ventana deslizante: máximo N mensajes por minuto y M caracteres."""

    def __init__(self, max_mensajes: int = 10, periodo: float = 60.0, max_caracteres: int = 1500) -> None:
        self.max_mensajes = max(1, int(max_mensajes))
        self.periodo = float(periodo)
        self.max_caracteres = max(1, int(max_caracteres))
        self._ventanas: dict[str, deque[float]] = {}
        self._bloqueo = Lock()

    def permitir(self, chat_id: str) -> tuple[bool, str]:
        ahora = time.monotonic()
        with self._bloqueo:
            ventana = self._ventanas.setdefault(str(chat_id), deque())
            while ventana and ahora - ventana[0] >= self.periodo:
                ventana.popleft()
            if len(ventana) >= self.max_mensajes:
                return False, f"Límite de velocidad: máximo {self.max_mensajes} mensajes por minuto. Espera un momento."
            ventana.append(ahora)
            return True, ""

    def validar_texto(self, texto: str) -> tuple[bool, str]:
        if len(texto or "") > self.max_caracteres:
            return False, f"Mensaje demasiado largo: máximo {self.max_caracteres} caracteres."
        return True, ""


def ejecutar_consola(agente: Agente, limitador: Limitador) -> None:
    from flujo_guiado import procesar_flujo, obtener_sesion, _norm

    print("=" * 60)
    print("🐾 Agente IA de Triaje y Apoyo Clínico Veterinario (Académico)")
    print("Opciones: 1=Triaje | 2=Dosis | 3=Fluidoterapia | 4=Riesgo Térmico")
    print("Comandos: /menu, /paciente, /reset, /salir. O escribe tu consulta clínica libre.")
    print("=" * 60)

    while True:
        try:
            texto = input("\nTú> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break
        if texto.lower() in {"/salir", "exit", "quit"}:
            print("Hasta luego.")
            break
        if not texto:
            continue

        permitido, motivo = limitador.permitir("consola")
        if not permitido:
            print(motivo)
            continue
        permitido, motivo = limitador.validar_texto(texto)
        if not permitido:
            print(motivo)
            continue

        sesion = obtener_sesion("consola")
        t_norm = _norm(texto)
        es_accion_menu = (
            any(k in t_norm for k in (
                "triaje", "dosis", "dosificacion", "fluido", "fluidoterapia",
                "termico", "calor", "paciente", "reset", "menu", "start", "volver",
                "1", "2", "3", "4"
            ))
            or texto.strip().startswith("/")
        )

        if sesion.estado != "MENU" or es_accion_menu:
            respuesta, _ = procesar_flujo("consola", texto, "Estudiante")
        else:
            try:
                respuesta = agente.procesar("consola", texto)
            except Exception as exc:
                respuesta = f"Error interno: {exc}"

        print(f"\nAgente> {respuesta}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Agente IA de triaje clínico veterinario (académico).")
    parser.add_argument("--canal", choices=["consola", "telegram"], default="consola", help="Canal de interacción.")
    args = parser.parse_args()

    agente = Agente()
    limitador = Limitador(
        max_mensajes=int(os.getenv("MAX_MENSAJES_POR_MINUTO", "10")),
        max_caracteres=int(os.getenv("MAX_CARACTERES", "1500")),
    )

    if args.canal == "telegram":
        from canal_telegram import ejecutar_telegram

        ejecutar_telegram(agente, limitador)
    else:
        ejecutar_consola(agente, limitador)


if __name__ == "__main__":
    main()
