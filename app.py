import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# 🔐 SECRET KEY (única línea agregada, necesaria para Flask en Vercel)
app.secret_key = os.environ.get("260790", "clave-segura")

SPREADSHEET_ID = "1SIUppcNpM8nObGGPzEcLBrN50lLU9_bH-_yYZFoP_uM"
RANGO_DIRECTORIO = "Directorio!A:E"
RANGO_REPORTES = "Reportes de entrega!A:M"
RANGO_REGISTRO = "Registro de consultas!A1"

# ============================
#  SEGURIDAD Y BLOQUEOS
# ============================
intentos_fallidos = {}
bloqueos_temporales = {}
conteo_bloqueos_temporales = {}
bloqueos_permanentes = set()

MAX_INTENTOS = 5
TIEMPO_BLOQUEO = timedelta(minutes=10)
MAX_BLOQUEOS_TEMP_PARA_PERMANENTE = 3

def ip_actual():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def verificar_bloqueo():
    ip = ip_actual()
    ahora = datetime.utcnow()
    if ip in bloqueos_permanentes: return "permanente"
    if ip in bloqueos_temporales:
        if ahora < bloqueos_temporales[ip]: return "temporal"
        else: del bloqueos_temporales[ip]
    return None

def obtener_credenciales():
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not cred_json: return None
    try:
        cred_dict = json.loads(cred_json.strip())
        return Credentials.from_service_account_info(
            cred_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    except:
        return None

def leer_hoja(rango):
    creds = obtener_credenciales()
    if not creds: return []
    try:
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango
        ).execute()
        return result.get("values", [])
    except:
        return []

def escribir_registro(fila):
    creds = obtener_credenciales()
    if not creds: return
    try:
        service = build("sheets", "v4", credentials=creds)
        body = {"values": [fila]}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGO_REGISTRO,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except:
        pass

def registrar_evento(usuario, motivo, institucion="-"):
    fecha = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M:%S")
    fila = [fecha, usuario, ip_actual(), motivo, institucion]
    escribir_registro(fila)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        nip = request.form["nip"]
        ip = ip_actual()

        estado = verificar_bloqueo()
        if estado:
            registrar_evento(usuario, f"Intento desde IP bloqueada ({estado})")
            return render_template("login.html", error=f"Acceso restringido: Bloqueo {estado}.")

        directorio = leer_hoja(RANGO_DIRECTORIO)
        institucion = None
        es_admin = False

        for fila in directorio[1:]:
            if len(fila) < 5: continue
            escuela, _, _, user, password = fila
            if usuario == user and nip == password:
                institucion = escuela
                es_admin = (escuela == "Administrador")
                break

        if institucion:
            intentos_fallidos.pop(ip, None)
            registrar_evento(usuario, "Inicio de sesión exitoso", institucion)

            reportes = leer_hoja(RANGO_REPORTES)
            headers = reportes[0] if reportes else []
            filas = reportes[1:] if reportes else []

            if es_admin:
                return render_template("admin.html", headers=headers, datos=filas)

            datos_usuario = [
                f for f in filas
                if len(f) > 5 and f[5] == institucion
            ]

            return render_template(
                "tabla.html",
                institucion=institucion,
                headers=headers,
                datos=datos_usuario
            )

        else:
            ahora = datetime.utcnow()
            intentos_fallidos[ip] = [
                t for t in intentos_fallidos.get(ip, [])
                if ahora - t < timedelta(minutes=10)
            ] + [ahora]

            if len(intentos_fallidos[ip]) >= MAX_INTENTOS:
                bloqueos_temporales[ip] = ahora + TIEMPO_BLOQUEO
                conteo_bloqueos_temporales[ip] = conteo_bloqueos_temporales.get(ip, 0) + 1

                if conteo_bloqueos_temporales[ip] >= MAX_BLOQUEOS_TEMP_PARA_PERMANENTE:
                    bloqueos_permanentes.add(ip)
                    registrar_evento(usuario, "BLOQUEO PERMANENTE")

            registrar_evento(usuario, "Credenciales incorrectas")
            return render_template("login.html", error="Usuario o NIP incorrectos")

    return render_template("login.html")

if __name__ == "__main__":
    app.run()
