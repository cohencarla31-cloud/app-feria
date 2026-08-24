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

# Llaves dinámicas (Esto evita el StreamlitAPIException para siempre)
if 'v_rk' not in st.session_state: st.session_state.v_rk = 0  # Reset de Vendedor
if 'c_rk' not in st.session_state: st.session_state.c_rk = 0  # Reset de Caja

# ==========================================
# 2. CONEXIÓN A GOOGLE
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
        st.error(f"Error al conectar con Master: {e}")
    return None

def limpiar_y_formatear_celular(celular_ingresado):
    num = ''.join(filter(str.isdigit, str(celular_ingresado)))
    if not num: return ""
    if str(celular_ingresado).strip().startswith("+"): return num
    if len(num) <= 9:
        if num.startswith("0"): num = num[1:]
        return f"598{num}"
    return num

# ==========================================
# 3. CARGA DE DATOS A PRUEBA DE FALLOS
# ==========================================
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
                precio_str = str(fila[2]).replace("$", "").replace(",", "").strip()
                try: precio = float(precio_str) if precio_str else 0.0
                except: precio = 0.0
                
                desc = 0.0
                if len(fila) >= 6 and fila[5].strip():
                    try: desc = float(str(fila[5]).replace("%", "").strip())
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
# 4. MODO TIENDA (CATÁLOGO DIGITAL PÚBLICO)
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel and link_excel != "SUSPENDIDO":
        try:
            productos, precios, descuentos, nombres_planos, clientes_dict, config = cargar_datos_feria(link_excel)
            nombre_feria = config.get("nombre_empresa", "Nuestra Feria")
            celular_feriante = config.get("celular_feriante", config.get("celular_contacto", ""))
            
            st.title(f"🛒 {nombre_feria}")
            st.markdown("Elige tus productos, completa tus datos y envía tu pedido directo a la feria.")
            st.divider()
            
            st.subheader("1️⃣ Tus Datos de Envío")
            nombre_cliente = st.text_input("Nombre y Apellido:")
            celular_cliente = st.text_input("Celular (Ej: 099123456 o +549...):", placeholder="099123456")
            direccion_cliente = st.text_input("Dirección de Envío (Calle, Nro y Esquina):")
            observaciones_cliente = st.text_area("Observaciones para el armado (Opcional):", placeholder="Ej: Bananas verdes...")
            
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
                    pedido_items = []
                    for p, c in cantidades_seleccionadas.items():
                        if c > 0: pedido_items.append(f"{p}: {c}kg")
                    for p, u in unidades_seleccionadas.items():
                        if u > 0: pedido_items.append(f"{p}: {u}un")
                            
                    if not pedido_items:
                        st.warning("⚠️ No has seleccionado ningún producto.")
                    else:
                        detalle_pedido_texto = " | ".join(pedido_items)
                        if observaciones_cliente:
                            detalle_pedido_texto += f" | 📝 Obs: {observaciones_cliente}"
                            
                        gc = conectar_google()
                        sh = gc.open_by_url(link_excel)
                        
                        celular_formateado = limpiar_y_formatear_celular(celular_cliente)
                        ahora = datetime.now(TZ_UY)
                        
                        sh.worksheet("Registro de Ventas").append_row([
                            ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                            "Web Online", nombre_cliente.strip(), detalle_pedido_texto, 1, 0, 
                            celular_formateado, direccion_cliente, "A definir", "Web - Pendiente"
                        ])
                        
                        try:
                            ws_cli = sh.worksheet("Clientes")
                            nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                            if nombre_cliente.strip().lower() not in nombres_existentes:
                                ws_cli.append_row([nombre_cliente.strip(), celular_formateado, "Web"])
                        except: pass
                        
                        st.success("✅ ¡Muchas gracias por tu compra! A la brevedad será armada y despachada.")
                        
                        if celular_feriante:
                            msg_feriante = f"🛒 *NUEVO PEDIDO WEB*\n\n👤 Cliente: {nombre_cliente}\n📱 Celular: {celular_formateado}\n📍 Dirección: {direccion_cliente}\n📦 Productos:\n{detalle_pedido_texto}"
                            if observaciones_cliente: msg_feriante += f"\n\n💬 Notas: {observaciones_cliente}"
                            num_feriante_limpio = limpiar_y_formatear_celular(celular_feriante)
                            st.link_button("📲 Enviar Aviso al Feriante por WhatsApp", f"https://wa.me/{num_feriante_limpio}?text={urllib.parse.quote(msg_feriante)}")
        except Exception as e:
            st.error(f"Error cargando la tienda online: {e}")
    else:
        st.error("Feria no encontrada o inactiva.")
    st.stop()

