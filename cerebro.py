"""Módulo de lenguaje intercambiable: ollama | api | reglas."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

PROVEEDOR = os.getenv("CEREBRO", "ollama").strip().lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODELO = os.getenv("OLLAMA_MODELO", "llama3.2:3b")
API_BASE = os.getenv("API_BASE", "https://api.groq.com/openai/v1").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
API_MODEL = os.getenv("API_MODEL", "llama-3.3-70b-versatile")
OBSERVACION = "OBSERVACION"


def _json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _normalizar(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto).lower())
        if unicodedata.category(c) != "Mn"
    )


def _accion(herramienta: str, args: dict[str, Any]) -> str:
    return _json({"accion": "usar", "herramienta": herramienta, "args": args})


def _final(texto: str) -> str:
    return _json({"accion": "final", "texto": texto})


def _numero(texto: str) -> float | None:
    try:
        return float(texto.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def _extraer_ciudad(pregunta: str) -> str:
    normalizada = _normalizar(pregunta)
    ciudades = {
        "medellin": "Medellin", "bogota": "Bogota", "cali": "Cali",
        "barranquilla": "Barranquilla", "cartagena": "Cartagena",
        "ciudad de mexico": "Ciudad de Mexico", "madrid": "Madrid",
        "buenos aires": "Buenos Aires", "lima": "Lima", "santiago": "Santiago",
    }
    for clave in sorted(ciudades, key=len, reverse=True):
        if clave in normalizada:
            return ciudades[clave]
    return "Medellin"


def _extraer_expresion(pregunta: str) -> str | None:
    texto = _normalizar(pregunta)
    patron = r"\d+(?:[.,]\d+)?(?:\s*(?:mg\s*/\s*kg|mg|kg|ml|\*|x|mas\*|/|\+|-)\s*\d+(?:[.,]\d+)?)+"
    coincidencia = re.search(patron, texto)
    if coincidencia:
        return coincidencia.group(0).replace(" x ", " * ")
    dosis = re.search(r"(\d+(?:[.,]\d+)?)\s*mg\s*/\s*kg", texto)
    peso = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)", texto)
    if dosis and peso:
        return f"{dosis.group(1)}*{peso.group(1)}"
    return None


def _extraer_parametros_dosis(pregunta: str) -> dict[str, Any] | None:
    texto = _normalizar(pregunta).replace(",", ".")
    m_dosis = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*kg", texto)
    if not m_dosis:
        m_dosis = re.search(r"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*ml)", texto)
    m_peso = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilos?)\b", texto)
    if m_dosis and m_peso:
        args: dict[str, Any] = {
            "dosis_mg_kg": float(m_dosis.group(1)),
            "peso_kg": float(m_peso.group(1)),
        }
        m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", texto)
        if m_pct:
            args["concentracion_pct"] = float(m_pct.group(1))
        m_conc = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*ml", texto)
        if m_conc:
            args["concentracion_mg_ml"] = float(m_conc.group(1))
        m_tab = re.search(r"tabletas?\s*(?:de\s*)?(\d+(?:\.\d+)?)\s*mg", texto)
        if m_tab:
            args["mg_por_tableta"] = float(m_tab.group(1))
        return args
    return None


def _decidir_accion(pregunta: str) -> str:
    texto = _normalizar(pregunta)

    if any(k in texto for k in ("golpe de calor", "calor", "temperatura", "humedad", "clima", "braquicefal", "ola termica")):
        return _accion("riesgo_golpe_calor", {"ciudad": _extraer_ciudad(pregunta)})

    if any(k in texto for k in ("fluido", "fluidoterapia", "hidrat", "deshidrat", "ml/h", "goteo", "liquido")):
        peso_m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)", texto)
        if not peso_m:
            return _final("Necesito el peso del paciente en kilogramos antes de calcular fluidoterapia.")
        deshid_m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", texto)
        if not deshid_m:
            return _final("Necesito el porcentaje de deshidratación para calcular el déficit.")
        args: dict[str, Any] = {
            "peso_kg": _numero(peso_m.group(1)),
            "deshidratacion_pct": _numero(deshid_m.group(1)),
        }
        mant_m = re.search(r"(\d+(?:[.,]\d+)?)\s*ml\s*/\s*kg", texto)
        if mant_m:
            args["mantenimiento_ml_kg"] = _numero(mant_m.group(1))
        return _accion("calcular_fluidoterapia", args)

    if any(k in texto for k in ("dosis", "mg", "calcular", "multiplicar", "cuanto", "cantidad")) and re.search(r"\d", texto):
        params_dosis = _extraer_parametros_dosis(pregunta)
        if params_dosis:
            return _accion("calcular_dosis_clinica", params_dosis)
        expresion = _extraer_expresion(pregunta)
        if expresion:
            return _accion("calculadora_dosis", {"expresion": expresion})
        return _final(
            "Para calcular la dosis exacta necesito la dosis en mg/kg y el peso en kg (por ejemplo: '10 mg/kg para un perro de 12 kg' o '0.2 mg/kg para 10 kg'). "
            "Regla médica: NUNCA se divide la dosis entre el peso; siempre se multiplica (Dosis Total mg = Dosis mg/kg × Peso kg)."
        )

    if any(k in texto for k in (
        "triaje", "urgencia", "clasifica", "codigo", "disnea", "respirar", "respira",
        "ahog", "asfixi", "juguete", "trago", "comio", "veneno", "intoxica",
        "vomito", "diarrea", "colapso", "convulsion", "fiebre", "prurito", "rasca", "comezon",
        "obstruid", "torsion", "mucosa", "cianot", "protocolo", "vacuna", "desparasit",
        "guia", "signo", "sintoma", "emergencia", "orina", "orinar", "inconsciente",
    )):
        return _accion("buscar_protocolos", {"consulta": pregunta})

    if re.search(r"\d", texto):
        expresion = _extraer_expresion(pregunta)
        if expresion:
            return _accion("calculadora_dosis", {"expresion": expresion})

    return _final(
        "Puedo ayudarte con: cálculo de dosis (mg/kg × peso), fluidoterapia, "
        "triaje basado en protocolos_vet/ y alerta térmica por ciudad. "
        "Indica el caso clínico o la operación requerida."
    )


def _extraer_observaciones(mensajes: list[dict[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    observaciones: list[tuple[str, dict[str, Any]]] = []
    for mensaje in mensajes:
        contenido = mensaje.get("content", "")
        if mensaje.get("role") == "user" and contenido.startswith(OBSERVACION):
            coincidencia = re.match(r"OBSERVACION \(([^)]+)\):\s*(.*)", contenido, re.S)
            if coincidencia:
                nombre, cuerpo = coincidencia.groups()
                try:
                    observaciones.append((nombre, json.loads(cuerpo)))
                except json.JSONDecodeError:
                    observaciones.append((nombre, {"ok": False, "error": cuerpo[:300]}))
    return observaciones


def _resumir_observaciones(observaciones: list[tuple[str, dict[str, Any]]]) -> str:
    exitosas = [(n, d) for n, d in observaciones if d.get("ok")]
    fallidas = [(n, d) for n, d in observaciones if not d.get("ok")]
    if not exitosas:
        errores = "; ".join(str(d.get("error", "error")) for _, d in fallidas)
        return f"No pude completar la operación: {errores or 'sin datos'}. Revisa los parámetros e inténtalo de nuevo."

    nombre, datos = exitosas[-1]
    partes: list[str] = []
    if nombre in ("calcular_dosis_clinica", "calculadora_dosis"):
        partes.append(str(datos.get("detalle", "")))
    elif nombre == "calcular_fluidoterapia":
        partes.append("FLUIDOTERAPIA CALCULADA:")
        partes.append(str(datos.get("detalle", "")))
        partes.append(f"Velocidad: {datos.get('velocidad_ml_h')} ml/h; total 24 h: {datos.get('total_24h_ml')} ml.")
    elif nombre == "buscar_protocolos":
        partes.append("SEGUN LOS PROTOCOLOS LOCALES (protocolos_vet/):")
        for resultado in datos.get("resultados", [])[:2]:
            partes.append(f"[{resultado.get('archivo')}] {resultado.get('texto')}")
    elif nombre == "riesgo_golpe_calor":
        partes.append(
            f"ALERTA TERMICA EN {str(datos.get('ciudad', '')).upper()}: CODIGO {datos.get('nivel')} "
            f"({datos.get('temperatura_c')} C, {datos.get('humedad_pct')} % HUMEDAD, "
            f"INDICE DE CALOR {datos.get('indice_calor_c')} C)."
        )
        partes.append(str(datos.get("recomendacion", "")))
        partes.append(str(datos.get("nota_braquicefalos", "")))
    else:
        partes.append(json.dumps(datos, ensure_ascii=False))

    if fallidas:
        partes.append("Nota: un intento previo falló y fue corregido automáticamente.")
    return " ".join(p for p in partes if p)


def _generar_reglas(mensajes: list[dict[str, str]]) -> str:
    observaciones = _extraer_observaciones(mensajes)
    if observaciones:
        return _final(_resumir_observaciones(observaciones))

    pregunta = ""
    for mensaje in reversed(mensajes):
        if mensaje.get("role") == "user" and not str(mensaje.get("content", "")).startswith(OBSERVACION):
            pregunta = str(mensaje.get("content", ""))
            break
    return _decidir_accion(pregunta)


def _generar_ollama(mensajes: list[dict[str, str]]) -> str:
    respuesta = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODELO,
            "messages": mensajes,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=120,
    )
    respuesta.raise_for_status()
    return str(respuesta.json()["message"]["content"])


def _generar_api(mensajes: list[dict[str, str]]) -> str:
    cabeceras = {"Content-Type": "application/json"}
    if API_KEY:
        cabeceras["Authorization"] = f"Bearer {API_KEY}"
    respuesta = requests.post(
        f"{API_BASE}/chat/completions",
        json={
            "model": API_MODEL,
            "messages": mensajes,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        headers=cabeceras,
        timeout=120,
    )
    respuesta.raise_for_status()
    return str(respuesta.json()["choices"][0]["message"]["content"])


def generar(mensajes: list[dict[str, str]]) -> str:
    """Devuelve siempre una cadena con intención de JSON (o reglas deterministas)."""
    if PROVEEDOR == "reglas":
        return _generar_reglas(mensajes)
    try:
        if PROVEEDOR == "api":
            return _generar_api(mensajes)
        return _generar_ollama(mensajes)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return _generar_reglas(mensajes)
