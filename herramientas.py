"""Catálogo de herramientas clínicas del agente.

Todas las funciones devuelven un dict con la clave ``ok`` para que el bucle
ReAct pueda convertirlo en una observación legible por el modelo.
"""
from __future__ import annotations

import ast
import math
import operator
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

import requests

BASE_DIR = Path(__file__).resolve().parent
PROTOCOLOS_DIR = BASE_DIR / "protocolos_vet"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

CIUDADES: dict[str, tuple[float, float]] = {
    "medellin": (6.2442, -75.5812),
    "bogota": (4.7110, -74.0721),
    "cali": (3.4516, -76.5320),
    "barranquilla": (10.9685, -74.7813),
    "cartagena": (10.3910, -75.4794),
    "ciudad de mexico": (19.4326, -99.1332),
    "madrid": (40.4168, -3.7038),
    "buenos aires": (-34.6037, -58.3816),
    "lima": (-12.0464, -77.0428),
    "santiago": (-33.4489, -70.6693),
}

_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "y",
    "o", "en", "por", "para", "con", "sin", "que", "es", "son", "se", "su",
    "sus", "al", "a", "cual", "como", "tipo", "tiene", "tengo", "hay",
    "sobre", "segun", "guias", "protocolo", "protocolos", "consulta", "dame",
    "necesito", "quiero", "por favor", "favor", "posible", "clinico", "clinica",
    "mi", "mis", "me", "le", "les", "te", "nos", "lo", "puede", "puedo", "debo",
    "hacer", "saber", "decir", "esta", "este", "estos", "estas", "esto", "fue", "era",
}

_SINONIMOS: dict[str, list[str]] = {
    "respirar": ["respiracion", "respiratoria", "disnea", "asfixia", "ahogo", "jadeo"],
    "respirando": ["respiracion", "respiratoria", "disnea", "asfixia", "ahogo", "jadeo"],
    "asfixia": ["disnea", "respiracion", "obstruccion", "ahogo"],
    "ahogo": ["disnea", "respiracion", "obstruccion", "asfixia"],
    "juguete": ["obstruccion", "cuerpo extrano"],
    "comio": ["obstruccion", "ingestion", "intoxicacion"],
    "trago": ["obstruccion", "cuerpo extrano"],
    "convulsion": ["convulsiones", "convulsionando"],
    "convulsiones": ["convulsion", "convulsionando"],
    "vomito": ["vomitos", "vomitando"],
    "vomitos": ["vomito", "vomitando"],
    "diarrea": ["diarreas"],
    "sangre": ["hemorragia", "sangrado"],
    "sangrando": ["hemorragia", "sangre"],
    "vacuna": ["vacunas", "vacunacion"],
    "vacunas": ["vacuna", "vacunacion"],
    "vacunar": ["vacunas", "vacunacion"],
    "desparasitar": ["desparasitaciones"],
    "comezon": ["prurito"],
    "rasca": ["prurito"],
    "rascado": ["prurito"],
    "orinar": ["obstruido", "orina", "miccion"],
}

_OPERADORES: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _limpiar_expresion(expresion: Any) -> str:
    texto = str(expresion).strip().lower()
    texto = re.sub(r"(?<=\d),(?=\d)", ".", texto)
    texto = texto.replace("×", "*").replace("÷", "/")
    texto = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", texto)
    texto = re.sub(r"mg\s*/\s*kg|mg|kg|ml|gr|\bg\b", " ", texto)
    texto = re.sub(r"[^0-9.\+\-\*/()\s]", " ", texto)
    return " ".join(texto.split())


def _evaluar_nodo(nodo: ast.AST) -> float:
    if isinstance(nodo, ast.Expression):
        return _evaluar_nodo(nodo.body)
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
        return float(nodo.value)
    if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, (ast.UAdd, ast.USub)):
        valor = _evaluar_nodo(nodo.operand)
        return valor if isinstance(nodo.op, ast.UAdd) else -valor
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
        izquierda = _evaluar_nodo(nodo.left)
        derecha = _evaluar_nodo(nodo.right)
        if isinstance(nodo.op, ast.Pow):
            if abs(derecha) > 10 or abs(izquierda) > 1_000_000:
                raise ValueError("Exponente o base fuera de rango.")
        return float(_OPERADORES[type(nodo.op)](izquierda, derecha))
    raise ValueError("Expresión no permitida: solo números y + - * / ( )")


