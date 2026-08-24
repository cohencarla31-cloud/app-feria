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
# 3. CARGA DE PRODUCTOS A PRUEBA DE FALLOS
# ==========================================
@st.cache_data(ttl=30)
def cargar_datos_feria(link):
    gc = conectar_google()
    sh = gc.open_by_url(link)
    
    # Leer todas las filas de Productos ignorando errores de cabecera usando get_all_values()
    worksheet_prod = sh.worksheet("Productos")
    filas_prod = worksheet_prod.get_all_values()
    
    productos = []
    precios = {}
    descuentos = {}
    nombres_planos = {}
    
    # Empezamos desde la fila 1 (saltando la cabecera 0)
    for fila in filas_prod[1:]:
        if len(fila) >= 3 and fila[1].strip() != "":  
            emoji = fila[0].strip()
            nombre = fila[1].strip()
            
            # Limpiar precio (remover símbolos de moneda y comas si las hubiera)
            precio_str = str(fila[2]).replace("$", "").replace(",", "").strip()
            try:
                precio = float(precio_str) if precio_str else 0.0
            except:
                precio = 0.0
                
            # Limpiar descuento (columna 5 o 6 según orden, por defecto 0)
            desc = 0.0
            if len(fila) >= 6 and str(fila[5]).strip() != "":
                desc_str = str(fila[5]).replace("%", "").strip()
                try:
                    desc = float(desc_str)
                except:
                    desc = 0.0
            
            prod_full = f"{emoji} {nombre}"
            productos.append(prod_full)
            precios[prod_full] = precio
            descuentos[prod_full] = desc
            nombres_planos[prod_full] = nombre

    # Cargar Configuración
    df_conf = pd.DataFrame(sh.worksheet("Configuracion").get_all_values())
    config = dict(zip(df_conf[0], df_conf[1])) if not df_conf.empty else {}
    
    return productos, precios, descuentos, nombres_planos, config

# ==========================================
# 4. MODO TIENDA (CATÁLOGO DIGITAL PÚBLICO)
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel and link_excel != "SUSPENDIDO":
        try:
            productos, precios, descuentos, nombres_planos, config = cargar_datos_feria(link_excel)
            nombre_feria = config.get("Nombre_Empresa", "Nuestra Feria")
            
            st.title(f"🛒 {nombre_feria}")
            st.markdown("Elige tus productos, completa tus datos de envío y haz tu pedido al instante.")
            st.divider()
            
            st.subheader("1️⃣ Tus Datos de Envío")
            nombre_cliente = st.text_input("Nombre y Apellido:")
            celular_cliente = st.text_input("Celular (Ej: 099123456):")
            direccion_cliente = st.text_input("Dirección de Envío (Calle, Nro y Esquina):")
            
            st.divider()
            st.subheader("2️⃣ Armá tu Pedido")
            
            cantidades_seleccionadas = {}
            for prod_full in productos:
                precio = precios.get(prod_full, 0)
                descuento = descuentos.get(prod_full, 0)
                
                if descuento > 0:
                    precio_final = precio * (1 - (descuento / 100))
                    label_precio = f"${precio_final:,.1f} (¡{descuento}% OFF!)"
                else:
                    label_precio = f"${precio:,.1f}"
                
                col_info, col_input = st.columns([2, 1])
                with col_info:
                    st.markdown(f"**{prod_full}**  \n*Precio:* {label_precio}")
                with col_input:
                    cantidades_seleccionadas[prod_full] = st.number_input(
                        f"Cant ({prod_full})", 
                        min_value=0.0, max_value=50.0, step=0.5, format="%.1f",
                        key=f"prod_{prod_full}", label_visibility="collapsed"
                    )
                st.markdown("---")
            
            if st.button("🚀 Enviar Pedido a la Feria", type="primary", use_container_width=True):
                if not nombre_cliente or not celular_cliente or not direccion_cliente:
                    st.error("⚠️ Por favor completa tu Nombre, Celular y Dirección de Envío.")
                else:
                    pedido_items = [f"{prod}: {cant}kg/un" for prod, cant in cantidades_seleccionadas.items() if cant > 0]
                    if not pedido_items:
                        st.warning("⚠️ No has seleccionado ningún producto.")
                    else:
                        detalle_pedido_texto = " | ".join(pedido_items)
                        gc = conectar_google()
                        sheet_ventas = gc.open_by_url(link_excel).worksheet("Registro de Ventas")
                        
                        ahora = datetime.now(TZ_UY)
                        sheet_ventas.append_row([
                            ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                            "Web", nombre_cliente, detalle_pedido_texto, 1, 0, 
                            celular_cliente, direccion_cliente, "A definir", "Web - Pendiente"
                        ])
                        st.success("✅ ¡Pedido enviado con éxito! El feriante lo está preparando.")
        except Exception as e:
            st.error(f"Error cargando la tienda online: {e}")
    else:
        st.error("Feria no encontrada o inactiva.")
    st.stop()

# ==========================================
# 5. MODO PRIVADO Y ACCESO LIMPIO (SUPER ADMIN INVISIBLE)
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None
    st.session_state.es_super_admin = False

if st.session_state.usuario_logueado is None:
    st.title("🔒 Ingreso al Sistema")
    st.markdown("Introduce los datos proporcionados para administrar tu comercio.")
    
    empresa_intento = st.text_input("Código de Empresa:", key="emp_norm").strip().upper()
    usuario_intento = st.text_input("Usuario:", key="usu_norm").strip()
    clave_intento = st.text_input("Contraseña:", type="password", key="cla_norm")
    
    if st.button("🚪 Ingresar", type="primary"):
        # 👑 TRUCO SUPER ADMIN INVISIBLE: Si pones código "MASTER" y tu clave secreta
        if empresa_intento == "MASTER" and clave_intento == "MiClaveSuperSecreta2026":
            # Te deja elegir a qué feria entrar escribiendo su código real de forma interna
            st.session_state.usuario_logueado = "SuperAdmin"
            st.session_state.rol_logueado = "Admin"
            # Por defecto te asigna el primer link o pedimos el código de feria en otro lado
            st.session_state.link_feria = obtener_datos_cliente("ILNONNO") # O la feria que gustes auditar
            st.session_state.es_super_admin = True
            st.rerun()
            
        # Ingreso normal de empleados / administradores de la feria
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
    st.stop()

# --- PANEL PRIVADO ---
with st.sidebar:
    color_rol = "👑" if st.session_state.rol_logueado == "Admin" else "🛒"
    st.success(f"{color_rol} Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.session_state.es_super_admin:
        st.warning("⚠️ Modo Super Admin Invisible")
    
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
