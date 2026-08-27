import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 1. CONFIGURACIÓN INICIAL
# ==========================================
st.set_page_config(page_title="App Ferias - SaaS", layout="centered", initial_sidebar_state="collapsed")
TZ_UY = timezone(timedelta(hours=-3))

LINK_MASTER_SHEET = "https://docs.google.com/spreadsheets/d/1CEuvlAwExOf1FS_ZYeFYw205aoVePb8SCmmLjUJTg-w/edit?gid=0#gid=0"

if 'v_rk' not in st.session_state: st.session_state.v_rk = 0 
if 'c_rk' not in st.session_state: st.session_state.c_rk = 0 
if 'carrito_vendedor' not in st.session_state: st.session_state.carrito_vendedor = []
if 'cli_v_temp' not in st.session_state: st.session_state.cli_v_temp = ""
if 'cel_v_temp' not in st.session_state: st.session_state.cel_v_temp = ""
if 'modo_vend' not in st.session_state: st.session_state.modo_vend = "🛍️ Nueva Venta Local"

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
    if str(celular_ingresado).strip().startswith("+"): return num
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
        
        if idx_est == 10:
            idx_pago, idx_dir = 9, 8
        else:
            idx_pago, idx_dir = 8, 10
            
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
        # Si el JSON guardado estaba vacío, se genera un respaldo con los ítems leídos
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
        
    productos, precios, descuentos, nombres_planos = [], {}, {}, {}
    try:
        ws_prod = sh.worksheet("Productos")
        for fila in ws_prod.get_all_values()[1:]:
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
                
                prod_full = f"{emoji} {nombre}"
                productos.append(prod_full)
                precios[prod_full] = precio
                descuentos[prod_full] = desc
                nombres_planos[prod_full] = nombre
    except: pass

    clientes_dict = {}
    try:
        ws_cli = sh.worksheet("Clientes")
        for fila in ws_cli.get_all_values()[1:]:
            if len(fila) >= 1 and fila[0].strip() and fila[0].strip().lower() != "nombre":
                nombre_c = fila[0].strip()
                celular_c = fila[1].strip() if len(fila) > 1 else ""
                clientes_dict[nombre_c] = celular_c
    except: pass
    
    return productos, precios, descuentos, nombres_planos, clientes_dict, config

# ==========================================
# 3. MODO TIENDA PÚBLICA
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel and link_excel != "SUSPENDIDO":
        try:
            productos, precios, descuentos, nombres_planos, clientes_dict, config = cargar_datos_feria(link_excel)
            nombre_feria = config.get("nombre_empresa", "Nuestra Feria")
            celular_feriante = config.get("celular_feriante", config.get("celular_contacto", "59893343092"))
            
            st.title(f"🛒 {nombre_feria}")
            st.markdown("Elige tus productos, completa tus datos y envía tu pedido directo a la feria.")
            st.divider()
            
            st.subheader("1️⃣ Tus Datos de Envío")
            nombre_cliente = st.text_input("Nombre y Apellido:")
            celular_cliente = st.text_input("Celular (Ej: 099123456 o +549...):", placeholder="099123456")
            direccion_cliente = st.text_input("Dirección de Envío (Calle, Nro y Esquina):")
            observaciones_cliente = st.text_area("Observaciones para el armado (Opcional):")
            
            st.divider()
            st.subheader("2️⃣ Armá tu Pedido")
            
            cantidades_seleccionadas = {}
            unidades_seleccionadas = {}
            
            for prod_full in productos:
                precio = precios.get(prod_full, 0)
                descuento = descuentos.get(prod_full, 0)
                precio_final = precio * (1 - (descuento / 100)) if descuento > 0 else precio
                label_precio = f"${precio_final:,.1f} (¡{descuento}% OFF!)" if descuento > 0 else f"${precio:,.1f}"
                
                st.markdown(f"**{prod_full}** — *Precio:* {label_precio}")
                tipo_medida_web = st.radio("Medida:", ["Kilos (kg)", "Unidades (un)"], horizontal=True, key=f"rmed_{prod_full}")
                
                if tipo_medida_web == "Kilos (kg)":
                    cantidades_seleccionadas[prod_full] = st.number_input(f"Cantidad (kg)", min_value=0.0, step=0.5, format="%.1f", key=f"wkg_{prod_full}")
                else:
                    unidades_seleccionadas[prod_full] = st.number_input(f"Cantidad (un)", min_value=0, step=1, key=f"wun_{prod_full}")
                st.markdown("---")
            
            if st.button("🚀 Enviar Pedido a la Feria", type="primary", use_container_width=True):
                if not nombre_cliente or not celular_cliente or not direccion_cliente:
                    st.error("⚠️ Por favor completa tu Nombre, Celular y Dirección de Envío.")
                else:
                    filas_web = []
                    ahora = datetime.now(TZ_UY)
                    celular_formateado = limpiar_y_formatear_celular(celular_cliente)
                    
                    items_estructurados = []
                    for p, c in cantidades_seleccionadas.items():
                        if c > 0:
                            n_plano = nombres_planos[p]
                            subt = c * (precios[p] * (1 - descuentos[p]/100))
                            ahor = c * (precios[p] * (descuentos[p]/100))
                            filas_web.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), "Web Online", nombre_cliente.strip(), n_plano, c, subt, celular_formateado, "Pendiente Pago", "Web - Pendiente", direccion_cliente, ahor, "{}"])
                            items_estructurados.append({"producto": n_plano, "cantidad": c, "cantidad_txt": f"{c}kg", "subtotal": subt, "ahorro": ahor, "tipo": "Propio"})
                    for p, u in unidades_seleccionadas.items():
                        if u > 0:
                            n_plano = nombres_planos[p]
                            subt = u * (precios[p] * (1 - descuentos[p]/100))
                            ahor = u * (precios[p] * (descuentos[p]/100))
                            filas_web.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), "Web Online", nombre_cliente.strip(), n_plano, u, subt, celular_formateado, "Pendiente Pago", "Web - Pendiente", direccion_cliente, ahor, "{}"])
                            items_estructurados.append({"producto": n_plano, "cantidad": u, "cantidad_txt": f"{int(u)}un", "subtotal": subt, "ahorro": ahor, "tipo": "Propio"})
                            
                    if not filas_web:
                        st.warning("⚠️ No has seleccionado ningún producto.")
                    else:
                        json_items = json.dumps(items_estructurados)
                        for f_w in filas_web: f_w[12] = json_items 
                        
                        if observaciones_cliente: filas_web[0][4] += f" | 📝 Obs: {observaciones_cliente}" 
                            
                        gc = conectar_google()
                        sh = gc.open_by_url(link_excel)
                        sh.worksheet("Registro de Ventas").append_rows(filas_web) 
                        
                        try:
                            ws_cli = sh.worksheet("Clientes")
                            nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                            if nombre_cliente.strip().lower() not in nombres_existentes:
                                ws_cli.append_row([nombre_cliente.strip(), celular_formateado, "Web"])
                        except: pass
                        
                        limpiar_cache_ventas() 
                        cargar_datos_feria.clear() 
                        
                        st.success("✅ ¡Muchas gracias por tu compra! A la brevedad será armada y despachada.")
                        
                        num_feriante_limpio = limpiar_y_formatear_celular(celular_feriante)
                        if not num_feriante_limpio: num_feriante_limpio = "59893343092"
                        msg_feriante = f"🛒 *NUEVO PEDIDO WEB*\n👤 Cliente: {nombre_cliente}\n📍 Dirección: {direccion_cliente}"
                        st.link_button("📲 Enviar Aviso al Feriante por WhatsApp", f"https://wa.me/{num_feriante_limpio}?text={urllib.parse.quote(msg_feriante)}")
        except Exception as e:
            st.error(f"Error cargando la tienda online: {e}")
    else:
        st.error("Feria no encontrada o inactiva.")
    st.stop()