def calcular_dosis_clinica(
    dosis_mg_kg: float,
    peso_kg: float,
    concentracion_mg_ml: float | None = None,
    concentracion_pct: float | None = None,
    mg_por_tableta: float | None = None,
    nombre_paciente: str = "PACIENTE",
) -> dict[str, Any]:
    """Calcula dosis veterinaria siguiendo el estándar ultra-conciso de 3 pasos sin Markdown."""
    try:
        dosis = float(dosis_mg_kg)
        peso = float(peso_kg)
    except (TypeError, ValueError):
        return {"ok": False, "error": "LA DOSIS Y EL PESO DEBEN SER NUMEROS VALIDOS."}

    if dosis <= 0:
        return {"ok": False, "error": "LA DOSIS DEBE SER MAYOR A CERO."}
    if not 0.05 <= peso <= 250:
        return {"ok": False, "error": "EL PESO DEBE ESTAR EN RANGO FISIOLOGICO (0.05 A 250 KG)."}

    # PASO 1: Dosis Total (mg) = Dosis indicada (mg/kg) × Peso del paciente (kg)
    dosis_total_mg = round(dosis * peso, 4)

    conc_utilizada = float(concentracion_mg_ml) if concentracion_mg_ml is not None else None
    pct_val = float(concentracion_pct) if concentracion_pct is not None else None
    tab_val = float(mg_por_tableta) if mg_por_tableta is not None else None

    volumen_ml: float | None = None
    cantidad_tab: float | None = None

    if pct_val is not None and pct_val > 0:
        conc_utilizada = round(pct_val * 10.0, 3)

    if conc_utilizada is not None and conc_utilizada > 0:
        volumen_ml = round(dosis_total_mg / conc_utilizada, 3)
        linea_formula = (
            "PASO 1: FORMULA\n"
            "DOSIS TOTAL (MG) = DOSIS INDICADA (MG/KG) x PESO DEL PACIENTE (KG)\n"
            "VOLUMEN A ADMINISTRAR (ML) = DOSIS TOTAL (MG) / CONCENTRACION DEL FARMACO (MG/ML)"
        )
        linea_operacion = (
            "PASO 2: OPERACION\n"
            f"DOSIS TOTAL = {dosis} MG/KG x {peso} KG = {dosis_total_mg} MG\n"
        )
        if pct_val is not None:
            linea_operacion += f"CONCENTRACION = {pct_val}% x 10 = {conc_utilizada} MG/ML\n"
        else:
            linea_operacion += f"CONCENTRACION = {conc_utilizada} MG/ML\n"
        linea_operacion += f"VOLUMEN = {dosis_total_mg} MG / {conc_utilizada} MG/ML = {volumen_ml} ML"
        linea_resultado = (
            "PASO 3: RESULTADO\n"
            f"ADMINISTRAR {volumen_ml} ML (EQUIVALENTE A {dosis_total_mg} MG TOTALES)."
        )
    elif tab_val is not None and tab_val > 0:
        cantidad_tab = round(dosis_total_mg / tab_val, 2)
        linea_formula = (
            "PASO 1: FORMULA\n"
            "DOSIS TOTAL (MG) = DOSIS INDICADA (MG/KG) x PESO DEL PACIENTE (KG)\n"
            "CANTIDAD TABLETAS = DOSIS TOTAL (MG) / CONCENTRACION POR TABLETA (MG)"
        )
        linea_operacion = (
            "PASO 2: OPERACION\n"
            f"DOSIS TOTAL = {dosis} MG/KG x {peso} KG = {dosis_total_mg} MG\n"
            f"CANTIDAD = {dosis_total_mg} MG / {tab_val} MG = {cantidad_tab} TABLETAS"
        )
        linea_resultado = (
            "PASO 3: RESULTADO\n"
            f"ADMINISTRAR {cantidad_tab} TABLETAS (EQUIVALENTE A {dosis_total_mg} MG TOTALES)."
        )
    else:
        linea_formula = (
            "PASO 1: FORMULA\n"
            "DOSIS TOTAL (MG) = DOSIS INDICADA (MG/KG) x PESO DEL PACIENTE (KG)"
        )
        linea_operacion = (
            "PASO 2: OPERACION\n"
            f"DOSIS TOTAL = {dosis} MG/KG x {peso} KG = {dosis_total_mg} MG"
        )
        linea_resultado = (
            "PASO 3: RESULTADO\n"
            f"DOSIS TOTAL EXACTA A ADMINISTRAR: {dosis_total_mg} MG."
        )

    detalle_clinico = f"{linea_formula}\n\n{linea_operacion}\n\n{linea_resultado}"

    return {
        "ok": True,
        "dosis_mg_kg": dosis,
        "peso_kg": peso,
        "dosis_total_mg": dosis_total_mg,
        "volumen_ml": volumen_ml,
        "cantidad_tab": cantidad_tab,
        "resultado": dosis_total_mg,
        "detalle": detalle_clinico,
    }