# ==========================================
# 5. MODO PRIVADO Y ACCESO
# ==========================================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.session_state.link_feria = None
    st.session_state.es_super_admin = False
if "carrito_vendedor" not in st.session_state: st.session_state.carrito_vendedor = []
if "pedido_activo_caja" not in st.session_state: st.session_state.pedido_activo_caja = {"cliente": "", "celular": "", "total": 0.0, "detalle": "", "items": []}

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
                if not ws_usuarios_nombre:
                    st.error("❌ No existe pestaña 'Usuarios' en el Excel.")
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
                                st.session_state.rol_logueado = valido.iloc[0].get(col_rol, 'Vendedor') if col_rol else 'Vendedor'
                                st.session_state.link_feria = link_excel
                                st.session_state.es_super_admin = False
                                st.rerun()
                            else: st.error("❌ Usuario o Contraseña incorrectos.")
                        else: st.error("❌ Faltan columnas 'Usuario' y 'Clave'.")
            except Exception as e: st.error(f"❌ Error de permisos: {e}")
        else: st.error("❌ Código de empresa inválido.")
    st.stop()

# --- PANEL PRIVADO ---
with st.sidebar:
    st.success(f"Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.carrito_vendedor = []
        st.session_state.pedido_activo_caja = {"cliente": "", "celular": "", "total": 0.0, "detalle": "", "items": []}
        st.rerun()

PRODUCTOS, PRECIOS, DESCUENTOS, NOMBRES, CLIENTES_DICT, CONFIG = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("nombre_empresa", "La Feria")
celular_feriante_local = CONFIG.get("celular_feriante", CONFIG.get("celular_contacto", ""))

st.title(f"🏢 {nombre_empresa}")

tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]: tabs_nombres.append("⚖️ Toma de Pedidos")
if st.session_state.rol_logueado in ["Admin", "Cajero"]: 
    tabs_nombres.append("💰 Caja y Cobro")
    tabs_nombres.append("🌐 Pedidos Web")
if st.session_state.rol_logueado == "Admin": tabs_nombres.append("📊 Panel Admin")

tabs = st.tabs(tabs_nombres)
idx = 0

