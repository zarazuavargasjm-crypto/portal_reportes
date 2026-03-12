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
RANGO_REGISTRO = "Registro de consultas!A:E"   # NUEVO


# ---------------------------------------------------------
#  CARGAR CREDENCIALES
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
#  LEER HOJA
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
#  ESCRIBIR EN HOJA (REGISTRO)
# ---------------------------------------------------------
def escribir_registro(fila):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)

    body = {"values": [fila]}

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGO_REGISTRO,
        valueInputOption="RAW",
        body=body
    ).execute()


# ---------------------------------------------------------
#  PARSEAR FECHA (FORMATO REAL DE LA HOJA)
# ---------------------------------------------------------
def parse_fecha(fecha_str):
    """
    La hoja guarda: 23/2/2026
    Google Sheets lo muestra como: lunes, 23 de febrero de 2026
    PERO el valor real es 23/2/2026 → este es el que recibimos.
    """
    if not fecha_str:
        return None

    try:
        return datetime.strptime(fecha_str, "%d/%m/%Y").date()
    except:
        return None


# ---------------------------------------------------------
#  PROCESAR REPORTES
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
            if institucion_fila != institucion:
                continue

            fecha_obj = parse_fecha(fecha_entrega)

            # Si está entregado y tiene más de 1 mes → NO mostrar
            if estatus == "Entregado" and fecha_obj and fecha_obj < limite:
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


# ---------------------------------------------------------
#  EJECUCIÓN EN RENDER
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
