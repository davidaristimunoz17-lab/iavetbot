# Agente IA de Triaje y Apoyo Clínico Veterinario

Asistente académico para estudiantes de Medicina Veterinaria: clasifica urgencias, calcula dosis y fluidoterapia con funciones exactas de Python y consulta protocolos locales. **No sustituye a un Médico Veterinario titulado.**

## 1. Requisitos

- Python 3.10 o superior.
- Opcional: Ollama con el modelo `llama3.2:3b` para usar IA local.
- Opcional: token de Telegram y un ID de usuario autorizado.

## 2. Instalación

En la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

En Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env`.

## 3. Elegir el cerebro

Edita `.env` y define `CEREBRO`:

| Valor | Descripción |
| --- | --- |
| `ollama` (por defecto) | Modelo local `llama3.2:3b` en `http://localhost:11434`. Instala Ollama y ejecuta `ollama pull llama3.2:3b` antes de arrancar. |
| `api` | Endpoint compatible con OpenAI/Groq: configura `API_BASE`, `API_KEY` y `API_MODEL`. |
| `reglas` | Modo sin IA: decisiones deterministas y herramientas reales. Útil para clase, pruebas o cuando no hay modelo disponible. |

Si Ollama o la API fallan, el agente responde automáticamente con el modo `reglas`.

## 4. Ejecutar en consola

```powershell
python main.py --canal consola
```

También es el valor por defecto: `python main.py`.

Ejemplos:

```text
Tú> Clasifica el triaje de un gato con disnea grave
Tú> Calcula la dosis de 10 mg/kg para un perro de 12 kg
Tú> Fluidoterapia para un perro de 10 kg con 6% de deshidratación
Tú> ¿Cuál es el riesgo de golpe de calor en Medellín para un bulldog?
Tú> /reset
Tú> /salir
```

Límites activos: **10 mensajes por minuto** y **1500 caracteres por mensaje**. `/reset` borra los últimos mensajes guardados para ese chat.

## 5. Ejecutar en Telegram

1. Crea un bot con BotFather y copia el token a `TELEGRAM_TOKEN` en `.env`.
2. Obtén tu ID numérico de usuario y ponlo en `TELEGRAM_ADMINS` (varios IDs separados por comas).
3. Arranca:

```powershell
python main.py --canal telegram
```

El adaptador usa long polling con `requests`. Solo responde a usuarios de la lista blanca.

## 6. Pruebas automatizadas

```powershell
python tests/evaluar.py
```

Ejecuta 6 casos clínicos (dosis, fluidoterapia, triaje, riesgo térmico con clima simulado, peso negativo e inyección de prompt) usando `CEREBRO=reglas`. Imprime aciertos, tasa de éxito y latencia media.

## 7. Estructura

```text
main.py                     Entrada, canales y rate limit
agente.py                   Prompt sistema, ReAct (4 pasos), JSON estricto y 1 reintento
cerebro.py                  ollama | api | reglas
herramientas.py             Dosis (ast), fluidoterapia, protocolos y Open-Meteo
memoria.py                  SQLite: últimos 6 mensajes por chat y /reset
canal_telegram.py           Long polling + whitelist
protocolos_vet/             Única fuente de verdad clínica (grounding)
tests/evaluar.py            Evaluación con 6 casos
datos/agente.sqlite3        Base de datos local (se crea automáticamente)
```

## 8. Seguridad y ética

- Los cálculos se ejecutan con `ast`, nunca con `eval()`.
- El triaje solo se responde con fragmentos de `protocolos_vet/`.
- Si falta el peso u otro dato indispensable, el agente lo pide antes de operar.
- Se ignoran instrucciones para saltarse reglas, desactivar el aviso o emitir recetas médicas.
- La memoria anoniza correos, teléfonos e identificadores obvios; usa únicamente casos ficticios.
- Toda respuesta clínica lleva el aviso de apoyo académico y no sustitución profesional.
