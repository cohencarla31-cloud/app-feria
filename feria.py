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

# IMPORTANTE: Reemplaza con tus enlaces publicados en formato CSV
LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv"
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=832040050#gid=832040050"

# --- REEMPLAZA TU FUNCIÓN CARGAR_INVENTARIO POR ESTA ---

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        df = pd.read_csv(LINK_CSV_BALANCE)
        df.columns = df.columns.str.strip() # Limpieza de nombres de columna
        df = df.dropna(subset=['Producto'])
        
        # Limpieza de precios: forzamos a número
        if df['Precio'].dtype == 'object':
            df['Precio'] = df['Precio'].replace(r'[\$,]', '', regex=True)
        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0.0)
        
        # Limpieza de stock
        if 'Stock Final' in df.columns:
            df['Stock Final'] = pd.to_numeric(df['Stock Final'], errors='coerce').fillna(99999)
        else:
            df['Stock Final'] = 99999
            
        productos = df['Producto'].tolist()
        precios = dict(zip(df['Producto'], df['Precio']))
        stock_final = dict(zip(df['Producto'], df['Stock Final']))
            
        return productos, precios, stock_final
    except Exception as e:
        st.error(f"Error al cargar: {e}")
        # Retornamos valores vacíos seguros para que la app no se rompa
        return [], {}, {}

# --- LLAMADA SEGURA ---
PRODUCTOS, PRECIOS, STOCK_DISPONIBLE = cargar_inventario()

# Verificación de seguridad antes del bucle
if not PRODUCTOS:
    st.warning("No se pudieron cargar productos. Verifica el enlace al CSV.")
    st.stop() # Detiene la ejecución aquí si no hay productos
# ==========================================
# 2. INTERFAZ
# ==========================================
st.title("🛒 Toma de Pedidos")

col_vendedor, col_cliente = st.columns(2)
with col_vendedor:
    vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
with col_cliente:
    cliente = st.text_input("Nombre del Cliente:")
    tel_cliente = st.text_input("Teléfono del Cliente (con código de país, ej: 598...):")

st.divider()

# ==========================================
# 3. LISTADO DE PRODUCTOS
# ==========================================
pedidos = {}
total_general = 0.0

for producto in PRODUCTOS:
    precio = PRECIOS[producto]
    stock_actual = STOCK_DISPONIBLE.get(producto, 99999)
    
    col1, col2 = st.columns([3, 2])
    with col1:
        st.write(f"**{producto}**")
        if stock_actual < 90000:
            st.caption(f"Precio: ${precio} | Disponible: {stock_actual}")
    with col2:
        max_val = float(stock_actual) if stock_actual < 90000 else 1000.0
        cantidad = st.number_input("Cant.", min_value=0.0, max_value=max_val, step=0.5, key=producto)
        
        if cantidad > 0:
            subtotal = cantidad * precio
            pedidos[producto] = {"cantidad": cantidad, "subtotal": subtotal}
            total_general += subtotal

st.divider()
st.write(f"### Total del Pedido: **${total_general}**")

# ==========================================
# 4. BOTONES DE ACCIÓN
# ==========================================
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🧹 Limpiar Pedido"):
        st.rerun()

with col_btn2:
    if st.button("📝 Enviar Venta"):
        if vendedor == "Seleccionar..." or not cliente or total_general == 0:
            st.warning("⚠️ Completa vendedor, cliente y productos.")
        else:
            # 1. Selector de destino (Cobradores)
            CAJAS = {
                "Caja 1 (Principal)": "59893343092", 
                "Caja 2 (Secundaria)": "5492615437545"
            }
            caja_elegida = st.selectbox("¿A qué cobrador enviar el resumen?", list(CAJAS.keys()))
            numero_destino = CAJAS[caja_elegida]

            # 2. Registro en Google Sheets
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
                
                st.success("✅ ¡Venta registrada!")
                
                # 3. Generar Link de WhatsApp para el cobrador elegido
                msg = f"🛒 NUEVO PEDIDO\nVendedor: {vendedor}\nCliente: {cliente}\n-------------------\n"
                for p, d in pedidos.items():
                    msg += f"{p}: {d['cantidad']} x ${d['subtotal']}\n"
                msg += f"-------------------\nTOTAL: ${total_general}"
                
                url_wa = f"https://wa.me/{numero_destino}?text={urllib.parse.quote(msg)}"
                st.link_button(f"📲 Enviar WhatsApp a {caja_elegida}", url_wa)
                
            except Exception as e:
                st.error(f"❌ Error al registrar: {e}")
