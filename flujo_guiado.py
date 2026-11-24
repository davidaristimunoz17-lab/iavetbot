"""Flujo conversacional guiado e interactivo para el Agente Veterinario.

Implementa:
1. Reglas estrictas de salida: texto plano limpio sin Markdown, títulos en MAYUSCULAS SOSTENIDAS.
2. Sistema cuantificable de Triaje Clínico de 5 preguntas exactas (escala de 0 a 15 puntos).
3. Módulo de dosificación ultra-conciso en 3 pasos directos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import herramientas
from agente import AVISO


def _norm(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto).lower())
        if unicodedata.category(c) != "Mn"
    ).strip()


@dataclass
class Paciente:
    nombre: str = ""
    especie: str = ""
    raza: str = ""
    sexo: str = ""
    edad: str = ""
    peso_kg: float | None = None

    def esta_completo(self) -> bool:
        return bool(
            self.nombre
            and self.especie
            and self.raza
            and self.sexo
            and self.edad
            and (self.peso_kg is not None and self.peso_kg > 0)
        )

    def faltantes(self) -> list[str]:
        faltan: list[str] = []
        if not self.nombre:
            faltan.append("NOMBRE")
        if not self.especie:
            faltan.append("ESPECIE (CANINO / FELINO)")
        if not self.raza:
            faltan.append("RAZA")
        if not self.sexo:
            faltan.append("SEXO (MACHO / HEMBRA)")
        if not self.edad:
            faltan.append("EDAD")
        if self.peso_kg is None or self.peso_kg <= 0:
            faltan.append("PESO EN KG")
        return faltan

    def resumen(self) -> str:
        peso_txt = f"{self.peso_kg} KG" if self.peso_kg else "PENDIENTE"
        return (
            "FICHA DEL PACIENTE:\n"
            f"NOMBRE: {self.nombre or 'PENDIENTE'}\n"
            f"ESPECIE: {self.especie or 'PENDIENTE'}\n"
            f"RAZA: {self.raza or 'PENDIENTE'}\n"
            f"SEXO: {self.sexo or 'PENDIENTE'}\n"
            f"EDAD: {self.edad or 'PENDIENTE'}\n"
            f"PESO: {peso_txt}"
        )


@dataclass
class SesionChat:
    chat_id: str
    estado: str = "MENU"
    opcion: str = ""
    paciente: Paciente = field(default_factory=Paciente)
    campo_pendiente: str = ""
    puntos_triaje: dict[str, int] = field(default_factory=dict)
    respuestas_texto: dict[str, str] = field(default_factory=dict)


SESIONES: dict[str, SesionChat] = {}


def obtener_sesion(chat_id: str) -> SesionChat:
    cid = str(chat_id)
    if cid not in SESIONES:
        SESIONES[cid] = SesionChat(chat_id=cid)
    return SESIONES[cid]


def resetear_sesion(chat_id: str) -> SesionChat:
    cid = str(chat_id)
    SESIONES[cid] = SesionChat(chat_id=cid)
    return SESIONES[cid]


# Teclados limpios para Telegram
KEYBOARD_MENU = {
    "keyboard": [
        [{"text": "1. TRIAJE CLINICO"}, {"text": "2. DOSIFICACION"}],
        [{"text": "3. FLUIDOTERAPIA"}, {"text": "4. RIESGO TERMICO"}],
        [{"text": "VER PACIENTE ACTUAL"}, {"text": "NUEVO PACIENTE (/RESET)"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}

KEYBOARD_VOLVER = {
    "keyboard": [
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

KEYBOARD_FLUIDO = {
    "keyboard": [
        [{"text": "5% (LEVE)"}, {"text": "7% (MODERADA)"}],
        [{"text": "9% (SEVERA)"}, {"text": "11% (CRITICA / SHOCK)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


KEYBOARD_TRIAJE_P1 = {
    "keyboard": [
        [{"text": "1. ALERTA Y RESPONSIVO (0 PUNTOS)"}],
        [{"text": "2. DEPRIMIDO, LETARGICO O DIFICIL DE DESPERTAR (2 PUNTOS)"}],
        [{"text": "3. COMATOSO O CONVULSIONANDO (3 PUNTOS)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

KEYBOARD_TRIAJE_P2 = {
    "keyboard": [
        [{"text": "1. ROSADAS Y LLENADO MENOR A 2 SEGUNDOS (0 PUNTOS)"}],
        [{"text": "2. PALIDAS, CONGESTIVAS O PEGAJOSAS, LLENADO 2S (1 PUNTO)"}],
        [{"text": "3. CIANOTICAS, ICTERICAS O LLENADO MAYOR A 3S (3 PUNTOS)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

KEYBOARD_TRIAJE_P3 = {
    "keyboard": [
        [{"text": "1. MUCOSAS HUMEDAS, PLIEGUE CUTANEO INMEDIATO (0 PUNTOS)"}],
        [{"text": "2. MUCOSAS SECAS, RETRASO LEVE A MODERADO (1 PUNTO)"}],
        [{"text": "3. MUCOSAS PEGAJOSAS, PLIEGUE PERSISTENTE O SHOCK (3 PUNTOS)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

KEYBOARD_TRIAJE_P4 = {
    "keyboard": [
        [{"text": "1. NORMAL, ESFUERZO LEVE (0 PUNTOS)"}],
        [{"text": "2. TAQUIPNEA MARCADA, ESFUERZO MODERADO (2 PUNTOS)"}],
        [{"text": "3. DISNEA GRAVE, BOQUEO, PATRON PARADOJICO (3 PUNTOS)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

KEYBOARD_TRIAJE_P5 = {
    "keyboard": [
        [{"text": "1. FUERTE Y SINCRONICO (0 PUNTOS)"}],
        [{"text": "2. DEBIL, FILIFORME O DIFICIL DE PALPAR (2 PUNTOS)"}],
        [{"text": "3. AUSENTE (3 PUNTOS)"}],
        [{"text": "VOLVER AL MENU PRINCIPAL"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


def _menu_principal_texto(nombre_usuario: str = "") -> str:
    saludo = f"HOLA {nombre_usuario.upper()}\n\n" if nombre_usuario else "BIENVENIDO\n\n"
    return (
        f"{saludo}AGENTE IA DE TRIAJE Y APOYO CLINICO VETERINARIO\n\n"
        "SELECCIONA UNA DE LAS SIGUIENTES OPCIONES:\n\n"
        "1. TRIAJE CLINICO: CUESTIONARIO CUANTITATIVO DE 5 PREGUNTAS (ESCALA DE 0 A 15 PUNTOS).\n"
        "2. DOSIFICACION EXACTA: CALCULO DIRECTO EN 3 PASOS (FORMULA, OPERACION, RESULTADO).\n"
        "3. PLAN DE FLUIDOTERAPIA: DEFICIT, MANTENIMIENTO Y VELOCIDAD DE GOTEO.\n"
        "4. RIESGO TERMICO: EVALUACION CLIMATICA Y GOLPE DE CALOR POR CIUDAD.\n\n"
        "ESCRIBE EL NUMERO DE LA OPCION (1, 2, 3 O 4) O SELECCIONA UN BOTON."
    )


def _pedir_ficha_texto(paciente: Paciente, opcion_nom: str) -> str:
    resumen_actual = ""
    if paciente.nombre or paciente.especie or paciente.peso_kg:
        resumen_actual = f"{paciente.resumen()}\n\n"

    return (
        f"FICHA DE INGRESO DEL PACIENTE (REQUERIDA PARA {opcion_nom.upper()}):\n\n"
        f"{resumen_actual}"
        "POR FAVOR PROPORCIONA LOS SIGUIENTES 6 DATOS:\n"
        "1. NOMBRE\n"
        "2. ESPECIE (CANINO / FELINO)\n"
        "3. RAZA\n"
        "4. SEXO (MACHO / HEMBRA)\n"
        "5. EDAD (EJ: 2 ANOS, 8 MESES)\n"
        "6. PESO EN KG (EJ: 12.5 KG)\n\n"
        "PUEDES ENVIARLOS TODOS JUNTOS SEPARADOS POR COMA:\n"
        "ROCKY, CANINO, BULLDOG, MACHO, 3 ANOS, 14 KG\n\n"
        "O ESCRIBE EL NOMBRE DEL PACIENTE PARA REGISTRARLOS DATO POR DATO."
    )


def _parsear_ficha_completa(texto: str, paciente: Paciente) -> bool:
    t_norm = _norm(texto)

    if any(k in t_norm for k in ("canino", "perro", "perra", "canina", "can")):
        paciente.especie = "CANINO"
    elif any(k in t_norm for k in ("felino", "gato", "gata", "felina", "minino")):
        paciente.especie = "FELINO"

    if re.search(r"\bmacho\b", t_norm):
        paciente.sexo = "MACHO"
    elif re.search(r"\bhembra\b", t_norm):
        paciente.sexo = "HEMBRA"

    m_edad = re.search(r"\b(\d+\s*(?:anos?|años?|meses|mes|semanas?|dias?|días?))\b", texto, re.I)
    if m_edad:
        paciente.edad = m_edad.group(1).upper()

    m_peso = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|k)\b", t_norm)
    if m_peso:
        try:
            paciente.peso_kg = float(m_peso.group(1).replace(",", "."))
        except ValueError:
            pass

    partes = [p.strip() for p in texto.split(",") if p.strip()]
    if len(partes) >= 2:
        if not paciente.nombre and partes[0]:
            paciente.nombre = partes[0].upper()

        for p in partes[1:]:
            p_n = _norm(p)
            if any(k in p_n for k in ("canino", "perro", "perra", "felino", "gato", "gata", "can", "fel")):
                if not paciente.especie:
                    paciente.especie = "CANINO" if any(k in p_n for k in ("can", "perr")) else "FELINO"
                continue
            if any(k in p_n for k in ("macho", "hembra")):
                if not paciente.sexo:
                    paciente.sexo = "MACHO" if "macho" in p_n else "HEMBRA"
                continue
            if re.search(r"\b\d+\s*(?:anos?|años?|meses|mes|semanas?|dias?|días?)\b", p_n):
                if not paciente.edad:
                    paciente.edad = p.upper()
                continue
            if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:kg|kilos?|k)\b", p_n) or re.match(r"^\d+(?:[.,]\d+)?$", p_n):
                if paciente.peso_kg is None:
                    m = re.search(r"(\d+(?:[.,]\d+)?)", p_n)
                    if m:
                        try:
                            paciente.peso_kg = float(m.group(1).replace(",", "."))
                        except ValueError:
                            pass
                continue
            if not paciente.raza and len(p) >= 3:
                paciente.raza = p.upper()

    return paciente.esta_completo()


def _preguntar_siguiente_campo(paciente: Paciente) -> tuple[str, str]:
    if not paciente.nombre:
        return "nombre", "POR FAVOR INDICA EL NOMBRE DEL PACIENTE:"
    if not paciente.especie:
        return "especie", f"CUAL ES LA ESPECIE DE {paciente.nombre}? (CANINO / FELINO):"
    if not paciente.raza:
        return "raza", f"CUAL ES LA RAZA DE {paciente.nombre}? (EJ: BULLDOG, LABRADOR, SIAMES, MESTIZO...):"
    if not paciente.sexo:
        return "sexo", f"CUAL ES EL SEXO DE {paciente.nombre}? (MACHO / HEMBRA):"
    if not paciente.edad:
        return "edad", f"CUAL ES LA EDAD APROXIMADA DE {paciente.nombre}? (EJ: 2 ANOS, 8 MESES):"
    if paciente.peso_kg is None or paciente.peso_kg <= 0:
        return "peso", f"CUAL ES EL PESO EN KG DE {paciente.nombre}? (EJ: 14 KG):"
    return "", ""


# 5 PREGUNTAS DEL SISTEMA CUANTIFICABLE DE TRIAJE

def _pregunta_triaje_1(p: Paciente) -> tuple[str, dict[str, Any]]:
    txt = (
        f"FICHA REGISTRADA:\n{p.resumen()}\n\n"
        "EVALUACION DE TRIAJE CLINICO (1 DE 5)\n"
        f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n\n"
        "PREGUNTA 1: ¿COMO ES EL ESTADO MENTAL DEL PACIENTE?\n"
        "- ALERTA Y RESPONSIVO: 0 PUNTOS\n"
        "- DEPRIMIDO, LETARGICO O DIFICIL DE DESPERTAR: 2 PUNTOS\n"
        "- COMATOSO O CONVULSIONANDO: 3 PUNTOS\n\n"
        "RESPONDE CON TU OPCION (O PULSA UN BOTON):"
    )
    return txt, KEYBOARD_TRIAJE_P1


def _pregunta_triaje_2(p: Paciente) -> tuple[str, dict[str, Any]]:
    txt = (
        "EVALUACION DE TRIAJE CLINICO (2 DE 5)\n"
        f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n\n"
        "PREGUNTA 2: ¿CUAL ES EL COLOR DE LAS MUCOSAS Y EL TIEMPO DE LLENADO CAPILAR?\n"
        "- ROSADAS Y LLENADO MENOR A 2 SEGUNDOS: 0 PUNTOS\n"
        "- PALIDAS, CONGESTIVAS O PEGAJOSAS, CON LLENADO DE 2 SEGUNDOS: 1 PUNTO\n"
        "- CIANOTICAS (AZULADAS), ICTERICAS (AMARILLAS) O LLENADO MAYOR A 3 SEGUNDOS: 3 PUNTOS\n\n"
        "RESPONDE CON TU OPCION (O PULSA UN BOTON):"
    )
    return txt, KEYBOARD_TRIAJE_P2


def _pregunta_triaje_3(p: Paciente) -> tuple[str, dict[str, Any]]:
    txt = (
        "EVALUACION DE TRIAJE CLINICO (3 DE 5)\n"
        f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n\n"
        "PREGUNTA 3: ¿EXISTE EVIDENCIA DE DESHIDRATACION O HIPOPERFUSION?\n"
        "- MUCOSAS HUMEDAS, PLIEGUE CUTANEO INMEDIATO: 0 PUNTOS\n"
        "- MUCOSAS SECAS, RETRASO LEVE A MODERADO DEL PLIEGUE: 1 PUNTO\n"
        "- MUCOSAS PEGAJOSAS, PLIEGUE PERSISTENTE O SIGNOS DE SHOCK: 3 PUNTOS\n\n"
        "RESPONDE CON TU OPCION (O PULSA UN BOTON):"
    )
    return txt, KEYBOARD_TRIAJE_P3


def _pregunta_triaje_4(p: Paciente) -> tuple[str, dict[str, Any]]:
    txt = (
        "EVALUACION DE TRIAJE CLINICO (4 DE 5)\n"
        f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n\n"
        "PREGUNTA 4: ¿EL PATRON RESPIRATORIO ES NORMAL?\n"
        "- NORMAL, ESFUERZO LEVE: 0 PUNTOS\n"
        "- TAQUIPNEA MARCADA, ESFUERZO MODERADO: 2 PUNTOS\n"
        "- DISNEA GRAVE, BOQUEO, PATRON PARADOJICO: 3 PUNTOS\n\n"
        "RESPONDE CON TU OPCION (O PULSA UN BOTON):"
    )
    return txt, KEYBOARD_TRIAJE_P4


def _pregunta_triaje_5(p: Paciente) -> tuple[str, dict[str, Any]]:
    txt = (
        "EVALUACION DE TRIAJE CLINICO (5 DE 5)\n"
        f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n\n"
        "PREGUNTA 5: ¿COMO ES LA CALIDAD DEL PULSO ARTERIAL?\n"
        "- FUERTE Y SINCRONICO: 0 PUNTOS\n"
        "- DEBIL, FILIFORME O DIFICIL DE PALPAR: 2 PUNTOS\n"
        "- AUSENTE: 3 PUNTOS\n\n"
        "RESPONDE CON TU OPCION (O PULSA UN BOTON):"
    )
    return txt, KEYBOARD_TRIAJE_P5


def _extraer_puntos_p1(texto: str) -> tuple[int, str] | None:
    t_n = _norm(texto)
    if any(k in t_n for k in ("3", "comatoso", "convulsion", "convulsionando", "inconsciente")):
        return 3, "COMATOSO O CONVULSIONANDO (3 PUNTOS)"
    if any(k in t_n for k in ("2", "deprimido", "letargico", "dificil de despertar", "decaido")):
        return 2, "DEPRIMIDO O LETARGICO (2 PUNTOS)"
    if any(k in t_n for k in ("1", "0", "alerta", "responsivo", "normal")):
        return 0, "ALERTA Y RESPONSIVO (0 PUNTOS)"
    return None


def _extraer_puntos_p2(texto: str) -> tuple[int, str] | None:
    t_n = _norm(texto)
    if any(k in t_n for k in ("3", "cianotica", "azul", "morada", "icterica", "amarilla", "mayor a 3", ">3", "> 3")):
        return 3, "CIANOTICAS, ICTERICAS O LLENADO > 3S (3 PUNTOS)"
    if any(k in t_n for k in ("2", "1", "palida", "congestiva", "pegajosa", "2 segundos")):
        return 1, "PALIDAS, CONGESTIVAS O LLENADO 2S (1 PUNTO)"
    if any(k in t_n for k in ("0", "rosada", "menor a 2", "<2", "< 2", "normal")):
        return 0, "ROSADAS Y LLENADO < 2S (0 PUNTOS)"
    return None


def _extraer_puntos_p3(texto: str) -> tuple[int, str] | None:
    t_n = _norm(texto)
    if any(k in t_n for k in ("3", "pegajosa", "persistente", "shock", "grave")):
        return 3, "PLIEGUE PERSISTENTE O SIGNOS DE SHOCK (3 PUNTOS)"
    if any(k in t_n for k in ("2", "1", "seca", "retraso leve", "moderado")):
        return 1, "MUCOSAS SECAS, RETRASO LEVE A MODERADO (1 PUNTO)"
    if any(k in t_n for k in ("0", "humeda", "inmediato", "normal", "hidratado")):
        return 0, "MUCOSAS HUMEDAS, PLIEGUE INMEDIATO (0 PUNTOS)"
    return None


def _extraer_puntos_p4(texto: str) -> tuple[int, str] | None:
    t_n = _norm(texto)
    if any(k in t_n for k in ("3", "disnea", "boqueo", "paradojico", "asfixia", "no respira")):
        return 3, "DISNEA GRAVE, BOQUEO O PATRON PARADOJICO (3 PUNTOS)"
    if any(k in t_n for k in ("2", "taquipnea", "esfuerzo moderado", "jadeo", "rapida")):
        return 2, "TAQUIPNEA O ESFUERZO MODERADO (2 PUNTOS)"
    if any(k in t_n for k in ("1", "0", "normal", "esfuerzo leve", "tranquila")):
        return 0, "NORMAL, ESFUERZO LEVE (0 PUNTOS)"
    return None


def _extraer_puntos_p5(texto: str) -> tuple[int, str] | None:
    t_n = _norm(texto)
    if any(k in t_n for k in ("3", "ausente", "sin pulso")):
        return 3, "PULSO AUSENTE (3 PUNTOS)"
    if any(k in t_n for k in ("2", "debil", "filiforme", "dificil")):
        return 2, "DEBIL, FILIFORME O DIFICIL DE PALPAR (2 PUNTOS)"
    if any(k in t_n for k in ("1", "0", "fuerte", "sincronico", "normal")):
        return 0, "FUERTE Y SINCRONICO (0 PUNTOS)"
    return None


def _evaluar_resultado_triaje(p: Paciente, puntos: dict[str, int], respuestas: dict[str, str]) -> str:
    pts_p1 = puntos.get("p1", 0)
    pts_p2 = puntos.get("p2", 0)
    pts_p3 = puntos.get("p3", 0)
    pts_p4 = puntos.get("p4", 0)
    pts_p5 = puntos.get("p5", 0)

    total_puntos = pts_p1 + pts_p2 + pts_p3 + pts_p4 + pts_p5

    desglose = (
        "DESGLOSE DE PUNTUACION CLINICA:\n"
        f"1. ESTADO MENTAL: {pts_p1} PTS ({respuestas.get('p1', '')})\n"
        f"2. MUCOSAS Y RELLENO CAPILAR: {pts_p2} PTS ({respuestas.get('p2', '')})\n"
        f"3. HIDRATACION / PERFUSION: {pts_p3} PTS ({respuestas.get('p3', '')})\n"
        f"4. PATRON RESPIRATORIO: {pts_p4} PTS ({respuestas.get('p4', '')})\n"
        f"5. PULSO ARTERIAL: {pts_p5} PTS ({respuestas.get('p5', '')})\n"
        f"PUNTAJE TOTAL: {total_puntos} / 15 PUNTOS"
    )

    alerta_critica = ""
    alerta_prioritaria_activada = False
    if pts_p1 == 3 or pts_p4 == 3 or pts_p5 == 3:
        alerta_prioritaria_activada = True
        signos_criticos = []
        if pts_p1 == 3:
            signos_criticos.append("ESTADO MENTAL COMATOSO O CONVULSION")
        if pts_p4 == 3:
            signos_criticos.append("DISNEA GRAVE O BOQUEO")
        if pts_p5 == 3:
            signos_criticos.append("PULSO ARTERIAL AUSENTE")
        criticos_txt = ", ".join(signos_criticos)
        alerta_critica = (
            "\nALERTA PRIORITARIA: SIGNO CRITICO VITAL INDIVIDUAL DETECTADO "
            f"({criticos_txt}). ATENCION MEDICA INMEDIATA OBLIGATORIA."
        )

    if total_puntos >= 9 or alerta_prioritaria_activada:
        clasificacion = "CODIGO ROJO (EMERGENCIA CRITICA / ATENCION INMEDIATA)"
        tiempo = "TIEMPO DE ESPERA: 0 MINUTOS"
        conducta = (
            "ACCIONES INMEDIATAS:\n"
            "1. DESPEJAR VIA AEREA Y ADMINISTRAR OXIGENOTERAPIA.\n"
            "2. ACCESO VENOSO URGENTE Y ESTABILIZACION HEMODINAMICA.\n"
            "3. TRASLADO INMEDIATO AL MEDICO VETERINARIO TITULADO."
        )
    elif total_puntos >= 4:
        clasificacion = "CODIGO AMARILLO (URGENCIA MODERADA / REQUIERE ATENCION PRONTA)"
        tiempo = "TIEMPO ESTIMADO DE EVALUACION: 30 A 60 MINUTOS"
        conducta = (
            "ACCIONES RECOMENDADAS:\n"
            "1. UBICAR EN SALA DE ESPERA O PRE-INGRESO BAJO VIGILANCIA.\n"
            "2. NO MEDICAR SIN EXPLORACION VETERINARIA PREVIA.\n"
            "3. EVALUAR REHIDRATACION O TRATAMIENTO MEDICO PRONTO."
        )
    else:
        clasificacion = "CODIGO VERDE (ESTABLE / SIN URGENCIA INMEDIATA)"
        tiempo = "CONSULTA PROGRAMABLE / TURNO ORDINARIO"
        conducta = (
            "ACCIONES RECOMENDADAS:\n"
            "1. COMPATIBLE CON CONSULTA EXTERNA, VACUNACION O CHEQUEO DE RUTINA.\n"
            "2. MANTENER RECOMENDACIONES Y MONITOREO AMBULATORIO.\n"
            "3. REEVALUAR SI LOS SIGNOS CLINICOS EMPEORAN."
        )

    return (
        f"CLASIFICACION FINAL DEL TRIAJE:\n"
        f"{clasificacion}\n"
        f"{tiempo}\n\n"
        f"{p.resumen()}\n\n"
        f"{desglose}\n"
        f"{alerta_critica}\n\n"
        f"{conducta}\n\n"
        f"{AVISO}\n\n"
        "SELECCIONA UNA OPCION EN EL MENU O INICIA OTRO CALCULO:"
    )


def _iniciar_opcion_tras_ficha(sesion: SesionChat) -> tuple[str, dict[str, Any] | None]:
    p = sesion.paciente
    op = sesion.opcion

    if op == "triaje":
        sesion.estado = "TRIAJE_P1"
        sesion.puntos_triaje = {}
        sesion.respuestas_texto = {}
        return _pregunta_triaje_1(p)

    if op == "dosis":
        sesion.estado = "DOSIS_VALOR"
        txt = (
            f"FICHA REGISTRADA:\n{p.resumen()}\n\n"
            f"DOSIFICACION EXACTA PARA {p.nombre.upper()} ({p.peso_kg} KG):\n\n"
            "INDICA LA DOSIS EN MG/KG Y LA CONCENTRACION DEL MEDICAMENTO.\n"
            "EJEMPLOS:\n"
            "MELOXICAM 0.2 MG/KG CON FRASCO AL 0.5%\n"
            "10 MG/KG CON FRASCO DE 50 MG/ML\n"
            "5 MG/KG CON TABLETAS DE 20 MG"
        )
        return txt, KEYBOARD_VOLVER

    if op == "fluidoterapia":
        sesion.estado = "FLUIDO_VALOR"
        txt = (
            f"FICHA REGISTRADA:\n{p.resumen()}\n\n"
            f"PLAN DE FLUIDOTERAPIA PARA {p.nombre.upper()} ({p.peso_kg} KG):\n\n"
            "EXPLICACION CLINICA DE CADA PORCENTAJE DE DESHIDRATACION:\n\n"
            "- < 5% (SUBCLINICA): NO EVIDENTE AL EXAMEN FISICO; SOSPECHA POR PERDIDAS RECIENTES.\n"
            "- 5% A 6% (LEVE): MUCOSAS LIGERAMENTE SECAS O PEGAJOSAS, PLIEGUE CUTANEO DORSAL RECUPERA ELASTICIDAD EN 1 A 2 SEGUNDOS, OJOS NORMALES.\n"
            "- 7% A 8% (MODERADA): MUCOSAS FRANCAMENTE SECAS, PLIEGUE CUTANEO TARDA DE 2 A 3 SEGUNDOS EN REGRESAR, LIGERO ENOFTALMOS (OJOS HUNDIDOS) Y TIEMPO DE LLENADO CAPILAR DE 2 SEGUNDOS.\n"
            "- 9% A 10% (SEVERA): PLIEGUE CUTANEO PERSISTENTE (> 3 SEGUNDOS), MUCOSAS MUY SECAS Y PALIDAS, ENOFTALMOS MARCADO, EXTREMIDADES FRIAS Y PULSO DEBIL.\n"
            "- 11% A 12%+ (CRITICA / SHOCK HIPOVOLEMICO): SIGNOS FRANCOS DE COLAPSO HEMODINAMICO, PULSO CASI IMPERCEPTIBLE, LLENADO CAPILAR > 3 SEGUNDOS Y RIESGO DE MUERTE INMINENTE.\n\n"
            "¿CUAL ES EL PORCENTAJE ESTIMADO DE DESHIDRATACION (%) DEL PACIENTE?\n"
            "ESCRIBE EL NUMERO (EJ: 5%, 6%, 8%, 10%) O SELECCIONA UN BOTON:"
        )
        return txt, KEYBOARD_FLUIDO

    if op == "clima":
        sesion.estado = "CLIMA_CIUDAD"
        txt = (
            f"FICHA REGISTRADA:\n{p.resumen()}\n\n"
            f"RIESGO TERMICO Y GOLPE DE CALOR PARA {p.nombre.upper()} (RAZA: {p.raza}):\n\n"
            "EN QUE CIUDAD SE ENCUENTRA EL PACIENTE? (EJ: MEDELLIN, BOGOTA, CALI...)"
        )
        return txt, KEYBOARD_VOLVER

    sesion.estado = "MENU"
    return _menu_principal_texto(), KEYBOARD_MENU


def procesar_flujo(chat_id: str, texto_usuario: str, nombre_usuario: str = "") -> tuple[str, dict[str, Any] | None]:
    sesion = obtener_sesion(chat_id)
    t = texto_usuario.strip()
    t_norm = _norm(t)

    if t_norm in ("/reset", "reset", "nuevo paciente", "nuevo paciente (/reset)"):
        sesion = resetear_sesion(chat_id)
        return (
            "SESION Y FICHA DEL PACIENTE REINICIADAS.\n\n"
            + _menu_principal_texto(nombre_usuario),
            KEYBOARD_MENU,
        )

    if t_norm in ("/start", "start", "hola", "ayuda", "/help", "/menu", "menu", "volver", "atras", "atras", "inicio", "volver al menu principal", "volver al menu"):
        sesion.estado = "MENU"
        sesion.opcion = ""
        sesion.campo_pendiente = ""
        return _menu_principal_texto(nombre_usuario), KEYBOARD_MENU

    if t_norm in ("/paciente", "ver paciente", "ver paciente actual"):
        return f"{sesion.paciente.resumen()}\n\nUSA /MENU PARA VOLVER A LAS OPCIONES.", KEYBOARD_MENU

    # ESTADO: MENÚ PRINCIPAL
    if sesion.estado == "MENU":
        if any(k in t_norm for k in ("triaje", "1")):
            sesion.opcion = "triaje"
            if not sesion.paciente.esta_completo():
                sesion.estado = "PIDIENDO_FICHA"
                return _pedir_ficha_texto(sesion.paciente, "EL TRIAJE CLINICO"), KEYBOARD_VOLVER
            return _iniciar_opcion_tras_ficha(sesion)

        if any(k in t_norm for k in ("dosis", "dosificacion", "2")):
            sesion.opcion = "dosis"
            if not sesion.paciente.esta_completo():
                sesion.estado = "PIDIENDO_FICHA"
                return _pedir_ficha_texto(sesion.paciente, "EL CALCULO DE DOSIS"), KEYBOARD_VOLVER
            return _iniciar_opcion_tras_ficha(sesion)

        if any(k in t_norm for k in ("fluido", "fluidoterapia", "3")):
            sesion.opcion = "fluidoterapia"
            if not sesion.paciente.esta_completo():
                sesion.estado = "PIDIENDO_FICHA"
                return _pedir_ficha_texto(sesion.paciente, "EL PLAN DE FLUIDOTERAPIA"), KEYBOARD_VOLVER
            return _iniciar_opcion_tras_ficha(sesion)

        if any(k in t_norm for k in ("clima", "calor", "termico", "4")):
            sesion.opcion = "clima"
            if not sesion.paciente.esta_completo():
                sesion.estado = "PIDIENDO_FICHA"
                return _pedir_ficha_texto(sesion.paciente, "LA ALERTA DE RIESGO TERMICO"), KEYBOARD_VOLVER
            return _iniciar_opcion_tras_ficha(sesion)

        return (
            "SELECCIONA UNA OPCION VALIDA (1, 2, 3 O 4):\n\n"
            + _menu_principal_texto(nombre_usuario),
            KEYBOARD_MENU,
        )

    # ESTADO: PIDIENDO FICHA
    if sesion.estado == "PIDIENDO_FICHA":
        if "," in t or len(t.split()) >= 4:
            _parsear_ficha_completa(t, sesion.paciente)

        if not sesion.paciente.esta_completo():
            cp = sesion.campo_pendiente or _preguntar_siguiente_campo(sesion.paciente)[0]
            if cp == "nombre" and not sesion.paciente.nombre:
                sesion.paciente.nombre = t.strip().upper()
            elif cp == "especie" and not sesion.paciente.especie:
                if any(k in t_norm for k in ("canino", "perro", "perra", "can")):
                    sesion.paciente.especie = "CANINO"
                elif any(k in t_norm for k in ("felino", "gato", "gata", "fel")):
                    sesion.paciente.especie = "FELINO"
                else:
                    sesion.paciente.especie = t.strip().upper()
            elif cp == "raza" and not sesion.paciente.raza:
                sesion.paciente.raza = t.strip().upper()
            elif cp == "sexo" and not sesion.paciente.sexo:
                if "macho" in t_norm:
                    sesion.paciente.sexo = "MACHO"
                elif "hembra" in t_norm:
                    sesion.paciente.sexo = "HEMBRA"
                else:
                    sesion.paciente.sexo = t.strip().upper()
            elif cp == "edad" and not sesion.paciente.edad:
                sesion.paciente.edad = t.strip().upper()
            elif cp == "peso" and (sesion.paciente.peso_kg is None or sesion.paciente.peso_kg <= 0):
                m = re.search(r"(\d+(?:[.,]\d+)?)", t_norm)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if val > 0:
                            sesion.paciente.peso_kg = val
                    except ValueError:
                        pass

        if sesion.paciente.esta_completo():
            sesion.campo_pendiente = ""
            return _iniciar_opcion_tras_ficha(sesion)

        campo, pregunta = _preguntar_siguiente_campo(sesion.paciente)
        sesion.campo_pendiente = campo
        faltan_txt = ", ".join(sesion.paciente.faltantes())
        return (
            f"DATOS PENDIENTES: {faltan_txt}\n\n{pregunta}",
            KEYBOARD_VOLVER,
        )

    # TRIAJE 1/5: ESTADO MENTAL
    if sesion.estado == "TRIAJE_P1":
        res = _extraer_puntos_p1(t)
        if res is None:
            return (
                "POR FAVOR SELECCIONA UNA OPCION VALIDA: 1, 2 O 3 (O PULSA UN BOTON):",
                KEYBOARD_TRIAJE_P1,
            )
        pts, desc = res
        sesion.puntos_triaje["p1"] = pts
        sesion.respuestas_texto["p1"] = desc
        sesion.estado = "TRIAJE_P2"
        return _pregunta_triaje_2(sesion.paciente)

    # TRIAJE 2/5: MUCOSAS Y LLENADO CAPILAR
    if sesion.estado == "TRIAJE_P2":
        res = _extraer_puntos_p2(t)
        if res is None:
            return (
                "POR FAVOR SELECCIONA UNA OPCION VALIDA: 1, 2 O 3 (O PULSA UN BOTON):",
                KEYBOARD_TRIAJE_P2,
            )
        pts, desc = res
        sesion.puntos_triaje["p2"] = pts
        sesion.respuestas_texto["p2"] = desc
        sesion.estado = "TRIAJE_P3"
        return _pregunta_triaje_3(sesion.paciente)

    # TRIAJE 3/5: DESHIDRATACIÓN O HIPOPERFUSIÓN
    if sesion.estado == "TRIAJE_P3":
        res = _extraer_puntos_p3(t)
        if res is None:
            return (
                "POR FAVOR SELECCIONA UNA OPCION VALIDA: 1, 2 O 3 (O PULSA UN BOTON):",
                KEYBOARD_TRIAJE_P3,
            )
        pts, desc = res
        sesion.puntos_triaje["p3"] = pts
        sesion.respuestas_texto["p3"] = desc
        sesion.estado = "TRIAJE_P4"
        return _pregunta_triaje_4(sesion.paciente)

    # TRIAJE 4/5: PATRÓN RESPIRATORIO
    if sesion.estado == "TRIAJE_P4":
        res = _extraer_puntos_p4(t)
        if res is None:
            return (
                "POR FAVOR SELECCIONA UNA OPCION VALIDA: 1, 2 O 3 (O PULSA UN BOTON):",
                KEYBOARD_TRIAJE_P4,
            )
        pts, desc = res
        sesion.puntos_triaje["p4"] = pts
        sesion.respuestas_texto["p4"] = desc
        sesion.estado = "TRIAJE_P5"
        return _pregunta_triaje_5(sesion.paciente)

    # TRIAJE 5/5: PULSO ARTERIAL
    if sesion.estado == "TRIAJE_P5":
        res = _extraer_puntos_p5(t)
        if res is None:
            return (
                "POR FAVOR SELECCIONA UNA OPCION VALIDA: 1, 2 O 3 (O PULSA UN BOTON):",
                KEYBOARD_TRIAJE_P5,
            )
        pts, desc = res
        sesion.puntos_triaje["p5"] = pts
        sesion.respuestas_texto["p5"] = desc
        sesion.estado = "MENU"
        res_final = _evaluar_resultado_triaje(sesion.paciente, sesion.puntos_triaje, sesion.respuestas_texto)
        return res_final, KEYBOARD_MENU

    # DOSIFICACIÓN (3 PASOS ULTRA-CONCISOS)
    if sesion.estado == "DOSIS_VALOR":
        p = sesion.paciente
        t_clean = t.replace(",", ".")

        m_dosis = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*kg", t_clean, re.I)
        if not m_dosis:
            m_dosis = re.search(r"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*ml)", t_clean, re.I)
        if not m_dosis:
            m_dosis = re.search(r"^\s*(\d+(?:\.\d+)?)\s*$", t_clean)

        if not m_dosis:
            return (
                "INDICA LA DOSIS EN MG/KG (EJEMPLO: 0.2 MG/KG O 10 MG/KG).\n"
                "SI TIENES CONCENTRACION INDICALA TAMBIEN (EJEMPLO: 0.5% O 20 MG/ML):",
                KEYBOARD_VOLVER,
            )

        dosis_val = float(m_dosis.group(1))

        m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", t_clean)
        pct_val = float(m_pct.group(1)) if m_pct else None

        m_conc = re.search(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*ml", t_clean, re.I)
        conc_val = float(m_conc.group(1)) if m_conc else None

        m_tab = re.search(r"tabletas?\s*(?:de\s*)?(\d+(?:\.\d+)?)\s*mg", t_clean, re.I)
        tab_val = float(m_tab.group(1)) if m_tab else None

        calc = herramientas.calcular_dosis_clinica(
            dosis_mg_kg=dosis_val,
            peso_kg=p.peso_kg or 10.0,
            concentracion_mg_ml=conc_val,
            concentracion_pct=pct_val,
            mg_por_tableta=tab_val,
            nombre_paciente=p.nombre,
        )

        sesion.estado = "MENU"
        res = f"{calc.get('detalle')}\n\n{AVISO}\n\nSELECCIONA OTRA OPCION EN EL MENU:"
        return res, KEYBOARD_MENU

    # FLUIDOTERAPIA
    if sesion.estado == "FLUIDO_VALOR":
        p = sesion.paciente
        m_pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%?", t_norm)
        if not m_pct:
            return (
                "GUIA RAPIDA DE DESHIDRATACION:\n"
                "- 5% - 6%: LEVE (MUCOSAS LEVEMENTE SECAS, PLIEGUE 1-2S)\n"
                "- 7% - 8%: MODERADA (MUCOSAS SECAS, PLIEGUE 2-3S, OJOS HUNDIDOS)\n"
                "- 9% - 10%: SEVERA (PLIEGUE PERSISTENTE, MUCOSAS PEGAJOSAS)\n"
                "- 11% - 12%: CRITICA / SHOCK (COLAPSO, LLENADO > 3S)\n\n"
                "POR FAVOR INDICA EL PORCENTAJE ESTIMADO (EJ: 5%, 6% O 8%):",
                KEYBOARD_VOLVER,
            )
        try:
            pct = float(m_pct.group(1).replace(",", "."))
        except ValueError:
            return ("PORCENTAJE NO VALIDO. INDICA UN NUMERO COMO 5% O 8%.", KEYBOARD_VOLVER)

        res_fluido = herramientas.calcular_fluidoterapia(peso_kg=p.peso_kg, deshidratacion_pct=pct)
        if not res_fluido.get("ok"):
            return (f"ERROR EN EL CALCULO: {res_fluido.get('error')}", KEYBOARD_VOLVER)

        sesion.estado = "MENU"
        res = (
            f"PLAN DE FLUIDOTERAPIA PARA {p.nombre.upper()}:\n\n"
            f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n"
            f"DESHIDRATACION ESTIMADA: {pct}%\n\n"
            "DESGLOSE DE LIQUIDOS (PROTOCOLO 24 HORAS):\n"
            f"1. DEFICIT POR DESHIDRATACION: {res_fluido.get('deficit_ml')} ML ({p.peso_kg} KG x {pct}% x 10)\n"
            f"2. MANTENIMIENTO DIARIO: {res_fluido.get('mantenimiento_ml')} ML ({p.peso_kg} KG x 50 ML/KG/DIA)\n"
            f"VOLUMEN TOTAL 24 HORAS: {res_fluido.get('total_24h_ml')} ML\n"
            f"VELOCIDAD DE INFUSION: {res_fluido.get('velocidad_ml_h')} ML/H\n"
            f"GOTEO ESTANDAR (NORMOGOTERO 20 GOTAS/ML): {round(res_fluido.get('velocidad_ml_h', 0) * 20 / 60, 1)} GOTAS/MIN\n\n"
            f"{AVISO}\n\n"
            "SELECCIONA OTRA OPCION EN EL MENU:"
        )
        return res, KEYBOARD_MENU

    # CLIMA / RIESGO TÉRMICO
    if sesion.estado == "CLIMA_CIUDAD":
        p = sesion.paciente
        ciudad = t.strip()
        res_clima = herramientas.riesgo_golpe_calor(ciudad)
        if not res_clima.get("ok"):
            return (f"NO SE PUDO CONSULTAR EL CLIMA: {res_clima.get('error')}", KEYBOARD_VOLVER)

        sesion.estado = "MENU"
        es_braqui = any(b in _norm(p.raza) for b in ("bulldog", "pug", "boxer", "shih", "boston", "pekin"))
        nota_braqui = (
            f"\nALERTA ESPECIAL PARA {p.raza.upper()}: AL SER RAZA BRAQUICEFALA, SU TERMORREGULACION ES DEFICIENTE. "
            "INTERPRETAR ESTA ALERTA CON MAXIMA PRECAUCION Y EVITAR EXPOSICION AL CALOR."
            if es_braqui else ""
        )

        res = (
            f"EVALUACION DE RIESGO TERMICO EN {str(res_clima.get('ciudad', ciudad)).upper()}:\n\n"
            f"PACIENTE: {p.nombre} ({p.especie}, {p.raza}, {p.peso_kg} KG)\n"
            f"NIVEL DE ALERTA: CODIGO {res_clima.get('nivel')}\n"
            f"TEMPERATURA ACTUAL: {res_clima.get('temperatura_c')} C\n"
            f"HUMEDAD RELATIVA: {res_clima.get('humedad_pct')} %\n"
            f"INDICE DE CALOR PERCIBIDO: {res_clima.get('indice_calor_c')} C\n\n"
            f"RECOMENDACIONES DE MANEJO:\n"
            f"{str(res_clima.get('recomendacion', '')).upper()}\n"
            f"{nota_braqui}\n\n"
            f"{AVISO}\n\n"
            "SELECCIONA OTRA OPCION EN EL MENU:"
        )
        return res, KEYBOARD_MENU

    sesion.estado = "MENU"
    return _menu_principal_texto(nombre_usuario), KEYBOARD_MENU
