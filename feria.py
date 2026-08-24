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

def limpiar_y_formatear_celular(celular_ingresado):
    num = ''.join(filter(str.isdigit, str(celular_ingresado)))
    if not num:
        return ""
    if str(celular_ingresado).strip().startswith("+"):
        return num
    if len(num) <= 9:
        if num.startswith("0"):
            num = num[1:]
        return f"598{num}"
    return num

# ==========================================
# 3. CARGA DE DATOS DE LA FERIA
# ==========================================
@st.cache_data(ttl=30)
def cargar_datos_feria(link):
    gc = conectar_google()
    sh = gc.open_by_url(link)
    
    # Productos
    worksheet_prod = sh.worksheet("Productos")
    filas_prod = worksheet_prod.get_all_values()
    
    productos = []
    precios = {}
    descuentos = {}
    nombres_planos = {}
    
    for fila in filas_prod[1:]:
        if len(fila) >= 3 and fila[1].strip() != "" and fila[1].strip().lower() != "producto":  
            emoji = fila[0].strip()
            nombre = fila[1].strip()
            
            precio_str = str(fila[2]).replace("$", "").replace(",", "").strip()
            try:
                precio = float(precio_str) if precio_str else 0.0
            except:
                precio = 0.0
                
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

    # Configuración
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
            celular_feriante = config.get("Celular_Feriante", config.get("Celular_Contacto", "59899000000"))
            
            st.title(f"🛒 {nombre_feria}")
            st.markdown("Elige tus productos, completa tus datos y envía tu pedido directo a la feria.")
            st.divider()
            
            st.subheader("1️⃣ Tus Datos de Envío")
            nombre_cliente = st.text_input("Nombre y Apellido:")
            celular_cliente = st.text_input("Celular (Ej: 099123456 o +549...):", placeholder="099123456")
            direccion_cliente = st.text_input("Dirección de Envío (Calle, Nro y Esquina):")
            observaciones_cliente = st.text_area("Observaciones o notas para el armado (Opcional):", placeholder="Ej: Las bananas un poco verdes, timbre roto, etc.")
            
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
                        if observaciones_cliente:
                            detalle_pedido_texto += f" | 📝 Obs: {observaciones_cliente}"
                            
                        gc = conectar_google()
                        sheet_ventas = gc.open_by_url(link_excel).worksheet("Registro de Ventas")
                        
                        celular_formateado = limpiar_y_formatear_celular(celular_cliente)
                        
                        ahora = datetime.now(TZ_UY)
                        sheet_ventas.append_row([
                            ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                            "Web Online", nombre_cliente, detalle_pedido_texto, 1, 0, 
                            celular_formateado, direccion_cliente, "A definir", "Web - Pendiente"
                        ])
                        
                        st.success("✅ ¡Muchas gracias por tu compra! A la brevedad será armada y despachada.")
                        
                        # Mensaje para notificar al feriante vía WhatsApp
                        msg_feriante = f"🛒 *NUEVO PEDIDO WEB*\n\n👤 Cliente: {nombre_cliente}\n📱 Celular: {celular_formateado}\n📍 Dirección: {direccion_cliente}\n📦 Productos:\n{detalle_pedido_texto}"
                        if observaciones_cliente:
                            msg_feriante += f"\n\n💬 Notas: {observaciones_cliente}"
                            
                        num_feriante_limpio = limpiar_y_formatear_celular(celular_feriante)
                        st.link_button("📲 Enviar Notificación al WhatsApp del Feriante", f"https://wa.me/{num_feriante_limpio}?text={urllib.parse.quote(msg_feriante)}")
        except Exception as e:
            st.error(f"Error cargando la tienda online: {e}")
    else:
        st.error("Feria no encontrada o inactiva.")
    st.stop()

# ==========================================
# 5. MODO PRIVADO Y ACCESO (SUPER ADMIN INVISIBLE)
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None
    st.session_state.es_super_admin = False
    st.session_state.carrito_vendedor = [] # Para acumular ítems antes de enviar a caja