def calculadora_dosis(expresion: str) -> dict[str, Any]:
    """Evalúa aritmética de dosis con ``ast`` (nunca con ``eval``)."""
    limpia = _limpiar_expresion(expresion)
    if not limpia or not re.search(r"\d", limpia):
        return {"ok": False, "error": "NO SE ENCONTRO UNA EXPRESION NUMERICA VALIDA."}
    try:
        arbol = ast.parse(limpia, mode="eval")
        resultado = _evaluar_nodo(arbol)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return {"ok": False, "error": f"EXPRESION INVALIDA: {exc}"}
    if not math.isfinite(resultado):
        return {"ok": False, "error": "EL RESULTADO NO ES UN NUMERO FINITO."}
    if resultado < 0:
        return {"ok": False, "error": "UNA DOSIS NO PUEDE SER NEGATIVA."}

    res_redondeado = round(resultado, 4)
    detalle = (
        "PASO 1: FORMULA\n"
        "DOSIS TOTAL (MG) = DOSIS INDICADA (MG/KG) x PESO DEL PACIENTE (KG)\n\n"
        "PASO 2: OPERACION\n"
        f"OPERACION = {limpia} = {res_redondeado} MG\n\n"
        "PASO 3: RESULTADO\n"
        f"DOSIS TOTAL: {res_redondeado} MG."
    )
    return {
        "ok": True,
        "expresion": limpia,
        "resultado": res_redondeado,
        "detalle": detalle,
    }


def calcular_fluidoterapia(
    peso_kg: float,
    deshidratacion_pct: float,
    mantenimiento_ml_kg: float = 50.0,
) -> dict[str, Any]:
    """Calcula mantenimiento, déficit, total 24 h y goteo en ml/h."""
    try:
        peso = float(peso_kg)
        deshidratacion = float(deshidratacion_pct)
        mantenimiento = float(mantenimiento_ml_kg)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Los parámetros deben ser números."}

    if not 0.1 <= peso <= 200:
        return {"ok": False, "error": "peso_kg debe estar entre 0.1 y 200 kg (rango fisiológico)."}
    if not 0 <= deshidratacion <= 15:
        return {"ok": False, "error": "deshidratacion_pct debe estar entre 0 y 15 %."}
    if not 30 <= mantenimiento <= 100:
        return {"ok": False, "error": "mantenimiento_ml_kg debe estar entre 30 y 100 ml/kg/día."}

    mantenimiento_ml = peso * mantenimiento
    deficit_ml = peso * deshidratacion * 10.0
    total_ml = mantenimiento_ml + deficit_ml
    return {
        "ok": True,
        "peso_kg": peso,
        "deshidratacion_pct": deshidratacion,
        "mantenimiento_ml": round(mantenimiento_ml, 2),
        "deficit_ml": round(deficit_ml, 2),
        "total_24h_ml": round(total_ml, 2),
        "velocidad_ml_h": round(total_ml / 24.0, 2),
        "detalle": (
            f"Mantenimiento {peso} kg × {mantenimiento} ml/kg = {round(mantenimiento_ml, 2)} ml; "
            f"déficit {peso} kg × {deshidratacion}% × 10 = {round(deficit_ml, 2)} ml; "
            f"total 24 h = {round(total_ml, 2)} ml; velocidad = {round(total_ml / 24.0, 2)} ml/h."
        ),
    }


