import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json
import time

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y ESTILOS DE MÁXIMO CONTRASTE
# ==========================================
st.set_page_config(page_title="App Ferias - SaaS", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* PESTAÑAS */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; justify-content: center; }
    .stTabs [data-baseweb="tab"] {
        height: 55px; white-space: pre-wrap; background-color: #ffffff;
        border-radius: 10px; font-size: 16px; font-weight: 700;
        padding: 0 15px; border: 2px solid #2e7b32; color: #1b5e20;
    }
    .stTabs [aria-selected="true"] { background-color: #2e7b32 !important; border-color: #1b5e20 !important; color: #ffffff !important; }
    
    /* TEXTOS GENERALES EN NEGRITA Y OSCUROS */
    p, label, span, div, .stMarkdown { color: #111111 !important; font-weight: 600; }
    
    /* BOTONES PRIMARIOS: BLANCOS CON LETRA NEGRA GIGANTE Y EN NEGRITA PARA MÁXIMA VISIBILIDAD */
    button[kind="primary"] {
        background-color: #ffffff !important;
        border: 3px solid #111111 !important;
        color: #111111 !important;
        font-weight: 900 !important;
        font-size: 18px !important;
        padding: 14px !important;
        border-radius: 8px !important;
        box-shadow: 0px 4px 6px rgba(0,0,0,0.2);
    }
    button[kind="primary"]:hover {
        background-color: #f0f0f0 !important;
        color: #000000 !important;
    }

    /* BOTONES SECUNDARIOS */
    button {
        font-weight: bold !important;
        color: #111111 !important;
    }

    /* ALERTAS / ERRORES ROJOS */
    div[data-baseweb="notification"] {
        background-color: #d32f2f !important;
        color: #ffffff !important;
    }
    div[data-baseweb="notification"] p {
        color: #ffffff !important;
        font-weight: bold !important;
        font-size: 16px !important;
    }

    html, body, [data-testid="stAppViewContainer"] { overscroll-behavior-y: none !important; -webkit-overflow-scrolling: touch; }
    [data-testid="stMainBlockContainer"] { padding-bottom: 140px !important; }
    [data-testid="stSidebar"], [data-testid="collapsedControl"], footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; visibility: hidden !important; }
    button[title="View fullscreen"] { display: none !important; visibility: hidden !important; }
    [data-testid="StyledFullScreenButton"] { display: none !important; visibility: hidden !important; }
    </style>
    
    <script>
    const borrarFullscreen = () => {
        const elementos = document.querySelectorAll('a, button, div, span, svg');
        elementos.forEach(el => {
            if (el.innerText && (el.innerText.includes('Fullscreen') || el.innerText.includes('Built with Streamlit'))) {
                let contenedor = el.closest('div[style*="position"]') || el.parentElement;
                if (contenedor) { contenedor.style.display = 'none'; }
                el.style.display = 'none';
            }
        });
    };
    setInterval(borrarFullscreen, 300);
    </script>
""", unsafe_allow_html=True)

TZ_UY = timezone(timedelta(hours=-3))
LINK_MASTER_SHEET = "https://docs.google.com/spreadsheets/d/1CEuvlAwExOf1FS_ZYeFYw205aoVePb8SCmmLjUJTg-w/edit?gid=0#gid=0"

if 'v_rk' not in st.session_state: st.session_state.v_rk = 0 
if 'cli_nombre' not in st.session_state: st.session_state.cli_nombre = ""
if 'cli_celular' not in st.session_state: st.session_state.cli_celular = "598"
if 'modo_tomar' not in st.session_state: st.session_state.modo_tomar = "🛍️ Venta Local"
if 'web_step' not in st.session_state: st.session_state.web_step = 1
if 'cliente_retomado_aviso' not in st.session_state: st.session_state.cliente_retomado_aviso = ""

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

@st.cache_data(ttl=300)
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
    if pd.isna(celular_ingresado) or str(celular_ingresado).strip() == "" or str(celular_ingresado).strip().lower() == "nan": 
        return ""
    cel_str = str(celular_ingresado).strip()
    if "e+" in cel_str or "." in cel_str:
        try: cel_str = str(int(float(cel_str)))
        except: pass
    num = ''.join(filter(str.isdigit, cel_str))
    if not num: return ""
    if len(num) == 10 and not num.startswith("0") and not num.startswith("54"):
        return f"549{num}"
    if num.startswith("549"): return num
    if len(num) <= 9:
        if num.startswith("0"): num = num[1:]
        return f"598{num}"
    return num

def get_estado_col_index(row):
    kw = ["caja", "web", "entregado", "cancelado", "cobrado", "fiado", "pendiente", "cuenta", "abono", "confirmado", "devuelto"]
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
                    "cliente": row[3], "celular": limpiar_y_formatear_celular(row[7]), "pago": pago, 
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
                v["json"] = json.dumps([{"producto": it.get("producto", ""), "cantidad": it.get("cantidad", 0), "cantidad_txt": it.get("cantidad_txt", f"{it.get('cantidad', 0)}"), "subtotal": it.get("subtotal", 0.0), "ahorro": it.get("ahorro", 0.0), "tipo": it.get("tipo", "Propio")} for it in v["items"]])
        except:
            v["json"] = json.dumps([{"producto": it.get("producto", ""), "cantidad": it.get("cantidad", 0), "cantidad_txt": it.get("cantidad_txt", f"{it.get('cantidad', 0)}"), "subtotal": it.get("subtotal", 0.0), "ahorro": it.get("ahorro", 0.0), "tipo": it.get("tipo", "Propio")} for it in v["items"]])
        v["detalle"] = " | ".join([f"{item.get('producto', '')} ({item.get('cantidad_txt', item.get('cantidad', ''))})" for item in v["items"]])
        
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
        
    productos, precios, descuentos, medidas, nombres_planos, medidas_planas, stock_inicial = [], {}, {}, {}, {}, {}, {}
    try:
        ws_prod = sh.worksheet("Productos")
        filas_p = ws_prod.get_all_values()
        cabeceras_p = [str(c).strip().lower() for c in filas_p[0]]
        
        idx_medida = cabeceras_p.index('medida') if 'medida' in cabeceras_p else 6
        idx_stock = cabeceras_p.index('stock') if 'stock' in cabeceras_p else (-1)
        if idx_stock == -1 and 'stock inicial' in cabeceras_p:
            idx_stock = cabeceras_p.index('stock inicial')
        
        for fila in filas_p[1:]:
            if len(fila) >= 3 and fila[1].strip() and fila[1].strip().lower() != "producto":  
                emoji = fila[0].strip()
                nombre = fila[1].strip()
                precio_str = str(fila[2]).replace("$", "").replace(",", ".").strip()
                try: precio = float(precio_str) if precio_str else 0.0
                except: precio = 0.0
                
                desc = 0.0
                if len(fila) >= 6 and str(fila[5]).strip() and str(fila[5]).strip().lower() != "nan":
                    desc_str = str(fila[5]).replace("%", "").replace(",", ".").strip()
                    try: desc = float(desc_str)
                    except: pass
                
                medida = "kg"
                if len(fila) > idx_medida and str(fila[idx_medida]).strip():
                    medida = str(fila[idx_medida]).strip().lower()
                
                s_ini = 0.0
                if idx_stock != -1 and len(fila) > idx_stock and str(fila[idx_stock]).strip():
                    try: s_ini = float(str(fila[idx_stock]).replace(",", "."))
                    except: pass
                
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
                stock_inicial[prod_full] = s_ini
    except: pass

    clientes_dict = {}
    try:
        ws_cli = sh.worksheet("Clientes")
        filas_cli = ws_cli.get_all_values()
        for fila in filas_cli[1:]:
            if len(fila) >= 1 and fila[0].strip() and fila[0].strip().lower() != "nombre":
                nombre_c = fila[0].strip().upper()
                celular_c = limpiar_y_formatear_celular(fila[1]) if len(fila) > 1 and fila[1] else ""
                clientes_dict[nombre_c] = celular_c
    except: pass
    
    return productos, precios, descuentos, medidas, nombres_planos, clientes_dict, config, medidas_planas, stock_inicial

# ==========================================
# 3. MODO TIENDA PÚBLICA (WIZARD CON 4 PASOS)
# ==========================================
query_params = st.query_params
if "feria" in query_params:
    codigo_feria = query_params["feria"]
    link_excel = obtener_datos_cliente(codigo_feria)
    
    if link_excel == "SUSPENDIDO":
        st.error("🚫 Esta tienda se encuentra temporalmente inactiva.")
        st.stop()
    elif not link_excel:
        st.error("⚠️ Error de conexión o código de feria inválido. Por favor, actualiza la página.")
        st.stop()
    
    try:
        productos, precios, descuentos, medidas, nombres_planos, clientes_dict, config, _, _ = cargar_datos_feria(link_excel)
        nombre_feria = config.get("nombre_empresa", config.get("nombre", "Nuestra Feria"))
        celular_feriante = config.get("celular_feriante", config.get("celular_contacto", "59893343092"))
        bienvenida_dia = config.get("bienvenida", config.get("ofertas", config.get("banner", "")))
        
        productos_ord_web = sorted(productos, key=lambda x: nombres_planos.get(x, x).strip().lower())
        
        st.title(f"🛒 {nombre_feria}")
        if bienvenida_dia: st.info(f"🔥 **OFERTAS Y NOVEDADES:**\n\n{bienvenida_dia}")
        
        with st.expander("ℹ️ Pasos para tu Pedido Online", expanded=(st.session_state.web_step == 1)):
            st.markdown("""
            1️⃣ **Datos:** Completa tu nombre, celular y dirección.
            2️⃣ **Productos:** **PRIMERO ELIGE LA MERCADERÍA CON SU PESO** y luego aprieta el botón de **'IR A MI CARRITO'** (arriba o abajo).
            3️⃣ **Revisión:** Verifica el total de tu compra.
            4️⃣ **Confirmar:** Envía el WhatsApp para asegurar el pedido.
            """)
        
        st.markdown(f"<h3 style='text-align: center; color: #2e7b32;'>📋 Paso {st.session_state.web_step} de 4</h3>", unsafe_allow_html=True)
        st.divider()

        if 'q_web' not in st.session_state: st.session_state.q_web = {}

        def procesar_carrito_web():
            st.session_state.carrito_web = []
            for p, dict_q in st.session_state.q_web.items():
                m = medidas.get(p, "kg")
                c = dict_q['kg_un'] + (dict_q['gr'] / 1000.0)
                if c > 0:
                    pr_orig = precios.get(p, 0)
                    desc_p = descuentos.get(p, 0)
                    pr_fin = pr_orig * (1 - desc_p/100)
                    st.session_state.carrito_web.append({
                        "producto": nombres_planos.get(p, p),
                        "cantidad": c, "cantidad_txt": f"{int(c)}un" if m=="un" else f"{c}kg",
                        "subtotal": c * pr_fin, "ahorro": c*(pr_orig - pr_fin)
                    })
            if not st.session_state.carrito_web:
                st.warning("⚠️ Debes sumar cantidades a al menos un producto.")
            else:
                st.session_state.web_step = 3
                st.rerun()

        if st.session_state.web_step == 1:
            st.subheader("1️⃣ Tus Datos de Entrega")
            if 'cli_web_nombre' not in st.session_state: st.session_state.cli_web_nombre = ""
            if 'cli_web_celular' not in st.session_state or not st.session_state.cli_web_celular: 
                st.session_state.cli_web_celular = "598"
            if 'cli_web_dir' not in st.session_state: st.session_state.cli_web_dir = ""
            if 'cli_web_obs' not in st.session_state: st.session_state.cli_web_obs = ""
            
            st.session_state.cli_web_nombre = st.text_input("Nombre y Apellido:", value=st.session_state.cli_web_nombre)
            st.session_state.cli_web_celular = st.text_input("Celular (Uy: 598 / Arg: 549):", value=st.session_state.cli_web_celular)
            st.session_state.cli_web_dir = st.text_input("Dirección de Envío (Calle, Nro y Esquina):", value=st.session_state.cli_web_dir)
            st.session_state.cli_web_obs = st.text_area("Observaciones (Opcional):", value=st.session_state.cli_web_obs)
            
            st.divider()
            if st.button("Siguiente: Elegir Productos ➡️", type="primary", use_container_width=True, key="btn_next_step1"):
                if not st.session_state.cli_web_nombre or not st.session_state.cli_web_dir:
                    st.error("⚠️ Por favor completa tu Nombre y Dirección.")
                else:
                    st.session_state.web_step = 2
                    if 'web_rk' not in st.session_state: st.session_state.web_rk = 0
                    st.session_state.web_rk += 1 
                    st.rerun()

        elif st.session_state.web_step == 2:
            st.subheader("2️⃣ Listado de Productos")
            st.markdown("<a name='inicio_web'></a>", unsafe_allow_html=True)
            st.warning("⚠️ **PRIMERO ELIGE LA MERCADERÍA CON SU PESO Y LUEGO APRIETA 'IR A MI CARRITO'** (puedes usar el botón de arriba, el de abajo, o los atajos junto a cada verdura).")
            
            if st.button("🛒 IR A MI CARRITO", type="primary", use_container_width=True, key="btn_cart_top_web"):
                procesar_carrito_web()

            st.markdown("---")
            filtro_txt = st.text_input("🔍 Buscar fruta o verdura por nombre...", "").lower()
            st.markdown("---")
            
            for prod_full in productos_ord_web:
                if filtro_txt and filtro_txt not in prod_full.lower(): continue
                
                if prod_full not in st.session_state.q_web:
                    st.session_state.q_web[prod_full] = {'kg_un': 0.0, 'gr': 0.0}
                
                medida_p = medidas.get(prod_full, "kg")
                precio_orig = precios.get(prod_full, 0)
                desc_p = descuentos.get(prod_full, 0)
                p_final = precio_orig * (1 - desc_p/100)
                
                col_inf, col_bot1, col_bot2 = st.columns([0.6, 0.2, 0.2])
                with col_inf:
                    st.markdown(f"<div style='margin-top: 5px;'><b style='font-size: 16px;'>{prod_full}</b><br><span style='color:#2e7b32; font-size: 14px; font-weight: bold;'>${p_final:,.1f}/{medida_p}</span></div>", unsafe_allow_html=True)
                with col_bot1:
                    if st.button("⬆️ Inicio", key=f"top_{prod_full}_{st.session_state.web_rk}", use_container_width=True):
                        st.rerun()
                with col_bot2:
                    if st.button("🛒 Carrito", key=f"bot_{prod_full}_{st.session_state.web_rk}", type="primary", use_container_width=True):
                        procesar_carrito_web()
                
                if medida_p == "un":
                    st.session_state.q_web[prod_full]['kg_un'] = st.number_input(
                        "Cantidad (Unidades)", min_value=0.0, step=1.0, 
                        value=float(st.session_state.q_web[prod_full]['kg_un']), 
                        key=f"w_k_{prod_full}_{st.session_state.web_rk}"
                    )
                else:
                    st.session_state.q_web[prod_full]['kg_un'] = st.number_input(
                        "Kilos (Ej: 0.5 medio, 1.5 kilo y medio)", min_value=0.0, step=0.5, 
                        value=float(st.session_state.q_web[prod_full]['kg_un']), 
                        key=f"w_k_{prod_full}_{st.session_state.web_rk}"
                    )
                    st.session_state.q_web[prod_full]['gr'] = st.number_input(
                        "Gramos extra (Ej: 250)", min_value=0.0, step=25.0, 
                        value=float(st.session_state.q_web[prod_full]['gr']), 
                        key=f"w_g_{prod_full}_{st.session_state.web_rk}"
                    )
                st.markdown("<hr style='margin: 8px 0 12px 0; border: 1px solid #ccc;'>", unsafe_allow_html=True)

            st.divider()
            
            if st.button("🛒 IR A MI CARRITO", type="primary", use_container_width=True, key="btn_cart_bottom_web"):
                procesar_carrito_web()

            if st.button("⬅️ Atrás", use_container_width=True, key="btn_back_step2_web"):
                st.session_state.web_step = 1
                st.session_state.web_rk += 1
                st.rerun()

        elif st.session_state.web_step == 3:
            st.subheader("3️⃣ Revisión de tu Pedido")
            st.markdown(f"**Cliente:** {st.session_state.cli_web_nombre.upper()}")
            st.markdown(f"**Dirección:** {st.session_state.cli_web_dir}")
            st.markdown("---")
            
            tot_web = 0.0
            idx_to_del = []
            
            for idx_cw, itw in enumerate(st.session_state.carrito_web):
                col_cruz, col_txt = st.columns([0.18, 0.82])
                with col_cruz:
                    if st.button("❌", key=f"del_w3_{idx_cw}"):
                        idx_to_del.append(idx_cw)
                with col_txt: 
                    st.markdown(f"<div style='padding-top: 6px;'><b>{itw['producto']}</b> ({itw['cantidad_txt']}) &nbsp; <span style='color:#2e7b32; font-weight: bold;'>${itw['subtotal']:,.1f}</span></div>", unsafe_allow_html=True)
                
                tot_web += itw['subtotal']
                st.markdown("<div style='margin-bottom: 4px;'></div>", unsafe_allow_html=True)
            
            if idx_to_del:
                rev_nom_web = {v: k for k, v in nombres_planos.items()}
                for d in sorted(idx_to_del, reverse=True):
                    rem_item = st.session_state.carrito_web.pop(d)
                    pf = rev_nom_web.get(rem_item['producto'], rem_item['producto'])
                    if pf in st.session_state.q_web:
                        st.session_state.q_web[pf] = {'kg_un': 0.0, 'gr': 0.0}
                st.rerun()
                
            st.markdown("---")
            st.markdown(f"### Total Estimado: **${tot_web:,.1f}**")
            st.warning("⚖️ El importe es estimado según el peso exacto en la balanza.")
            st.divider()
            
            if st.button("Confirmar y Enviar ➡️", type="primary", use_container_width=True, key="btn_confirm_web"):
                try:
                    if not st.session_state.carrito_web:
                        st.warning("Tu carrito está vacío.")
                        st.stop()
                        
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
                    time.sleep(1)
                    st.session_state.web_step = 4
                    st.rerun()
                except Exception as ex_step3:
                    st.error(f"Error al procesar el pedido: {ex_step3}")

            if st.button("⬅️ Volver a Productos", use_container_width=True, key="btn_back_step3_web"):
                st.session_state.web_step = 2
                st.session_state.web_rk += 1
                st.rerun()

        elif st.session_state.web_step == 4:
            st.subheader("4️⃣ Paso Final: Enviar WhatsApp")
            st.success("✅ ¡Tu pedido se guardó con éxito en el local!")
            st.markdown("⚠️ **Muy importante:** Envía este aviso por WhatsApp para asegurar el armado rápido de tu pedido.")
            
            num_feriante_limpio = limpiar_y_formatear_celular(celular_feriante)
            if not num_feriante_limpio: num_feriante_limpio = "59893343092"
            
            tot_web = sum(i['subtotal'] for i in st.session_state.carrito_web)
            detalle_str = "\n".join([f"• {i['producto']} ({i['cantidad_txt']})" for i in st.session_state.carrito_web])
            msg_feriante = f"🛒 *NUEVO PEDIDO WEB*\n👤 Cliente: {st.session_state.cli_web_nombre.upper()}\n📍 Dirección: {st.session_state.cli_web_dir}\n💰 Total Est.: ${tot_web:,.1f}\n\n📦 *Mi Pedido:*\n{detalle_str}"
            
            link_ws_web = f"https://api.whatsapp.com/send?phone={num_feriante_limpio}&text={urllib.parse.quote(msg_feriante)}"
            st.link_button("📲 ENVIAR AVISO AL LOCAL AHORA", link_ws_web, type="primary", use_container_width=True)
            
            st.divider()
            if st.button("🔄 Hacer otro pedido", use_container_width=True, key="btn_new_order_web"):
                st.session_state.carrito_web = []
                if 'q_web' in st.session_state: del st.session_state.q_web
                st.session_state.cli_web_obs = ""
                st.session_state.web_step = 1
                if 'web_rk' not in st.session_state: st.session_state.web_rk = 0
                st.session_state.web_rk += 1
                st.rerun()

    except Exception as e:
        st.error(f"Error en tienda web: {e}")
    st.stop()

# ==========================================
# 4. MODO PRIVADO Y LOGIN DE SEGURIDAD
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
    
    if st.button("🚪 Ingresar", type="primary", key="btn_login"):
        time.sleep(1.5)
        
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

# Obtener datos globales
ventas_data_global = obtener_ventas(st.session_state.link_feria)
PRODUCTOS, PRECIOS, DESCUENTOS, MEDIDAS, NOMBRES, CLIENTES_DICT, CONFIG, MEDIDAS_PLANAS, STOCK_INICIAL = cargar_datos_feria(st.session_state.link_feria)
nombre_empresa = CONFIG.get("nombre_empresa", CONFIG.get("nombre", "La Feria"))
celular_feriante_local = CONFIG.get("celular_feriante", CONFIG.get("celular_contacto", "59893343092"))

productos_ord_loc = sorted(PRODUCTOS, key=lambda x: NOMBRES.get(x, x).strip().lower())

with st.sidebar:
    st.success(f"Hola, **{st.session_state.usuario_logueado}**\n\nRol: {st.session_state.rol_logueado}")
    if st.button("Cerrar Sesión", key="btn_logout"):
        st.session_state.usuario_logueado = None
        st.session_state.cliente_retomado_aviso = ""
        st.session_state.cli_nombre = ""
        st.session_state.cli_celular = "598"
        if 'q_loc' in st.session_state: del st.session_state.q_loc
        st.rerun()

st.title(f"🏢 {nombre_empresa}")

# ==========================================
# 5. PESTAÑAS Y ROLES ORDENADOS
# ==========================================
tabs_nombres = ["📖 Guía y Flujo"]
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]: 
    tabs_nombres.append("📝 Tomar Pedido")
if st.session_state.rol_logueado in ["Admin", "Cajero"]: 
    tabs_nombres.append("🌐 Estado Pedidos Web")
    tabs_nombres.append("💰 Caja y Cobro")
    tabs_nombres.append("💳 Cuentas A Cobrar")
    tabs_nombres.append("🛵 Entregas a Domicilio")
if st.session_state.rol_logueado == "Admin": 
    tabs_nombres.append("📊 Panel Admin")
    tabs_nombres.append("📈 Reportes Pro (Stock y Ventas)")
    tabs_nombres.append("📥 Reportes Pro (Saldos Pendientes)")

tabs = st.tabs(tabs_nombres)
idx = 0

# =======================================================
# PESTAÑA 1: GUÍA Y DIAGRAMA DE FLUJO VISUAL COMPLETO
# =======================================================
with tabs[idx]:
    st.write("### 📖 Guía de Uso y Diagrama de Flujo del Sistema")
    st.info("Este esquema visual muestra el camino exacto que recorre cada pedido dentro del negocio:")
    
    st.markdown("""
    ```text
    [ 🌐 CLIENTE WEB ] ---> ( Estado Pedidos Web ) ---> [ ⚖️ AJUSTAR PEDIDO WEB ]
           |                                                        |
           v                                                        v
    ( Envía por WhatsApp )                                  ( Pesa en balanza )
                                                                    |
                                                                    v
    [ 🏪 VENTA LOCAL ]  ---> ( Tomar Pedido ) --------> [ 💳 CAJA Y COBRO ]
           ^                                                        |
           |                                                        +---> [ 🛵 Reparto / Logística ]
    ( Retomar desde Caja )                                          +---> [ 💳 Cuentas a Cobrar ]
