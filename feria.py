import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y OCULTAMIENTO
# ==========================================
st.set_page_config(page_title="App Ferias - SaaS", layout="centered", initial_sidebar_state="collapsed")

hide_streamlit_style = """
            <style>
            header {visibility: hidden !important; display: none !important;}
            [data-testid="stHeader"] {display: none !important;}
            [data-testid="stToolbar"] {display: none !important;}
            footer {visibility: hidden !important; display: none !important;}
            .stAppDeployButton {display: none !important;}
            .viewerBadge_container__1QSob {display: none !important;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

TZ_UY = timezone(timedelta(hours=-3))
LINK_MASTER_SHEET = "https://docs.google.com/spreadsheets/d/1CEuvlAwExOf1FS_ZYeFYw205aoVePb8SCmmLjUJTg-w/edit?gid=0#gid=0"

if 'v_rk' not in st.session_state: st.session_state.v_rk = 0 
if 'c_rk' not in st.session_state: st.session_state.c_rk = 0 
if 'carrito_vendedor' not in st.session_state: st.session_state.carrito_vendedor = []
if 'input_cliente_nombre' not in st.session_state: st.session_state.input_cliente_nombre = ""
if 'input_cliente_celular' not in st.session_state: st.session_state.input_cliente_celular = ""
if 'web_step' not in st.session_state: st.session_state.web_step = 1
if 'cliente_retomado_aviso' not in st.session_state: st.session_state.cliente_retomado_aviso = ""
if 'carrito_web' not in st.session_state: st.session_state.carrito_web = []

# ==========================================
# 2. CONEXIÓN Y CACHÉ OPTIMIZADO
# ==========================================
@st.cache_resource
def conectar_google():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]), scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=15)
def obtener_ventas(link_excel):
    try:
        gc = conectar_google()
        return gc.open_by_url(link_excel).worksheet("Registro de Ventas").get_all_values()
    except: return []

def limpiar_cache_ventas():
    obtener_ventas.clear()

def obtener_datos_cliente(codigo_empresa):
    try:
        gc = conectar_google()
        master = gc.open_by_url(LINK_MASTER_SHEET).sheet1
        registros = master.get_all_records()
        for fila in registros:
            if str(fila.get("Codigo_Empresa", "")).upper() == codigo_empresa.upper():
                if str(fila.get("Estado", "")).strip().capitalize() == "Activo":
                    return fila.get("Link_Excel")
                else: return "SUSPENDIDO"
    except: pass
    return None

def limpiar_y_formatear_celular(celular_ingresado):
    num = ''.join(filter(str.isdigit, str(celular_ingresado)))
    if not num: return ""
    if len(num) == 10 and not num.startswith("0") and not num.startswith("54"):
        return f"549{num}"
    if num.startswith("549"): return num
    if len(num) <= 9:
        if num.startswith("0"): num = num[1:]
        return f"598{num}"
    return num

def get_estado_col_index(row):
    kw = ["caja", "web", "entregado", "cancelado", "cobrado", "fiado", "pendiente"]
    if len(row) > 10 and any(k in str(row[10]).lower() for k in kw): return 10
    if len(row) > 9 and any(k in str(row[9]).lower() for k in kw): return 9
    return 9

def agrupar_pedidos(data, filtro_estados=None):
    ordenes = {}
    for i, row in enumerate(data):
        if i == 0: continue
        row = row + [""] * (13 - len(row))
        idx_est = get_estado_col_index(row)
        estado = str(row[idx_est]).strip()
        
        if idx_est == 10: idx_pago, idx_dir = 9, 8
        else: idx_pago, idx_dir = 8, 10
            
        pago = str(row[idx_pago]).strip()
        direccion = str(row[idx_dir]).strip()
        
        if not filtro_estados or estado in filtro_estados:
            key = (row[0], row[1], row[3]) 
            if key not in ordenes:
                ordenes[key] = {
                    "filas": [], "fecha": row[0], "hora": row[1], "vendedor": row[2],
                    "cliente": row[3], "celular": row[7], "pago": pago, 
                    "estado": estado, "direccion": direccion,
                    "total": 0.0, "ahorro": 0.0, "items": [],
                    "idx_est": idx_est, "idx_pago": idx_pago, "idx_dir": idx_dir,
                    "json": row[12] if len(row) > 12 and row[12].strip() != "" else "[]"
                }
            ordenes[key]["filas"].append(i + 1)
            
            try: cant = float(str(row[5]).replace(",", "."))
            except: cant = 0.0
            try: subt = float(str(row[6]).replace("$","").replace(",","."))
            except: subt = 0.0
            try: ahorro = float(str(row[11]).replace("$","").replace(",","."))
            except: ahorro = 0.0
            
            ordenes[key]["total"] += subt
            ordenes[key]["ahorro"] += ahorro
            ordenes[key]["items"].append({"producto": row[4], "cantidad": cant, "subtotal": subt, "ahorro": ahorro, "tipo": "Propio"})
            
    for k, v in ordenes.items():
        try:
            parsed_json = json.loads(v["json"])
            if not parsed_json and v["items"]:
                v["json"] = json.dumps([{"producto": it["producto"], "cantidad": it["cantidad"], "cantidad_txt": f"{it['cantidad']}un", "subtotal": it["subtotal"], "ahorro": it["ahorro"], "tipo": "Propio"} for it in v["items"]])
        except:
            v["json"] = json.dumps([{"producto": it["producto"], "cantidad": it["cantidad"], "cantidad_txt": f"{it['cantidad']}un", "subtotal": it["subtotal"], "ahorro": it["ahorro"], "tipo": "Propio"} for it in v["items"]])
        v["detalle"] = " | ".join([f"{item['producto']} ({item['cantidad']})" for item in v["items"]])
        
    lista_ordenes = list(ordenes.values())
    lista_ordenes.sort(key=lambda x: x["filas"][0])
    return lista_ordenes

@st.cache_data(ttl=30)
def cargar_datos_feria(link):
    gc = conectar_google()
    sh = gc.open_by_url(link)
    config = {}
    try:
        ws_conf = sh.worksheet("Configuracion")
        for row in ws_conf.get_all_values():
            if len(row) >= 2 and row[0].strip():
                config[row[0].strip().lower()] = row[1].strip()
    except: pass
        
    productos, precios, descuentos, medidas, nombres_planos, medidas_planas = [], {}, {}, {}, {}, {}
    try:
        ws_prod = sh.worksheet("Productos")
        filas_p = ws_prod.get_all_values()
        cabeceras_p = [str(c).strip().lower() for c in filas_p[0]]
        idx_medida = cabeceras_p.index('medida') if 'medida' in cabeceras_p else 6
        
        for fila in filas_p[1:]:
            if len(fila) >= 3 and fila[1].strip() and fila[1].strip().lower() != "producto":  
                emoji = fila[0].strip()
                nombre = fila[1].strip()
                precio_str = str(fila[2]).replace("$", "").replace(",", ".").strip()
                try: precio = float(precio_str) if precio_str else 0.0
                except: precio = 0.0
                
                desc = 0.0
                if len(fila) >= 6 and fila[5].strip():
                    desc_str = str(fila[5]).replace("%", "").replace(",", ".").strip()
                    try: desc = float(desc_str)
                    except: pass
                
                medida = "kg"
                if len(fila) > idx_medida and str(fila[idx_medida]).strip():
                    medida = str(fila[idx_medida]).strip().lower()
                
                prod_full = f"{emoji} {nombre}"
                productos.append(prod_full)
                precios[prod_full] = precio
                precios[nombre] = precio
                descuentos[prod_full] = desc
                descuentos[nombre] = desc
                medidas[prod_full] = medida
                medidas[nombre] = medida
                nombres_planos[prod_full] = nombre
                medidas_planas[nombre] = medida
                medidas_planas[prod_full] = medida
    except: pass

    clientes_dict = {}
    try:
        ws_cli = sh.worksheet("Clientes")
        for fila in ws_cli.get_all_values()[1:]:
            if len(fila) >= 1 and fila[0].strip() and fila[0].strip().lower() != "nombre":
                nombre_c = fila[0].strip().upper()
                celular_c = fila[1].strip() if len(fila) > 1 else ""
                clientes_dict[nombre_c] = celular_c
    except: pass
    
    return productos, precios, descuentos, medidas, nombres_planos, clientes_dict, config, medidas_planas

# ==========================================
# 3. MODO TIENDA PÚBLICA (WIZARD CON PASOS EXPLICADOS Y SELECTOR DE PRODUCTOS)
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel and link_excel != "SUSPENDIDO":
        try:
            productos, precios, descuentos, medidas, nombres_planos, clientes_dict, config, _ = cargar_datos_feria(link_excel)
            nombre_feria = config.get("nombre_empresa", config.get("nombre", "Nuestra Feria"))
            celular_feriante = config.get("celular_feriante", config.get("celular_contacto", "59893343092"))
            bienvenida_dia = config.get("bienvenida", config.get("ofertas", config.get("banner", "")))
            
            st.title(f"🛒 {nombre_feria}")
            if bienvenida_dia: st.info(f"🔥 **OFERTAS Y NOVEDADES DE HOY:**\n\n{bienvenida_dia}")
            
            # Explicación previa de los pasos
            with st.expander("ℹ️ ¿Cómo realizar tu pedido online? (Pasos)", expanded=(st.session_state.web_step == 1)):
                st.markdown("""
                1. **Tus Datos:** Ingresa tu nombre, celular y dirección de envío.
                2. **Armar Pedido:** Selecciona del desplegable los productos que deseas y añade la cantidad exacta (kilos, gramos o unidades).
                3. **Revisión:** Verifica el total estimado de tu compra.
                4. **Enviar WhatsApp:** Envía el comprobante directamente al feriante para asegurar tu lugar.
                """)
            
            st.markdown(f"<h3 style='text-align: center; color: #4CAF50;'>📋 Paso {st.session_state.web_step} de 4</h3>", unsafe_allow_html=True)
            st.divider()

            # PASO 1: DATOS
            if st.session_state.web_step == 1:
                st.subheader("1️⃣ Tus Datos de Entrega")
                st.session_state.cli_web_nombre = st.text_input("Nombre y Apellido:", value=st.session_state.get('cli_web_nombre', ''))
                st.session_state.cli_web_celular = st.text_input("Celular (Ej: 099123456):", value=st.session_state.get('cli_web_celular', ''), placeholder="Ej: 099123456")
                st.session_state.cli_web_dir = st.text_input("Dirección de Envío (Calle, Nro y Esquina):", value=st.session_state.get('cli_web_dir', ''))
                st.session_state.cli_web_obs = st.text_area("Observaciones (Opcional):", value=st.session_state.get('cli_web_obs', ''))
                
                st.divider()
                if st.button("Siguiente: Elegir Productos ➡️", type="primary", use_container_width=True):
                    if not st.session_state.cli_web_nombre or not st.session_state.cli_web_dir:
                        st.error("⚠️ Por favor completa tu Nombre y Dirección.")
                    else:
                        st.session_state.web_step = 2
                        st.rerun()

            # PASO 2: SELECTOR DE PRODUCTOS (ESTILO LOCAL)
            elif st.session_state.web_step == 2:
                st.subheader("2️⃣ Elegir Productos")
                
                prod_buscado = st.selectbox("Seleccionar producto del catálogo:", ["Seleccionar..."] + productos)
                if prod_buscado != "Seleccionar...":
                    medida_p = medidas.get(prod_buscado, "kg")
                    precio_orig = precios.get(prod_buscado, 0)
                    desc_p = descuentos.get(prod_buscado, 0)
                    p_final = precio_orig * (1 - desc_p/100)
                    
                    st.markdown(f"**Precio:** ${p_final:,.1f} por {medida_p}" + (f" ({desc_p}% OFF)" if desc_p > 0 else ""))
                    
                    if medida_p == "un":
                        cant_web = float(st.number_input("Cantidad (unidades):", min_value=0, step=1, key="w_un"))
                        cant_txt = f"{int(cant_web)}un"
                    else:
                        col_k, col_g = st.columns(2)
                        with col_k: kg_w = st.number_input("Kilos", min_value=0.0, step=1.0, key="w_kg")
                        with col_g: gr_w = st.number_input("Gramos", min_value=0.0, step=50.0, key="w_gr")
                        cant_web = kg_w + (gr_w / 1000.0)
                        cant_txt = f"{cant_web}kg"
                        
                    if cant_web > 0:
                        if st.button("➕ Agregar al Carrito Web", type="primary"):
                            subt = cant_web * p_final
                            ahorro_i = cant_web * (precio_orig - p_final)
                            st.session_state.carrito_web.append({
                                "producto": nombres_planos.get(prod_buscado, prod_buscado),
                                "cantidad": cant_web, "cantidad_txt": cant_txt,
                                "subtotal": subt, "ahorro": ahorro_i
                            })
                            st.success(f"✅ Agregado: {prod_buscado}")
                            st.rerun()

                if st.session_state.carrito_web:
                    st.markdown("#### 🛒 Tu Carrito Actual:")
                    tot_c = 0.0
                    for idx_cw, itw in enumerate(st.session_state.carrito_web):
                        st.write(f"• {itw['producto']} ({itw['cantidad_txt']}) — **${itw['subtotal']:,.1f}**")
                        tot_c += itw['subtotal']
                    st.markdown(f"**Total Parcial:** ${tot_c:,.1f}")

                st.divider()
                colA, colB = st.columns(2)
                with colA:
                    if st.button("⬅️ Atrás (Datos)", use_container_width=True):
                        st.session_state.web_step = 1
                        st.rerun()
                with colB:
                    if st.button("Revisar Pedido ➡️", type="primary", use_container_width=True):
                        if not st.session_state.carrito_web:
                            st.warning("⚠️ Agrega al menos un producto.")
                        else:
                            st.session_state.web_step = 3
                            st.rerun()

            # PASO 3: REVISIÓN
            elif st.session_state.web_step == 3:
                st.subheader("3️⃣ Revisión de tu Pedido")
                
                tot_web = sum(i['subtotal'] for i in st.session_state.carrito_web)
                st.markdown(f"**Cliente:** {st.session_state.cli_web_nombre.upper()}")
                st.markdown(f"**Dirección:** {st.session_state.cli_web_dir}")
                st.markdown("---")
                for itw in st.session_state.carrito_web:
                    st.markdown(f"• {itw['producto']} ({itw['cantidad_txt']}) — ${itw['subtotal']:,.1f}")
                st.markdown(f"### Total Estimado: **${tot_web:,.1f}**")
                st.warning("⚖️ El importe es estimado según el peso exacto en la balanza.")
                st.divider()
                
                colA, colB = st.columns(2)
                with colA:
                    if st.button("⬅️ Modificar Carrito", use_container_width=True):
                        st.session_state.web_step = 2
                        st.rerun()
                with colB:
                    if st.button("Confirmar y Guardar ➡️", type="primary", use_container_width=True):
                        filas_web = []
                        ahora = datetime.now(TZ_UY)
                        celular_formateado = limpiar_y_formatear_celular(st.session_state.cli_web_celular)
                        nombre_mayus = st.session_state.cli_web_nombre.upper()
                        
                        items_estructurados = []
                        for itw in st.session_state.carrito_web:
                            filas_web.append([
                                ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), "Web Online", 
                                nombre_mayus, itw['producto'], itw['cantidad'], itw['subtotal'], 
                                celular_formateado, "Pendiente Pago", "Web - Pendiente", 
                                st.session_state.cli_web_dir, itw['ahorro'], "{}"
                            ])
                            items_estructurados.append({"producto": itw['producto'], "cantidad": itw['cantidad'], "cantidad_txt": itw['cantidad_txt'], "subtotal": itw['subtotal'], "ahorro": itw['ahorro'], "tipo": "Propio"})
                        
                        json_items = json.dumps(items_estructurados)
                        for f_w in filas_web: f_w[12] = json_items 
                        if st.session_state.cli_web_obs: filas_web[0][4] += f" | 📝 Obs: {st.session_state.cli_web_obs}" 
                            
                        gc = conectar_google()
                        sh = gc.open_by_url(link_excel)
                        sh.worksheet("Registro de Ventas").append_rows(filas_web) 
                        
                        try:
                            ws_cli = sh.worksheet("Clientes")
                            nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                            if nombre_mayus not in nombres_existentes:
                                ws_cli.append_row([nombre_mayus, celular_formateado, "Web"])
                        except: pass
                        
                        limpiar_cache_ventas() 
                        cargar_datos_feria.clear() 
                        st.session_state.web_step = 4
                        st.rerun()

            # PASO 4: WHATSAPP OBLIGATORIO
            elif st.session_state.web_step == 4:
                st.subheader("4️⃣ Paso Final: Enviar WhatsApp")
                st.success("✅ ¡Pedido guardado con éxito!")
                st.markdown("⚠️ **Obligatorio:** Envía el aviso por WhatsApp para que te quede el comprobante en tu historial.")
                
                num_feriante_limpio = limpiar_y_formatear_celular(celular_feriante)
                if not num_feriante_limpio: num_feriante_limpio = "59893343092"
                
                tot_web = sum(i['subtotal'] for i in st.session_state.carrito_web)
                detalle_str = "\n".join([f"• {i['producto']} ({i['cantidad_txt']})" for i in st.session_state.carrito_web])
                msg_feriante = f"🛒 *NUEVO PEDIDO WEB*\n👤 Cliente: {st.session_state.cli_web_nombre.upper()}\n📍 Dirección: {st.session_state.cli_web_dir}\n💰 Total Est.: ${tot_web:,.1f}\n\n📦 *Mi Pedido:*\n{detalle_str}"
                
                st.link_button("📲 ENVIAR AVISO POR WHATSAPP (Obligatorio)", f"https://wa.me/{num_feriante_limpio}?text={urllib.parse.quote(msg_feriante)}", type="primary", use_container_width=True)
                
                st.divider()
                if st.button("🔄 Hacer otro pedido", use_container_width=True):
                    st.session_state.carrito_web = []
                    st.session_state.cli_web_obs = ""
                    st.session_state.web_step = 1
                    st.rerun()

        except Exception as e:
            st.error(f"Error en tienda web: {e}")
    st.stop()

# ==========================================
# 4. MODO PRIVADO Y LOGIN
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None
    st.session_state.es_super_admin = False

if st.session_state.usuario_logueado is None:
    st.title("🔒 Ingreso al Sistema")
    empresa_intento = st.text_input("Código de Empresa:", key="emp_norm").strip().upper()
    usuario_intento = st.text_input("Usuario:", key="usu_norm").strip()
    clave_intento = st.text_input("Contraseña:", type="password", key="cla_norm")
    
    if st.button("🚪 Ingresar", type="primary"):
        if empresa_intento == "MASTER" and clave_intento == "MiClaveSuperSecreta2026":
            st.session_state.usuario_logueado, st.session_state.rol_logueado = "SuperAdmin", "Admin"
            st.session_state.link_feria = obtener_datos_cliente("ILNONNO")
            st.session_state.es_super_admin = True
            st.rerun()
            
        link_excel = obtener_datos_cliente(empresa_intento)
        if link_excel == "SUSPENDIDO": st.error("❌ Cuenta suspendida.")
        elif link_excel:
            try:
                gc = conectar_google()
                sh = gc.open_by_url(link_excel)
                ws_nombres = [ws.title for ws in sh.worksheets()]
                ws_usuarios_nombre = next((n for n in ws_nombres if "usuario" in n.lower()), None)
                if not ws_usuarios_nombre: st.error("❌ Falta pestaña Usuarios.")
                else:
                    filas_usu = sh.worksheet(ws_usuarios_nombre).get_all_values()
                    if len(filas_usu) > 1:
                        cabeceras = [str(c).strip() if str(c).strip() else f"Col_{i}" for i, c in enumerate(filas_usu[0])]
                        df_usuarios = pd.DataFrame(filas_usu[1:], columns=cabeceras).astype(str)
                        col_usu = next((c for c in df_usuarios.columns if 'usuario' in c.lower()), None)
                        col_cla = next((c for c in df_usuarios.columns if 'clave' in c.lower() or 'contraseña' in c.lower()), None)
                        col_rol = next((c for c in df_usuarios.columns if 'rol' in c.lower()), None)
                        
                        if col_usu and col_cla:
                            valido = df_usuarios[(df_usuarios[col_usu].str.lower() == usuario_intento.lower()) & (df_usuarios[col_cla] == clave_intento)]
                            if not valido.empty:
                                st.session_state.usuario_logueado = usuario_intento
                                rol_bruto = valido.iloc[0].get(col_rol, 'Vendedor') if col_rol else 'Vendedor'
                                rol_limpio = str(rol_bruto).strip().capitalize()
                                if rol_limpio not in ["Admin", "Cajero", "Vendedor"]: rol_limpio = "Vendedor"
                                st.session_state.rol_logueado = rol_limpio
                                st.session_state.link_feria = link_excel
                                st.session_state.es_super_admin = False
                                st.rerun()
                            else: st.error("❌ Credenciales incorrectas.")
            except Exception as e: st.error(f"❌ Error: {e}")
        else: st.error("❌ Código inválido.")
    st.stop()

ventas_data_global = obtener_ventas(st.session_state.link_feria)

with st.sidebar:
    st.success(f"Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.carrito_vendedor = []
        st.session_state.cliente_retomado_aviso = ""
        st.rerun()

PRODUCTOS, PRECIOS, DESCUENTOS, MEDIDAS, NOMBRES, CLIENTES_DICT, CONFIG, MEDIDAS_PLANAS = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("nombre_empresa", CONFIG.get("nombre", "La Feria"))
celular_feriante_local = CONFIG.get("celular_feriante", CONFIG.get("celular_contacto", "59893343092"))

st.title(f"🏢 {nombre_empresa}")

# ==========================================
# 5. PESTAÑAS Y ROLES
# ==========================================
tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]: 
    tabs_nombres.append("📝 Tomar Pedido")
    tabs_nombres.append("🔄 Retomar Pedidos")
if st.session_state.rol_logueado in ["Admin", "Cajero"]: 
    tabs_nombres.append("💰 Caja y Cobro")
    tabs_nombres.append("🌐 Estado Pedidos Web")
    tabs_nombres.append("🛵 Entregas a Domicilio")
    tabs_nombres.append("💳 Control de Fiados")
if st.session_state.rol_logueado == "Admin": 
    tabs_nombres.append("📊 Panel Admin")
    tabs_nombres.append("📈 Reportes Pro")

tabs = st.tabs(tabs_nombres)
idx = 0

def ui_retomar_pedidos(ventas_data):
    st.write("### 🔄 Panel de Pedidos para Retomar")
    try:
        mis_pendientes = [p for p in agrupar_pedidos(ventas_data, ["En Caja", "Web - En Caja"]) if p['vendedor'] == st.session_state.usuario_logueado]
        
        if not mis_pendientes:
            st.info("No tienes pedidos tuyos esperando en la Caja.")
        else:
            for p in mis_pendientes:
                col_r1, col_r2 = st.columns([3,1])
                tipo_origen = "🌐 WEB" if "Web" in p['estado'] else "🏪 LOCAL"
                
                with col_r1: st.write(f"📦 **[{tipo_origen}] {p['cliente']}** - ${p['total']:,.1f} ({p['fecha']} - {p['hora']})")
                with col_r2:
                    if st.button("Retomar", key=f"ret_panel_{p['filas'][0]}"):
                        try:
                            items_rec = json.loads(p['json'])
                            if items_rec: st.session_state.carrito_vendedor = items_rec
                            else: st.session_state.carrito_vendedor = p['items']
                        except: st.session_state.carrito_vendedor = p['items']
                        
                        st.session_state.input_cliente_nombre = p['cliente']
                        st.session_state.input_cliente_celular = p['celular']
                        st.session_state.cliente_retomado_aviso = p['cliente']
                        
                        gc = conectar_google()
                        ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                        col_est = chr(65 + p['idx_est'])
                        updates = [{'range': f'{col_est}{f}', 'values': [["Cancelado (Retomado)"]]} for f in p['filas']]
                        ws.batch_update(updates)
                        
                        limpiar_cache_ventas()
                        st.session_state.v_rk += 1
                        st.success(f"✅ ¡Pedido recuperado! Ve a la pestaña '📝 Tomar Pedido'.")
                        st.rerun()
                st.markdown("---")
    except: pass

# =======================================================
# PESTAÑA 1: TOMAR PEDIDO
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    with tabs[idx]:
        if st.session_state.cliente_retomado_aviso:
            st.warning(f"⚠️ **ESTÁS EDITANDO EL PEDIDO RETOMADO DE:** `{st.session_state.cliente_retomado_aviso}`.")
            if st.button("❌ Quitar aviso"):
                st.session_state.cliente_retomado_aviso = ""
                st.rerun()

        col_m1, col_m2 = st.columns([3,1])
        with col_m1: 
            st.session_state.modo_vend = st.radio("Modo:", ["🛍️ Nueva Venta Local", "🌐 Armar Pedido Web"], horizontal=True, key="modo_v_radio")
        with col_m2: 
            if st.button("🔄 Sincronizar"): 
                limpiar_cache_ventas()
                st.rerun()
        st.divider()

        if st.session_state.modo_vend == "🛍️ Nueva Venta Local":
            st.markdown("### 👤 Paso 1: Datos del Cliente")
            def actualizar_cliente_seleccionado():
                sel = st.session_state.get(f"sel_cli_{st.session_state.v_rk}", "Escribir nuevo...")
                if sel != "Escribir nuevo...":
                    st.session_state.input_cliente_nombre = sel
                    st.session_state.input_cliente_celular = CLIENTES_DICT.get(sel, "")
                else:
                    st.session_state.input_cliente_nombre = ""
                    st.session_state.input_cliente_celular = ""

            lista_clientes_base = sorted(list(CLIENTES_DICT.keys())) if CLIENTES_DICT else []
            opciones_cli = ["Escribir nuevo..."] + lista_clientes_base
            index_def = 0
            if st.session_state.input_cliente_nombre in lista_clientes_base:
                index_def = opciones_cli.index(st.session_state.input_cliente_nombre)
                
            st.selectbox("Seleccionar Cliente:", opciones_cli, index=index_def, key=f"sel_cli_{st.session_state.v_rk}", on_change=actualizar_cliente_seleccionado)
            
            cliente_vendedor = st.text_input("Nombre y Apellido:", value=st.session_state.input_cliente_nombre, key=f"txt_cli_{st.session_state.v_rk}")
            celular_vendedor = st.text_input("Celular:", value=st.session_state.input_cliente_celular, placeholder="099...", key=f"txt_cel_{st.session_state.v_rk}")
            st.session_state.input_cliente_nombre = cliente_vendedor.strip().upper()
            st.session_state.input_cliente_celular = celular_vendedor

            st.divider()
            st.markdown("### 🛒 Paso 2: Productos")
            
            prod_buscado = st.selectbox("Buscar Producto:", ["Seleccionar..."] + PRODUCTOS, key=f"prod_b_{st.session_state.v_rk}")
            if prod_buscado != "Seleccionar...":
                medida_p = MEDIDAS.get(prod_buscado, "kg")
                if medida_p == "un":
                    cant = float(st.number_input("Cantidad (unidades)", min_value=0, step=1, key=f"uv_{st.session_state.v_rk}"))
                    formato_txt = f"{int(cant)}un"
                else:
                    c1, c2 = st.columns(2)
                    with c1: k_v = st.number_input("Kilos", min_value=0.0, step=1.0, key=f"kv_{st.session_state.v_rk}")
                    with c2: g_v = st.number_input("Gramos", min_value=0.0, step=50.0, key=f"gv_{st.session_state.v_rk}")
                    cant = k_v + (g_v / 1000.0)
                    formato_txt = f"{cant}kg"
                
                if cant > 0:
                    pr_orig = precios.get(prod_buscado, 0)
                    desc_p = descuentos.get(prod_buscado, 0)
                    pr_fin = pr_orig * (1 - desc_p/100)
                    subt = cant * pr_fin
                    if st.button("➕ Agregar al Carrito", key=f"btn_add_{st.session_state.v_rk}"):
                        st.session_state.carrito_vendedor.append({
                            "id": datetime.now().timestamp(), "producto": NOMBRES.get(prod_buscado, prod_buscado),
                            "cantidad": cant, "cantidad_txt": formato_txt, "subtotal": subt, "ahorro": cant*(pr_orig-pr_fin), "tipo": "Propio"
                        })
                        st.session_state.v_rk += 1
                        st.rerun()

            if st.session_state.carrito_vendedor:
                st.markdown("#### Resumen Carrito")
                tot_c = 0.0
                del_idx = []
                for i, item in enumerate(st.session_state.carrito_vendedor):
                    st.write(f"• {item['producto']} ({item['cantidad_txt']}) — ${item['subtotal']:,.1f}")
                    tot_c += item['subtotal']
                    if st.button("❌ Borrar", key=f"del_{item.get('id', i)}_{i}"): del_idx.append(i)
                if del_idx:
                    for di in sorted(del_idx, reverse=True): st.session_state.carrito_vendedor.pop(di)
                    st.rerun()

                st.markdown(f"### Total: **${tot_c:,.1f}**")
                st.divider()

                if st.button("🚀 Enviar a Caja", type="primary", use_container_width=True):
                    if not st.session_state.input_cliente_nombre:
                        st.error("⚠️ Falta el nombre del cliente.")
                    else:
                        ahora = datetime.now(TZ_UY)
                        cel_f = limpiar_y_formatear_celular(st.session_state.input_cliente_celular)
                        items_json = json.dumps(st.session_state.carrito_vendedor)
                        filas = []
                        for item in st.session_state.carrito_vendedor:
                            filas.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), st.session_state.usuario_logueado, st.session_state.input_cliente_nombre, item['producto'], item['cantidad'], item['subtotal'], cel_f, "Efectivo", "En Caja", "", item.get('ahorro', 0), items_json])
                        
                        gc = conectar_google()
                        gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas").append_rows(filas)
                        limpiar_cache_ventas()
                        st.session_state.carrito_vendedor = []
                        st.session_state.cliente_retomado_aviso = ""
                        st.success("✅ Pedido enviado a caja con éxito!")
                        st.rerun()
        else:
            # ARMAR PEDIDO WEB
            st.write("### 📦 Armar Pedido Web (Ajuste Balanza)")
            try:
                pedidos_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente"])
                if not pedidos_web:
                    st.info("No hay pedidos web pendientes.")
                else:
                    opciones_w = ["Seleccionar..."] + [f"{p['fecha']} | {p['cliente']} (ID {p['filas'][0]})" for p in pedidos_web]
                    sel_w = st.selectbox("Seleccionar pedido web:", opciones_w)
                    if sel_w != "Seleccionar...":
                        idx_w = int(sel_w.split("(ID ")[1].replace(")", ""))
                        p_sel = next(x for x in pedidos_web if x["filas"][0] == idx_w)
                        
                        st.write(f"👤 **Cliente:** {p_sel['cliente']} | 📍 **Dir:** {p_sel['direccion']}")
                        tot_real = 0.0
                        nuevos_i = []
                        
                        for idx_item, it in enumerate(p_sel["items"]):
                            medida_p = MEDIDAS_PLANAS.get(it["producto"], "kg")
                            st.write(f"🛍️ **{it['producto']}**")
                            if medida_p == "un":
                                p_real = st.number_input("Real (un):", value=float(it['cantidad']), step=1.0, key=f"w_un_{idx_w}_{idx_item}")
                            else:
                                k_in = int(it['cantidad'])
                                g_in = (it['cantidad'] - k_in) * 1000
                                c1, c2 = st.columns(2)
                                with c1: kr = st.number_input("Kilos", value=float(k_in), step=1.0, key=f"w_k_{idx_w}_{idx_item}")
                                with c2: gr = st.number_input("Gramos", value=float(g_in), step=50.0, key=f"w_g_{idx_w}_{idx_item}")
                                p_real = kr + (gr / 1000.0)
                            
                            pr_u = precios.get(it["producto"], precios.get(nombres_planos.get(it["producto"], it["producto"]), 100))
                            desc_u = descuentos.get(it["producto"], 0)
                            sub_r = p_real * (pr_u * (1 - desc_u/100))
                            tot_real += sub_r
                            c_txt = f"{int(p_real)}un" if medida_p == "un" else f"{p_real}kg"
                            nuevos_i.append({"producto": it["producto"], "cantidad": p_real, "cantidad_txt": c_txt, "subtotal": sub_r, "ahorro": p_real*(pr_u*(desc_u/100)), "tipo": "Propio"})
                        
                        st.markdown(f"### Total Ajustado: **${tot_real:,.1f}**")
                        if st.button("⚖️ Confirmar y Enviar a Caja", type="primary"):
                            gc = conectar_google()
                            ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            col_est = chr(65 + p_sel['idx_est'])
                            ws.batch_update([{'range': f'{col_est}{f}', 'values': [["Cancelado (Ajustado)"]]} for f in p_sel["filas"]])
                            
                            ahora = datetime.now(TZ_UY)
                            filas_nuevas = []
                            json_str = json.dumps(nuevos_i)
                            for ni in nuevos_i:
                                filas_nuevas.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), st.session_state.usuario_logueado, p_sel["cliente"], ni['producto'], ni['cantidad'], ni['subtotal'], p_sel["celular"], "Pendiente Pago", "Web - En Caja", p_sel["direccion"], ni['ahorro'], json_str])
                            ws.append_rows(filas_nuevas)
                            limpiar_cache_ventas()
                            st.success("✅ ¡Ajustado y enviado a caja!")
                            st.rerun()
            except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 2: RETOMAR PEDIDOS
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    with tabs[idx]:
        ui_retomar_pedidos(ventas_data_global)
    idx += 1

# =======================================================
# PESTAÑA 3: CAJA Y COBRO
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Caja y Cobro General")
        try:
            pedidos_caja = agrupar_pedidos(ventas_data_global, ["En Caja", "Web - En Caja"])
            if not pedidos_caja:
                st.info("No hay pedidos en caja.")
            else:
                sel_cj = st.selectbox("Seleccionar pedido para cobrar:", ["Seleccionar..."] + [f"{p['fecha']} | {p['cliente']} (${p['total']}) (ID {p['filas'][0]})" for p in pedidos_caja])
                if sel_cj != "Seleccionar...":
                    id_cj = int(sel_cj.split("(ID ")[1].replace(")", ""))
                    p_cj = next(x for x in pedidos_caja if x['filas'][0] == id_cj)
                    
                    st.write(f"👤 **Cliente:** {p_cj['cliente']} | **Total:** ${p_cj['total']:,.1f}")
                    pago_sel = st.selectbox("Forma de pago:", ["Efectivo", "Tarjeta", "MercadoPago", "FIADO"], key="c_pago_sel")
                    
                    if st.button("💵 Cerrar Cobro", type="primary"):
                        gc = conectar_google()
                        ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                        col_p = chr(65 + p_cj['idx_pago'])
                        col_e = chr(65 + p_cj['idx_est'])
                        
                        est_f = "Fiado Pendiente" if pago_sel == "FIADO" else "Cobrado"
                        if "Web" in p_cj['estado']: est_f = "Web - " + est_f
                        
                        upd = []
                        for f in p_cj['filas']:
                            upd.append({'range': f'{col_p}{f}', 'values': [[pago_sel]]})
                            upd.append({'range': f'{col_e}{f}', 'values': [[est_f]]})
                        ws.batch_update(upd)
                        limpiar_cache_ventas()
                        
                        msg = f"👋 Hola {p_cj['cliente']}, registramos tu pago de ${p_cj['total']:,.1f} ({pago_sel}). ¡Gracias!"
                        st.success("✅ ¡Cobro registrado con éxito!")
                        st.link_button("📲 Enviar WhatsApp", f"https://wa.me/{limpiar_y_formatear_celular(p_cj['celular'])}?text={urllib.parse.quote(msg)}", type="primary")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 4: ESTADO DE LOS PEDIDOS WEB
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 🌐 Estado de los Pedidos Web")
        try:
            p_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente", "Web - En Caja"])
            if not p_web: st.info("No hay pedidos web activos.")
            else:
                for pw in p_web:
                    st.write(f"• **{pw['cliente']}** | Estado: `{pw['estado']}` | Monto: ${pw['total']:,.1f} | Dir: {pw['direccion']}")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 5: ENTREGAS A DOMICILIO (SIN COBRO, SOLO LOGÍSTICA)
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 🛵 Control de Entregas a Domicilio (Logística)")
        try:
            todas = agrupar_pedidos(ventas_data_global)
            entregas = [e for e in todas if e['estado'] in ["Cobrado", "Fiado Pendiente", "Pendiente Pago", "Web - Cobrado", "Web - Fiado Pendiente", "Web - Pendiente Pago", "Entregado"] and e["direccion"].strip() != ""]
            
            if not entregas: st.info("No hay entregas pendientes.")
            else:
                for ent in entregas:
                    st.write(f"🏠 **{ent['cliente']}** - {ent['direccion']} | Estado: `{ent['estado']}`")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("🛵 Marcar Entregado", key=f"ent_ok_{ent['filas'][0]}"):
                            gc = conectar_google()
                            ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            col_e = chr(65 + ent['idx_est'])
                            ws.batch_update([{'range': f'{col_e}{f}', 'values': [["Entregado"]]} for f in ent['filas']])
                            limpiar_cache_ventas()
                            st.rerun()
                    with c2:
                        st.link_button("📲 Avisar 'Va en Camino'", f"https://wa.me/{limpiar_y_formatear_celular(ent['celular'])}?text={urllib.parse.quote(f'Hola {ent[\"cliente\"]}. Tu pedido va en camino a tu domicilio.')}")
                    st.markdown("---")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 6: CONTROL DE FIADOS (CUENTAS CORRIENTES)
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Control de Fiados y Cuentas Corrientes")
        try:
            todas_o = agrupar_pedidos(ventas_data_global)
            fiados_activos = [o for o in todas_o if "fiado" in o['pago'].lower() or "fiado" in o['estado'].lower()]
            
            # Agrupar por cliente
            clientes_fiado = {}
            for f_ord in fiados_activos:
                cli = f_ord['cliente']
                if cli not in clientes_dewar: clientes_fiado[cli] = {"total": 0.0, "pedidos": []}
                # Solo sumar si no está cancelado
                if "cancelado" not in f_ord['estado'].lower():
                    clientes_fiado[cli]["total"] += f_ord['total']
                    clientes_fiado[cli]["pedidos"].append(f_ord)
                    
            if not clientes_fiado:
                st.info("ℹ️ No hay clientes con cuentas fiadas pendientes.")
            else:
                for c_name, c_info in clientes_fiado.items():
                    if c_info["total"] > 0:
                        with st.expander(f"👤 {c_name} — Deuda Total: ${c_info['total']:,.1f}"):
                            for p_det in c_info["pedidos"]:
                                origen_t = "Web" if "Web" in p_det['estado'] else "Local"
                                st.write(f"• [{origen_t}] {p_det['fecha']} | Detalle: {p_det['detalle']} | **${p_det['total']:,.1f}**")
                            
                            pago_parcial = st.number_input(f"Monto que paga {c_name} ($):", min_value=0.0, max_value=c_info["total"], step=100.0, key=f"pago_f_{c_name}")
                            if st.button(f"💵 Registrar Pago / Abono de {c_name}", key=f"btn_pf_{c_name}", type="primary"):
                                nuevo_saldo = c_info["total"] - pago_parcial
                                cel_cliente = c_info["pedidos"][0]['celular']
                                
                                if nuevo_saldo <= 0:
                                    msg_wsp = f"👋 Hola {c_name}, registramos tu pago de ${pago_parcial:,.1f}. ✅ ¡Tu deuda ha sido saldada por completo! Muchas gracias."
                                    # Marcar como cobrado el primer pedido o todos si canceló completo
                                    gc = conectar_google()
                                    ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                    for pd in c_info["pedidos"]:
                                        col_e = chr(65 + pd['idx_est'])
                                        ws.batch_update([{'range': f'{col_e}{f}', 'values': [["Cobrado"]]} for f in pd['filas']])
                                else:
                                    msg_wsp = f"👋 Hola {c_name}, registramos tu pago/abono de ${pago_parcial:,.1f}. ⚠️ Te queda un saldo pendiente de ${nuevo_saldo:,.1f}."
                                
                                limpiar_cache_ventas()
                                st.success("✅ ¡Pago registrado con éxito!")
                                st.link_button("📲 Enviar WhatsApp del Estado de Cuenta", f"https://wa.me/{limpiar_y_formatear_celular(cel_cliente)}?text={urllib.parse.quote(msg_wsp)}", type="primary")
                                st.rerun()
        except Exception as e: st.error(f"Error cargando fiados: {e}")
    idx += 1

# =======================================================
# PESTAÑA 7: PANEL ADMIN
# =======================================================
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📊 Panel Admin")
        try:
            ordenes_admin = agrupar_pedidos(ventas_data_global, None)
            tot_neto = sum(p['total'] for p in ordenes_admin if "cancelado" not in p['estado'].lower() and "caja" not in p['estado'].lower() and "pendiente" not in p['estado'].lower() and "fiado" not in p['pago'].lower())
            st.metric("Recaudación Neta (Cobrada)", f"${tot_neto:,.1f}")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 8: REPORTES PRO
# =======================================================
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📈 Reportes Pro")
        st.info("Módulo de analítica avanzada disponible.")
    idx += 1
