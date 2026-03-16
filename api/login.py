import os
import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader

# Cargar templates desde /api/templates
env = Environment(loader=FileSystemLoader("api/templates"))

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
RANGO_DIRECTORIO = "Directorio!A:E"
RANGO_REPORTES = "Reportes de entrega!A:M"
RANGO_REGISTRO = "Registro de consultas!A1"

intentos_fallidos = {}
bloqueos_temporales = {}
conteo_bloqueos_temporales = {}
bloqueos_permanentes = set()

MAX_INTENTOS = 5
TIEMPO_BLOQUEO = timedelta(minutes=10)
MAX_BLOQUEOS_TEMP_PARA_PERMANENTE = 3

def obtener_credenciales():
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not cred_json:
        return None
    try:
        cred_dict = json.loads(cred_json)
        return Credentials.from_service_account_info(
            cred_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    except:
        return None

def leer_hoja(rango):
    creds = obtener_credenciales()
    if not creds:
        return []
    try:
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango
        ).execute()
        return result.get("values", [])
    except:
        return []

def handler(request):
    method = request["method"]

    if method == "GET":
        template = env.get_template("login.html")
        return template.render()

    if method == "POST":
        body = request.get("body", {})
        usuario = body.get("usuario", "")
        nip = body.get("nip", "")

        directorio = leer_hoja(RANGO_DIRECTORIO)
        institucion = None
        es_admin = False

        for fila in directorio[1:]:
            if len(fila) < 5:
                continue
            escuela, _, _, user, password = fila
            if usuario == user and nip == password:
                institucion = escuela
                es_admin = (escuela == "Administrador")
                break

        if not institucion:
            template = env.get_template("login.html")
            return template.render(error="Usuario o NIP incorrectos")

        reportes = leer_hoja(RANGO_REPORTES)
        headers = reportes[0] if reportes else []
        filas = reportes[1:] if reportes else []

        if es_admin:
            template = env.get_template("admin.html")
            return template.render(headers=headers, datos=filas)

        datos_usuario = [
            f for f in filas
            if len(f) > 5 and f[5] == institucion
        ]

        template = env.get_template("tabla.html")
        return template.render(
            institucion=institucion,
            headers=headers,
            datos=datos_usuario
        )
