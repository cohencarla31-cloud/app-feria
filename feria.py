import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 1. CONFIGURACIÓN INICIAL (UTC-3 URUGUAY)
# ==========================================
st.set_page_config(page_title="App Ferias", layout="centered", initial_sidebar_state="collapsed")
TZ_UY = timezone(timedelta(hours=-3))

# 🔥 AQUÍ PONES EL LINK DE TU EXCEL MASTER
LINK_MASTER_SHEET = "https://docs.google.com/spreadsheets/d/1CEuvlAwExOf1FS_ZYeFYw205aoVePb8SCmmLjUJTg-w/edit?gid=0#gid=0"

# ==========================================
# 2. CONEXIÓN A GOOGLE Y LECTURA DE MASTER
# ==========================================
@st.cache_resource
def conectar_google():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]), scopes=scopes)
    return gspread.authorize(creds)

def obtener_datos_cliente(codigo_empresa):
    try:
        gc = conectar_google()
        master = gc.open_by_url(LINK_MASTER_SHEET).sheet1
        registros = master.get_all_records()
        for fila in registros:
            if str(fila.get("Codigo_Empresa", "")).upper() == codigo_empresa.upper():
                if fila.get("Estado", "") == "Activo":
                    return fila.get("Link_Excel")
                else:
                    return "SUSPENDIDO"
    except Exception as e:
        st.error(f"Error al conectar con la base maestra: {e}")
    return None

# ==========================================
# 3. MODO TIENDA (CATÁLOGO DIGITAL PARA EL CLIENTE FINAL)
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel and link_excel != "SUSPENDIDO":
        try:
            # Leemos configuración y productos de la feria
            df_conf = pd.read_excel(link_excel, sheet_name="Configuracion", header=None, dtype=str)
            config = dict(zip(df_conf[0], df_conf[1]))
            nombre_feria = config.get("Nombre_Empresa", "Nuestra Feria")
            
            df_prod = pd.read_excel(link_excel, sheet_name="Productos", dtype=str).fillna("")
            df_prod['Precio'] = pd.to_numeric(df_prod['Precio'], errors='coerce').fillna(0)
            df_prod['Descuento'] = pd.to_numeric(df_prod['Descuento'], errors='coerce').fillna(0)
            
            st.title(f"🛒 {nombre_feria}")
            st.markdown("Elige tus productos, completa tus datos de envío y haz tu pedido al instante.")
            st.divider()
            
            # Formulario de datos del cliente
            st.subheader("1️⃣ Tus Datos de Envío")
            nombre_cliente = st.text_input("Nombre y Apellido:")
            celular_cliente = st.text_input("Celular (Ej: 099123456):")
            direccion_cliente = st.text_input("Dirección de Envío (Calle, Nro y Esquina):")
            
            st.divider()
            st.subheader("2️⃣ Armá tu Pedido")
            st.markdown("Selecciona los kilos o cantidades que deseas de cada producto:")
            
            # Diccionario para capturar las cantidades seleccionadas por el cliente
            cantidades_seleccionadas = {}
            
            # Mostramos los productos en una lista interactiva limpia
            for index, row in df_prod.iterrows():
                emoji = row['Emoji']
                producto = row['Producto']
                precio = row['Precio']
                descuento = row['Descuento']
                
                if producto: # Si hay producto válido
                    # Si tiene descuento, mostramos el precio tachado o aclarado
                    if descuento > 0:
                        precio_final = precio * (1 - (descuento / 100))
                        label_precio = f"${precio_final:,.1f} (¡{descuento}% OFF!)"
                    else:
                        label_precio = f"${precio:,.1f}"
                    
                    col_info, col_input = st.columns([2, 1])
                    with col_info:
                        st.markdown(f"**{emoji} {producto}**  \n*Precio:* {label_precio}")
                    with col_input:
                        # Selector de cantidad (kilos o unidades)
                        cantidades_seleccionadas[producto] = st.number_input(
                            f"Cant ({producto})", 
                            min_value=0.0, 
                            max_value=50.0, 
                            step=0.5, 
                            format="%.1f",
                            key=f"prod_{index}",
                            label_visibility="collapsed"
                        )
                    st.markdown("---")
            
            if st.button("🚀 Enviar Pedido a la Feria", type="primary", use_container_width=True):
                if not nombre_cliente or not celular_cliente or not direccion_cliente:
                    st.error("⚠️ Por favor completa tu Nombre, Celular y Dirección de Envío.")
                else:
                    # Filtramos solo los productos que el cliente pidió (cantidad > 0)
                    pedido_items = [f"{prod}: {cant}kg/un" for prod, cant in cantidades_seleccionadas.items() if cant > 0]
                    
                    if not pedido_items:
                        st.warning("⚠️ No has seleccionado ningún producto.")
                    else:
                        # Unimos todos los ítems en un texto resumido para el registro
                        detalle_pedido_texto = " | ".join(pedido_items)
                        
                        gc = conectar_google()
                        sheet_ventas = gc.open_by_url(link_excel).worksheet("Registro de Ventas")
                        
                        ahora = datetime.now(TZ_UY)
                        # Guardamos en el Excel de la feria
                        sheet_ventas.append_row([
                            ahora.strftime("%d/%m/%Y"), 
                            ahora.strftime("%H:%M:%S"), 
                            "Web", 
                            nombre_cliente, 
                            detalle_pedido_texto, 
                            1, 
                            0, 
                            celular_cliente, 
                            direccion_cliente, 
                            "A definir", 
                            "Web - Pendiente"
                        ])
                        st.success("✅ ¡Pedido enviado con éxito! El feriante lo está preparando y te contactará a la brevedad.")
        except Exception as e:
            st.error(f"Error cargando la tienda online: {e}")
    else:
        st.error("Feria no encontrada o inactiva.")
    
    st.stop()

