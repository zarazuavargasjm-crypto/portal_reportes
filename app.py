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


# ---------------------------------------------------------
#  CREDENCIALES
# ---------------------------------------------------------
def obtener_credenciales():
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")

    if not cred_json:
        raise ValueError("La variable GOOGLE_CREDENTIALS no está definida")

    try:
        cred_json = str(cred_json).strip()
        cred_dict = json.loads(cred_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error al decodificar GOOGLE_CREDENTIALS: {e}")

    creds = Credentials.from_service_account_info(
        cred_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
    )
    return creds


# ---------------------------------------------------------
#  LECTURA DE HOJA
# ---------------------------------------------------------
def leer_hoja(rango):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rango
    ).execute()
    return result.get("values", [])


# ---------------------------------------------------------
#  ESCRITURA EN REGISTRO (AGREGAR FILA)
# ---------------------------------------------------------
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


# ---------------------------------------------------------
#  PARSEAR FECHA (ROBUSTO)
# ---------------------------------------------------------
def parse_fecha(fecha_str):
    if not fecha_str:
        return None

    fecha_str = fecha_str.strip()

    formatos = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y"
    ]

    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt).date()
        except:
            pass

    return None


# ---------------------------------------------------------
#  PROCESAR REPORTES (LÓGICA CORRECTA)
# ---------------------------------------------------------
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
        if len(fila) < len(headers):
            fila += [""] * (len(headers) - len(fila))

        institucion_fila = fila[5]   # F
        fecha_entrega = fila[10]     # K
        estatus = fila[12] if len(fila) > 12 else ""

        # -------------------------
        # FILTRO PARA USUARIOS
        # -------------------------
        if not es_admin:

            # Filtrar por institución
            if institucion_fila != institucion:
                continue

            fecha_obj = parse_fecha(fecha_entrega)

            # PENDIENTES → SIEMPRE SE MUESTRAN
            if estatus == "Pendiente":
                datos_filtrados.append(fila)
                continue

            # ENTREGADOS SIN FECHA → NO mostrar
            if estatus == "Entregado" and not fecha_obj:
                continue

            # ENTREGADOS CON MÁS DE 30 DÍAS → NO mostrar
            if estatus == "Entregado" and fecha_obj < limite:
                continue

            # ENTREGADOS RECIENTES → mostrar
            datos_filtrados.append(fila)
            continue

        # -------------------------
        # ADMIN VE TODO
        # -------------------------
        datos_filtrados.append(fila)

    return headers, datos_filtrados


# ---------------------------------------------------------
#  REGISTRAR ACCESO
# ---------------------------------------------------------
def registrar_acceso(usuario, tipo, institucion):
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ip = request.remote_addr or "N/A"

    fila = [fecha, usuario, ip, tipo, institucion]
    escribir_registro(fila)


# ---------------------------------------------------------
#  LOGIN
# ---------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        nip = request.form["nip"]

        directorio = leer_hoja(RANGO_DIRECTORIO)

        institucion = None
        es_admin = False

        for fila in directorio[1:]:
            if len(fila) < 5:
                continue

            escuela = fila[0]
            user = fila[3]
            password = fila[4]

            if usuario == user and nip == password:
                institucion = escuela
                if escuela == "Administrador":
                    es_admin = True
                break

        if not institucion:
            return render_template("login.html", error="Usuario o NIP incorrectos")

        # Registrar acceso
        registrar_acceso(usuario, "Administrador" if es_admin else "Usuario", institucion)

        # Leer reportes
        reportes = leer_hoja(RANGO_REPORTES)

        if es_admin:
            headers, datos = procesar_reportes(reportes, es_admin=True)
            return render_template("admin.html", headers=headers, datos=datos)
        else:
            headers, datos = procesar_reportes(reportes, institucion=institucion, es_admin=False)
            return render_template("tabla.html", institucion=institucion, headers=headers, datos=datos)

    return render_template("login.html")