# ==========================================
# 4. MODO PRIVADO Y ACCESO
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
                if not ws_usuarios_nombre: st.error("❌ No existe pestaña 'Usuarios' en el Excel.")
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
                            else: st.error("❌ Usuario o Contraseña incorrectos.")
                        else: st.error("❌ Faltan columnas 'Usuario' y 'Clave'.")
            except Exception as e: st.error(f"❌ Error de permisos: {e}")
        else: st.error("❌ Código de empresa inválido.")
    st.stop()

ventas_data_global = obtener_ventas(st.session_state.link_feria)

with st.sidebar:
    st.success(f"Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.carrito_vendedor = []
        if 'msg_vendedor' in st.session_state: del st.session_state.msg_vendedor
        st.rerun()

PRODUCTOS, PRECIOS, DESCUENTOS, NOMBRES, CLIENTES_DICT, CONFIG = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("nombre_empresa", "La Feria")
celular_feriante_local = CONFIG.get("celular_feriante", CONFIG.get("celular_contacto", "59893343092"))

st.title(f"🏢 {nombre_empresa}")

tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]: tabs_nombres.append("⚖️ Toma de Pedidos")
if st.session_state.rol_logueado in ["Admin", "Cajero"]: 
    tabs_nombres.append("💰 Caja y Cobro")
    tabs_nombres.append("🌐 Pedidos Web")
    tabs_nombres.append("🛵 Entregas")
if st.session_state.rol_logueado == "Admin": 
    tabs_nombres.append("📊 Panel Admin")

tabs = st.tabs(tabs_nombres)
idx = 0

def ui_retomar_pedidos(ventas_data):
    st.write("### 🔄 Pedidos Enviados a Caja (Aún no cobrados)")
    try:
        mis_pendientes = [p for p in agrupar_pedidos(ventas_data, ["En Caja", "Web - En Caja"]) if p['vendedor'] == st.session_state.usuario_logueado]
        
        if not mis_pendientes:
            st.info("No tienes pedidos tuyos esperando en la Caja.")
        else:
            for p in mis_pendientes:
                col_r1, col_r2 = st.columns([3,1])
                tipo_origen = "🌐 WEB" if "Web" in p['estado'] else "🏪 LOCAL"
                
                with col_r1: st.write(f"📦 **[{tipo_origen}] {p['cliente']}** - ${p['total']:,.1f} (Hora: {p['hora']})")
                with col_r2:
                    if st.button("Retomar", key=f"ret_{p['filas'][0]}"):
                        try:
                            items_rec = json.loads(p['json'])
                            if items_rec:
                                st.session_state.carrito_vendedor = items_rec
                            else:
                                st.session_state.carrito_vendedor = p['items']
                        except:
                            st.session_state.carrito_vendedor = p['items']
                        
                        st.session_state.cli_v_temp = p['cliente']
                        st.session_state.cel_v_temp = p['celular']
                        
                        gc = conectar_google()
                        ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                        
                        col_est = chr(65 + p['idx_est'])
                        updates = [{'range': f'{col_est}{f}', 'values': [["Cancelado (Retomado)"]]} for f in p['filas']]
                        ws.batch_update(updates)
                        
                        limpiar_cache_ventas()
                        st.session_state.v_rk += 1
                        st.session_state.modo_vend = "🛍️ Nueva Venta Local"
                        st.toast(f"✅ Pedido de {p['cliente']} recuperado.", icon="🔄")
                        st.rerun()
    except: pass


