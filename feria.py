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

LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv"
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=832040050#gid=832040050"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        df = pd.read_csv(LINK_CSV_BALANCE)
        df = df.dropna(subset=['Producto'])
        
        # Flexibilidad: si no existe la columna de stock, asignamos un valor muy alto (infinito)
        if 'Stock Final' in df.columns:
            stock_final = dict(zip(df['Producto'], df['Stock Final']))
        else:
            # Si no hay control de stock, cada producto tiene "stock infinito" (99999)
            stock_final = {p: 99999 for p in df['Producto']}
            
        productos = df['Producto'].tolist()
        precios = dict(zip(df['Producto'], df['Precio']))
        
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
    
    col1, col2 = st.columns([3, 2])
    with col1:
        st.write(f"**{producto}**")
        # Solo mostramos el stock si es un número razonable (menos de 99999)
        if stock_actual < 90000:
            st.caption(f"Precio: ${precio} | Stock: {stock_actual}")
        else:
            st.caption(f"Precio: ${precio}")
            
    with col2:
        # El límite es el stock real o infinito
        max_val = float(stock_actual) if stock_actual < 90000 else 1000.0
        cantidad = st.number_input("Cant.", min_value=0.0, max_value=max_val, step=0.5, key=producto)
        
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
        # ... (Tu lógica de envío sigue igual)
        st.success("¡Venta procesada!")
