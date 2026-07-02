import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. SISTEMA DE SUSCRIPCIÓN
# ==========================================
FECHA_VENCIMIENTO = date(2026, 8, 2) 
hoy = date.today()

st.set_page_config(page_title="Punto de Venta Feria", page_icon="🛒", layout="centered")

if hoy > FECHA_VENCIMIENTO:
    st.error("⚠️ La licencia de la aplicación ha expirado.")
    st.stop()

# ==========================================
# 2. CONEXIÓN A GOOGLE SHEETS
# ==========================================
LINK_CSV_GOOGLE_SHEETS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv"
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=0#gid=0"

@st.cache_data(ttl=30)
def cargar_inventario(url):
    try:
        df = pd.read_csv(url)
        precios = dict(zip(df['Producto'], df['Precio']))
        stock = dict(zip(df['Producto'], df['Stock']))
        return precios, stock
    except:
        return {"Manzana": 150.0}, {"Manzana": 100.0}

PRODUCTOS, STOCK_DISPONIBLE = cargar_inventario(LINK_CSV_GOOGLE_SHEETS)

# ==========================================
# 3. INTERFAZ: DATOS GENERALES
# ==========================================
st.title("🛒 Toma de Pedidos")

col_vendedor, col_cliente = st.columns(2)
with col_vendedor:
    vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
with col_cliente:
    cliente = st.text_input("Nombre del Cliente:")

st.divider()

# ==========================================
# 4. FORMULARIO DE PRODUCTOS
# ==========================================
st.subheader("Frutas y Verduras")
pedidos = {}
total_general = 0.0

for producto, precio in PRODUCTOS.items():
    stock_actual = STOCK_DISPONIBLE.get(producto, 0.0)
    
    col1, col2 = st.columns([3, 2])
    with col1:
        st.write(f"**{producto}**")
        st.caption(f"Precio: ${precio} | Disponible: {stock_actual} kg/un.")
    with col2:
        cantidad = st.number_input("Cant.", min_value=0.0, max_value=float(stock_actual), step=0.5, key=producto, label_visibility="collapsed")
        
        if cantidad > 0:
            subtotal = cantidad * precio
            pedidos[producto] = {"cantidad": cantidad, "subtotal": subtotal}
            total_general += subtotal

st.divider()
st.write(f"### Total del Pedido: **${total_general}**")

# ==========================================
# 5. ENVÍO Y GUARDADO EN BASE DE DATOS
# ==========================================
CAJAS = {"Caja 1 (Principal)": "59893343092", "Caja 2 (Secundaria)": "5492615437545"}

st.subheader("Enviar Pedido")
caja_elegida = st.selectbox("¿A qué línea enviar?", list(CAJAS.keys()))
numero_destino = CAJAS[caja_elegida]

if st.button("📝 Enviar y Guardar Venta", use_container_width=True):
    if vendedor == "Seleccionar...":
        st.error("Por favor, selecciona el nombre del Vendedor.")
    elif not cliente:
        st.error("Por favor, ingresa el nombre del Cliente.")
    elif total_general == 0:
        st.warning("No has ingresado ningún producto al pedido.")
    else:
        # --- 1. GUARDAR MAGÍCAMENTE EN EL EXCEL ---
        try:
            # Conectar usando el robot
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_file("credenciales.json", scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Abrir el archivo y la pestaña
            archivo_excel = gc.open_by_url(LINK_NORMAL_DEL_EXCEL)
            pestana_ventas = archivo_excel.worksheet("Registro de Ventas")
            
            # Sacar la hora exacta
            fecha_actual = date.today().strftime("%d/%m/%Y")
            hora_actual = datetime.now().strftime("%H:%M:%S")
            
            # Guardar cada producto vendido como una fila nueva
            for p, datos in pedidos.items():
                fila = [fecha_actual, hora_actual, vendedor, cliente, p, datos['cantidad'], datos['subtotal']]
                pestana_ventas.append_row(fila)
            
            st.success("✅ Venta registrada correctamente en el Excel.")
            
        except Exception as e:
            st.error(f"⚠️ Error al guardar en el Excel: {e}")

        # --- 2. ABRIR WHATSAPP ---
        mensaje = f"NUEVO PEDIDO\nVendedor: {vendedor}\nCliente: {cliente}\n-------------------\n"
        for p, datos in pedidos.items():
            mensaje += f"- {datos['cantidad']} x {p} = ${datos['subtotal']}\n"
        mensaje += f"-------------------\nTOTAL A COBRAR: ${total_general}"

        mensaje_codificado = urllib.parse.quote(mensaje.encode('utf-8'))
        link_whatsapp = f"https://wa.me/{numero_destino}?text={mensaje_codificado}"
        
        st.link_button(f"📲 Enviar WhatsApp a la {caja_elegida}", link_whatsapp, use_container_width=True)