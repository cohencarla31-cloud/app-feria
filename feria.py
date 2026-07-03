import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(page_title="Punto de Venta Feria", page_icon="🛒", layout="centered")

# Reemplaza con tus enlaces publicados a la web (Archivo -> Compartir -> Publicar en la web -> CSV)
LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv"
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=0#gid=0"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        # La app solo lee la pestaña "Balance" donde ya está todo calculado
        df = pd.read_csv(LINK_CSV_BALANCE)
        
        # Filtramos filas vacías
        df = df.dropna(subset=['Producto'])
        
        productos = df['Producto'].tolist()
        precios = dict(zip(df['Producto'], df['Precio']))
        stock_final = dict(zip(df['Producto'], df['Stock Final']))
        
        return productos, precios, stock_final
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return [], {}, {}

PRODUCTOS, PRECIOS, STOCK_DISPONIBLE = cargar_inventario()

# ==========================================
# 2. INTERFAZ
# ==========================================
st.title("🛒 Toma de Pedidos")
col_vendedor, col_cliente = st.columns(2)
with col_vendedor:
    vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
with col_cliente:
    cliente = st.text_input("Nombre del Cliente:")

st.divider()

# ==========================================
# 3. LISTADO DE PRODUCTOS
# ==========================================
st.subheader("Disponibles")
pedidos = {}
total_general = 0.0

for producto in PRODUCTOS:
    precio = PRECIOS[producto]
    stock_actual = STOCK_DISPONIBLE.get(producto, 0.0)
    
    # Mostrar producto con emoji (si el nombre en Balance lo incluye)
    col1, col2 = st.columns([3, 2])
    with col1:
        st.write(f"**{producto}**")
        st.caption(f"Precio: ${precio} | Stock: {stock_actual}")
    with col2:
        cantidad = st.number_input("Cant.", min_value=0.0, max_value=float(stock_actual), step=0.5, key=producto)
        
        if cantidad > 0:
            subtotal = cantidad * precio
            pedidos[producto] = {"cantidad": cantidad, "subtotal": subtotal}
            total_general += subtotal

st.divider()
st.write(f"### Total: **${total_general}**")

# ==========================================
# 4. BOTONES
# ==========================================
col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    if st.button("🧹 Limpiar"):
        st.rerun()

with col_btn2:
    if st.button("📝 Enviar"):
        if vendedor == "Seleccionar..." or not cliente or total_general == 0:
            st.warning("Completa vendedor, cliente y productos.")
        else:
            # GUARDAR EN EXCEL
            try:
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                cred_dict = json.loads(st.secrets["llave_google"])
                creds = Credentials.from_service_account_info(cred_dict, scopes=scopes)
                gc = gspread.authorize(creds)
                sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
                
                fecha = date.today().strftime("%d/%m/%Y")
                hora = datetime.now().strftime("%H:%M:%S")
                for p, d in pedidos.items():
                    sheet.append_row([fecha, hora, vendedor, cliente, p, d['cantidad'], d['subtotal']])
                
                st.success("¡Venta registrada!")
                
                # ENLACE WHATSAPP
                msg = f"Pedido de {cliente}\nVendedor: {vendedor}\n"
                for p, d in pedidos.items():
                    msg += f"{p}: {d['cantidad']} x ${d['subtotal']}\n"
                msg += f"TOTAL: ${total_general}"
                
                url_wa = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                st.link_button("📲 Enviar WhatsApp", url_wa)
            except Exception as e:
                st.error(f"Error: {e}")