if st.session_state.usuario_logueado is None:
    st.title("🔒 Ingreso al Sistema")
    st.markdown("Introduce los datos de acceso para administrar el comercio.")
    
    empresa_intento = st.text_input("Código de Empresa:", key="emp_norm").strip().upper()
    usuario_intento = st.text_input("Usuario:", key="usu_norm").strip()
    clave_intento = st.text_input("Contraseña:", type="password", key="cla_norm")
    
    if st.button("🚪 Ingresar", type="primary"):
        if empresa_intento == "MASTER" and clave_intento == "MiClaveSuperSecreta2026":
            st.session_state.usuario_logueado = "SuperAdmin"
            st.session_state.rol_logueado = "Admin"
            st.session_state.link_feria = obtener_datos_cliente("ILNONNO")
            st.session_state.es_super_admin = True
            st.rerun()
            
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
        st.session_state.carrito_vendedor = []
        st.rerun()

PRODUCTOS, PRECIOS, DESCUENTOS, NOMBRES, CONFIG = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("Nombre_Empresa", "La Feria")
celular_feriante_local = CONFIG.get("Celular_Feriante", "59899000000")

st.title(f"🏢 {nombre_empresa}")

tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    tabs_nombres.append("⚖️ Toma de Pedidos")
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    tabs_nombres.append("💰 Caja y Cobro")
if st.session_state.rol_logueado == "Admin":
    tabs_nombres.append("📊 Panel Admin & Web")

tabs = st.tabs(tabs_nombres)
idx = 0

# --- PESTAÑA 1: VENDEDOR (CON ACUMULADOR E ÍTEM MANUAL) ---
with tabs[idx]:
    st.write("### 📝 Armar Carrito de Compra (Vendedor)")
    cliente_vendedor = st.text_input("Nombre del Cliente:", key="cli_v")
    
    # Elección entre producto del catálogo o ítem manual libre
    tipo_ingreso = st.radio("Tipo de ítem:", ["Catálogo de Productos", "Ítem Manual / Libre"], horizontal=True)
    
    if tipo_ingreso == "Catálogo de Productos":
        prod_buscado = st.selectbox("Buscar Producto:", ["Seleccionar..."] + PRODUCTOS)
        if prod_buscado != "Seleccionar...":
            col1, col2 = st.columns(2)
            with col1: kilos = st.number_input("Kilos:", min_value=0.0, step=1.0, key="kv")
            with col2: gramos = st.number_input("Gramos:", min_value=0.0, max_value=999.0, step=50.0, key="gv")
            
            cant = kilos + (gramos / 1000.0)
            if cant > 0:
                precio_orig = PRECIOS.get(prod_buscado, 0)
                desc_pct = DESCUENTOS.get(prod_buscado, 0)
                precio_final = precio_orig * (1 - (desc_pct / 100))
                subtotal = cant * precio_final
                
                st.info(f"Subtotal de este ítem: **${subtotal:,.1f}**")
                if st.button("➕ Agregar al Carrito"):
                    st.session_state.carrito_vendedor.append({
                        "producto": NOMBRES.get(prod_buscado),
                        "cantidad": cant,
                        "subtotal": subtotal
                    })
                    st.success("Ítem agregado al carrito temporal.")
    else:
        desc_manual = st.text_input("Descripción del Producto Manual (Ej: Cajón de madera, Varios):")
        precio_manual = st.number_input("Precio Total ($):", min_value=0.0, step=10.0)
        if st.button("➕ Agregar Ítem Manual"):
            if desc_manual and precio_manual > 0:
                st.session_state.carrito_vendedor.append({
                    "producto": desc_manual,
                    "cantidad": 1.0,
                    "subtotal": precio_manual
                })
                st.success("Ítem manual agregado.")
            else:
                st.error("Completa la descripción y el precio.")

    # Mostrar Carrito Actual Acumulado
    if st.session_state.carrito_vendedor:
        st.divider("---")
        st.subheader("🛒 Carrito Actual del Cliente")
        df_carrito = pd.DataFrame(st.session_state.carrito_vendedor)
        st.dataframe(df_carrito, use_container_width=True)
        
        total_carrito = df_carrito['subtotal'].sum()
        st.markdown(f"### Total Acumulado: **${total_carrito:,.1f}**")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("🚀 Enviar Todo a Caja", type="primary"):
                if not cliente_vendedor:
                    st.error("⚠️ Ingresa el nombre del cliente.")
                else:
                    gc = conectar_google()
                    sheet = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                    ahora = datetime.now(TZ_UY)
                    
                    detalle_resumen = " | ".join([f"{row['producto']}: {row['cantidad']}un" for row in st.session_state.carrito_vendedor])
                    
                    sheet.append_row([
                        ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                        st.session_state.usuario_logueado, cliente_vendedor, 
                        detalle_resumen, 1, total_carrito, "", "", "En Caja"
                    ])
                    st.success("✅ ¡Pedido completo enviado a la Caja con éxito!")
                    st.session_state.carrito_vendedor = []
        with col_c2:
            if st.button("🗑️ Vaciar Carrito"):
                st.session_state.carrito_vendedor = []
                st.rerun()
    idx += 1

