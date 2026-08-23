import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 0. CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(page_title="Punto de Venta Feria", layout="centered")

# ==========================================
# 1. SISTEMA DE SEGURIDAD Y ROLES
# ==========================================
USUARIOS_PERMITIDOS = {
    "Juan": {"clave": "juan123", "rol": "Vendedor"},
    "Pedro": {"clave": "pedro456", "rol": "Vendedor"},
    "María": {"clave": "maria789", "rol": "Vendedor"},
    "Caja Principal": {"clave": "caja2026", "rol": "Admin"},
    "Dueño": {"clave": "admin000", "rol": "Admin"}
}

if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None

if st.session_state.usuario_logueado is None:
    st.title("🔒 Acceso al Sistema")
    st.write("Por favor, identifícate para comenzar a tomar pedidos.")
    
    with st.container():
        st.write("---")
        usuario_intento = st.selectbox("Usuario:", ["Seleccionar..."] + list(USUARIOS_PERMITIDOS.keys()))
        clave_intento = st.text_input("Contraseña:", type="password")
        
        if st.button("🚪 Ingresar"):
            if usuario_intento == "Seleccionar...":
                st.warning("Selecciona un usuario válido.")
            else:
                datos_usuario = USUARIOS_PERMITIDOS.get(usuario_intento)
                if datos_usuario["clave"] == clave_intento:
                    st.session_state.usuario_logueado = usuario_intento
                    st.session_state.rol_logueado = datos_usuario["rol"]
                    st.rerun()
                else:
                    st.error("❌ Contraseña incorrecta.")
    
    st.stop() 

with st.sidebar:
    color_rol = "🟢" if st.session_state.rol_logueado == "Vendedor" else "👑"
    st.success(f"{color_rol} Usuario: **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión"):
        st.session_state.usuario_logueado = None
        st.session_state.rol_logueado = None
        st.rerun()

# ==========================================
# 2. INVENTARIO Y CONEXIONES (APP PRINCIPAL)
# ==========================================
LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?output=csv" 
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=832040050#gid=832040050"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        df = pd.read_csv(LINK_CSV_BALANCE, encoding='utf-8', on_bad_lines='skip')
        df.columns = df.columns.str.strip()
        
        col_prod = next((c for c in df.columns if "roducto" in c.lower()), None)
        if 'Emoji' in df.columns:
            df['Prod_Full'] = df['Emoji'].astype(str) + " " + df[col_prod].astype(str)
        else:
            df['Prod_Full'] = df[col_prod].astype(str)
            
        nombres_planos = dict(zip(df['Prod_Full'], df[col_prod].astype(str).str.strip()))
        col_precio = next((c for c in df.columns if "recio" in c.lower()), None)
        df['Precio_Num'] = df[col_precio].astype(str).str.replace('$', '', regex=False).str.replace(',', '.', regex=False) if col_precio else "0"
        
        precios = dict(zip(df['Prod_Full'], pd.to_numeric(df['Precio_Num'], errors='coerce').fillna(0)))
        descuentos = {p: 0 for p in df['Prod_Full']}
        col_desc = next((c for c in df.columns if "escuento" in c.lower()), None)
        if col_desc:
            descuentos = dict(zip(df['Prod_Full'], pd.to_numeric(df[col_desc], errors='coerce').fillna(0)))
            
        return df['Prod_Full'].tolist(), precios, descuentos, nombres_planos
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return [], {}, {}, {}

PRODUCTOS, PRECIOS, DESCUENTOS, NOMBRES_PLANOS = cargar_inventario()

def obtener_ventas_hoy():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]), scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
        return sheet.get_all_values(), sheet
    except Exception as e:
        st.error("Error al conectar con Google Sheets.")
        return [], None

if "carrito_vendedor" not in st.session_state: st.session_state.carrito_vendedor = []
if "carrito_cajero" not in st.session_state: st.session_state.carrito_cajero = []

st.title("🛒 Sistema de Feria")

if st.session_state.rol_logueado == "Admin":
    tabs = st.tabs(["📝 Tomar Pedido", "💻 Retomar y Cobrar (Caja)", "📊 Panel Admin"])
    tab_vendedor = tabs[0]
    tab_cajero = tabs[1]
    tab_admin = tabs[2]
