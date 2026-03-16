import os
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave-segura")  # usa variable de entorno en Vercel

# Ruta principal: login
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        nip = request.form.get("nip")

        # Ejemplo simple de validación (ajusta según tu lógica real)
        if usuario == "admin" and nip == "1234":
            session["usuario"] = usuario
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", error="Usuario o NIP incorrecto")

    return render_template("login.html")

# Ruta admin
@app.route("/admin")
def admin():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("admin.html")

# Ruta tabla
@app.route("/tabla")
def tabla():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("tabla.html")

# Cerrar sesión
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Para correr localmente
if __name__ == "__main__":
    app.run(debug=True)