# --- PESTAÑA 2: CAJA Y COBRO (CON WHATSAPP PERSONALIZADO Y AHORRO) ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Cobrar y Enviar Ticket por WhatsApp")
        cliente_caja = st.text_input("Nombre del Cliente (Caja):", key="cc_name")
        monto_cobro = st.number_input("Monto Total a Cobrar ($):", min_value=0.0, step=10.0, format="%.1f", key="cc_monto")
        ahorro_descuento = st.number_input("Ahorro / Descuento aplicado ($ Opcional):", min_value=0.0, step=5.0, format="%.1f", key="cc_ahorro")
        forma_pago = st.selectbox("Forma de Pago:", ["Efectivo", "Tarjeta", "MercadoPago", "FIADO"], key="cc_pago")
        celular_caja = st.text_input("Celular del Cliente (Ej: 099123456 o +549...):", placeholder="099123456", key="cel_caja")
        
        if st.button("Registrar Cobro y Generar Ticket WhatsApp", type="primary"):
            if not cliente_caja or monto_cobro <= 0 or not celular_caja:
                st.error("⚠️ Completa el Nombre, el Monto y el Celular para enviar el ticket.")
            else:
                gc = conectar_google()
                sheet = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                ahora = datetime.now(TZ_UY)
                estado_venta = "Fiado Pendiente" if forma_pago == "FIADO" else "Cobrado"
                
                celular_formateado = limpiar_y_formatear_celular(celular_caja)
                
                sheet.append_row([
                    ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                    st.session_state.usuario_logueado, cliente_caja, 
                    "Venta en Caja", 1, monto_cobro, celular_formateado, "", forma_pago, estado_venta
                ])
                
                # Ticket personalizado con nombre, agradecimiento y ahorro si lo hay
                if forma_pago == "FIADO":
                    msg = f"👋 Hola *{cliente_caja}*, registramos tu compra en *{nombre_empresa}* por un total de *${monto_cobro:,.1f}* bajo la modalidad *FIADO*."
                else:
                    msg = f"👋 Hola *{cliente_caja}*, tu pago de *${monto_cobro:,.1f}* con *{forma_pago}* fue procesado con éxito."
                
                if ahorro_descuento > 0:
                    msg += f"\n🎉 ¡Con esta compra tuviste un ahorro total de *${ahorro_descuento:,.1f}*!"
                    
                msg += f"\n\n💚 ¡Muchas gracias por elegirnos y confiar en *{nombre_empresa}*! Te esperamos pronto."
                
                st.success(f"✅ ¡Venta registrada con éxito ({estado_venta})!")
                st.link_button("📲 Enviar Ticket por WhatsApp al Cliente", f"https://wa.me/{celular_formateado}?text={urllib.parse.quote(msg)}")
        idx += 1