# --- PESTAÑA 1: VENDEDOR ---
with tabs[idx]:
    # Mostrar alertas persistentes de éxito
    if 'msg_vendedor' in st.session_state:
        st.success(st.session_state.msg_vendedor)
        del st.session_state.msg_vendedor

    modo_vendedor = st.radio("Modo de trabajo:", ["🛍️ Nueva Venta Local", "🌐 Armar Pedido Web Pendiente"], horizontal=True)
    st.divider()

    if modo_vendedor == "🛍️ Nueva Venta Local":
        st.write("### 📝 Armar Carrito de Compra")
        
        opciones_cli = ["Escribir nuevo..."] + list(CLIENTES_DICT.keys()) if CLIENTES_DICT else ["Escribir nuevo..."]
        tipo_cli_sel = st.selectbox("Seleccionar Cliente de la Base:", opciones_cli)
        
        if tipo_cli_sel == "Escribir nuevo...":
            cliente_vendedor = st.text_input("Nombre del Cliente:")
            celular_vendedor = st.text_input("Celular:", placeholder="099123456")
        else:
            cliente_vendedor = tipo_cli_sel
            celular_vendedor = CLIENTES_DICT.get(cliente_vendedor, "")
            st.info(f"👤 **{cliente_vendedor}** | 📱 {celular_vendedor if celular_vendedor else 'Sin número'}")

        tipo_ingreso = st.radio("Tipo de ítem:", ["Catálogo de Productos", "Ítem Manual / Libre"], horizontal=True)
        
        if tipo_ingreso == "Catálogo de Productos":
            prod_buscado = st.selectbox("Buscar Producto:", ["Seleccionar..."] + PRODUCTOS)
            if prod_buscado != "Seleccionar...":
                tipo_medida = st.radio("Forma de venta:", ["Kilos / Gramos", "Unidades"], horizontal=True)
                
                if tipo_medida == "Kilos / Gramos":
                    col1, col2 = st.columns(2)
                    # Usamos v_rk en la llave para resetearlos automáticamente al agregar
                    with col1: kilos = st.number_input("Kilos:", min_value=0.0, step=1.0, key=f"kv_{st.session_state.v_rk}")
                    with col2: gramos = st.number_input("Gramos:", min_value=0.0, step=50.0, key=f"gv_{st.session_state.v_rk}")
                    cant = kilos + (gramos / 1000.0)
                    formato_txt = f"{cant}kg"
                else:
                    unidades = st.number_input("Unidades:", min_value=0, step=1, key=f"uv_{st.session_state.v_rk}")
                    cant = float(unidades)
                    formato_txt = f"{int(cant)}un"
                
                if cant > 0:
                    precio_final = PRECIOS.get(prod_buscado, 0) * (1 - (DESCUENTOS.get(prod_buscado, 0) / 100))
                    subtotal = cant * precio_final
                    st.info(f"Subtotal: **${subtotal:,.1f}**")
                    
                    if st.button("➕ Agregar al Carrito"):
                        st.session_state.carrito_vendedor.append({
                            "id": datetime.now().timestamp(), "producto": NOMBRES.get(prod_buscado),
                            "cantidad": formato_txt, "subtotal": subtotal, "tipo": "Propio"
                        })
                        st.session_state.v_rk += 1 # Destruye las casillas y genera nuevas en cero
                        st.rerun()
        else:
            desc_manual = st.text_input("Descripción del ítem manual:", key=f"dm_{st.session_state.v_rk}")
            precio_manual = st.number_input("Precio Total ($):", min_value=0.0, step=10.0, key=f"pm_{st.session_state.v_rk}")
            es_ajeno = st.selectbox("¿Este ítem es Propio o Ajeno?", ["Propio", "Ajeno"], key=f"pa_{st.session_state.v_rk}")
            if st.button("➕ Agregar Ítem Manual"):
                if desc_manual and precio_manual > 0:
                    st.session_state.carrito_vendedor.append({
                        "id": datetime.now().timestamp(), "producto": desc_manual,
                        "cantidad": "1un", "subtotal": precio_manual, "tipo": es_ajeno
                    })
                    st.session_state.v_rk += 1
                    st.rerun()

        if st.session_state.carrito_vendedor:
            st.divider()
            st.subheader("🛒 Carrito Actual")
            total_carrito = 0.0
            indices_a_borrar = []
            for i, item in enumerate(st.session_state.carrito_vendedor):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1: st.markdown(f"**{item['producto']}** ({item['cantidad']}) - **${item['subtotal']:,.1f}** *[{item['tipo']}]*")
                with c2: total_carrito += item['subtotal']
                with c3:
                    if st.button("❌", key=f"del_{item['id']}"): indices_a_borrar.append(i)
            
            if indices_a_borrar:
                for index in sorted(indices_a_borrar, reverse=True): st.session_state.carrito_vendedor.pop(index)
                st.rerun()

            st.markdown(f"### Total: **${total_carrito:,.1f}**")
            if st.button("🚀 Enviar a Caja", type="primary"):
                if not cliente_vendedor: st.error("⚠️ Ingresa el nombre del cliente.")
                else:
                    det = " | ".join([f"{r['producto']}: {r['cantidad']} ({r['tipo']})" for r in st.session_state.carrito_vendedor])
                    st.session_state.pedido_activo_caja = {"cliente": cliente_vendedor, "celular": celular_vendedor, "total": total_carrito, "detalle": det, "items": list(st.session_state.carrito_vendedor)}
                    
                    gc = conectar_google()
                    sh_feria = gc.open_by_url(st.session_state.link_feria)
                    celular_limpio = limpiar_y_formatear_celular(celular_vendedor)
                    
                    sh_feria.worksheet("Registro de Ventas").append_row([
                        datetime.now(TZ_UY).strftime("%d/%m/%Y"), datetime.now(TZ_UY).strftime("%H:%M:%S"), 
                        st.session_state.usuario_logueado, cliente_vendedor, det, 1, total_carrito, celular_limpio, "", "En Caja"
                    ])
                    
                    try:
                        ws_cli = sh_feria.worksheet("Clientes")
                        nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                        if cliente_vendedor.strip().lower() not in nombres_existentes:
                            ws_cli.append_row([cliente_vendedor.strip(), celular_limpio, "Local"])
                    except: pass
                    
                    st.session_state.msg_vendedor = "✅ ¡Enviado a Caja Exitosamente!"
                    st.session_state.carrito_vendedor = []
                    st.session_state.c_rk += 1 # Resetear la caja para que reciba lo nuevo
                    st.rerun()
    
    else:
        st.write("### 📦 Armar Pedido Web (Ajuste de Pesos en Balanza)")
        try:
            gc = conectar_google()
            ventas_ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
            ventas_data = ventas_ws.get_all_values()
            
            pedidos_web = []
            for i, row in enumerate(ventas_data):
                if i == 0: continue
                if len(row) > 10 and "web" in str(row[10]).lower() and "pendiente" in str(row[10]).lower():
                    pedidos_web.append({
                        "fila_idx": i + 1, "fecha": row[0], "cliente": row[3],
                        "detalle": row[4], "celular": row[7], "direccion": row[8]
                    })
            
            if not pedidos_web:
                st.info("No hay pedidos web pendientes para armar.")
            else:
                opciones_web = ["Seleccionar..."] + [f"{p['cliente']} - {p['fecha']} (Fila {p['fila_idx']})" for p in pedidos_web]
                sel_web = st.selectbox("Selecciona el pedido a preparar:", opciones_web)
                
                if sel_web != "Seleccionar...":
                    idx_selec = int(sel_web.split("(Fila ")[1].replace(")", ""))
                    pedido_sel = next(p for p in pedidos_web if p["fila_idx"] == idx_selec)
                    
                    st.write(f"👤 **Cliente:** {pedido_sel['cliente']} | 📱 **Celular:** {pedido_sel['celular']}")
                    st.write(f"📍 **Dirección:** {pedido_sel['direccion']}")
                    st.divider()
                    
                    items_raw = pedido_sel['detalle'].split(" | ")
                    observaciones = ""
                    total_real_calculado = 0.0
                    nuevos_items = []
                    
                    st.markdown("#### Ingresa el peso/cant real de la balanza:")
                    
                    for idx_item, item in enumerate(items_raw):
                        if item.startswith("📝 Obs:"):
                            observaciones = item.replace("📝 Obs:", "").strip()
                            continue
                        
                        if ":" in item:
                            prod_name_raw, cant_str = item.split(":", 1)
                            prod_name = prod_name_raw.strip()
                            cant_str = cant_str.strip()
                            
                            is_kg = "kg" in cant_str
                            cant_val = float(''.join(c for c in cant_str if c.isdigit() or c=='.'))
                            
                            col_a, col_b = st.columns([1, 1])
                            with col_a: st.write(f"🛍️ **{prod_name}** (Pidió: {cant_str})")
                            with col_b:
                                if is_kg:
                                    peso_real = st.number_input("Peso real (kg):", value=float(cant_val), step=0.1, key=f"adj_kg_{idx_item}_{st.session_state.v_rk}")
                                    txt_cant = f"{peso_real}kg"
                                    cant_final = peso_real
                                else:
                                    peso_real = st.number_input("Unidades reales:", value=int(cant_val), step=1, key=f"adj_un_{idx_item}_{st.session_state.v_rk}")
                                    txt_cant = f"{int(peso_real)}un"
                                    cant_final = float(peso_real)
                            
                            precio_unitario, descuento_aplicado = 0.0, 0.0
                            for p_full in PRECIOS.keys():
                                if prod_name in p_full:
                                    precio_unitario = PRECIOS[p_full]
                                    descuento_aplicado = DESCUENTOS.get(p_full, 0.0)
                                    break
                                    
                            precio_final = precio_unitario * (1 - (descuento_aplicado / 100))
                            sub_real = cant_final * precio_final
                            total_real_calculado += sub_real
                            
                            nuevos_items.append({"producto": prod_name, "cantidad": txt_cant, "subtotal": sub_real, "tipo": "Propio"})
                    
                    if observaciones: st.info(f"📝 **Nota:** {observaciones}")
                    st.markdown(f"### Total Exacto: **${total_real_calculado:,.1f}**")
                    
                    if st.button("⚖️ Confirmar Pesos y Enviar a Caja", type="primary"):
                        det_real = " | ".join([f"{r['producto']}: {r['cantidad']}" for r in nuevos_items])
                        if observaciones: det_real += f" | 📝 Obs: {observaciones}"
                        
                        ventas_ws.update_cell(pedido_sel["fila_idx"], 11, "Web - En Caja")
                        
                        st.session_state.pedido_activo_caja = {
                            "cliente": pedido_sel['cliente'], "celular": pedido_sel['celular'],
                            "total": total_real_calculado, "detalle": f"(Web Ajustado) {det_real}", "items": nuevos_items
                        }
                        
                        st.session_state.msg_vendedor = "✅ ¡Pesos confirmados y enviado a Caja!"
                        st.session_state.v_rk += 1
                        st.session_state.c_rk += 1
                        st.rerun()
        except Exception as e:
            st.error(f"Error cargando pedidos web: {e}")
    idx += 1