else:
    tabs = st.tabs(["📝 Tomar Pedido", "💻 Retomar y Cobrar (Caja)"])
    tab_vendedor = tabs[0]
    tab_cajero = tabs[1]
    tab_admin = None

# ==========================================
# PESTAÑA 1: MODO VENDEDOR
# ==========================================
with tab_vendedor:
    st.write("### Datos del Cliente")
    col1, col2 = st.columns(2)
    with col1:
        vendedor = st.session_state.usuario_logueado
        st.text_input("Vendedor:", value=vendedor, disabled=True) 
        cliente = st.text_input("Nombre del Cliente:", key="cliente")
    with col2:
        caja = st.selectbox("¿A qué Caja se envía?", ["Caja 1", "Caja 2"], key="caja")
        tel_cliente = st.text_input("Celular del Cliente (Ej: 598...):", key="tel_cliente")
    
    st.divider()
    st.write("### 🔍 Buscador de Productos")
    
    col_busc, col_btn = st.columns([8, 2])
    with col_busc:
        prod_buscado = st.selectbox("Escribe o busca el producto:", ["Seleccionar..."] + PRODUCTOS, key="buscador_vendedor")
    with col_btn:
        st.write("")
        st.write("")
        if st.button("➕ Agregar"):
            if prod_buscado != "Seleccionar..." and prod_buscado not in st.session_state.carrito_vendedor:
                st.session_state.carrito_vendedor.append(prod_buscado)
                st.rerun()

    pedidos_vendedor = {}
    total_vendedor = 0.0

    if st.session_state.carrito_vendedor:
        st.write("### 🛒 Tu Carrito")
        
        for p in st.session_state.carrito_vendedor:
            with st.container():
                col_nombre, col_quitar = st.columns([8, 2])
                col_nombre.markdown(f"**{p}**")
                if col_quitar.button("❌ Quitar", key=f"del_vend_{p}"):
                    st.session_state.carrito_vendedor.remove(p)
                    st.rerun()
                
                es_unidad = "unidad" in p.lower() or "(u)" in p.lower()
                tipo_medida = st.radio("Se vende por:", ["Peso (Kgs/Grs)", "Unidades"], index=1 if es_unidad else 0, key=f"medida_vend_{p}", horizontal=True)
                
                if tipo_medida == "Unidades":
                    cant = st.number_input("Cantidad (Unidades):", min_value=0, step=1, key=f"uni_vend_{p}")
                    cant_txt = f"{int(cant)} Unidades"
                else:
                    c_kilos, c_gramos = st.columns(2)
                    with c_kilos: kilos = st.number_input("Kilos:", min_value=0, step=1, key=f"kg_vend_{p}")
                    with c_gramos: gramos = st.number_input("Gramos:", min_value=0, max_value=999, step=50, key=f"gr_vend_{p}")
                    cant = kilos + (gramos / 1000.0)
                    cant_txt = f"{cant:.3f} Kgs"

                if cant > 0:
                    precio = PRECIOS.get(p, 0)
                    subtotal = cant * (precio * (1 - (DESCUENTOS.get(p, 0) / 100)))
                    pedidos_vendedor[p] = {"cant": cant, "cant_txt": cant_txt, "subtotal": subtotal}
                    total_vendedor += subtotal
                st.divider()

    if total_vendedor > 0:
        st.write(f"### Subtotal: ${total_vendedor:,.1f}")
        if st.button("🚀 Enviar a Caja"):
            if not cliente:
                st.warning("Falta completar el nombre del Cliente.")
            else:
                _, sheet = obtener_ventas_hoy()
                if sheet:
                    for p, d in pedidos_vendedor.items():
                        sheet.append_row([str(date.today()), datetime.now().strftime("%H:%M:%S"), vendedor, cliente, NOMBRES_PLANOS.get(p, p), d['cant'], d['subtotal'], tel_cliente])
                    
                    st.success("✅ Pedido enviado a Caja y guardado en Excel.")
                    
                    msg_caja = f"🛒 NUEVO PEDIDO\n👤 Vend: {vendedor} | Cliente: {cliente}\n📱 Tel: {tel_cliente}\n-------------------\n"
                    for p, d in pedidos_vendedor.items():
                        msg_caja += f" • {d['cant_txt']} x {p} = ${d['subtotal']:,.1f}\n"
                    msg_caja += f"-------------------\n💰 TOTAL: ${total_vendedor:,.1f}\n\n*Ya puedes retomar este pedido en la Pestaña Cajero.*"
                    
                    num_caja = "59893343092" if caja == "Caja 1" else "59899111222"
                    st.link_button(f"📲 Avisar a {caja} por WhatsApp", f"https://wa.me/{num_caja}?text={urllib.parse.quote(msg_caja)}")
                    
                    st.session_state.carrito_vendedor = []