# =======================================================
# PESTAÑA 1: VENDEDOR
# =======================================================
with tabs[idx]:
    col_m1, col_m2 = st.columns([3,1])
    with col_m1: 
        st.session_state.modo_vend = st.radio("Modo de trabajo:", ["🛍️ Nueva Venta Local", "🌐 Armar Pedido Web", "🔄 Retomar Pedido"], horizontal=True, key="modo_v_radio")
    with col_m2: 
        if st.button("🔄 Sincronizar"): 
            limpiar_cache_ventas()
            st.rerun()
    st.divider()

    if st.session_state.modo_vend == "🛍️ Nueva Venta Local":
        st.write("### 📝 Armar Carrito de Compra")
        
        opciones_cli = ["Escribir nuevo..."] + list(CLIENTES_DICT.keys()) if CLIENTES_DICT else ["Escribir nuevo..."]
        tipo_cli_sel = st.selectbox("Seleccionar Cliente de la Base:", opciones_cli)
        
        if tipo_cli_sel == "Escribir nuevo...":
            cliente_vendedor = st.text_input("Nombre del Cliente:", value=st.session_state.get('cli_v_temp', ''))
            celular_vendedor = st.text_input("Celular (Opcional):", value=st.session_state.get('cel_v_temp', ''), placeholder="099123456")
        else:
            cliente_vendedor = tipo_cli_sel
            celular_sugerido = CLIENTES_DICT.get(cliente_vendedor, "")
            celular_vendedor = st.text_input("Celular del Cliente (Puedes editarlo si cambió):", value=celular_sugerido)

        tipo_ingreso = st.radio("Tipo de ítem:", ["Catálogo de Productos", "Ítem Manual / Libre"], horizontal=True)
        
        if tipo_ingreso == "Catálogo de Productos":
            prod_buscado = st.selectbox("Buscar Producto:", ["Seleccionar..."] + PRODUCTOS)
            if prod_buscado != "Seleccionar...":
                tipo_medida = st.radio("Forma de venta:", ["Kilos / Gramos", "Unidades"], horizontal=True)
                
                if tipo_medida == "Kilos / Gramos":
                    col1, col2 = st.columns(2)
                    with col1: kilos = st.number_input("Kilos:", min_value=0.0, step=1.0, key=f"kv_{st.session_state.v_rk}")
                    with col2: gramos = st.number_input("Gramos:", min_value=0.0, step=50.0, key=f"gv_{st.session_state.v_rk}")
                    cant = kilos + (gramos / 1000.0)
                    formato_txt = f"{cant}kg"
                else:
                    unidades = st.number_input("Unidades:", min_value=0, step=1, key=f"uv_{st.session_state.v_rk}")
                    cant = float(unidades)
                    formato_txt = f"{int(cant)}un"
                
                if cant > 0:
                    precio_orig = PRECIOS.get(prod_buscado, 0)
                    desc_pct = DESCUENTOS.get(prod_buscado, 0)
                    precio_final = precio_orig * (1 - (desc_pct / 100))
                    subtotal = cant * precio_final
                    ahorro_item = cant * (precio_orig - precio_final)
                    
                    st.info(f"Subtotal: **${subtotal:,.1f}**" + (f" (Ahorro de ${ahorro_item:,.1f})" if ahorro_item>0 else ""))
                    
                    if st.button("➕ Agregar al Carrito"):
                        st.session_state.carrito_vendedor.append({
                            "id": datetime.now().timestamp(), "producto": NOMBRES.get(prod_buscado),
                            "cantidad": cant, "cantidad_txt": formato_txt, "subtotal": subtotal, "ahorro": ahorro_item, "tipo": "Propio"
                        })
                        st.session_state.v_rk += 1
                        st.rerun()
        else:
            desc_manual = st.text_input("Descripción del ítem manual:", key=f"dm_{st.session_state.v_rk}")
            precio_manual = st.number_input("Precio Total ($):", min_value=0.0, step=10.0, key=f"pm_{st.session_state.v_rk}")
            es_ajeno = st.selectbox("¿Este ítem es Propio o Ajeno?", ["Propio", "Ajeno"], key=f"pa_{st.session_state.v_rk}")
            if st.button("➕ Agregar Ítem Manual"):
                if desc_manual and precio_manual > 0:
                    st.session_state.carrito_vendedor.append({
                        "id": datetime.now().timestamp(), "producto": desc_manual,
                        "cantidad": 1.0, "cantidad_txt": "1un", "subtotal": precio_manual, "ahorro": 0.0, "tipo": es_ajeno
                    })
                    st.session_state.v_rk += 1
                    st.rerun()

        if st.session_state.carrito_vendedor:
            st.divider()
            st.subheader("🛒 Carrito Actual")
            total_carrito, total_ahorro = 0.0, 0.0
            indices_a_borrar = []
            
            for i, item in enumerate(st.session_state.carrito_vendedor):
                t_item = item.get('tipo', 'Propio')
                c_txt = item.get('cantidad_txt', str(item.get('cantidad', 1)))
                
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1: st.markdown(f"**{item['producto']}** (Cant: {c_txt}) - **${item['subtotal']:,.1f}** *[{t_item}]*")
                with c2: 
                    total_carrito += item['subtotal']
                    total_ahorro += item.get('ahorro', 0.0)
                with c3:
                    if st.button("❌", key=f"del_{item['id']}"): indices_a_borrar.append(i)
            
            if indices_a_borrar:
                for index in sorted(indices_a_borrar, reverse=True): st.session_state.carrito_vendedor.pop(index)
                st.rerun()

            st.markdown(f"### Total: **${total_carrito:,.1f}**")
            if total_ahorro > 0: st.success(f"🎉 Ahorro Total para el cliente: ${total_ahorro:,.1f}")
            
            if st.button("🚀 Enviar a Caja", type="primary"):
                if not cliente_vendedor: st.error("⚠️ Ingresa el nombre del cliente.")
                else:
                    det = " | ".join([f"{r['producto']}: {r.get('cantidad_txt', str(r.get('cantidad', 1)))} ({r.get('tipo', 'Propio')})" for r in st.session_state.carrito_vendedor])
                    items_json = json.dumps(st.session_state.carrito_vendedor)
                    celular_limpio = limpiar_y_formatear_celular(celular_vendedor)
                    ahora = datetime.now(TZ_UY)
                    
                    filas_a_insertar = []
                    for item in st.session_state.carrito_vendedor:
                        filas_a_insertar.append([
                            ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                            st.session_state.usuario_logueado, cliente_vendedor, 
                            item['producto'], item['cantidad'], item['subtotal'], 
                            celular_limpio, "Efectivo", "En Caja", "", item.get('ahorro', 0.0), items_json
                        ])
                        
                    gc = conectar_google()
                    sh_feria = gc.open_by_url(st.session_state.link_feria)
                    sh_feria.worksheet("Registro de Ventas").append_rows(filas_a_insertar)
                    
                    try:
                        ws_cli = sh_feria.worksheet("Clientes")
                        nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                        if cliente_vendedor.strip().lower() not in nombres_existentes:
                            ws_cli.append_row([cliente_vendedor.strip(), celular_limpio, "Local"])
                    except: pass
                    
                    limpiar_cache_ventas()
                    st.session_state.msg_vendedor = "✅ ¡Pedido enviado a la Caja exitosamente!"
                    
                    num_cajero = limpiar_y_formatear_celular(celular_feriante_local)
                    if not num_cajero: num_cajero = "59893343092"
                    st.session_state.link_vendedor = f"https://wa.me/{num_cajero}?text={urllib.parse.quote(f'💳 *NUEVO PEDIDO EN CAJA*\n👨‍💼 Vendedor: {st.session_state.usuario_logueado}\n👤 Cliente: {cliente_vendedor}\n💰 Total a cobrar: ${total_carrito:,.1f}\n📦 Detalle: {det}')}"
                    
                    # LIMPIEZA ABSOLUTA DE MEMORIA Y ESTADO PARA NUEVA VENTA
                    st.session_state.carrito_vendedor = []
                    st.session_state.cli_v_temp = ""
                    st.session_state.cel_v_temp = ""
                    st.session_state.v_rk += 1
                    st.rerun()

        # BLOQUE DE WHATSAPP VISIBLE EN TOMA DE PEDIDOS
        if 'msg_vendedor' in st.session_state:
            st.success(st.session_state.msg_vendedor)
            if 'link_vendedor' in st.session_state and st.session_state.link_vendedor:
                st.link_button("📲 Avisar al Cajero (Enviar WhatsApp)", st.session_state.link_vendedor, type="primary")
            if st.button("✅ Crear Nuevo Pedido / Seguir Trabajando", type="secondary"):
                del st.session_state.msg_vendedor
                if 'link_vendedor' in st.session_state: del st.session_state.link_vendedor
                st.session_state.cli_v_temp = ""
                st.session_state.cel_v_temp = ""
                st.session_state.carrito_vendedor = []
                st.session_state.v_rk += 1
                st.rerun()

        st.divider()
        ui_retomar_pedidos(ventas_data_global)

    elif st.session_state.modo_vend == "🔄 Retomar Pedido":
        ui_retomar_pedidos(ventas_data_global)

    elif st.session_state.modo_vend == "🌐 Armar Pedido Web":
        st.write("### 📦 Armar Pedido Web (Ajuste de Pesos en Balanza)")
        try:
            pedidos_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente"])
            
            if not pedidos_web:
                st.info("No hay pedidos web pendientes para armar.")
            else:
                opciones_web = ["Seleccionar..."] + [f"{p['hora']} | {p['cliente']} - (ID {p['filas'][0]})" for p in pedidos_web]
                sel_web = st.selectbox("Selecciona el pedido a preparar:", opciones_web)
                
                if sel_web != "Seleccionar...":
                    idx_selec = int(sel_web.split("(ID ")[1].replace(")", ""))
                    pedido_sel = next(p for p in pedidos_web if p["filas"][0] == idx_selec)
                    
                    st.write(f"👤 **Cliente:** {pedido_sel['cliente']} | 📱 **Celular:** {pedido_sel['celular']}")
                    st.write(f"📍 **Dirección:** {pedido_sel['direccion']}")
                    st.divider()
                    
                    total_real_calculado, total_ahorro_web = 0.0, 0.0
                    nuevos_items = []
                    
                    st.markdown("#### Ingresa el peso/cant real de la balanza:")
                    for idx_item, item in enumerate(pedido_sel["items"]):
                        prod_name = item["producto"]
                        if "📝 Obs:" in prod_name: continue
                        
                        try: cant_val = float(''.join(c for c in str(item["cantidad"]) if c.isdigit() or c=='.'))
                        except: cant_val = 1.0
                        
                        col_a, col_b = st.columns([1, 1])
                        with col_a: st.write(f"🛍️ **{prod_name}**")
                        with col_b:
                            peso_real = st.number_input("Real (kg o un):", value=float(cant_val), step=0.1, key=f"adj_{idx_item}_{st.session_state.v_rk}")
                        
                        precio_unitario, descuento_aplicado = 0.0, 0.0
                        for p_full in PRECIOS.keys():
                            if prod_name in p_full:
                                precio_unitario = PRECIOS[p_full]
                                descuento_aplicado = DESCUENTOS.get(p_full, 0.0)
                                break
                                
                        precio_final = precio_unitario * (1 - (descuento_aplicado / 100))
                        sub_real = peso_real * precio_final
                        ahorro_real = peso_real * (precio_unitario - precio_final)
                        
                        total_real_calculado += sub_real
                        total_ahorro_web += ahorro_real
                        
                        nuevos_items.append({"producto": prod_name, "cantidad": peso_real, "cantidad_txt": f"{peso_real}", "subtotal": sub_real, "ahorro": ahorro_real, "tipo": "Propio"})
                    
                    st.markdown(f"### Total Exacto: **${total_real_calculado:,.1f}**")
                    if total_ahorro_web > 0: st.success(f"Ahorro para el cliente: ${total_ahorro_web:,.1f}")
                    
                    if st.button("⚖️ Confirmar Pesos y Enviar a Caja", type="primary"):
                        gc = conectar_google()
                        ws_ventas = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                        
                        col_est = chr(65 + pedido_sel['idx_est'])
                        updates = [{'range': f'{col_est}{f}', 'values': [["Cancelado (Ajustado)"]]} for f in pedido_sel["filas"]]
                        ws_ventas.batch_update(updates)
                        
                        ahora = datetime.now(TZ_UY)
                        filas_web_nuevas = []
                        items_json = json.dumps(nuevos_items)
                        
                        for n_it in nuevos_items:
                            filas_web_nuevas.append([
                                ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                                st.session_state.usuario_logueado, pedido_sel["cliente"], 
                                n_it['producto'], n_it['cantidad'], n_it['subtotal'], 
                                pedido_sel["celular"], "Pendiente Pago", "Web - En Caja", pedido_sel["direccion"], n_it['ahorro'], items_json
                            ])
                        ws_ventas.append_rows(filas_web_nuevas)
                        
                        limpiar_cache_ventas()
                        st.session_state.msg_vendedor = "✅ ¡Pesos confirmados y enviado a Caja!"
                        
                        num_cajero = limpiar_y_formatear_celular(celular_feriante_local)
                        if not num_cajero: num_cajero = "59893343092"
                        st.session_state.link_vendedor = f"https://wa.me/{num_cajero}?text={urllib.parse.quote(f'💳 *CAJA (WEB Ajustado)*\nCliente: {pedido_sel['cliente']}\nTotal a cobrar: ${total_real_calculado:,.1f}')}"
                        
                        st.session_state.v_rk += 1
                        st.rerun()

            if 'msg_vendedor' in st.session_state:
                st.success(st.session_state.msg_vendedor)
                if 'link_vendedor' in st.session_state and st.session_state.link_vendedor:
                    st.link_button("📲 Avisar al Cajero (Enviar WhatsApp)", st.session_state.link_vendedor, type="primary")
                if st.button("✅ Seguir trabajando", type="secondary"):
                    del st.session_state.msg_vendedor
                    st.rerun()

        except Exception as e:
            st.error(f"Error cargando pedidos web: {e}")
    idx += 1

