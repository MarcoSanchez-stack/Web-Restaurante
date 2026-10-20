import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DB_NAME = "restaurante_costos.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. Tabla de Ingredientes / Insumos
    c.execute('''CREATE TABLE IF NOT EXISTS ingredientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        unidad TEXT NOT NULL,
        costo_unitario REAL NOT NULL
    )''')
    
    # 2. Tabla de Platos
    c.execute('''CREATE TABLE IF NOT EXISTS platos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        precio_venta REAL NOT NULL
    )''')
    
    # 3. Relación Plato - Ingredientes (Receta)
    c.execute('''CREATE TABLE IF NOT EXISTS plato_ingredientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plato_id INTEGER,
        ingrediente_id INTEGER,
        cantidad REAL NOT NULL,
        FOREIGN KEY(plato_id) REFERENCES platos(id),
        FOREIGN KEY(ingrediente_id) REFERENCES ingredientes(id)
    )''')
    
    # 4. Tabla de Adiciones / Extras
    c.execute('''CREATE TABLE IF NOT EXISTS adiciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        costo_inversion REAL NOT NULL,
        precio_extra REAL NOT NULL
    )''')
    
    # 5. Tabla de Registro de Ventas
    c.execute('''CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        plato_id INTEGER,
        cantidad INTEGER NOT NULL,
        adiciones_info TEXT,
        inversion_total REAL NOT NULL,
        venta_total REAL NOT NULL,
        FOREIGN KEY(plato_id) REFERENCES platos(id)
    )''')
    
    # Precargar los platos principales si la base de datos es nueva
    c.execute("SELECT COUNT(*) FROM platos")
    if c.fetchone()[0] == 0:
        platos_iniciales = [
            ("Lasaña de pollo", 25000),
            ("Sándwich de Pulled Pork (con papas casco o francesa)", 28000),
            ("Pechuga con ensalada de pepino", 24000),
            ("Costillas BBQ con papas casco a las finas hierbas", 35000)
        ]
        c.executemany("INSERT INTO platos (nombre, precio_venta) VALUES (?, ?)", platos_iniciales)
        
        adiciones_iniciales = [
            ("Porción extra de papas (casco/francesa)", 2500, 6000),
            ("Queso gratinado extra", 1800, 4500),
            ("Salsa BBQ extra", 500, 2000)
        ]
        c.executemany("INSERT INTO adiciones (nombre, costo_inversion, precio_extra) VALUES (?, ?, ?)", adiciones_iniciales)
        
    conn.commit()
    conn.close()

# --- RUTA PRINCIPAL ---

@app.route("/")
def index():
    mes_actual = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    conn = get_db()
    c = conn.cursor()

    ingredientes = c.execute("SELECT * FROM ingredientes").fetchall()
    adiciones = c.execute("SELECT * FROM adiciones").fetchall()

    # Calcular costo y ganancia por cada plato
    platos_raw = c.execute("SELECT * FROM platos").fetchall()
    platos = []
    for p in platos_raw:
        receta = c.execute('''
            SELECT pi.id as rel_id, i.nombre, pi.cantidad, i.unidad, (pi.cantidad * i.costo_unitario) as subtotal
            FROM plato_ingredientes pi
            JOIN ingredientes i ON pi.ingrediente_id = i.id
            WHERE pi.plato_id = ?
        ''', (p["id"],)).fetchall()
        
        costo_plato = sum(r["subtotal"] for r in receta)
        detalle = ", ".join([f"{r['nombre']} ({r['cantidad']} {r['unidad']})" for r in receta])
        
        platos.append({
            "id": p["id"],
            "nombre": p["nombre"],
            "precio_venta": p["precio_venta"],
            "costo_plato": costo_plato,
            "ganancia_plato": p["precio_venta"] - costo_plato,
            "detalle_ingredientes": detalle
        })

    # Historial de ventas del mes seleccionado
    historial_ventas = c.execute('''
        SELECT v.*, COALESCE(p.nombre, 'Plato eliminado') as plato_nombre
        FROM ventas v
        LEFT JOIN platos p ON v.plato_id = p.id
        WHERE v.fecha LIKE ?
        ORDER BY v.id DESC
    ''', (f"{mes_actual}%",)).fetchall()

    # Cálculos globales del mes
    platos_vendidos = sum(v["cantidad"] for v in historial_ventas)
    inversion_mes = sum(v["inversion_total"] for v in historial_ventas)
    venta_neta_mes = sum(v["venta_total"] for v in historial_ventas)
    ganancia_bruta = venta_neta_mes - inversion_mes

    # Regla de comisión: 10% hasta 999.999 COP, 20% si supera ese valor
    if venta_neta_mes > 999999:
        porcentaje_comision = 20
        pago_vendedor = venta_neta_mes * 0.20
    else:
        porcentaje_comision = 10
        pago_vendedor = venta_neta_mes * 0.10

    resumen = {
        "platos_vendidos": platos_vendidos,
        "inversion": inversion_mes,
        "venta_neta": venta_neta_mes,
        "ganancia_bruta": ganancia_bruta,
        "porcentaje_comision": porcentaje_comision,
        "pago_vendedor": pago_vendedor,
        "ganancia_final": ganancia_bruta - pago_vendedor
    }

    conn.close()
    
    return render_template(
        "index.html",
        mes_actual=mes_actual,
        ingredientes=ingredientes,
        adiciones=adiciones,
        platos=platos,
        historial_ventas=historial_ventas,
        resumen=resumen
    )

