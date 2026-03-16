import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

print("=== APP.PY CARGADO CORRECTAMENTE ===")

# ============================
#  CONFIGURACIÓN
# ============================
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
print("DEBUG SPREADSHEET_ID:", SPREADSHEET_ID)

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

# ============================
#  FUNCIONES AUXILIARES
# ============================

def ip_actual():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def verificar_bloqueo():
    ip = ip_actual()
    ahora = datetime.utcnow()
    if ip in bloqueos_permanentes:
        return "permanente"
    if ip in bloqueos_temporales:
        if ahora < bloqueos_temporales[ip]:
            return "temporal"
        else:
            del bloqueos_temporales[ip]
    return None

def obtener_credenciales():
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not cred_json:
        print("DEBUG CREDENCIALES: NO HAY GOOGLE_CREDENTIALS EN VERCEL")
        return None
    try:
        cred_dict = json.loads(cred_json.strip())
        print("DEBUG CREDENCIALES: CARGADAS CORRECTAMENTE")
        return Credentials.from_service_account_info(
            cred_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    except Exception as e:
        print("ERROR AL CARGAR CREDENCIALES:", e)
        return None

def leer_hoja(rango):
    print(f"=== LEYENDO HOJA: {rango} ===")
    creds = obtener_credenciales()
    if not creds:
        print("DEBUG leer_hoja: SIN CREDENCIALES")
        return []
    try:
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango
        ).execute()
        values = result.get("values", [])
        print(f"DEBUG leer_hoja: {len(values)} filas leídas")
        return values
    except Exception as e:
        print("ERROR LEYENDO GOOGLE SHEETS:", e)
        return []

def escribir_registro(fila):
    creds = obtener_credenciales()
    if not creds:
        print("DEBUG escribir_registro: SIN CREDENCIALES")
        return
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
        print("DEBUG escribir_registro: REGISTRO ESCRITO")
    except Exception as e:
        print("ERROR escribiendo registro:", e)

def registrar_evento(usuario, motivo, institucion="-"):
    fecha = (datetime.utcnow() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M:%S")
    fila = [fecha, usuario, ip_actual(), motivo, institucion]
    escribir_registro(fila)

# ============================
#  RUTA PRINCIPAL
# ============================

@app.route("/", methods=["GET", "POST"])
def login():
    print("=== LOGIN ACCEDIDO ===")
    if request.method == "POST":
        print("=== POST LOGIN ===")
        usuario = request.form["usuario"]
        nip = request.form["nip"]
        print("DEBUG usuario:", usuario)

        ip = ip_actual()

        estado = verificar_bloqueo()
        if estado:
            registrar_evento(usuario, f"Intento desde IP bloqueada ({estado})")
            return render_template("login.html", error=f"Acceso restringido: Bloqueo {estado}.")

        print("=== LEYENDO DIRECTORIO ===")
        directorio = leer_hoja(RANGO_DIRECTORIO)
        print("DEBUG DIRECTORIO:", directorio)

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

        if institucion:
            print("=== LOGIN EXITOSO ===")
            print("Institución:", institucion)

            intentos_fallidos.pop(ip, None)
            registrar_evento(usuario, "Inicio de sesión exitoso", institucion)

            print("=== LEYENDO REPORTES ===")
            reportes = leer_hoja(RANGO_REPORTES)
            print("DEBUG REPORTES:", reportes)

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
            print("=== LOGIN FALLIDO ===")
            registrar_evento(usuario, "Credenciales incorrectas")
            return render_template("login.html", error="Usuario o NIP incorrectos")

    return render_template("login.html")

# ============================
#  EJECUCIÓN LOCAL
# ============================

if __name__ == "__main__":
    app.run()