# =======================================================
# PESTAÑA 2: CAJA Y COBRO
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        col_c1, col_c2 = st.columns([3,1])
        with col_c1: st.write("### 💳 Módulo de Caja y Cobro")
        with col_c2: 
            if st.button("🔄 Refrescar Caja"):
                limpiar_cache_ventas()
                st.rerun()
                
        if 'ticket_generado' in st.session_state:
            st.success(st.session_state.ticket_generado["msg"])
            if st.session_state.ticket_generado["link"]:
                st.link_button("📲 Enviar Ticket al Cliente por WhatsApp", st.session_state.ticket_generado["link"], type="primary")
            if st.button("Cerrar Aviso y seguir cobrando"):
                del st.session_state.ticket_generado
                st.rerun()
            st.divider()

        try:
            pedidos_en_caja = agrupar_pedidos(ventas_data_global, ["En Caja", "Web - En Caja"])

            if not pedidos_en_caja:
                st.info("No hay pedidos esperando en Caja.")
                st.write("#### 💰 Cobro Manual / Directo")
                c_cliente = st.text_input("Cliente:", key="cm_cli")
                c_monto = st.number_input("Monto ($):", min_value=0.0, step=10.0, key="cm_mon")
                c_pago = st.selectbox("Forma de Pago:", ["Tarjeta", "Efectivo", "MercadoPago", "FIADO", "Pendiente Pago"], key="cm_pag")
                c_cel = st.text_input("Celular:", placeholder="099...", key="cm_cel")
                if st.button("Cobrar Venta Directa", type="primary"):
                    if c_cliente and c_monto > 0:
                        est = "Fiado Pendiente" if c_pago == "FIADO" else ("Pendiente Pago" if "Pendiente" in c_pago else "Cobrado")
                        cel_fmt = limpiar_y_formatear_celular(c_cel)
                        gc = conectar_google()
                        gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas").append_row([
                            datetime.now(TZ_UY).strftime("%d/%m/%Y"), datetime.now(TZ_UY).strftime("%H:%M:%S"), 
                            st.session_state.usuario_logueado, c_cliente, "Caja Directa", 1, c_monto, cel_fmt, c_pago, est, "", 0
                        ])
                        limpiar_cache_ventas()
                        
                        if "Pendiente" in c_pago:
                            msg = f"👋 Hola *{c_cliente}*, tu pedido de *{nombre_empresa}* está listo.\nTotal a abonar: *${c_monto:,.1f}*.\n💚 ¡Te avisaremos cuando vayamos en camino a llevarte tu pedido!"
                        else:
                            msg = f"👋 Hola *{c_cliente}*, gracias por comprar en *{nombre_empresa}*.\nTotal: *${c_monto:,.1f}* ({c_pago}).\n💚 ¡Te esperamos pronto!"
                            
                        st.session_state.ticket_generado = {"msg": f"✅ ¡Cobro registrado ({est})!", "link": f"https://wa.me/{cel_fmt}?text={urllib.parse.quote(msg)}" if cel_fmt else None}
                        st.rerun()
                    else: st.error("Falta Nombre o Monto.")
            else:
                opciones_caja = ["Selecciona un pedido..."]
                for p in pedidos_en_caja:
                    tipo_origen = "🌐 WEB" if "Web" in p['estado'] else f"🏪 LOCAL"
                    opciones_caja.append(f"{p['hora']} | [{tipo_origen}] {p['cliente']} - ${p['total']:,.1f} (ID {p['filas'][0]})")
                
                sel_caja = st.selectbox("🛒 Pedidos esperando para ser cobrados:", opciones_caja)
                
                if sel_caja != "Selecciona un pedido...":
                    idx_selec = int(sel_caja.split("(ID ")[1].replace(")", ""))
                    pedido_c = next(p for p in pedidos_en_caja if p['filas'][0] == idx_selec)
                    
                    st.info(f"👨‍💼 **Origen/Armador:** {pedido_c['vendedor']}\n\n🛍️ **Detalle:** {pedido_c['detalle']}")
                    
                    c_cliente = st.text_input("Cliente:", value=pedido_c['cliente'], key="cp_cli")
                    c_monto = st.number_input("Monto Total ($):", value=pedido_c['total'], min_value=0.0, step=10.0, key="cp_mon")
                    
                    opciones_pago = ["Tarjeta", "Efectivo", "MercadoPago", "FIADO", "Pendiente Pago"]
                    def_pago_idx = 4 if "Web" in pedido_c['estado'] else 0
                    c_pago = st.selectbox("Forma de Pago:", opciones_pago, index=def_pago_idx, key="cp_pag")
                    
                    c_cel = st.text_input("Celular:", value=pedido_c['celular'], key="cp_cel")
                    
                    ahorro_total = pedido_c['ahorro']
                    if ahorro_total > 0: st.success(f"Este pedido incluye un ahorro de: ${ahorro_total:,.1f}")
                    
                    col_bt1, col_bt2, col_bt3 = st.columns(3)
                    with col_bt1:
                        if st.button(f"💵 Cerrar Ticket", type="primary", use_container_width=True):
                            est = "Fiado Pendiente" if c_pago == "FIADO" else ("Pendiente Pago" if "Pendiente" in c_pago else "Cobrado")
                            if "Web" in pedido_c['estado']: est = "Web - " + est
                            
                            cel_fmt = limpiar_y_formatear_celular(c_cel)
                            
                            gc = conectar_google()
                            ws_ventas = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            
                            col_pago_letra = chr(65 + pedido_c['idx_pago'])
                            col_est_letra = chr(65 + pedido_c['idx_est'])
                            
                            updates = []
                            for f in pedido_c['filas']:
                                updates.extend([
                                    {'range': f'D{f}', 'values': [[c_cliente]]},
                                    {'range': f'H{f}', 'values': [[cel_fmt]]},
                                    {'range': f'{col_pago_letra}{f}', 'values': [[c_pago]]},
                                    {'range': f'{col_est_letra}{f}', 'values': [[est]]}
                                ])
                            ws_ventas.batch_update(updates)
                            limpiar_cache_ventas()
                            
                            if "Pendiente" in c_pago:
                                msg = f"👋 Hola *{c_cliente}*, tu pedido de *{nombre_empresa}* está listo.\nTotal a abonar: *${c_monto:,.1f}*.\n💚 ¡Te avisaremos cuando vayamos en camino a llevarte tu pedido!"
                            else:
                                msg = f"👋 Hola *{c_cliente}*, gracias por comprar en *{nombre_empresa}*.\nTotal: *${c_monto:,.1f}* ({c_pago})."
                                
                            if ahorro_total > 0: msg += f"\n🎉 ¡Con esta compra tuviste un ahorro total de *${ahorro_total:,.1f}*!"
                            msg += f"\n💚 ¡Te esperamos pronto!"
                            
                            st.session_state.ticket_generado = {"msg": f"✅ ¡Ticket cerrado ({est})!", "link": f"https://wa.me/{cel_fmt}?text={urllib.parse.quote(msg)}" if cel_fmt else None}
                            st.rerun()
                            
                    with col_bt2:
                        if st.button("🔄 Retomar para Editar", use_container_width=True):
                            gc = conectar_google()
                            ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            col_est_letra = chr(65 + pedido_c['idx_est'])
                            updates = [{'range': f'{col_est_letra}{f}', 'values': [["Cancelado (Retomado)"]]} for f in pedido_c['filas']]
                            ws.batch_update(updates)
                            limpiar_cache_ventas()
                            
                            try:
                                items_rec = json.loads(pedido_c['json'])
                                if items_rec:
                                    st.session_state.carrito_vendedor = items_rec
                                else:
                                    st.session_state.carrito_vendedor = pedido_c['items']
                            except:
                                st.session_state.carrito_vendedor = pedido_c['items']
                            
                            st.session_state.cli_v_temp = c_cliente
                            st.session_state.cel_v_temp = c_cel
                            st.session_state.modo_vend = "🛍️ Nueva Venta Local"
                            
                            st.session_state.ticket_generado = {"msg": f"✅ Pedido devuelto a 'Toma de Pedidos' para editarse.", "link": None}
                            st.rerun()
                            
                    with col_bt3:
                        if st.button("❌ Eliminar Pedido", type="secondary", use_container_width=True):
                            gc = conectar_google()
                            ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            col_est_letra = chr(65 + pedido_c['idx_est'])
                            updates = [{'range': f'{col_est_letra}{f}', 'values': [["Cancelado"]]} for f in pedido_c['filas']]
                            ws.batch_update(updates)
                            limpiar_cache_ventas()
                            st.rerun()
        except Exception as e:
            st.error(f"Error procesando la caja: {e}")
    idx += 1

