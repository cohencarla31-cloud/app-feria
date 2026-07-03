import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# Configuración de página
st.set_page_config(page_title="Punto de Venta Feria", layout="centered")

LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv" 
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=985182239#gid=985182239"

# --- 1. CARGA DE DATOS ---
@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        # encoding='utf-8' para los emojis
        df = pd.read_csv(LINK_CSV_BALANCE, encoding='utf-8')
        df.columns = df.columns.str.strip()
        df = df.dropna(subset=['Producto'])
        
        # Búsqueda flexible de columna Stock
        col_stock = next((col for col in df.columns if "Stock" in col), None)
        
        productos = df['Producto'].astype(str).tolist()
        precios = dict(zip(df['Producto'], pd.to_numeric(df['Precio'], errors='coerce').fillna(0)))
        
        if col_stock:
            stock = dict(zip(df['Producto'], pd.to_numeric(df[col_stock], errors='coerce').fillna(99999)))
        else:
            stock = {p: 99999 for p in productos}
            
        return productos, precios, stock
    except Exception as e:
        st.error(f"Error cargando inventario: {e}")
        return [], {}, {}

PRODUCTOS, PRECIOS, STOCK_DISPONIBLE = cargar_inventario()

# --- 2. ESTADO DE SESIÓN ---
if 'pedido_confirmado' not in st.session_state:
    st.session_state.pedido_confirmado = None

# --- 3. INTERFAZ ---
st.title("🛒 Toma de Pedidos")
vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
cliente = st.text_input("Nombre del Cliente:")

pedidos = {}
total_general = 0.0

for p in PRODUCTOS:
    cant = st.number_input(f"{p}", min_value=0.0, step=0.5, key=p)
    if cant > 0:
        sub = cant * PRECIOS.get(p, 0)
        pedidos[p] = {"cant": cant, "sub": sub}
        total_general += sub

st.write(f"### Total: ${total_general}")

# --- 4. ACCIONES ---
if st.button("📝 Enviar Venta"):
    if vendedor == "Seleccionar..." or not cliente or total_general == 0:
        st.warning("Completa los datos del pedido.")
    else:
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            cred_dict = json.loads(st.secrets["llave_google"])
            creds = Credentials.from_service_account_info(cred_dict, scopes=scopes)
            gc = gspread.authorize(creds)
            sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
            
            for p, d in pedidos.items():
                sheet.append_row([str(date.today()), str(datetime.now().time()), vendedor, cliente, p, d['cant'], d['sub']])
            
            st.session_state.pedido_confirmado = True
            st.session_state.datos_pedido = (vendedor, cliente, pedidos, total_general)
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

# Botón de WhatsApp persistente
if st.session_state.pedido_confirmado:
    v, c, peds, total = st.session_state.datos_pedido
    caja = st.selectbox("Selecciona a quién enviar:", ["Caja 1", "Caja 2"])
    num = "59893343092" if caja == "Caja 1" else "59893343092"
    
    msg = f"Pedido de {c}\n" + "".join([f"{prod}: {d['cant']} x ${d['sub']}\n" for prod, d in peds.items()])
    st.link_button("📲 Enviar WhatsApp", f"https://wa.me/{num}?text={urllib.parse.quote(msg)}")
    
    if st.button("Nuevo Pedido"):
        st.session_state.pedido_confirmado = None
        st.rerun()