# --- PESTAÑA 2: CAJA Y COBRO ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Módulo de Caja y Cobro")
        
        # Avisos de éxito del ticket anterior
        if 'ticket_generado' in st.session_state:
            st.success(st.session_state.ticket_generado["msg"])
            if st.session_state.ticket_generado["link"]:
                st.link_button("📲 Enviar Ticket al Cliente", st.session_state.ticket_generado["link"])
            if st.button("Cerrar Aviso"):
                del st.session_state.ticket_generado
                st.rerun()
            st.divider()

        autocli = st.session_state.pedido_activo_caja.get("cliente", "")
        autocel = st.session_state.pedido_activo_caja.get("celular", "")
        autototal = float(st.session_state.pedido_activo_caja.get("total", 0.0))
        autodet = st.session_state.pedido_activo_caja.get("detalle", "")
        
        if autodet:
            st.info(f"📥 Pedido pendiente recibido de Vendedor para **{autocli}** por **${autototal:,.1f}**")
            if not "(Web Ajustado)" in autodet:
                if st.button("🔄 Retomar Pedido (Devolver al Carrito)"):
                    st.session_state.carrito_vendedor = st.session_state.pedido_activo_caja.get("items", [])
                    st.session_state.pedido_activo_caja = {"cliente": "", "celular": "", "total": 0.0, "detalle": "", "items": []}
                    st.session_state.c_rk += 1
                    st.warning("Carrito restaurado en 'Toma de Pedidos'.")
                    st.rerun()

        # Usar key vinculada al estado de reinicio (c_rk) para asegurar autocompletado sin errores
        cliente_caja = st.text_input("Cliente:", value=autocli, key=f"c_cli_{st.session_state.c_rk}")
        monto_cobro = st.number_input("Total a Cobrar ($):", min_value=0.0, value=autototal, step=10.0, format="%.1f", key=f"c_tot_{st.session_state.c_rk}")
        ahorro_descuento = st.number_input("Ahorro / Descuento aplicado ($ Opcional):", min_value=0.0, step=5.0, format="%.1f", key=f"c_desc_{st.session_state.c_rk}")
        forma_pago = st.selectbox("Forma de Pago:", ["Efectivo", "Tarjeta", "MercadoPago", "FIADO"], key=f"c_fp_{st.session_state.c_rk}")
        celular_caja = st.text_input("Celular del Cliente:", value=autocel, placeholder="099...", key=f"c_cel_{st.session_state.c_rk}")
        
        if st.button("Registrar Cobro y Generar Ticket", type="primary"):
            if not cliente_caja or monto_cobro <= 0: st.error("⚠️ Falta Nombre o Monto.")
            else:
                estado_venta = "Fiado Pendiente" if forma_pago == "FIADO" else "Cobrado"
                celular_formateado = limpiar_y_formatear_celular(celular_caja)
                
                gc = conectar_google()
                sh_feria = gc.open_by_url(st.session_state.link_feria)
                
                sh_feria.worksheet("Registro de Ventas").append_row([
                    datetime.now(TZ_UY).strftime("%d/%m/%Y"), datetime.now(TZ_UY).strftime("%H:%M:%S"), 
                    st.session_state.usuario_logueado, cliente_caja, autodet if autodet else "Caja Directa", 1, monto_cobro, celular_formateado, "", forma_pago, estado_venta
                ])
                
                try:
                    ws_cli = sh_feria.worksheet("Clientes")
                    nombres_existentes = [str(x).strip().lower() for x in ws_cli.col_values(1)[1:]]
                    if cliente_caja.strip().lower() not in nombres_existentes:
                        ws_cli.append_row([cliente_caja.strip(), celular_formateado, "Caja"])
                except: pass
                
                msg = f"👋 Hola *{cliente_caja}*, gracias por comprar en *{nombre_empresa}*.\nTotal: *${monto_cobro:,.1f}* ({forma_pago}).\n💚 ¡Te esperamos pronto!"
                
                st.session_state.ticket_generado = {
                    "msg": f"✅ ¡Cobro registrado con éxito ({estado_venta})!",
                    "link": f"https://wa.me/{celular_formateado}?text={urllib.parse.quote(msg)}" if celular_formateado else None
                }
                
                st.session_state.pedido_activo_caja = {"cliente": "", "celular": "", "total": 0.0, "detalle": "", "items": []}
                st.session_state.c_rk += 1
                st.rerun()
    idx += 1