# --- PESTAÑA 3: PEDIDOS WEB ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        col_w1, col_w2 = st.columns([3,1])
        with col_w1: st.write("### 🌐 Gestión de Pedidos Online")
        with col_w2: 
            if st.button("🔄 Refrescar Web"):
                limpiar_cache_ventas()
                st.rerun()
                
        try:
            pedidos_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente", "Web - En Caja"])
            if not pedidos_web:
                st.info("ℹ️ No hay pedidos web pendientes en este momento.")
            else:
                for p in pedidos_web:
                    if p["estado"] == "Web - Pendiente":
                        with st.expander(f"🔴 NUEVO: {p['cliente']} - Hora: {p['hora']}"):
                            st.write(f"**Detalle original:** {p['detalle']}\n\n**Dirección:** {p['direccion']}\n\n**Celular:** {p['celular']}")
                            st.info("El vendedor debe armarlo y pesarlo en la pestaña 'Toma de Pedidos'.")
                            st.link_button("📲 Reenviar 'Pedido Recibido'", f"https://wa.me/{limpiar_y_formatear_celular(p['celular'])}?text={urllib.parse.quote(f'Hola {p['cliente']} 🛒. ¡Recibimos tu pedido en {nombre_empresa}! A la brevedad será armado. ¡Gracias!')}")
                    else:
                        with st.expander(f"🟡 ARMADO Y EN CAJA: {p['cliente']} - ${p['total']:,.1f}"):
                            st.write(f"**Detalle:** {p['detalle']}\n\n**Dirección:** {p['direccion']}")
                            st.info("Este pedido ya fue armado y está en la Caja esperando generar el ticket o el cobro.")
        except: st.error("Error leyendo pedidos web.")
    idx += 1

