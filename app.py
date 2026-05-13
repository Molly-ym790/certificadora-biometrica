import os
import time
import hashlib
import subprocess
import datetime
import numpy as np
from deepface import DeepFace
import cv2
from flask import Flask, render_template_string, request, send_file, url_for  # 🔴 NUEVO
from PIL import Image, ImageDraw
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

app = Flask(__name__)
UMBRAL = 0.6

vector1_global = None
vector2_global = None
distancia_global = None
similitud_global = None

def generar_certificado(nombre, correo):

    if not os.path.exists("certificados"):
        os.makedirs("certificados")

    fecha = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    base = f"{nombre}_{fecha}"

    key_path = os.path.join("certificados", base + ".key")
    csr_path = os.path.join("certificados", base + ".csr")
    crt_path = os.path.join("certificados", base + ".crt")

    # Generar clave privada
    subprocess.run([
        "openssl","genrsa",
        "-out", key_path,
        "2048"
    ])

    # Crear CSR
    subprocess.run([
        "openssl","req","-new",
        "-key", key_path,
        "-out", csr_path,
        "-subj", f"/C=MX/O=AC_Biometrica/CN={nombre}/emailAddress={correo}"
    ])

    # Generar certificado
    subprocess.run([
        "openssl","x509","-req",
        "-days","365",
        "-in", csr_path,
        "-signkey", key_path,
        "-out", crt_path
    ])

    return crt_path


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def dibujar_bounding_boxes(img_path, output_path):

    image = cv2.imread(img_path)

    detecciones = DeepFace.extract_faces(
        img_path=img_path,
        detector_backend='retinaface',
        enforce_detection=True
    )

    contador = 0

    for face in detecciones:

        area = face["facial_area"]

        x = area["x"]
        y = area["y"]
        w = area["w"]
        h = area["h"]

        cv2.rectangle(
            image,
            (x, y),
            (x + w, y + h),
            (0, 0, 255),
            3
        )

        contador += 1

    cv2.imwrite(output_path, image)

    return contador


def comparar_rostros(img1_path, img2_path):

    inicio = time.time()

    resultado_verificacion = DeepFace.verify(
        img1_path=img1_path,
        img2_path=img2_path,
        model_name='Facenet',
        detector_backend='retinaface',
        enforce_detection=True
    )

    embedding1 = DeepFace.represent(
        img_path=img1_path,
        model_name='Facenet',
        detector_backend='retinaface',
        enforce_detection=True
    )

    embedding2 = DeepFace.represent(
        img_path=img2_path,
        model_name='Facenet',
        detector_backend='retinaface',
        enforce_detection=True
    )

    vec1 = embedding1[0]["embedding"]
    vec2 = embedding2[0]["embedding"]

    distancia = resultado_verificacion["distance"]

    similitud = round((1 - distancia) * 100, 2)

    tiempo = round(time.time() - inicio, 4)

    hash1 = sha256_file(img1_path)
    hash2 = sha256_file(img2_path)

    boxes1 = len(embedding1)
    boxes2 = len(embedding2)

    return {
        "distancia": round(distancia, 6),
        "similitud": similitud,
        "vec1": vec1,
        "vec2": vec2,
        "boxes1": boxes1,
        "boxes2": boxes2,
        "tiempo": tiempo,
        "hash1": hash1,
        "hash2": hash2
    }


