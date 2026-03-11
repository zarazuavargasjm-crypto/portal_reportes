import os
import json
from flask import Flask, render_template, request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

SPREADSHEET_ID = "1SIUppcNpM8nObGGPzEcLBrN50lLU9_bH-_yYZFoP_uM"
RANGO_DIRECTORIO = "Directorio!A:E"
RANGO_REPORTES = "Reportes de entrega!A:M"

# Crear credenciales desde la variable de entorno
def obtener_credenciales():
    # 1) Leer la variable de entorno
    cred_json = os.environ.get("GOOGLE_CREDENTIALS")

    # 2) Validar que exista
    if not cred_json:
        raise ValueError("La variable GOOGLE_CREDENTIALS no está definida")

    try:
        # 3) Asegurar que sea texto y limpiar espacios invisibles
        cred_json = str(cred_json).strip()

        # 4) Convertir el JSON (texto) a diccionario de Python
        cred_dict = json.loads(cred_json)
    except json.JSONDecodeError as e:
        # 5) Si el JSON está mal formado, lanzar un error claro
        raise ValueError(f"Error al decodificar GOOGLE_CREDENTIALS: {e}")

    # 6) Crear las credenciales de servicio con los scopes necesarios
    creds = Credentials.from_service_account_info(
        cred_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return creds

# Leer datos desde Google Sheets
def leer_hoja(rango):
    creds = obtener_credenciales()
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rango
    ).execute()
    return result.get("values", [])

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        nip = request.form["nip"]

        directorio = leer_hoja(RANGO_DIRECTORIO)

        institucion = None

        # Directorio: A=Escuela, B=Responsable, C=Correo, D=Usuario, E=NIP
        for fila in directorio[1:]:
            if len(fila) < 5:
                continue

            escuela = fila[0]
            user = fila[3]
            password = fila[4]

            if usuario == user and nip == password:
                institucion = escuela
                break

        if not institucion:
            return render_template("login.html", error="Usuario o NIP incorrectos")

        # Leer reportes
        reportes = leer_hoja(RANGO_REPORTES)
        headers = reportes[0]

        # Filtrar por institución (columna F = índice 5)
        filtrados = [fila for fila in reportes[1:] if len(fila) > 5 and fila[5] == institucion]

        return render_template(
            "tabla.html",
            institucion=institucion,
            headers=headers,
            datos=filtrados
        )

    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True)