# --- PESTAÑA 4: ENTREGAS ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        col_e1, col_e2 = st.columns([3,1])
        with col_e1: st.write("### 🛵 Control de Entregas a Domicilio")
        with col_e2: 
            if st.button("🔄 Refrescar Entregas"):
                limpiar_cache_ventas()
                st.rerun()

        if 'entrega_msg' in st.session_state:
            st.success(st.session_state.entrega_msg["msg"])
            if st.session_state.entrega_msg["link"]:
                st.link_button("📲 Enviar Recibo por WhatsApp", st.session_state.entrega_msg["link"], type="primary")
            if st.button("Cerrar Aviso", key="btn_cerrar_e"):
                del st.session_state.entrega_msg
                st.rerun()
            st.divider()

        try:
            entregas_pendientes = agrupar_pedidos(ventas_data_global, ["Cobrado", "Fiado Pendiente", "Pendiente Pago", "Web - Cobrado", "Web - Fiado Pendiente", "Web - Pendiente Pago"])
            entregas_pendientes = [e for e in entregas_pendientes if e["direccion"].strip() != ""]
                    
            if entregas_pendientes:
                for p in entregas_pendientes:
                    with st.container():
                        st.write(f"🏠 **{p['cliente']}** - {p['direccion']}")
                        st.write(f"*Detalle:* {p['detalle']} ({p['estado']}) - **Total: ${p['total']:,.1f}**")
                        
                        c_e1, c_e2, c_e3 = st.columns(3)
                        
                        if "Pendiente Pago" in p['estado']:
                            with c_e1:
                                pago_entrega = st.selectbox("Cobrar con:", ["Efectivo", "MercadoPago", "Tarjeta"], key=f"pe_{p['filas'][0]}")
                            with c_e2:
                                if st.button("💵 Cobrar y Entregar", key=f"ce_{p['filas'][0]}", type="primary"):
                                    gc = conectar_google()
                                    ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                    
                                    col_pago_letra = chr(65 + p['idx_pago'])
                                    col_est_letra = chr(65 + p['idx_est'])
                                    
                                    updates = []
                                    for f in p['filas']:
                                        updates.append({'range': f'{col_pago_letra}{f}', 'values': [[pago_entrega]]})
                                        updates.append({'range': f'{col_est_letra}{f}', 'values': [["Entregado"]]})
                                    ws.batch_update(updates)
                                    limpiar_cache_ventas()
                                    
                                    cel_f = limpiar_y_formatear_celular(p['celular'])
                                    msg = f"👋 Hola {p['cliente']}, registramos tu pago de ${p['total']:,.1f} y tu pedido ya fue entregado. ¡Muchas gracias por elegir {nombre_empresa}! 💚"
                                    st.session_state.entrega_msg = {"msg": "✅ ¡Cobro y Entrega registrados con éxito!", "link": f"https://wa.me/{cel_f}?text={urllib.parse.quote(msg)}" if cel_f else None}
                                    st.rerun()
                        else:
                            with c_e1:
                                if st.button("🛵 Marcar Entregado", key=f"ent_{p['filas'][0]}"):
                                    gc = conectar_google()
                                    ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                    col_est_letra = chr(65 + p['idx_est'])
                                    updates = [{'range': f'{col_est_letra}{f}', 'values': [["Entregado"]]} for f in p['filas']]
                                    ws.batch_update(updates)
                                    limpiar_cache_ventas()
                                    st.toast("✅ Pedido marcado como entregado silenciosamente.", icon="✅")
                                    st.rerun()
                                    
                        with c_e3: st.link_button("📲 Avisar 'Va en Camino'", f"https://wa.me/{limpiar_y_formatear_celular(p['celular'])}?text={urllib.parse.quote(f'Hola {p['cliente']} 🛵. Tu pedido de {nombre_empresa} va en camino a tu domicilio.')}")
                        st.markdown("---")
            else: st.info("No hay entregas pendientes.")
        except: pass
    idx += 1