@app.route("/exportar_pdf", methods=["POST"])
def exportar_pdf():

    file_path = "reporte_biometrico.pdf"
    doc = SimpleDocTemplate(file_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>REPORTE TÉCNICO DE VALIDACIÓN BIOMÉTRICA</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Distancia Euclidiana: {distancia_global}", styles["Normal"]))
    elements.append(Paragraph(f"Porcentaje de Similitud: {similitud_global} %", styles["Normal"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Vector Imagen 1</b>", styles["Heading3"]))
    elements.append(Preformatted(str(vector1_global), styles["Code"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Vector Imagen 2</b>", styles["Heading3"]))
    elements.append(Preformatted(str(vector2_global), styles["Code"]))

    doc.build(elements)

    return send_file(file_path, as_attachment=True)


@app.route("/", methods=["GET", "POST"])
def index():

    global vector1_global, vector2_global, distancia_global, similitud_global

    if request.method == "POST":

        datos = request.form.to_dict()
        nombre_completo = datos["nombres"] + "_" + datos["apellidos"]
        correo = datos["correo"]

        certificado = generar_certificado(nombre_completo, correo)

        img1 = request.files["foto1"]
        img2 = request.files["foto2"]

        # Crear carpeta static si no existe
        if not os.path.exists("static"):
            os.makedirs("static")

        img1_path = os.path.join("static", "credencial.jpg")
        img2_path = os.path.join("static", "selfie.jpg")

        img1.save(img1_path)
        img2.save(img2_path)

        box1_path = os.path.join("static", "credencial_box.jpg")
        box2_path = os.path.join("static", "selfie_box.jpg")

        dibujar_bounding_boxes(img1_path, box1_path)
        dibujar_bounding_boxes(img2_path, box2_path)

        resultado = comparar_rostros(img1_path, img2_path)

        vector1_global = resultado["vec1"]
        vector2_global = resultado["vec2"]
        distancia_global = resultado["distancia"]
        similitud_global = resultado["similitud"]

        return render_template_string(CERT_TEMPLATE,
                                      datos=datos,
                                      resultado=resultado,
                                      umbral=UMBRAL)

    return render_template_string(REGISTRO_TEMPLATE)


# =========================
# REGISTRO
# =========================

REGISTRO_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Registro Usuario</title>
<style>
body{font-family:Segoe UI;background:#f0f0f0;padding:40px;}
.form-box{background:white;padding:30px;border-radius:8px;width:500px;margin:auto;box-shadow:0 0 10px gray;}
input{width:100%;padding:8px;margin:5px 0;}
button{padding:10px;width:100%;background:#1f2a5a;color:white;border:none;}
</style>
</head>
<body>
<div class="form-box">
<h2>Registro de Usuario</h2>
<form method="POST" enctype="multipart/form-data">
<input name="nombres" placeholder="Nombre(s)" required>
<input name="apellidos" placeholder="Apellido(s)" required>
<input name="domicilio" placeholder="Domicilio">
<input name="cp" placeholder="CP">
<input name="telefono" placeholder="Teléfono">
<input name="ocupacion" placeholder="Ocupación">
<input name="estado_civil" placeholder="Estado Civil">
<input name="correo" placeholder="Correo">
<input name="nacionalidad" placeholder="Nacionalidad">
<br>
Foto 1 (Credencial):
<input type="file" name="foto1" required>
Foto 2 (Selfie):
<input type="file" name="foto2" required>
<br><br>
<button type="submit">Validar Identidad</button>
</form>
</div>
</body>
</html>
"""

# =========================
# CERTIFICADO
# =========================

CERT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Certificado</title>
<style>
body{font-family:Segoe UI;background:#d4d0c8;margin:0;}
.window{width:1000px;margin:30px auto;background:#ece9d8;border:1px solid gray;box-shadow:3px 3px 10px gray;}
.titlebar{background:#0a246a;color:white;padding:6px;font-weight:bold;}
.tabs{background:#ece9d8;padding:5px;}
.tab{display:inline-block;background:#d4d0c8;padding:5px 15px;border:1px solid gray;border-bottom:none;margin-right:5px;cursor:pointer;}
.content{display:none;background:white;padding:20px;border-top:1px solid gray;height:500px;overflow:auto;}
</style>
<script>
function openTab(id){
    let c=document.getElementsByClassName("content");
    for(let i=0;i<c.length;i++) c[i].style.display="none";
    document.getElementById(id).style.display="block";
}
</script>
</head>
<body onload="openTab('general')">

<div class="window">
<div class="titlebar">Certificado Digital Biométrico</div>

<div class="tabs">
<div class="tab" onclick="openTab('general')">General</div>
<div class="tab" onclick="openTab('detalles')">Detalles</div>
<div class="tab" onclick="openTab('ruta')">Ruta de certificación</div>
<div class="tab" onclick="openTab('bio')">Validación biométrica</div>
</div>

<div id="general" class="content">
<h3>{{datos.nombres}} {{datos.apellidos}}</h3>
<p>Email: {{datos.correo}}</p>
<p>Nacionalidad: {{datos.nacionalidad}}</p>
<p>Válido hasta 2030</p>
</div>

<div id="detalles" class="content">
<pre>
Certificate:
   Data:
       Version: 3 (0x2)
       Serial Number: 1 (0x1)
       Signature Algorithm: sha256WithRSAEncryption
       Issuer: C=MX, O=Autoridad Certificadora Biométrica,
               CN=AC Biométrica Raíz
       Validity
           Not Before: 04 Mar 2026 GMT
           Not After : 04 Mar 2030 GMT
       Subject: CN={{datos.nombres}} {{datos.apellidos}},
                email={{datos.correo}}
       Subject Public Key Info:
           Public Key Algorithm: rsaEncryption
           RSA Public Key: (2048 bit)
           Exponent: 65537 (0x10001)
       X509v3 extensions:
           Basic Constraints: CA:FALSE
           Key Usage: Digital Signature
   Signature Algorithm: sha256WithRSAEncryption
   
</pre>
</div>

<div id="ruta" class="content">
Autoridad Raíz<br>↓<br>Autoridad Biométrica<br>↓<br>Usuario Certificado
</div>

<div id="bio" class="content">
<h3>Resultados de Validación Biométrica</h3>
<p><b>Distancia Euclidiana:</b> {{resultado.distancia}}</p>
<p><b>Porcentaje de Similitud:</b> {{resultado.similitud}} %</p>

{% if resultado.distancia < umbral %}
<p style="color:green;">✔ Identidad Coincide</p>
{% else %}
<p style="color:red;">✖ Identidad No Coincide</p>
{% endif %}

<hr>

<h3>🧬 Vector Biométrico Facial (Modelo FaceNet - 128 Dimensiones)</h3>
<p>
Representación matemática única del rostro generada por red neuronal profunda.
Cada uno de los 128 valores describe características geométricas del rostro.
</p>

<div style="display:flex; gap:40px;">
<div>
<h4>Imagen 1</h4>
<img src="{{ url_for('static', filename='credencial_box.jpg') }}" width="300"> <!-- 🔴 NUEVO -->
<div style="
background:black;
color:#00ff00;
font-size:10px;
max-height:150px;
max-width:300px;
overflow:auto;
padding:10px;
white-space:pre-wrap;
word-wrap:break-word;
border-radius:5px;
">
{{resultado.vec1}}
</div>
</div>


<div>
<h4>Imagen 2</h4>
<img src="{{ url_for('static', filename='selfie_box.jpg') }}" width="300"> <!-- 🔴 NUEVO -->
<div style="
background:black;
color:#00ff00;
font-size:10px;
max-height:150px;
max-width:300px;
overflow:auto;
padding:10px;
white-space:pre-wrap;
word-wrap:break-word;
border-radius:5px;
">
{{resultado.vec2}}
</div>
</div>
</div>

<hr>

<h4>Proceso Técnico</h4>
<pre>
1️⃣ Detección de rostros HOG
   Rostros imagen 1: {{resultado.boxes1}}
   Rostros imagen 2: {{resultado.boxes2}}

2️⃣ Extracción embeddings 128D (ResNet). 
Convierte cada rostro en un vector numérico de 128 dimensiones usando una red neuronal profunda (ResNet entrenada con millones de rostros).
Cada dimensión representa características geométricas y texturales del rostro.

3️⃣ Se calcula la distancia euclidiana:
   d = √ Σ (x_i - y_i)^2

Donde:

𝑥𝑖 es el componente del vector 1

𝑦𝑖 es el componente del vector 2

4️⃣ Comparación contra umbral ({{umbral}})
Si:

d < 0.6 → Coincidencia biométrica
d ≥ 0.6 → No coincidencia

5️⃣ Hash SHA256:
   Imagen 1: {{resultado.hash1}}
   Imagen 2: {{resultado.hash2}}
Tiempo total: {{resultado.tiempo}} segundos
</pre>

<form method="POST" action="/exportar_pdf">
<button type="submit">Exportar PDF</button>
</form>

</div>
</div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000, debug=True)