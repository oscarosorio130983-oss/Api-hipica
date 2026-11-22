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


class FuenteHipodromo(BaseModel