# --- RUTAS PARA AGREGAR DATOS ---

@app.route("/agregar_ingrediente", methods=["POST"])
def agregar_ingrediente():
    conn = get_db()
    conn.execute("INSERT INTO ingredientes (nombre, unidad, costo_unitario) VALUES (?, ?, ?)",
                 (request.form["nombre"], request.form["unidad"], float(request.form["costo"])))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/agregar_adicion", methods=["POST"])
def agregar_adicion():
    conn = get_db()
    conn.execute("INSERT INTO adiciones (nombre, costo_inversion, precio_extra) VALUES (?, ?, ?)",
                 (request.form["nombre"], float(request.form["costo_inversion"]), float(request.form["precio_extra"])))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/agregar_plato", methods=["POST"])
def agregar_plato():
    conn = get_db()
    conn.execute("INSERT INTO platos (nombre, precio_venta) VALUES (?, ?)",
                 (request.form["nombre"], float(request.form["precio_venta"])))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/asignar_ingrediente", methods=["POST"])
def asignar_ingrediente():
    conn = get_db()
    conn.execute("INSERT INTO plato_ingredientes (plato_id, ingrediente_id, cantidad) VALUES (?, ?, ?)",
                 (int(request.form["plato_id"]), int(request.form["ingrediente_id"]), float(request.form["cantidad"])))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/registrar_venta", methods=["POST"])
def registrar_venta():
    plato_id = int(request.form["plato_id"])
    cantidad = int(request.form["cantidad"])
    adiciones_ids = request.form.getlist("adiciones")
    
    conn = get_db()
    c = conn.cursor()
    
    plato = c.execute("SELECT * FROM platos WHERE id = ?", (plato_id,)).fetchone()
    costo_receta = c.execute('''
        SELECT SUM(pi.cantidad * i.costo_unitario) as total
        FROM plato_ingredientes pi
        JOIN ingredientes i ON pi.ingrediente_id = i.id
        WHERE pi.plato_id = ?
    ''', (plato_id,)).fetchone()["total"] or 0.0

    costo_adiciones = 0.0
    precio_adiciones = 0.0
    nombres_adiciones = []

    for aid in adiciones_ids:
        ad = c.execute("SELECT * FROM adiciones WHERE id = ?", (int(aid),)).fetchone()
        if ad:
            costo_adiciones += ad["costo_inversion"]
            precio_adiciones += ad["precio_extra"]
            nombres_adiciones.append(ad["nombre"])

    inversion_total = (costo_receta * cantidad) + costo_adiciones
    venta_total = (plato["precio_venta"] * cantidad) + precio_adiciones
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute('''INSERT INTO ventas (fecha, plato_id, cantidad, adiciones_info, inversion_total, venta_total)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (fecha_actual, plato_id, cantidad, ", ".join(nombres_adiciones), inversion_total, venta_total))
    
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# --- RUTAS PARA ELIMINAR / LIMPIAR REGISTROS ---

@app.route("/eliminar_venta/<int:venta_id>", methods=["POST"])
def eliminar_venta(venta_id):
    conn = get_db()
    conn.execute("DELETE FROM ventas WHERE id = ?", (venta_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/limpiar_ventas", methods=["POST"])
def limpiar_ventas():
    conn = get_db()
    conn.execute("DELETE FROM ventas")
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/limpiar_receta/<int:plato_id>", methods=["POST"])
def limpiar_receta(plato_id):
    conn = get_db()
    conn.execute("DELETE FROM plato_ingredientes WHERE plato_id = ?", (plato_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/eliminar_plato/<int:plato_id>", methods=["POST"])
def eliminar_plato(plato_id):
    conn = get_db()
    conn.execute("DELETE FROM plato_ingredientes WHERE plato_id = ?", (plato_id,))
    conn.execute("DELETE FROM platos WHERE id = ?", (plato_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/eliminar_ingrediente/<int:ingrediente_id>", methods=["POST"])
def eliminar_ingrediente(ingrediente_id):
    conn = get_db()
    conn.execute("DELETE FROM plato_ingredientes WHERE ingrediente_id = ?", (ingrediente_id,))
    conn.execute("DELETE FROM ingredientes WHERE id = ?", (ingrediente_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/eliminar_adicion/<int:adicion_id>", methods=["POST"])
def eliminar_adicion(adicion_id):
    conn = get_db()
    conn.execute("DELETE FROM adiciones WHERE id = ?", (adicion_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    print("Servidor iniciado en: http://127.0.0.1:5000")
    app.run(debug=True)

