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
st.set_page_config(page_title="App Ferias - SaaS", layout="centered", initial_sidebar_state="collapsed")
TZ_UY = timezone(timedelta(hours=-3))

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
                if str(fila.get("Estado", "")).strip().capitalize() == "Activo":
                    return fila.get("Link_Excel")
                else:
                    return "SUSPENDIDO"
    except Exception as e:
        st.error(f"Error al conectar con la base maestra: {e}")
    return None

# ==========================================
# 3. FUNCIÓN DE CARGA CON DEPURACIÓN VISUAL
# ==========================================
@st.cache_data(ttl=30)
def cargar_datos_feria(link):
    gc = conectar_google()
    sh = gc.open_by_url(link)
    
    # Cargar Productos
    worksheet_prod = sh.worksheet("Productos")
    data_prod = worksheet_prod.get_all_records()
    df_prod = pd.DataFrame(data_prod).fillna("")
    
    # 🔍 MOSTRAR EN PANTALLA LO QUE LEE EL ROBOT
    st.write("---")
    st.write("🔍 **Depuración - Lo que leyó gspread de tu hoja Productos:**")
    st.dataframe(df_prod)
    st.write("---")
    
    # Normalizar nombres de columnas
    df_prod.columns = [str(col).strip() for col in df_prod.columns]
    
    col_precio = next((c for c in df_prod.columns if 'precio' in c.lower()), 'Precio')
    col_emoji = next((c for c in df_prod.columns if 'emoji' in c.lower()), 'Emoji')
    col_producto = next((c for c in df_prod.columns if 'producto' in c.lower() or 'articulo' in c.lower()), 'Producto')
    col_desc = next((c for c in df_prod.columns if 'descuento' in c.lower() or 'desc' in c.lower()), 'Descuento')
    
    df_prod['Precio'] = pd.to_numeric(df_prod[col_precio], errors='coerce').fillna(0)
    df_prod['Descuento'] = pd.to_numeric(df_prod[col_desc], errors='coerce').fillna(0) 
    
    df_prod['Prod_Full'] = df_prod[col_emoji].astype(str) + " " + df_prod[col_producto].astype(str)
    productos = df_prod['Prod_Full'].tolist()
    precios = dict(zip(df_prod['Prod_Full'], df_prod['Precio']))
    descuentos = dict(zip(df_prod['Prod_Full'], df_prod['Descuento']))
    nombres_planos = dict(zip(df_prod['Prod_Full'], df_prod[col_producto]))
    
    df_conf = pd.DataFrame(sh.worksheet("Configuracion").get_all_values())
    config = dict(zip(df_conf[0], df_conf[1])) if not df_conf.empty else {}
    
    return productos, precios, descuentos, nombres_planos, config

# ==========================================
# 4. MODO PRIVADO Y LOGIN
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None
    st.session_state.es_super_admin = False

if st.session_state.usuario_logueado is None:
    st.title("🔒 Acceso al Sistema")
    
    tab_login_normal, tab_login_super = st.tabs(["Empleados / Feriantes", "👑 Super Admin (Tú)"])
    
    with tab_login_normal:
        empresa_intento = st.text_input("Código de Empresa (Ej: ILNONNO):", key="emp_norm").upper()
        usuario_intento = st.text_input("Usuario:", key="usu_norm")
        clave_intento = st.text_input("Contraseña:", type="password", key="cla_norm")
        
        if st.button("🚪 Ingresar como Empleado"):
            link_excel = obtener_datos_cliente(empresa_intento)
            if link_excel == "SUSPENDIDO":
                st.error("❌ Cuenta suspendida.")
            elif link_excel:
                try:
                    gc = conectar_google()
                    sh = gc.open_by_url(link_excel)
                    df_usuarios = pd.DataFrame(sh.worksheet("Usuarios").get_all_records()).astype(str)
                    
                    usuario_valido = df_usuarios[(df_usuarios['Usuario'].str.lower() == usuario_intento.lower()) & (df_usuarios['Clave'] == clave_intento)]
                    
                    if not usuario_valido.empty:
                        st.session_state.usuario_logueado = usuario_intento
                        st.session_state.rol_logueado = usuario_valido.iloc[0]['Rol']
                        st.session_state.link_feria = link_excel
                        st.session_state.es_super_admin = False
                        st.rerun()
                    else:
                        st.error("❌ Usuario o Contraseña incorrectos.")
                except Exception as e:
                    st.error(f"❌ Error de permisos o lectura de usuarios: {e}")
            else:
                st.error("❌ Código de empresa inválido o inactivo en el Master.")

    with tab_login_super:
        st.markdown("Acceso maestro exclusivo para la dueña de la plataforma SaaS.")
        clave_maestra = st.text_input("Clave Maestra Global:", type="password", key="cla_super")
        codigo_a_revisar = st.text_input("Código de Empresa a Auditar (Ej: ILNONNO):", key="emp_super").upper()
        
        if st.button("🚀 Ingresar como Super Admin"):
            if clave_maestra == "MiClaveSuperSecreta2026": 
                link_excel = obtener_datos_cliente(codigo_a_revisar)
                if link_excel and link_excel != "SUSPENDIDO":
                    st.session_state.usuario_logueado = "SuperAdmin"
                    st.session_state.rol_logueado = "Admin"
                    st.session_state.link_feria = link_excel
                    st.session_state.es_super_admin = True
                    st.rerun()
                else:
                    st.error("❌ El código de empresa no existe o está suspendido en el Master.")
            else:
                st.error("❌ Clave maestra incorrecta.")
    st.stop()

# --- PANEL PRIVADO ---
with st.sidebar:
    color_rol = "👑" if st.session_state.rol_logueado == "Admin" else "🛒"
    st.success(f"{color_rol} Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.session_state.es_super_admin:
        st.warning("⚠️ Modo Super Admin Activo")
    
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.rol_logueado = None
        st.session_state.link_feria = None
        st.session_state.es_super_admin = False
        st.rerun()

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
        st.write("### 📊 Panel Admin")
        st.success("Panel de Control activo.")
