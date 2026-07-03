import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

st.set_page_config(page_title="Punto de Venta Feria", layout="centered")

# --- CONFIGURACIÓN ---
LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv" 
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=832040050#gid=832040050"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        df = pd.read_csv(LINK_CSV_BALANCE, encoding='utf-8')
        df.columns = df.columns.str.strip()
        
        # Procesamos emojis: si existe columna Emoji, la unimos. Si no, tomamos Producto solo.
        if 'Emoji' in df.columns:
            df['Prod_Full'] = df['Emoji'].astype(str) + " " + df['Producto'].astype(str)
        else:
            df['Prod_Full'] = df['Producto'].astype(str)
            
        precios = dict(zip(df['Prod_Full'], pd.to_numeric(df['Precio'], errors='coerce').fillna(0)))
        
        col_stock = next((c for c in df.columns if "Stock" in c), None)
        stock = dict(zip(df['Prod_Full'], pd.to_numeric(df[col_stock], errors='coerce').fillna(99999))) if col_stock else {}
        
        return df['Prod_Full'].tolist(), precios, stock
    except Exception as e:
        st.error(f"Error carga: {e}")
        return [], {}, {}

PRODUCTOS, PRECIOS, STOCK = cargar_inventario()

# --- INTERFAZ ---
st.title("🛒 Toma de Pedidos")
vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
cliente = st.text_input("Nombre del Cliente:")
tel_cliente = st.text_input("Teléfono del Cliente (ej: 598...):")

pedidos = {}
total_general = 0.0

for p in PRODUCTOS:
    cant = st.number_input(f"{p}", min_value=0.0, step=0.5, key=p)
    if cant > 0:
        sub = cant * PRECIOS.get(p, 0)
        pedidos[p] = {"cant": cant, "sub": sub}
        total_general += sub

st.write(f"### TOTAL A COBRAR: ${total_general}")

# --- ACCIONES ---
col1, col2 = st.columns(2)
with col1:
    if st.button("🧹 Limpiar"):
        st.rerun()

with col2:
    if st.button("📝 Enviar Venta"):
        if vendedor == "Seleccionar..." or not cliente or total_general == 0:
            st.warning("Completa los datos.")
        else:
            try:
                # Registro en Sheets
                creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]))
                gc = gspread.authorize(creds)
                sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
                for p, d in pedidos.items():
                    sheet.append_row([str(date.today()), str(datetime.now().time()), vendedor, cliente, p, d['cant'], d['sub']])
                
                # Mensaje Formato image_f849cd_2.png
                msg = f"NUEVO PEDIDO\nVendedor: {vendedor}\nCliente: {cliente}\n-------------------\n"
                for p, d in pedidos.items():
                    msg += f" • {d['cant']} x {p} = ${d['sub']}\n"
                msg += f"-------------------\nTOTAL A COBRAR: ${total_general}"
                
                # Botón WhatsApp para el cobrador
                caja = st.selectbox("Enviar a:", ["Caja 1", "Caja 2"])
                num = "59893343092" if caja == "Caja 1" else "59893343092"
                st.link_button("📲 Enviar a Caja", f"https://wa.me/{num}?text={urllib.parse.quote(msg)}")
                
                st.success("✅ Venta registrada.")
            except Exception as e:
                st.error(f"Error: {e}")