# --- PESTAÑA 3: PANEL ADMIN, WEB & RECORDATORIO DE FIADOS (+10 DÍAS) ---
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📊 Panel de Control, Pedidos Web y Fiados")
        
        try:
            gc = conectar_google()
            sh = gc.open_by_url(st.session_state.link_feria)
            sheet_ventas = sh.worksheet("Registro de Ventas")
            registros_ventas = sheet_ventas.get_all_records()
            
            if registros_ventas:
                df_ventas = pd.DataFrame(registros_ventas)
                
                # Métricas
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.metric(label="Total Registros", value=len(df_ventas))
                with col_m2:
                    if 'Monto' in df_ventas.columns:
                        total_recaudado = pd.to_numeric(df_ventas['Monto'], errors='coerce').sum()
                        st.metric(label="Monto Total ($)", value=f"${total_recaudado:,.1f}")
                
                st.divider()
                
                # SECCIÓN A: GESTIÓN DE PEDIDOS WEB PENDIENTES
                st.subheader("🌐 Gestión de Pedidos Online Recibidos")
                if 'Estado' in df_ventas.columns:
                    df_web = df_ventas[df_ventas['Estado'].str.contains("Web", case=False, na=False)]
                    if not df_web.empty:
                        for i, row in df_web.iterrows():
                            with st.expander(f"📦 Pedido de {row.get('Cliente', 'Cliente')} - Fecha: {row.get('Fecha', '')} ({row.get('Estado', '')})"):
                                st.write(f"**Detalle:** {row.get('Detalle', '')}")
                                st.write(f"**Dirección:** {row.get('Direccion', '')}")
                                st.write(f"**Celular:** {row.get('Celular', '')}")
                                
                                c_w1, c_w2 = st.columns(2)
                                with c_w1:
                                    msg_recibido = f"Hola *{row.get('Cliente', 'Cliente')}* 🛒. ¡Recibimos tu pedido en *{nombre_empresa}*! A la brevedad será armado y despachado. ¡Gracias por elegirnos!"
                                    cel_w = limpiar_y_formatear_celular(row.get('Celular', ''))
                                    st.link_button(f"📲 Reenviar 'Pedido Recibido' (Wsp)", f"https://wa.me/{cel_w}?text={urllib.parse.quote(msg_recibido)}")
                                with c_w2:
                                    msg_camino = f"Hola *{row.get('Cliente', 'Cliente')}* 🛵. Tu pedido de *{nombre_empresa}* ya va en camino a tu domicilio. ¡Que lo disfrutes!"
                                    st.link_button(f"🛵 Avisar 'Va en Camino' (Wsp)", f"https://wa.me/{cel_w}?text={urllib.parse.quote(msg_camino)}")
                    else:
                        st.info("No hay pedidos web pendientes en este momento.")
                
                st.divider()
                
                # SECCIÓN B: GESTIÓN DE FIADOS Y RECORDATORIOS (>10 DÍAS)
                st.subheader("💳 Control de Fiados y Recordatorios de Deuda")
                if 'Estado' in df_ventas.columns and 'Forma_Pago' in df_ventas.columns:
                    df_fiados = df_ventas[df_ventas['Forma_Pago'].str.contains("FIADO", case=False, na=False)]
                    if not df_fiados.empty:
                        st.markdown("Clientes con saldos pendientes o fiados registrados:")
                        for i, row in df_fiados.iterrows():
                            # Calcular antigüedad aproximada basada en la fecha del registro
                            try:
                                fecha_venta = datetime.strptime(row.get('Fecha', ''), "%d/%m/%Y").date()
                                dias_transcurridos = (datetime.now(TZ_UY).date() - fecha_venta).days
                            except:
                                dias_transcurridos = 0
                                
                            alerta_vencido = "⚠️ *Más de 10 días*" if dias_transcurridos >= 10 else f"({dias_transcurridos} días)"
                            
                            with st.container():
                                st.write(f"👤 **{row.get('Cliente', '')}** | 💰 Monto: **${row.get('Monto', 0)}** | Fecha: {row.get('Fecha', '')} {alerta_vencido}")
                                msg_recordatorio = f"👋 Hola *{row.get('Cliente', '')}*, te escribimos amablemente desde *{nombre_empresa}* para recordarte que tienes un saldo pendiente de *${row.get('Monto', 0)}* correspondiente a tu compra del {row.get('Fecha', '')}. Cuando puedas pasar o realizar transferencia nos avisas. ¡Muchas gracias por tu confianza! 💚"
                                cel_f = limpiar_y_formatear_celular(row.get('Celular', ''))
                                if cel_f:
                                    st.link_button(f"📲 Enviar Recordatorio de Deuda a {row.get('Cliente', '')}", f"https://wa.me/{cel_f}?text={urllib.parse.quote(msg_recordatorio)}")
                                st.markdown("---")
                    else:
                        st.info("No hay registros de fiados activos.")
                
                st.subheader("📋 Planilla Completa de Ventas")
                st.dataframe(df_ventas, use_container_width=True)
            else:
                st.info("ℹ️ Aún no hay registros cargados.")
        except Exception as e:
            st.error(f"Error cargando el panel de administración: {e}")
