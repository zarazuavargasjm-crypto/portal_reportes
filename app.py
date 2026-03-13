import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

SPREADSHEET_ID = "1SIUppcNpM8nObGGPzEcLBrN50lLU9_bH-_yYZFoP_uM"
RANGO_DIRECTORIO = "Directorio!A:E"
RANGO_REPORTES = "Reportes de entrega!A:M"
RANGO_REGISTRO = "Registro de consultas!A1"

# ============================
#  HEALTH CHECK (Render)
# ============================
@app.route("/health")
def health():
    return "OK", 200

# ============================
#  CREDENCIALES
# ============================
def obtener_credenciales():
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")
    cred_dict = json.loads(cred_json.strip())
    creds = Credentials.from_service_account_info(
        cred_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
    )
    return creds

# ============================
#  LEER HOJA
# ============================
def leer_hoja(rango):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rango
    ).execute()
    return result.get("values", [])

# ============================
#  ESCRIBIR REGISTRO
# ============================
def escribir_registro(fila):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)
    body = {"values": [fila]}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGO_REGISTRO,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

# ============================
#  PARSEAR FECHA
# ============================
def parse_fecha(fecha_str):
    if not fecha_str:
        return None

    fecha_str = str(fecha_str).strip()

    if fecha_str.isdigit():
        try:
            base = datetime(1899, 12, 30)
            return (base + timedelta(days=int(fecha_str))).date()
        except:
            pass

    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }

    if "," in fecha_str and "de" in fecha_str:
        try:
            partes = fecha_str.split(",")[1].strip()
            dia, _, mes_txt, _, anio = partes.split()
            mes = meses.get(mes_txt.lower())
            if mes:
                return datetime(int(anio), mes, int(dia)).date()
        except:
            pass

    formatos = [
        "%d/%m/%Y", "%d/%m/%y",
        "%d-%m-%Y", "%d-%m-%y"
    ]

    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt).date()
        except:
            pass

    return None

# ============================
#  PROCESAR REPORTES
# ============================
def procesar_reportes(reportes, institucion=None, es_admin=False):
    if not reportes:
        return [], []

    headers = reportes[0]
    filas = reportes[1:]

    hoy = datetime.utcnow().date()
    limite = hoy - timedelta(days=30)

    datos_filtrados = []

    for fila in filas:
        fila = list(fila)
        fila += [""] * (len(headers) - len(fila))

        institucion_fila = fila[5]
        fecha_entrega = fila[11]
        estatus = fila[12]

        if not es_admin:

            if institucion_fila != institucion:
                continue

            fecha_obj = parse_fecha(fecha_entrega)

            if estatus == "Pendiente":
                datos_filtrados.append(fila)
                continue

            if estatus == "Entregado" and not fecha_obj:
                continue

            if estatus == "Entregado" and fecha_obj < limite:
                continue

            if estatus == "Entregado":
                datos_filtrados.append(fila)
                continue

        datos_filtrados.append(fila)

    return headers, datos_filtrados

# ============================
#  REGISTRO DE ACCESO
# ============================
def registrar_acceso(usuario, tipo, institucion):
    fecha_utc = datetime.utcnow()
    fecha_mex = fecha_utc - timedelta(hours=6)
    fecha = fecha_mex.strftime("%d/%m/%Y %H:%M:%S")
    ip = ip_actual()
    fila = [fecha, usuario, ip, tipo, institucion]
    escribir_registro(fila)

# ============================
#  REGISTRO DE INTENTOS FALLIDOS
# ============================
def registrar_intento_sheet(usuario, motivo, institucion="-"):
    fecha_utc = datetime.utcnow()
    fecha_mex = fecha_utc - timedelta(hours=6)
    fecha = fecha_mex.strftime("%d/%m/%Y %H:%M:%S")
    ip = ip_actual()
    fila = [fecha, usuario, ip, motivo, institucion]
    escribir_registro(fila)

def registrar_bloqueo_permanente_sheet(ip):
    fecha_utc = datetime.utcnow()
    fecha_mex = fecha_utc - timedelta(hours=6)
    fecha = fecha_mex.strftime("%d/%m/%Y %H:%M:%S")
    fila = [fecha, "-", ip, "Bloqueo permanente", "-"]
    escribir_registro(fila)

# ============================
#  SEGURIDAD
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

    if ip in bloqueos_permanentes:
        return "permanente"

    if ip in bloqueos_temporales:
        if ahora < bloqueos_temporales[ip]:
            return "temporal"
        else:
            del bloqueos_temporales[ip]

    return None

def bloquear_ip_permanente(ip):
    if ip not in bloqueos_permanentes:
        bloqueos_permanentes.add(ip)
        registrar_bloqueo_permanente_sheet(ip)

def registrar_intento_fallido_seguridad():
    ip = ip_actual()
    ahora = datetime.utcnow()

    if ip not in intentos_fallidos:
        intentos_fallidos[ip] = []

    intentos_fallidos[ip].append(ahora)

    intentos_fallidos[ip] = [
        t for t in intentos_fallidos[ip]
        if ahora - t < timedelta(minutes=10)
    ]

    if len(intentos_fallidos[ip]) >= MAX_INTENTOS:
        bloqueos_temporales[ip] = ahora + TIEMPO_BLOQUEO
        intentos_fallidos[ip] = []

        conteo_bloqueos_temporales[ip] = conteo_bloqueos_temporales.get(ip, 0) + 1

        if conteo_bloqueos_temporales[ip] >= MAX_BLOQUEOS_TEMP_PARA_PERMANENTE:
            bloquear_ip_permanente(ip)

# ============================
#  LOGIN
# ============================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        nip = request.form["nip"]

        estado_bloqueo = verificar_bloqueo()
        if estado_bloqueo == "permanente":
            registrar_intento_sheet(usuario, "IP bloqueada permanentemente", "-")
            return render_template("login.html", error="Acceso bloqueado permanentemente.")
        elif estado_bloqueo == "temporal":
            registrar_intento_sheet(usuario, "IP bloqueada temporalmente", "-")
            return render_template("login.html", error="Demasiados intentos fallidos. Intenta más tarde.")

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
            registrar_intento_fallido_seguridad()
            registrar_intento_sheet(usuario, "Credenciales incorrectas", "-")
            return render_template("login.html", error="Usuario o NIP incorrectos")

        ip = ip_actual()
        intentos_fallidos.pop(ip, None)

        registrar_acceso(usuario, "Administrador" if es_admin else "Usuario", institucion)

        reportes = leer_hoja(RANGO_REPORTES)

        if es_admin:
            headers, datos = procesar_reportes(reportes, es_admin=True)
            return render_template("admin.html", headers=headers, datos=datos)

        headers, datos = procesar_reportes(reportes, institucion=institucion, es_admin=False)
        return render_template("tabla.html", institucion=institucion, headers=headers, datos=datos)

    return render_template("login.html")