def _stem(palabra: str) -> str:
    for fin in ("ando", "iendo", "aron", "eron", "aste", "iste", "aria", "eria", "cion", "siones", "ciones", "mente", "ades", "anza", "ores", "uras", "amos", "emos", "imos", "aban", "asen", "ados", "idos", "ada", "ida", "ado", "ido", "es", "as", "os", "a", "e", "o"):
        if palabra.endswith(fin) and len(palabra) - len(fin) >= 4:
            return palabra[:-len(fin)]
    return palabra


def _tokenizar(texto: str) -> set[str]:
    tokens = re.findall(r"[a-záéíóúüñ]+", unicodedata.normalize("NFD", texto.lower()))
    tokens = ["".join(c for c in t if unicodedata.category(c) != "Mn") for t in tokens]
    res: set[str] = set()
    for t in tokens:
        if len(t) > 2 and t not in _STOPWORDS:
            res.add(t)
            res.add(_stem(t))
            if t in _SINONIMOS:
                for s in _SINONIMOS[t]:
                    s_norm = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
                    res.add(s_norm)
                    res.add(_stem(s_norm))
    return res


def buscar_protocolos(consulta: str) -> dict[str, Any]:
    """Busca secciones clínicas relevantes en los Markdown locales (grounding)."""
    tokens = _tokenizar(str(consulta))
    if not tokens:
        return {"ok": False, "error": "La consulta no contiene términos útiles."}
    if not PROTOCOLOS_DIR.exists():
        return {"ok": False, "error": "No existe la carpeta protocolos_vet/."}

    resultados: list[dict[str, Any]] = []
    for archivo in sorted(PROTOCOLOS_DIR.glob("*.md")):
        texto = archivo.read_text(encoding="utf-8", errors="replace")
        secciones = re.split(r"\n(?=##\s+)", texto)
        for sec in secciones:
            sec = sec.strip()
            if not sec:
                continue
            lineas = [l for l in sec.splitlines() if l.strip()]
            titulo = lineas[0] if lineas else ""
            if titulo.startswith("# Protocolo"):
                continue

            keywords = _tokenizar(sec)
            coincidencias = sorted(tokens & keywords)
            if not coincidencias:
                continue

            peso = 0.5 if "reglas de seguridad" in titulo.lower() else 1.0
            score = (len(coincidencias) / math.sqrt(len(keywords) + 1)) * peso

            resultados.append({
                "archivo": archivo.name,
                "coincidencias": coincidencias,
                "score": score,
                "texto": re.sub(r"[*#_`~]", "", sec[:1200]).strip(),
            })

    resultados.sort(key=lambda r: r["score"], reverse=True)
    if not resultados:
        return {
            "ok": False,
            "error": "No hay evidencia en protocolos_vet/ para esa consulta. No inventes contenido clínico.",
        }

    # Si el primer resultado tiene una coincidencia clínica dominante, devolvemos solo ese código
    if len(resultados) > 1 and resultados[0]["score"] >= 1.7 * resultados[1]["score"]:
        seleccionados = resultados[:1]
    else:
        seleccionados = resultados[:2]

    return {"ok": True, "resultados": seleccionados, "fuente": "protocolos_vet/"}


def riesgo_golpe_calor(ciudad: str) -> dict[str, Any]:
    """Consulta Open-Meteo y estima alerta térmica para mascotas."""
    normalizada = "".join(
        c for c in unicodedata.normalize("NFD", str(ciudad).lower())
        if unicodedata.category(c) != "Mn"
    ).strip()
    nombre = normalizada or "medellin"
    coords = CIUDADES.get(nombre)
    if coords is None:
        coincidencia = next((c for c in CIUDADES if nombre in c or c in nombre), None)
        coords = CIUDADES[coincidencia] if coincidencia else CIUDADES["medellin"]
        nombre = coincidencia or "medellin (predeterminada)"

    try:
        respuesta = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": coords[0],
                "longitude": coords[1],
                "current": "temperature_2m,relative_humidity_2m",
                "timezone": "auto",
            },
            timeout=8,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        actual = datos["current"]
        temperatura = float(actual["temperature_2m"])
        humedad = float(actual["relative_humidity_2m"])
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": f"No se pudo consultar Open-Meteo: {exc}"}

    t, h = temperatura, humedad
    indice = (
        -8.78469475556 + 1.61139411 * t + 2.33854883889 * h
        - 0.14611605 * t * h - 0.012308094 * t * t
        - 0.0164248277778 * h * h + 0.002211732 * t * t * h
        + 0.00072546 * t * h * h - 0.000003582 * t * t * h * h
    )
    indice = round(max(indice, t), 1)

    if indice >= 39 or temperatura >= 35:
        nivel = "ROJO"
        recomendacion = "Evita paseos y exposición; riesgo crítico de golpe de calor."
    elif indice >= 32:
        nivel = "NARANJA"
        recomendacion = "Paseos solo en horas frescas, sombra y agua permanente."
    elif indice >= 27:
        nivel = "AMARILLO"
        recomendacion = "Vigila a braquicéfalos, cachorros y animales senior."
    else:
        nivel = "VERDE"
        recomendacion = "Condición térmica favorable, mantén agua disponible."

    return {
        "ok": True,
        "ciudad": nombre,
        "temperatura_c": round(temperatura, 1),
        "humedad_pct": round(humedad, 1),
        "indice_calor_c": indice,
        "nivel": nivel,
        "recomendacion": recomendacion,
        "nota_braquicefalos": "En braquicéfalos (Pug, Bulldog) cualquier alerta se interpreta con un nivel más de severidad.",
    }


