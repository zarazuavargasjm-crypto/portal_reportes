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
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return creds


def leer_hoja(rango):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rango
    ).execute()
    return result.get("values", [])


def parse_fecha(fecha_str):
    if not fecha_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(fecha_str, fmt).date()
        except ValueError:
            continue
    return None


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

        folio = fila[0]              # A
        institucion_fila = fila[5]   # F
        fecha_entrega = fila[10]     # K
        estatus = fila[12] if len(fila) > 12 else ""  # M

        if not es_admin and institucion_fila != institucion:
            continue

        if not es_admin:
            fecha_obj = parse_fecha(fecha_entrega)
            if estatus == "Entregado" and fecha_obj is not None and fecha_obj < limite:
                continue

        datos_filtrados.append(fila)

    return headers, datos_filtrados


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

        reportes = leer_hoja(RANGO_REPORTES)

        if es_admin:
            headers, datos = procesar_reportes(reportes, es_admin=True)
            return render_template(
                "admin.html",
                headers=headers,
                datos=datos
            )
        else:
            headers, datos = procesar_reportes(reportes, institucion=institucion, es_admin=False)
            return render_template(
                "tabla.html",
                institucion=institucion,
                headers=headers,
                datos=datos
            )

    return render_template("login.html")


if __name__ == "__main__":
    app.run(debug=True)