# ==========================================
# PESTAÑA 2: MODO CAJERO
# ==========================================
with tab_cajero:
    st.write("### 🔎 Buscar Pedidos Pendientes de Hoy")
    if st.button("🔄 Actualizar Base de Datos"):
        st.rerun()
        
    datos, sheet_caja = obtener_ventas_hoy()
    hoy_str = str(date.today())
    clientes_hoy = {}
    
    for row in datos:
        if len(row) >= 7 and row[0] == hoy_str:
            c_nombre = row[3]
            c_prod = row[4]
            c_subt = float(row[6]) if row[6] else 0.0
            c_cel = row[7] if len(row) >= 8 else ""
            
            if c_nombre not in clientes_hoy:
                clientes_hoy[c_nombre] = {"productos": [], "total": 0.0, "celular": c_cel}
            
            clientes_hoy[c_nombre]["productos"].append(f"{c_prod} (${c_subt:,.1f})")
            clientes_hoy[c_nombre]["total"] += c_subt

    lista_clientes = ["Seleccionar Cliente..."] + list(clientes_hoy.keys())
    cliente_seleccionado = st.selectbox("Selecciona el Cliente a cobrar:", lista_clientes)
    
    if cliente_seleccionado != "Seleccionar Cliente...":
        datos_cliente = clientes_hoy[cliente_seleccionado]
        tel_cajero = st.text_input("Celular del Cliente:", value=datos_cliente["celular"], key="tel_cajero")
        
        st.info(f"**Ya pidió hoy (${datos_cliente['total']:,.1f}):**\n\n" + "\n".join([f"• {p}" for p in datos_cliente["productos"]]))
        
        st.divider()
        st.write("### ➕ ¿Quiere agregar algo más en la caja?")
        
        col_busc_c, col_btn_c = st.columns([8, 2])
        with col_busc_c:
            prod_caja = st.selectbox("Buscar extra:", ["Seleccionar..."] + PRODUCTOS, key="buscador_cajero")
        with col_btn_c:
            st.write("")
            st.write("")
            if st.button("➕ Agregar Extra"):
                if prod_caja != "Seleccionar..." and prod_caja not in st.session_state.carrito_cajero:
                    st.session_state.carrito_cajero.append(prod_caja)
                    st.rerun()
        
        pedidos_extra = {}
        total_extra = 0.0
        
        for p in st.session_state.carrito_cajero:
            with st.container():
                col_nombre, col_quitar = st.columns([8, 2])
                col_nombre.markdown(f"**{p}**")
                if col_quitar.button("❌ Quitar", key=f"del_caj_{p}"):
                    st.session_state.carrito_cajero.remove(p)
                    st.rerun()
                
                es_unidad = "unidad" in p.lower() or "(u)" in p.lower()
                tipo_medida = st.radio("Se vende por:", ["Peso (Kgs/Grs)", "Unidades"], index=1 if es_unidad else 0, key=f"medida_caj_{p}", horizontal=True)
                
                if tipo_medida == "Unidades":
                    cant = st.number_input("Cantidad (Unidades):", min_value=0, step=1, key=f"uni_caj_{p}")
                    cant_txt = f"{int(cant)} Unidades"
                else:
                    c_kilos, c_gramos = st.columns(2)
                    with c_kilos: kilos = st.number_input("Kilos:", min_value=0, step=1, key=f"kg_caj_{p}")
                    with c_gramos: gramos = st.number_input("Gramos:", min_value=0, max_value=999, step=50, key=f"gr_caj_{p}")
                    cant = kilos + (gramos / 1000.0)
                    cant_txt = f"{cant:.3f} Kgs"

                if cant > 0:
                    precio = PRECIOS.get(p, 0)
                    subtotal = cant * (precio * (1 - (DESCUENTOS.get(p, 0) / 100)))
                    pedidos_extra[p] = {"cant": cant, "cant_txt": cant_txt, "subtotal": subtotal}
                    total_extra += subtotal
                st.divider()
        
        gran_total = datos_cliente['total'] + total_extra
        st.write(f"### 💰 GRAN TOTAL A COBRAR: ${gran_total:,.1f}")
        
        if st.button("✅ Cerrar Venta y Enviar Ticket al Cliente"):
            if sheet_caja and pedidos_extra:
                for p, d in pedidos_extra.items():
                    sheet_caja.append_row([str(date.today()), datetime.now().strftime("%H:%M:%S"), st.session_state.usuario_logueado, cliente_seleccionado, NOMBRES_PLANOS.get(p, p), d['cant'], d['subtotal'], tel_cajero])
            
            msg_final = f"👋 Hola {cliente_seleccionado}, gracias por comprar en la feria.\n\n"
            msg_final += f"🧾 *RESUMEN DE TU COMPRA:*\n"
            msg_final += "\n".join([f"• {p}" for p in datos_cliente["productos"]]) + "\n"
            if pedidos_extra:
                msg_final += "\n".join([f"• {d['cant_txt']} x {p} (${d['subtotal']:,.1f})" for p, d in pedidos_extra.items()]) + "\n"
            msg_final += f"-------------------\n💰 TOTAL ABONADO: ${gran_total:,.1f}\n\n¡Que lo disfrutes! 🍎"
            
            if tel_cajero:
                num_cliente = tel_cajero.replace(" ", "").replace("+", "")
                st.link_button("📲 Enviar Ticket FINAL al Cliente", f"https://wa.me/{num_cliente}?text={urllib.parse.quote(msg_final)}")
            else:
                st.warning("⚠️ No hay número de celular para enviar el ticket, pero la venta se registró.")
            
            st.session_state.carrito_cajero = []

