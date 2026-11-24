"""Persistencia conversacional en SQLite (solo 6 mensajes por chat)."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "datos"
DB_PATH = DB_DIR / "agente.sqlite3"
LIMITE_MENSAJES = 6


def _anonimizar(texto: str) -> str:
    """Evita guardar identificadores obvios de pacientes reales."""
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[CORREO_REDACTADO]", texto)
    texto = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[TELEFONO_REDACTADO]", texto)
    texto = re.sub(r"\b(?:HC|historia\s*clinica|cedula|id)\s*[:#-]?\s*\d+\b", "[ID_REDACTADO]", texto, flags=re.I)
    return texto[:4000]


class Memoria:
    def __init__(self, ruta: Path | str = DB_PATH) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        conexion = sqlite3.connect(self.ruta, timeout=10)
        try:
            conexion.execute("PRAGMA journal_mode=WAL")
            yield conexion
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def _inicializar(self) -> None:
        with self._conectar() as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS mensajes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conexion.execute(
                "CREATE INDEX IF NOT EXISTS idx_mensajes_chat ON mensajes(chat_id, id)"
            )

    def guardar(self, chat_id: str, rol: str, contenido: str) -> None:
        with self._conectar() as conexion:
            conexion.execute(
                "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, ?, ?)",
                (str(chat_id), rol, _anonimizar(str(contenido))),
            )

    def obtener(self, chat_id: str, limite: int = LIMITE_MENSAJES) -> list[dict[str, str]]:
        with self._conectar() as conexion:
            filas = conexion.execute(
                """
                SELECT rol, contenido FROM (
                    SELECT id, rol, contenido FROM mensajes
                    WHERE chat_id = ? ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
                """,
                (str(chat_id), max(1, min(int(limite), LIMITE_MENSAJES))),
            ).fetchall()
        return [{"role": rol, "content": contenido} for rol, contenido in filas]

    def borrar(self, chat_id: str) -> None:
        with self._conectar() as conexion:
            conexion.execute("DELETE FROM mensajes WHERE chat_id = ?", (str(chat_id),))

    def describir(self, chat_id: str) -> str:
        return f"{len(self.obtener(chat_id))}/{LIMITE_MENSAJES} mensajes en memoria"