# ==========================================
# 4. MODO PRIVADO (SISTEMA DE GESTIÓN INTERNO)
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None

if st.session_state.usuario_logueado is None:
    st.title("🔒 Acceso al Sistema (Empleados)")
    
    with st.container():
        empresa_intento = st.text_input("Código de Empresa (Ej: ILNONNO):").upper()
        usuario_intento = st.text_input("Usuario:")
        clave_intento = st.text_input("Contraseña:", type="password")
        
        if st.button("🚪 Ingresar"):
            link_excel = obtener_datos_cliente(empresa_intento)
            
            if link_excel == "SUSPENDIDO":
                st.error("❌ Cuenta suspendida.")
            elif link_excel:
                try:
                    df_usuarios = pd.read_excel(link_excel, sheet_name="Usuarios", dtype=str)
                    usuario_valido = df_usuarios[(df_usuarios['Usuario'].str.lower() == usuario_intento.lower()) & (df_usuarios['Clave'] == clave_intento)]
                    
                    if not usuario_valido.empty:
                        st.session_state.usuario_logueado = usuario_intento
                        st.session_state.rol_logueado = usuario_valido.iloc[0]['Rol']
                        st.session_state.link_feria = link_excel
                        st.rerun()
                    else:
                        st.error("❌ Usuario o Contraseña incorrectos.")
                except Exception as e:
                    st.error(f"Error al leer usuarios: {e}")
            else:
                st.error("❌ Código de empresa inválido.")
    st.stop()

# --- PANEL PRIVADO ---
with st.sidebar:
    color_rol = "👑" if st.session_state.rol_logueado == "Admin" else "🛒"
    st.success(f"{color_rol} Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.rol_logueado = None
        st.session_state.link_feria = None
        st.rerun()

@st.cache_data(ttl=30)
def cargar_datos_feria(link):
    df_prod = pd.read_excel(link, sheet_name="Productos", dtype=str).fillna("")
    df_prod['Precio'] = pd.to_numeric(df_prod['Precio'], errors='coerce').fillna(0)
    df_prod['Descuento'] = pd.to_numeric(df_prod['Descuento'], errors='coerce').fillna(0) 
    
    df_prod['Prod_Full'] = df_prod['Emoji'] + " " + df_prod['Producto']
    productos = df_prod['Prod_Full'].tolist()
    precios = dict(zip(df_prod['Prod_Full'], df_prod['Precio']))
    descuentos = dict(zip(df_prod['Prod_Full'], df_prod['Descuento']))
    nombres_planos = dict(zip(df_prod['Prod_Full'], df_prod['Producto']))
    
    df_conf = pd.read_excel(link, sheet_name="Configuracion", header=None, dtype=str)
    config = dict(zip(df_conf[0], df_conf[1]))
    return productos, precios, descuentos, nombres_planos, config

PRODUCTOS, PRECIOS, DESCUENTOS, NOMBRES, CONFIG = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("Nombre_Empresa", "La Feria")

st.title(f"🏢 {nombre_empresa}")

tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    tabs_nombres.append("⚖️ Toma de Pedidos")
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    tabs_nombres.append("💰 Caja y Cobro")
if st.session_state.rol_logueado == "Admin":
    tabs_nombres.append("📊 Panel Admin")

tabs = st.tabs(tabs_nombres)
idx = 0

# --- PESTAÑA 1: VENDEDOR ---
with tabs[idx]:
    st.write("### 📝 Ingresar Pedido Nuevo")
    cliente = st.text_input("Nombre del Cliente:")
    
    prod_buscado = st.selectbox("Buscar Producto:", ["Seleccionar..."] + PRODUCTOS)
    if prod_buscado != "Seleccionar...":
        col1, col2 = st.columns(2)
        with col1: kilos = st.number_input("Kilos:", min_value=0, step=1)
        with col2: gramos = st.number_input("Gramos:", min_value=0, max_value=999, step=50)
        
        cant = kilos + (gramos / 1000.0)
        if cant > 0:
            precio_orig = PRECIOS.get(prod_buscado, 0)
            desc_pct = DESCUENTOS.get(prod_buscado, 0)
            precio_final = precio_orig * (1 - (desc_pct / 100))
            subtotal = cant * precio_final
            
            st.info(f"Subtotal: **${subtotal:,.1f}**")
            
            if st.button("Enviar a Caja"):
                gc = conectar_google()
                sheet = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                ahora = datetime.now(TZ_UY)
                sheet.append_row([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), st.session_state.usuario_logueado, cliente, NOMBRES.get(prod_buscado), cant, subtotal, "", "", "En Caja"])
                st.success("✅ Enviado a la caja exitosamente.")
    idx += 1

# --- PESTAÑA 2: CAJA Y COBRO ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Cobrar y Enviar Ticket")
        forma_pago = st.selectbox("Forma de Pago:", ["Efectivo", "Tarjeta", "MercadoPago", "FIADO"])
        celular = st.text_input("Celular del Cliente:")
        
        if st.button("Cerrar Venta y Enviar WhatsApp"):
            msg = f"👋 Hola, gracias por comprar en *{nombre_empresa}*.\nTu pago con {forma_pago} fue registrado correctamente. ¡Gracias!"
            num = celular.replace(" ", "").replace("+", "")
            st.link_button("📲 Enviar Mensaje", f"https://wa.me/{num}?text={urllib.parse.quote(msg)}")
        idx += 1

# --- PESTAÑA 3: ADMIN ---
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📊 Métricas de Hoy")
        st.success("Panel de Control activo.")