# --- PESTAÑA 3: PEDIDOS WEB ---
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 🌐 Gestión de Pedidos Online")
        try:
            gc = conectar_google()
            ventas_data = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas").get_all_values()
            hay_web = False
            for row in ventas_data[1:]:
                if len(row) > 10 and "web" in str(row[10]).lower() and "pendiente" in str(row[10]).lower():
                    hay_web = True
                    cli, det, monto, cel, direc = row[3], row[4], row[6], row[7], row[8]
                    with st.expander(f"📦 Pendiente: {cli} - {row[0]}"):
                        st.write(f"**Detalle original:** {det}\n\n**Dirección:** {direc}\n\n**Celular:** {cel}")
                        c1, c2 = st.columns(2)
                        with c1: st.link_button("📲 Reenviar 'Pedido Recibido'", f"https://wa.me/{limpiar_y_formatear_celular(cel)}?text={urllib.parse.quote(f'Hola {cli} 🛒. ¡Recibimos tu pedido en {nombre_empresa}! A la brevedad será armado. ¡Gracias por elegirnos!')}")
                        with c2: st.link_button("🛵 Avisar 'Va en Camino'", f"https://wa.me/{limpiar_y_formatear_celular(cel)}?text={urllib.parse.quote(f'Hola {cli} 🛵. Tu pedido de {nombre_empresa} va en camino a tu domicilio.')}")
            
            if not hay_web: st.info("ℹ️ No hay pedidos web pendientes. (Ve a la pestaña Toma de Pedidos para armarlos).")
        except: st.error("Error leyendo pedidos web.")
    idx += 1

