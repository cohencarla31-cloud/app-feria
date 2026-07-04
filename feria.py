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
st.set_page_config(page_title="Punto de Venta Feria", layout="centered")

# IMPORTANTE: Reemplaza con tus enlaces reales
LINK_CSV_BALANCE = "TU_ENLACE_CSV_BALANCE" 
LINK_NORMAL_DEL_EXCEL = "TU_ENLACE_EDICION_EXCEL"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        df = pd.read_csv(LINK_CSV_BALANCE, encoding='utf-8')
        df.columns = df.columns.str.strip()
        
        # Unir Emoji y Producto si están separados
        if 'Emoji' in df.columns:
            df['Prod_Full'] = df['Emoji'].astype(str) + " " + df['Producto'].astype(str)
        else:
            df['Prod_Full'] = df['Producto'].astype(str)
            
        precios = dict(zip(df['Prod_Full'], pd.to_numeric(df['Precio'], errors='coerce').fillna(0)))
        
        # Búsqueda flexible del stock
        col_stock = next((c for c in df.columns if "Stock" in c), None)
        stock = dict(zip(df['Prod_Full'], pd.to_numeric(df[col_stock], errors='coerce').fillna(99999))) if col_stock else {}
        
        return df['Prod_Full'].tolist(), precios, stock
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return [], {}, {}

PRODUCTOS, PRECIOS, STOCK = cargar_inventario()

# ==========================================
# 2. INTERFAZ Y DATOS DEL CLIENTE
# ==========================================
st.title("🛒 Toma de Pedidos")

col_datos1, col_datos2 = st.columns(2)
with col_datos1:
    vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
    cliente = st.text_input("Nombre del Cliente:")
with col_datos2:
    caja = st.selectbox("¿A qué Caja se envía?", ["Caja 1", "Caja 2"])
    tel_cliente = st.text_input("Celular del Cliente (Ej: 598...):")

st.divider()

# ==========================================
# 3. LISTADO DE PRODUCTOS (BALANZA INTELIGENTE)
# ==========================================
pedidos = {}
total_general = 0.0

st.write("### Productos")
for p in PRODUCTOS:
    cant = st.number_input(f"{p}", min_value=0.0, step=0.05, key=p)
    
    if cant > 0:
        # Traductor de Balanza: Por defecto Kg, a menos que diga "Unidad" o "(U)"
        if "unidad" in p.lower() or "(u)" in p.lower():
            st.caption(f"📦 *Entendí:* **{int(cant)} unidad(es)**")
        else:
            kilos = int(cant)
            gramos = int(round((cant - kilos) * 1000))
            if kilos > 0 and gramos > 0:
                st.caption(f"⚖️ *Entendí:* **{kilos} Kilo(s) y {gramos} gramos**")
            elif kilos > 0 and gramos == 0:
                st.caption(f"⚖️ *Entendí:* **{kilos} Kilo(s) exactos**")
            else:
                st.caption(f"⚖️ *Entendí:* **{gramos} gramos**")
            
        sub = cant * PRECIOS.get(p, 0)
        pedidos[p] = {"cant": cant, "sub": sub}
        total_general += sub

st.divider()

# ==========================================
# 4. DESCUENTOS Y TOTAL
# ==========================================
col_desc, col_tot = st.columns(2)
with col_desc:
    descuento_porcentaje = st.selectbox("¿Aplicar Descuento?", [0, 10, 15, 20, 25, 30])
with col_tot:
    monto_descuento = total_general * (descuento_porcentaje / 100)
    total_final = total_general - monto_descuento
    st.write(f"### TOTAL: ${total_final:,.1f}")

st.divider()

# ==========================================
# 5. BOTONES DE ACCIÓN Y REGISTRO
# ==========================================
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🧹 Limpiar Pedido"):
        st.rerun()

with col_btn2:
    if st.button("📝 Enviar Venta"):
        if vendedor == "Seleccionar..." or not cliente or total_final == 0:
            st.warning("⚠️ Falta completar Vendedor, Cliente o ingresar productos.")
        else:
            try:
                # 1. Guardar en Google Sheets (Con los permisos corregidos)
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]), scopes=scopes)
                gc = gspread.authorize(creds)
                sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
                
                for p, d in pedidos.items():
                    sheet.append_row([str(date.today()), str(datetime.now().time()), vendedor, cliente, p, d['cant'], d['sub']])
                
                st.success("✅ Venta registrada correctamente en el Excel.")
                
                # 2. Armar el mensaje para la CAJA
                msg_caja = f"🛒 NUEVO PEDIDO\n👤 Vendedor: {vendedor}\n🗣️ Cliente: {cliente}\n-------------------\n"
                for p, d in pedidos.items():
                    msg_caja += f" • {d['cant']} x {p} = ${d['sub']:,.1f}\n"
                
                msg_caja += f"-------------------\n"
                if descuento_porcentaje > 0:
                    msg_caja += f"Subtotal: ${total_general:,.1f}\n"
                    msg_caja += f"⚠️ DESCUENTO ({descuento_porcentaje}%): -${monto_descuento:,.1f}\n"
                    msg_caja += f"-------------------\n"
                msg_caja += f"💰 TOTAL A COBRAR: ${total_final:,.1f}"
                
                num_caja = "59893343092" if caja == "Caja 1" else "59899111222"
                url_caja = f"https://wa.me/{num_caja}?text={urllib.parse.quote(msg_caja)}"
                
                # 3. Armar el mensaje para el CLIENTE
                msg_cliente = f"👋 Hola {cliente}, aquí tienes el detalle de tu compra en la Feria:\n-------------------\n"
                for p, d in pedidos.items():
                    msg_cliente += f" • {d['cant']} x {p} = ${d['sub']:,.1f}\n"
                
                if descuento_porcentaje > 0:
                    msg_cliente += f"-------------------\n"
                    msg_cliente += f"Subtotal: ${total_general:,.1f}\n"
                    msg_cliente += f"🎁 Tu Descuento: -${monto_descuento:,.1f}\n"
                
                msg_cliente += f"-------------------\n💰 TOTAL: ${total_final:,.1f}\n\n¡Muchas gracias por elegirnos! 🍎"
                
                # Formatear el número del cliente (quitar espacios si los puso)
                num_cliente = tel_cliente.replace(" ", "").replace("+", "")
                url_cliente = f"https://wa.me/{num_cliente}?text={urllib.parse.quote(msg_cliente)}"
                
                # 4. Mostrar los botones de WhatsApp
                st.info("👇 Haz clic en los botones para enviar los mensajes:")
                st.link_button(f"📲 Enviar Resumen a {caja}", url_caja)
                
                if tel_cliente:
                    st.link_button("📲 Enviar Ticket al Cliente", url_cliente)
                else:
                    st.caption("*(No se ingresó celular del cliente para enviar su ticket)*")
                
            except Exception as e:
                st.error(f"❌ Error al registrar: {e}")