HERRAMIENTAS: dict[str, Callable[..., dict[str, Any]]] = {
    "calculadora_dosis": calculadora_dosis,
    "calcular_dosis_clinica": calcular_dosis_clinica,
    "calcular_fluidoterapia": calcular_fluidoterapia,
    "buscar_protocolos": buscar_protocolos,
    "riesgo_golpe_calor": riesgo_golpe_calor,
}

ESQUEMAS: dict[str, dict[str, Any]] = {
    "calculadora_dosis": {
        "descripcion": "Evalúa aritmética exacta de dosis (mg/kg × peso). Nunca computes mentalmente.",
        "args": {"expresion": "str: p. ej. '10 mg/kg * 12 kg' o '10*12'"},
    },
    "calcular_dosis_clinica": {
        "descripcion": "Calcula dosis veterinaria con el flujo de 2 pasos clínicos (Dosis Total mg y Volumen ml / tabletas) y auto-verificación.",
        "args": {
            "dosis_mg_kg": "float: dosis en mg/kg",
            "peso_kg": "float: peso del paciente en kg",
            "concentracion_mg_ml": "float opcional: concentración líquida en mg/ml",
            "concentracion_pct": "float opcional: concentración en % (ej: 0.5 o 2.0)",
            "mg_por_tableta": "float opcional: miligramos por tableta",
            "nombre_paciente": "str opcional: nombre del paciente",
        },
    },
    "calcular_fluidoterapia": {
        "descripcion": "Calcula mantenimiento, déficit, total 24 h y ml/h con rangos fisiológicos.",
        "args": {
            "peso_kg": "float obligatorio",
            "deshidratacion_pct": "float obligatorio (0-15)",
            "mantenimiento_ml_kg": "float opcional, por defecto 50.0",
        },
    },
    "buscar_protocolos": {
        "descripcion": "Busca párrafos en protocolos_vet/. Úsala para triaje o cualquier guía clínica.",
        "args": {"consulta": "str: tema clínico a buscar"},
    },
    "riesgo_golpe_calor": {
        "descripcion": "Consulta temperatura/humedad actuales y devuelve nivel de alerta térmica.",
        "args": {"ciudad": "str: ciudad (Medellin, Bogota, Cali, Madrid, ...)"},
    },
}


def ejecutar(nombre: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Despacha una herramienta validando nombre y argumentos."""
    args = args or {}
    funcion = HERRAMIENTAS.get(str(nombre))
    if funcion is None:
        return {"ok": False, "error": f"Herramienta desconocida: {nombre}"}
    if not isinstance(args, dict):
        return {"ok": False, "error": "Los args deben ser un objeto JSON."}
    try:
        return funcion(**args)
    except TypeError as exc:
        return {"ok": False, "error": f"Argumentos inválidos para {nombre}: {exc}"}
    except Exception as exc:  # último recurso: el bucle debe sobrevivir
        return {"ok": False, "error": f"Fallo inesperado en {nombre}: {exc}"}


def catalogo() -> str:
    """Devuelve el catálogo serializable para inyectarlo en el prompt."""
    import json

    return json.dumps(ESQUEMAS, ensure_ascii=False, indent=2)