# --- PESTAÑA 4: PANEL ADMIN ---
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📊 Panel de Control y Fiados")
        try:
            gc = conectar_google()
            ventas_data = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas").get_all_values()
            
            total_recaudado = 0.0
            fiados = []
            
            for row in ventas_data[1:]:
                if len(row) > 6:
                    if len(row) > 4 and "ajeno" not in str(row[4]).lower():
                        try: total_recaudado += float(str(row[6]).replace("$","").replace(",","").strip())
                        except: pass
                if len(row) > 9 and "fiado" in str(row[9]).lower():
                    fiados.append(row)
            
            c1, c2 = st.columns(2)
            c1.metric("Total Registros", len(ventas_data)-1)
            c2.metric("Recaudación Propia Neta ($)", f"${total_recaudado:,.1f}")
            st.divider()
            
            st.subheader("💳 Control de Fiados Activos")
            if fiados:
                for row in fiados:
                    fecha, cli, monto, cel = row[0], row[3], row[6], row[7] if len(row)>7 else ""
                    try: dias = (datetime.now(TZ_UY).date() - datetime.strptime(fecha, "%d/%m/%Y").date()).days
                    except: dias = 0
                    alerta = "⚠️ *Más de 10 días*" if dias >= 10 else f"({dias} días)"
                    st.write(f"👤 **{cli}** | 💰 **${monto}** | Fecha: {fecha} {alerta}")
                    if cel: st.link_button(f"📲 Recordar a {cli}", f"https://wa.me/{limpiar_y_formatear_celular(cel)}?text={urllib.parse.quote(f'👋 Hola {cli}, desde {nombre_empresa} te recordamos tu saldo pendiente de ${monto} de la fecha {fecha}. ¡Gracias!')}")
            else: st.info("ℹ️ No hay fiados activos.")
        except: st.error("Error cargando panel admin.")