# ==========================================
# PESTAÑA 3: PANEL ADMIN (Oculta para vendedores)
# ==========================================
if tab_admin:
    with tab_admin:
        st.write("### 📊 Panel de Control del Día")
        st.caption("Solo los administradores o cajas pueden ver esta sección.")
        
        datos_admin, _ = obtener_ventas_hoy()
        
        if datos_admin and len(datos_admin) > 1:
            # 1. Cargamos todo a un DataFrame
            df_ventas = pd.DataFrame(datos_admin)
            
            # 2. Aseguramos tener al menos 8 columnas para no romper el código si el excel tiene menos
            for i in range(len(df_ventas.columns), 8):
                df_ventas[i] = ""
                
            # 3. Recortamos a 8 columnas y nombramos
            df_ventas = df_ventas.iloc[:, :8]
            df_ventas.columns = ["Fecha", "Hora", "Vendedor", "Cliente", "Producto", "Cantidad", "Subtotal", "Celular"]
            
            # 4. Eliminamos la fila de títulos si existe (normalmente la fila 0)
            if df_ventas.iloc[0]["Fecha"].lower() == "fecha":
                df_ventas = df_ventas.iloc[1:]
            
            # 5. Filtramos solo lo de hoy
            df_ventas_hoy = df_ventas[df_ventas["Fecha"] == str(date.today())].copy()
            
            if not df_ventas_hoy.empty:
                # Convertimos subtotales asegurando formato numérico (evita errores con comas o textos)
                df_ventas_hoy["Subtotal"] = pd.to_numeric(df_ventas_hoy["Subtotal"].astype(str).str.replace(',', '.'), errors="coerce").fillna(0)
                
                total_recaudado = df_ventas_hoy["Subtotal"].sum()
                
                st.metric(label="💰 Recaudación Total de Hoy", value=f"${total_recaudado:,.1f}")
                
                st.write("---")
                st.write("#### 🏆 Ventas por Vendedor")
                ventas_por_vend = df_ventas_hoy.groupby("Vendedor")["Subtotal"].sum().reset_index()
                
                ventas_por_vend["Subtotal"] = ventas_por_vend["Subtotal"].apply(lambda x: f"${x:,.1f}")
                st.dataframe(ventas_por_vend, hide_index=True, use_container_width=True)
                
            else:
                st.info("Todavía no hay ventas registradas en el día de hoy.")
        else:
            st.info("El Registro de Ventas está vacío. Comienza a tomar pedidos.")
