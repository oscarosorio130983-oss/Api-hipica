from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import httpx
import jwt
import hashlib
import datetime
import os
import re

app = FastAPI(
    title="API Análisis Hípico y Retrospectos",
    description="Backend para retrospectos en PDF, omisión automática sin archivo, pronósticos y acceso con Google.",
    version="1.0.0",
)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "TU_WEB_CLIENT_ID.apps.googleusercontent.com")
JWT_SECRET = os.getenv("JWT_SECRET", "cambia-esta-clave-jwt-secreta-por-una-larga")
SUPERADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("SUPERADMIN_EMAILS", "").split(",")
    if e.strip()
}

CARPETA_PDFS = Path("retrospectos_pdf")
CARPETA_PDFS.mkdir(exist_ok=True)

CATALOGO_PDFS: dict[str, dict] = {}
PRONOSTICOS_POR_DOC: dict[str, dict] = {}

HEADERS_NAVEGADOR = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    )
}


class GoogleAuthRequest(BaseModel):
    token_google: str


class FuenteHipodromo(BaseModel):
    nombre: str
    url: str
    pais: str | None = None


class PronosticoRequest(BaseModel):
    doc_id: str
    carrera: int | None = None
    notas: str | None = None


def crear_token_jwt(payload: dict, horas: int = 24) -> str:
    data = payload.copy()
    expira = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=horas)
    data["exp"] = expira
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")


def verificar_token_jwt(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token faltante o inválido",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado o no válido",
        ) from exc


@app.get("/")
def inicio():
    return {
        "estado": "ok",
        "servicio": "API Análisis Hípico y Retrospectos",
        "docs": "/docs",
    }


@app.get("/health")
def salud():
    return {"status": "healthy"}


@app.post("/auth/google")
def auth_google(req: GoogleAuthRequest):
    try:
        info = id_token.verify_oauth2_token(
            req.token_google,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error verificando token de Google: {exc}",
        ) from exc

    email = (info.get("email") or "").lower()
    rol = "superadmin" if email in SUPERADMIN_EMAILS else "usuario"
    token = crear_token_jwt({"sub": info.get("sub"), "email": email, "rol": rol})
    return {"access_token": token, "token_type": "bearer", "rol": rol, "email": email}


@app.get("/retrospectos")
def listar_retrospectos():
    return {"total": len(CATALOGO_PDFS), "items": list(CATALOGO_PDFS.values())}


@app.post("/pronosticos")
def guardar_pronostico(req: PronosticoRequest, authorization: str | None = Header(default=None)):
    usuario = verificar_token_jwt(authorization)
    clave = f"{req.doc_id}:{req.carrera or 'general'}"
    PRONOSTICOS_POR_DOC[clave] = {
        "doc_id": req.doc_id,
        "carrera": req.carrera,
        "notas": req.notas,
        "autor": usuario.get("email"),
    }
    return {"guardado": True, "pronostico": PRONOSTICOS_POR_DOC[clave]}


@app.get("/pdf/{nombre_archivo}")
def descargar_pdf(nombre_archivo: str):
    ruta = CARPETA_PDFS / Path(nombre_archivo).name
    if not ruta.exists() or not ruta.is_file():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado")
    return FileResponse(path=ruta, media_type="application/pdf", filename=ruta.name)