# --- PESTAÑA 5: PANEL ADMIN ---
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        col_p1, col_p2 = st.columns([3,1])
        with col_p1: st.write("### 📊 Panel de Control y Fiados")
        with col_p2: 
            if st.button("🔄 Refrescar Panel"):
                limpiar_cache_ventas()
                st.rerun()

        try:
            ordenes_admin = agrupar_pedidos(ventas_data_global, None)
            
            total_recaudado = 0.0
            ventas_locales = []
            ventas_web = []
            fiados = []
            
            for p in ordenes_admin:
                est = p['estado'].lower()
                is_web = "web" in p['vendedor'].lower() or "web" in est
                
                if "cancelado" not in est and "caja" not in est and "pendiente" not in est: 
                    total_recaudado += p['total']
                
                if "fiado" in p['pago'].lower() and "cancelado" not in est and "caja" not in est:
                    fiados.append(p)
                
                if "cancelado" not in est and "caja" not in est:
                    fila_dict = {
                        "Fecha": p['fecha'], "Hora": p['hora'], "Vendedor": p['vendedor'], 
                        "Cliente": p['cliente'], "Monto": f"${p['total']:,.1f}", "Pago": p['pago'], "Estado": p['estado']
                    }
                    if is_web: ventas_web.append(fila_dict)
                    else: ventas_locales.append(fila_dict)
            
            c1, c2 = st.columns(2)
            c1.metric("Total Órdenes Exitosas", len(ventas_locales) + len(ventas_web))
            c2.metric("Recaudación Neta ($)", f"${total_recaudado:,.1f}")
            st.divider()
            
            # --- TABLA 1: VENTAS LOCALES ---
            st.subheader("🏪 Resumen de Ventas Locales (Presenciales)")
            if ventas_locales:
                df_locales = pd.DataFrame(ventas_locales)
                st.dataframe(df_locales, use_container_width=True)
                csv_locales = df_locales.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Reporte Locales (CSV)",
                    data=csv_locales,
                    file_name=f'Ventas_Locales_{datetime.now().strftime("%Y%m%d")}.csv',
                    mime='text/csv',
                    key="dl_loc"
                )
            else: st.info("No hay ventas locales registradas.")

            st.divider()

            # --- TABLA 2: COMPRAS WEB ---
            st.subheader("🌐 Resumen de Compras Online (Web)")
            if ventas_web:
                df_web = pd.DataFrame(ventas_web)
                st.dataframe(df_web, use_container_width=True)
                csv_web = df_web.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Reporte Web (CSV)",
                    data=csv_web,
                    file_name=f'Ventas_Web_{datetime.now().strftime("%Y%m%d")}.csv',
                    mime='text/csv',
                    key="dl_web"
                )
            else: st.info("No hay compras web registradas.")
            
            st.divider()
            st.subheader("💳 Control de Fiados Activos")
            if fiados:
                for p in fiados:
                    try: dias = (datetime.now(TZ_UY).date() - datetime.strptime(p['fecha'], "%d/%m/%Y").date()).days
                    except: dias = 0
                    alerta = "⚠️ *Más de 10 días*" if dias >= 10 else f"({dias} días)"
                    st.write(f"👤 **{p['cliente']}** | 💰 **${p['total']}** | Fecha: {p['fecha']} {alerta}")
                    if p['celular']: st.link_button(f"📲 Recordar a {p['cliente']}", f"https://wa.me/{limpiar_y_formatear_celular(p['celular'])}?text={urllib.parse.quote(f'👋 Hola {p['cliente']}, desde {nombre_empresa} te recordamos tu saldo pendiente de ${p['total']} de la fecha {p['fecha']}. ¡Gracias!')}")
            else: st.info("ℹ️ No hay fiados activos.")
        except Exception as e: st.error(f"Error cargando panel admin: {e}")
