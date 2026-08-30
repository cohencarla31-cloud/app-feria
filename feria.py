import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json
import time

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y CSS (CON BOTÓN FLOTANTE DE ANCLAJE)
# ==========================================
st.set_page_config(page_title="App Ferias - SaaS", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    div.row-widget.stRadio > div { flex-wrap: wrap; justify-content: center; gap: 8px; }
    div.row-widget.stRadio > div > label { background-color: #f0f2f6; padding: 10px 15px; border-radius: 8px; font-size: 16px; border: 2px solid #ddd; cursor: pointer; margin: 2px; }
    div.row-widget.stRadio > div > label:hover { border-color: #ff4b4b; background-color: #ffcccc; }
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        overscroll-behavior-y: none !important;
        -webkit-overflow-scrolling: touch;
        overflow-x: hidden !important; 
    }
    
    [data-testid="stMainBlockContainer"] { 
        padding-bottom: 140px !important; 
        overflow-x: hidden !important;
    }
    
    [data-testid="stSidebar"], [data-testid="collapsedControl"], footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; visibility: hidden !important; }
    button[title="View fullscreen"] { display: none !important; visibility: hidden !important; }
    [data-testid="StyledFullScreenButton"] { display: none !important; visibility: hidden !important; }
    
    /* BOTÓN FLOTANTE INTELIGENTE PARA IR AL FINAL AL INSTANTE */
    .btn-flotante-fin {
        position: fixed;
        bottom: 80px;
        right: 20px;
        background-color: #2e7b32;
        color: white;
        padding: 10px 16px;
        border-radius: 30px;
        font-weight: bold;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
        z-index: 99999;
        text-decoration: none;
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    .btn-flotante-fin:hover {
        background-color: #235d26;
        color: white;
    }
    
    @media (max-width: 600px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 5px !important;
        }
        div[data-testid="column"] {
            min-width: 0 !important;
            padding: 0 2px !important;
        }
        div[data-baseweb="input"] button {
            width: 25px !important;
            padding: 0 !important;
        }
        label[data-testid="stWidgetLabel"] p {
            font-size: 13px !important;
            color: #444 !important;
        }
    }
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
    kw = ["caja", "web", "entregado", "cancelado", "cobrado", "fiado", "pendiente", "cuenta", "abono"]
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
            2️⃣ **Productos:** Usa las flechitas o escribe la cantidad debajo de cada producto.
            3️⃣ **Revisión:** Verifica el total de tu compra.
            4️⃣ **Confirmar:** Envía el WhatsApp para asegurar el pedido.
            """)
        
        st.markdown(f"<h3 style='text-align: center; color: #4CAF50;'>📋 Paso {st.session_state.web_step} de 4</h3>", unsafe_allow_html=True)
        st.divider()

        if 'q_web' not in st.session_state: st.session_state.q_web = {}

        if st.session_state.web_step == 1:
            st.subheader("1️⃣ Tus Datos de Entrega")
            if 'cli_web_nombre' not in st.session_state: st.session_state.cli_web_nombre = ""
            if 'cli_web_celular' not in st.session_state or not st.session_state.cli_web_celular: 
                st.session_state.cli_web_celular = "598"
            if 'cli_web_dir' not in st.session_state: st.session_state.cli_web_dir = ""
            if 'cli_web_obs' not in st.session_state: st.session_state.cli_web_obs = ""
            
            st.session_state.cli_web_nombre = st.text_input("Nombre y Apellido:", value=st.session_state.cli_web_nombre)
            st.session_state.cli_web_celular = st.text_input("Celular (Cambia el 598 por tu código de país si estás fuera. Ej Arg: 549):", value=st.session_state.cli_web_celular)
            st.session_state.cli_web_dir = st.text_input("Dirección de Envío (Calle, Nro y Esquina):", value=st.session_state.cli_web_dir)
            st.session_state.cli_web_obs = st.text_area("Observaciones (Opcional):", value=st.session_state.cli_web_obs)
            
            st.divider()
            if st.button("Siguiente: Elegir Productos ➡️", type="primary", use_container_width=True):
                if not st.session_state.cli_web_nombre or not st.session_state.cli_web_dir:
                    st.error("⚠️ Por favor completa tu Nombre y Dirección.")
                else:
                    st.session_state.web_step = 2
                    if 'web_rk' not in st.session_state: st.session_state.web_rk = 0
                    st.session_state.web_rk += 1 
                    st.rerun()

        elif st.session_state.web_step == 2:
            st.subheader("2️⃣ Listado de Productos")
            st.markdown("Puedes sumar usando las flechitas o tocando la casilla para **escribir el número**.")
            
            # ANCLA INVISIBLE ARRIBA
            st.markdown("<div id='arriba-catalogo'></div>", unsafe_allow_html=True)
            
            # BOTÓN FLOTANTE PARA IR AL FINAL AL INSTANTE
            st.markdown("""
                <a href="#fin-catalogo" class="btn-flotante-fin">
                    🛒 Ir al Carrito ⬇️
                </a>
            """, unsafe_allow_html=True)

            filtro_txt = st.text_input("🔍 Buscar fruta o verdura por nombre...", "").lower()
            st.markdown("---")
            
            for prod_full in productos_ord_web:
                if filtro_txt and filtro_txt not in prod_full.lower(): continue
                
                if prod_full not in st.session_state.q_web:
                    st.session_state.q_web[prod_full] = {'kg_un': 0, 'gr': 0.0}
                
                medida_p = medidas.get(prod_full, "kg")
                precio_orig = precios.get(prod_full, 0)
                desc_p = descuentos.get(prod_full, 0)
                p_final = precio_orig * (1 - desc_p/100)
                
                st.markdown(f"<div style='margin-top: 5px; margin-bottom: 2px;'><b style='font-size: 16px;'>{prod_full}</b> <span style='color:#2e7b32; font-size: 14px; margin-left: 5px;'>${p_final:,.1f}/{medida_p}</span></div>", unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    st.session_state.q_web[prod_full]['kg_un'] = st.number_input(
                        "Kg/Unid", min_value=0, step=1, 
                        value=int(st.session_state.q_web[prod_full]['kg_un']), 
                        key=f"w_k_{prod_full}_{st.session_state.web_rk}"
                    )
                with c2:
                    if medida_p != "un":
                        st.session_state.q_web[prod_full]['gr'] = st.number_input(
                            "Gramos", min_value=0.0, step=50.0, 
                            value=float(st.session_state.q_web[prod_full]['gr']), 
                            key=f"w_g_{prod_full}_{st.session_state.web_rk}"
                        )
                st.markdown("<hr style='margin: 8px 0 12px 0;'>", unsafe_allow_html=True)

            # ANCLA FINAL DEL CATÁLOGO
            st.markdown("<div id='fin-catalogo'></div>", unsafe_allow_html=True)
            st.divider()
            
            # BOTONES APILADOS Y BOTÓN PARA SUBIR
            if st.button("Revisar Carrito ➡️", type="primary", use_container_width=True):
                st.session_state.carrito_web = []
                for p, dict_q in st.session_state.q_web.items():
                    m = medidas.get(p, "kg")
                    c = dict_q['kg_un'] if m == "un" else dict_q['kg_un'] + (dict_q['gr'] / 1000.0)
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
                    st.warning("⚠️ Debes sumar cantidades a al menos un producto para continuar.")
                else:
                    st.session_state.web_step = 3
                    st.rerun()

            if st.button("⬅️ Atrás", use_container_width=True):
                st.session_state.web_step = 1
                st.session_state.web_rk += 1
                st.rerun()

            st.markdown("""
                <div style="text-align: center; margin-top: 15px;">
                    <a href="#arriba-catalogo" style="color: #666; font-size: 14px; text-decoration: underline;">⬆️ Volver arriba al buscador</a>
                </div>
            """, unsafe_allow_html=True)

        elif st.session_state.web_step == 3:
            st.subheader("3️⃣ Revisión de tu Pedido")
            st.markdown(f"**Cliente:** {st.session_state.cli_web_nombre.upper()}")
            st.markdown(f"**Dirección:** {st.session_state.cli_web_dir}")
            st.markdown("---")
            
            tot_web = 0.0
            idx_to_del = []
            
            # CRUZ A LA IZQUIERDA Y TEXTO A LA DERECHA
            for idx_cw, itw in enumerate(st.session_state.carrito_web):
                c1, c2 = st.columns([1, 5])
                with c1:
                    if st.button("❌", key=f"del_w3_{idx_cw}"):
                        idx_to_del.append(idx_cw)
                with c2: 
                    st.markdown(f"<div style='padding-top: 6px;'><b>{itw['producto']}</b> ({itw['cantidad_txt']}) &nbsp; <span style='color:#2e7b32'><b>${itw['subtotal']:,.1f}</b></span></div>", unsafe_allow_html=True)
                
                tot_web += itw['subtotal']
            
            if idx_to_del:
                rev_nom_web = {v: k for k, v in nombres_planos.items()}
                for d in sorted(idx_to_del, reverse=True):
                    rem_item = st.session_state.carrito_web.pop(d)
                    pf = rev_nom_web.get(rem_item['producto'], rem_item['producto'])
                    if pf in st.session_state.q_web:
                        st.session_state.q_web[pf] = {'kg_un': 0, 'gr': 0.0}
                st.rerun()
                
            st.markdown("---")
            st.markdown(f"### Total Estimado: **${tot_web:,.1f}**")
            st.warning("⚖️ El importe es estimado según el peso exacto en la balanza.")
            st.divider()
            
            if st.button("Confirmar y Enviar ➡️", type="primary", use_container_width=True):
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

            if st.button("⬅️ Volver a Productos", use_container_width=True):
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
            
            st.link_button("📲 ENVIAR AVISO AL LOCAL AHORA", f"https://wa.me/{num_feriante_limpio}?text={urllib.parse.quote(msg_feriante)}", type="primary", use_container_width=True)
            
            st.divider()
            if st.button("🔄 Hacer otro pedido", use_container_width=True):
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
    
    if st.button("🚪 Ingresar", type="primary"):
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
    if st.button("Cerrar Sesión"):
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
tabs_nombres = []
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]: 
    tabs_nombres.append("📝 Tomar Pedido")
if st.session_state.rol_logueado in ["Admin", "Cajero"]: 
    tabs_nombres.append("💰 Caja y Cobro")
    tabs_nombres.append("💳 Cuentas A Cobrar")
    tabs_nombres.append("🌐 Estado Pedidos Web")
    tabs_nombres.append("🛵 Entregas a Domicilio")
if st.session_state.rol_logueado == "Admin": 
    tabs_nombres.append("📊 Panel Admin")
    tabs_nombres.append("📈 Reportes Pro (Stock y Ventas)")
    tabs_nombres.append("📥 Reportes Pro (Saldos Pendientes)")

if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    tabs_nombres.append("📖 Guía de Uso")

tabs = st.tabs(tabs_nombres)
idx = 0

# =======================================================
# PESTAÑA 1: TOMAR PEDIDO ( CON BOTÓN FLOTANTE )
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    with tabs[idx]:
        if 'msg_vendedor' in st.session_state and st.session_state.msg_vendedor:
            st.success(st.session_state.msg_vendedor)
            st.markdown("### ¡El pedido ya está en Caja! 💸")
            st.write("Avisa al cajero para que inicie el cobro o preparación.")
            if 'link_vendedor' in st.session_state and st.session_state.link_vendedor:
                st.link_button("📲 ENVIAR WHATSAPP AL CAJERO (Obligatorio)", st.session_state.link_vendedor, type="primary", use_container_width=True)
            st.divider()
            if st.button("✅ Crear un Nuevo Pedido", use_container_width=True):
                st.session_state.msg_vendedor = ""
                st.session_state.link_vendedor = ""
                if 'q_loc' in st.session_state: del st.session_state.q_loc
                st.rerun()
        
        else:
            if st.session_state.cliente_retomado_aviso:
                st.warning(f"⚠️ **PROCESANDO AL CLIENTE:** `{st.session_state.cliente_retomado_aviso}`.")
                if st.button("❌ Quitar aviso"):
                    st.session_state.cliente_retomado_aviso = ""
                    st.rerun()

            col_m1, col_m2 = st.columns([3,1])
            with col_m1: 
                st.session_state.modo_tomar = st.radio("Acción:", ["🛍️ Venta Local", "🌐 Ajustar Pedido Web", "🔄 Retomar Pendientes"], horizontal=True, index=["🛍️ Venta Local", "🌐 Ajustar Pedido Web", "🔄 Retomar Pendientes"].index(st.session_state.modo_tomar))
            with col_m2: 
                if st.button("🔄 Sincronizar"): 
                    limpiar_cache_ventas()
                    st.rerun()
            st.divider()

            if st.session_state.modo_tomar == "🛍️ Venta Local":
                st.markdown("### 👤 Paso 1: Datos del Cliente")
                
                lista_clientes_base = sorted(list(CLIENTES_DICT.keys())) if CLIENTES_DICT else []
                opciones_cli = ["Escribir nuevo..."] + lista_clientes_base
                
                if not st.session_state.cli_celular:
                    st.session_state.cli_celular = "598"

                def callback_cliente():
                    sel = st.session_state.get(f"sel_cli_loc_{st.session_state.v_rk}", "Escribir nuevo...")
                    if sel != "Escribir nuevo...":
                        st.session_state.cli_nombre = sel
                        st.session_state.cli_celular = CLIENTES_DICT.get(sel, "598")
                    else:
                        st.session_state.cli_nombre = ""
                        st.session_state.cli_celular = "598"

                current_name = st.session_state.get("cli_nombre", "")
                index_def = 0
                if current_name in lista_clientes_base:
                    index_def = opciones_cli.index(current_name)
                    
                st.selectbox("Seleccionar Cliente Frecuente:", opciones_cli, index=index_def, key=f"sel_cli_loc_{st.session_state.v_rk}", on_change=callback_cliente)
                
                st.session_state.cli_nombre = st.text_input("Nombre y Apellido:", value=st.session_state.cli_nombre).strip().upper()
                st.session_state.cli_celular = st.text_input("Celular (Uy: 598... / Arg: 549...):", value=st.session_state.cli_celular)

                st.divider()

                st.markdown("### 🛒 Paso 2: Catálogo de Productos")
                st.markdown("Puedes sumar con las flechas o tocar la casilla para escribir el número.")
                
                # ANCLA INVISIBLE ARRIBA
                st.markdown("<div id='arriba-catalogo-local'></div>", unsafe_allow_html=True)
                
                # BOTÓN FLOTANTE PARA IR AL FINAL AL INSTANTE EN VENTA LOCAL
                st.markdown("""
                    <a href="#fin-catalogo-local" class="btn-flotante-fin">
                        🛒 Ir al Total ⬇️
                    </a>
                """, unsafe_allow_html=True)

                if 'q_loc' not in st.session_state:
                    st.session_state.q_loc = {p: {'kg_un': 0, 'gr': 0.0} for p in productos_ord_loc}
                
                filtro_txt_loc = st.text_input("🔍 Buscar fruta o verdura por nombre...", "", key=f"txt_loc_{st.session_state.v_rk}").lower()
                st.markdown("---")

                for prod_full in productos_ord_loc:
                    if filtro_txt_loc and filtro_txt_loc not in prod_full.lower(): continue
                    
                    if prod_full not in st.session_state.q_loc: 
                        st.session_state.q_loc[prod_full] = {'kg_un': 0, 'gr': 0.0}
                    
                    medida_p = MEDIDAS.get(prod_full, "kg")
                    precio_orig = PRECIOS.get(prod_full, 0)
                    desc_p = DESCUENTOS.get(prod_full, 0)
                    p_final = precio_orig * (1 - desc_p/100)
                    
                    st.markdown(f"<div style='margin-bottom: 2px;'><b style='font-size: 16px;'>{prod_full}</b> <span style='color:#2e7b32; font-size: 14px; margin-left: 5px;'>${p_final:,.1f}/{medida_p}</span></div>", unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.session_state.q_loc[prod_full]['kg_un'] = st.number_input(
                            "Kg / Unid", min_value=0, step=1, 
                            key=f"loc_k_{prod_full}_{st.session_state.v_rk}", 
                            value=int(st.session_state.q_loc[prod_full]['kg_un'])
                        )
                    with c2:
                        if medida_p != "un":
                            st.session_state.q_loc[prod_full]['gr'] = st.number_input(
                                "Gramos", min_value=0.0, step=50.0, 
                                key=f"loc_g_{prod_full}_{st.session_state.v_rk}", 
                                value=float(st.session_state.q_loc[prod_full]['gr'])
                            )
                    st.markdown("<hr style='margin: 8px 0 12px 0;'>", unsafe_allow_html=True)

                # ANCLA FINAL EN VENTA LOCAL
                st.markdown("<div id='fin-catalogo-local'></div>", unsafe_allow_html=True)

                tot_c = 0.0
                tot_ahor = 0.0
                carrito_vend = []
                
                for p, dict_q in st.session_state.q_loc.items():
                    m = MEDIDAS.get(p, "kg")
                    c = dict_q['kg_un'] if m == "un" else dict_q['kg_un'] + (dict_q['gr'] / 1000.0)
                    if c > 0:
                        pr_orig = PRECIOS.get(p, 0)
                        desc_p = DESCUENTOS.get(p, 0)
                        pr_fin = pr_orig * (1 - desc_p/100)
                        tot_c += c * pr_fin
                        tot_ahor += c * (pr_orig - pr_fin)
                        carrito_vend.append({
                            "producto": NOMBRES.get(p, p),
                            "cantidad": c, "cantidad_txt": f"{int(c)}un" if m=="un" else f"{c}kg",
                            "subtotal": c * pr_fin, "ahorro": c * (pr_orig - pr_fin), "tipo": "Propio"
                        })
                        
                st.markdown(f"### Total a Pagar: **${tot_c:,.1f}**")
                if tot_ahor > 0: st.success(f"🎉 Ahorro Total del Cliente: ${tot_ahor:,.1f}")
                st.divider()

                if st.button("🚀 Enviar a Caja", type="primary", use_container_width=True):
                    if not st.session_state.cli_nombre:
                        st.error("⚠️ Falta el nombre del cliente en el Paso 1.")
                    elif tot_c <= 0:
                        st.warning("⚠️ No has seleccionado ningún producto.")
                    else:
                        ahora = datetime.now(TZ_UY)
                        cel_f = limpiar_y_formatear_celular(st.session_state.cli_celular)
                        cli_nombre_final = st.session_state.cli_nombre.strip().upper()
                                
                        items_json = json.dumps(carrito_vend)
                        filas = []
                        for item in carrito_vend:
                            filas.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), st.session_state.usuario_logueado, cli_nombre_final, item['producto'], item['cantidad'], item['subtotal'], cel_f, "Efectivo", "En Caja", "", item.get('ahorro', 0), items_json])
                        
                        gc = conectar_google()
                        gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas").append_rows(filas)
                        limpiar_cache_ventas()
                        time.sleep(1)
                        
                        det = " | ".join([f"{r['producto']}: {r['cantidad_txt']}" for r in carrito_vend])
                        st.session_state.msg_vendedor = "✅ ¡Pedido enviado a la Caja con éxito!"
                        num_cajero = limpiar_y_formatear_celular(celular_feriante_local)
                        if not num_cajero: num_cajero = "59893343092"
                        st.session_state.link_vendedor = f"https://wa.me/{num_cajero}?text={urllib.parse.quote(f'💳 *NUEVO PEDIDO EN CAJA*\n👨‍💼 Vendedor: {st.session_state.usuario_logueado}\n👤 Cliente: {cli_nombre_final}\n💰 Total: ${tot_c:,.1f}\n📦 Detalle: {det}')}"
                        
                        st.session_state.v_rk += 1
                        st.rerun()

                st.markdown("""
                    <div style="text-align: center; margin-top: 15px;">
                        <a href="#arriba-catalogo-local" style="color: #666; font-size: 14px; text-decoration: underline;">⬆️ Volver arriba al buscador</a>
                    </div>
                """, unsafe_allow_html=True)

            elif st.session_state.modo_tomar == "🌐 Ajustar Pedido Web":
                st.write("### 📦 Armar Pedido Web (Comparativa: Pedido Original vs Peso Real)")
                try:
                    pedidos_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente"])
                    if not pedidos_web:
                        st.info("No hay pedidos web pendientes para armar.")
                    else:
                        opciones_w = ["Seleccionar..."] + [f"{p['fecha']} | {p['cliente']} (ID {p['filas'][0]})" for p in pedidos_web]
                        sel_w = st.selectbox("Seleccionar pedido web a preparar:", opciones_w)
                        if sel_w != "Seleccionar...":
                            idx_w = int(sel_w.split("(ID ")[1].replace(")", ""))
                            p_sel = next(x for x in pedidos_web if x["filas"][0] == idx_w)
                            
                            st.write(f"👤 **Cliente:** {p_sel['cliente']} | 📍 **Dir:** {p_sel['direccion']}")
                            st.markdown("---")
                            
                            tot_real = 0.0
                            tot_ahor_w = 0.0
                            nuevos_i = []
                            
                            for idx_item, it in enumerate(p_sel["items"]):
                                medida_p = MEDIDAS_PLANAS.get(it["producto"], "kg")
                                
                                st.markdown(f"**Pidió:** {it['producto']}  *(Cant aprox: {it['cantidad']})*")
                                
                                c_k, c_g = st.columns(2)
                                if medida_p == "un":
                                    with c_k:
                                        p_real = st.number_input(f"Real (un):", value=float(it['cantidad']), step=1.0, key=f"w_un_{idx_w}_{idx_item}")
                                else:
                                    k_in = int(it['cantidad'])
                                    g_in = (it['cantidad'] - k_in) * 1000
                                    with c_k: 
                                        kr = st.number_input("Kilos", value=float(k_in), step=1.0, key=f"w_k_{idx_w}_{idx_item}")
                                    with c_g: 
                                        gr = st.number_input("Gramos", value=float(g_in), step=50.0, key=f"w_g_{idx_w}_{idx_item}")
                                    p_real = kr + (gr / 1000.0)
                                
                                pr_u = PRECIOS.get(it["producto"], PRECIOS.get(NOMBRES.get(it["producto"], it["producto"]), 100))
                                desc_u = DESCUENTOS.get(it["producto"], 0)
                                sub_r = p_real * (pr_u * (1 - desc_u/100))
                                ahor_iw = p_real * (pr_u * (desc_u/100))
                                
                                tot_real += sub_r
                                tot_ahor_w += ahor_iw
                                c_txt = f"{int(p_real)}un" if medida_p == "un" else f"{p_real}kg"
                                nuevos_i.append({"producto": it["producto"], "cantidad": p_real, "cantidad_txt": c_txt, "subtotal": sub_r, "ahorro": ahor_iw, "tipo": "Propio"})
                                st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
                            
                            st.markdown(f"### Total Ajustado: **${tot_real:,.1f}**")
                            if tot_ahor_w > 0: st.success(f"Ahorro para el cliente: ${tot_ahor_w:,.1f}")
                                
                            if st.button("⚖️ Confirmar Pesos y Enviar a Caja Web", type="primary", use_container_width=True):
                                gc = conectar_google()
                                ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                col_est = chr(65 + p_sel['idx_est'])
                                ws.batch_update([{'range': f'{col_est}{f}', 'values': [["Cancelado (Ajustado)"]]} for f in p_sel["filas"]])
                                
                                ahora = datetime.now(TZ_UY)
                                filas_nuevas = []
                                json_str = json.dumps(nuevos_i)
                                for ni in nuevos_i:
                                    filas_nuevas.append([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), st.session_state.usuario_logueado, p_sel["cliente"], ni['producto'], ni['cantidad'], ni['subtotal'], p_sel["celular"], "Envío Cuenta", "Web - En Caja", p_sel["direccion"], ni['ahorro'], json_str])
                                ws.append_rows(filas_nuevas)
                                limpiar_cache_ventas()
                                time.sleep(1)
                                
                                st.session_state.msg_ajuste_web = "✅ ¡Pesos confirmados y enviado a Caja Web!"
                                msg_caj = f"💳 *CAJA (WEB Ajustado)*\nCliente: {p_sel['cliente']}\nTotal a cobrar: ${tot_real:,.1f}"
                                num_cajero = limpiar_y_formatear_celular(celular_feriante_local)
                                if not num_cajero: num_cajero = "59893343092"
                                st.session_state.link_ajuste_web = f"https://wa.me/{num_cajero}?text={urllib.parse.quote(msg_caj)}"
                                st.rerun()

                except Exception as e: 
                    st.error(f"Error: {e}")

                if st.session_state.get('msg_ajuste_web'):
                    st.success(st.session_state.msg_ajuste_web)
                    if st.session_state.get('link_ajuste_web'):
                        st.link_button("📲 Avisar al Cajero (WhatsApp)", st.session_state.link_ajuste_web, type="primary", use_container_width=True)
                    if st.button("✅ Seguir Ajustando"):
                        st.session_state.msg_ajuste_web = ""
                        st.session_state.link_ajuste_web = ""
                        st.rerun()

            elif st.session_state.modo_tomar == "🔄 Retomar Pendientes":
                st.write("### 🔄 Panel de Pedidos para Retomar")
                try:
                    mis_pendientes = [p for p in agrupar_pedidos(ventas_data_global, ["En Caja", "Web - En Caja"]) if p['vendedor'] == st.session_state.usuario_logueado]
                    if not mis_pendientes:
                        st.info("No tienes pedidos tuyos esperando en la Caja.")
                    else:
                        for p in mis_pendientes:
                            col_r1, col_r2 = st.columns([3,1])
                            tipo_origen = "🌐 WEB" if "Web" in p['estado'] else "🏪 LOCAL"
                            with col_r1: st.write(f"📦 **[{tipo_origen}] {p['cliente']}** - ${p['total']:,.1f} ({p['fecha']} - {p['hora']})")
                            with col_r2:
                                if st.button("Retomar", key=f"ret_panel_{p['filas'][0]}", type="primary", use_container_width=True):
                                    
                                    st.session_state.cli_nombre = p['cliente']
                                    st.session_state.cli_celular = p['celular']
                                    st.session_state.cliente_retomado_aviso = p['cliente']
                                    st.session_state.modo_tomar = "🛍️ Venta Local"
                                    st.session_state.v_rk += 1
                                    
                                    q_dict = {pr: {'kg_un': 0, 'gr': 0.0} for pr in productos_ord_loc}
                                    rev_nom = {v: k for k, v in NOMBRES.items()}
                                    try:
                                        items_rec = json.loads(p['json']) if p['json'] else p['items']
                                        for it in items_rec:
                                            pf = rev_nom.get(it['producto'], it['producto'])
                                            if pf in q_dict:
                                                m = MEDIDAS.get(pf, "kg")
                                                cant = float(it['cantidad'])
                                                if m == "un": q_dict[pf]['kg_un'] = int(cant)
                                                else:
                                                    q_dict[pf]['kg_un'] = int(cant)
                                                    q_dict[pf]['gr'] = (cant - int(cant)) * 1000
                                    except: pass
                                    
                                    st.session_state.q_loc = q_dict
                                    
                                    gc = conectar_google()
                                    ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                    col_est = chr(65 + p['idx_est'])
                                    ws.batch_update([{'range': f'{col_est}{f}', 'values': [["Cancelado (Retomado)"]]} for f in p['filas']])
                                    
                                    limpiar_cache_ventas()
                                    time.sleep(1)
                                    st.rerun()
                            st.markdown("---")
                except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 2: CAJA Y COBRO
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Módulo de Caja y Cobro")
        sub_caja_1, sub_caja_2 = st.tabs(["🏪 Ventas Locales en Caja", "🌐 Pedidos Web (Envío de Cuenta)"])
        
        with sub_caja_1:
            try:
                pedidos_local = agrupar_pedidos(ventas_data_global, ["En Caja"])
                if not pedidos_local:
                    st.info("No hay ventas locales en caja.")
                else:
                    sel_loc = st.selectbox("Seleccionar venta local:", ["Seleccionar..."] + [f"{p['fecha']} | {p['cliente']} (${p['total']}) (ID {p['filas'][0]})" for p in pedidos_local], key="sel_loc_box")
                    if sel_loc != "Seleccionar...":
                        id_l = int(sel_loc.split("(ID ")[1].replace(")", ""))
                        pl = next(x for x in pedidos_local if x['filas'][0] == id_l)
                        
                        st.write(f"👤 **Cliente:** {pl['cliente']} | **Total:** ${pl['total']:,.1f}")
                        st.write(f"🛍️ **Detalle:** {pl['detalle']}")
                        pago_l = st.selectbox("Forma de pago:", ["Efectivo", "Tarjeta", "MercadoPago", "A Cuenta"], key="p_loc")
                        
                        col_bl1, col_bl2 = st.columns(2)
                        with col_bl1:
                            if st.button("💵 Cerrar Cobro Local", type="primary", use_container_width=True):
                                gc = conectar_google()
                                ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                col_p = chr(65 + pl['idx_pago'])
                                col_e = chr(65 + pl['idx_est'])
                                est_f = "Fiado Pendiente" if pago_l == "A Cuenta" else "Cobrado"
                                
                                upd = []
                                for f in pl['filas']:
                                    upd.append({'range': f'{col_p}{f}', 'values': [[pago_l]]})
                                    upd.append({'range': f'{col_e}{f}', 'values': [[est_f]]})
                                ws.batch_update(upd)
                                limpiar_cache_ventas()
                                time.sleep(1)
                                
                                if pago_l == "A Cuenta":
                                    msg = f"👋 Hola {pl['cliente']}, tu compra de ${pl['total']:,.1f} en *{nombre_empresa}* quedó registrada a tu cuenta. ¡Gracias!"
                                else:
                                    msg = f"👋 Hola {pl['cliente']}, registramos tu pago de ${pl['total']:,.1f} ({pago_l}). ¡Gracias!"
                                    
                                st.success("✅ ¡Cobro registrado!")
                                st.link_button("📲 Enviar WhatsApp", f"https://wa.me/{limpiar_y_formatear_celular(pl['celular'])}?text={urllib.parse.quote(msg)}", type="primary", use_container_width=True)
                        with col_bl2:
                            if st.button("🔄 Retomar para Editar", use_container_width=True):
                                gc = conectar_google()
                                ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                col_e = chr(65 + pl['idx_est'])
                                ws.batch_update([{'range': f'{col_e}{f}', 'values': [["Cancelado (Retomado)"]]} for f in pl['filas']])
                                limpiar_cache_ventas()
                                time.sleep(1)
                                
                                st.session_state.cli_nombre = pl['cliente']
                                st.session_state.cli_celular = pl['celular']
                                st.session_state.cliente_retomado_aviso = pl['cliente']
                                st.session_state.modo_tomar = "🛍️ Venta Local"
                                st.session_state.v_rk += 1
                                
                                q_dict = {pr: {'kg_un': 0, 'gr': 0.0} for pr in productos_ord_loc}
                                rev_nom = {v: k for k, v in NOMBRES.items()}
                                try:
                                    items_rec = json.loads(pl['json']) if pl['json'] else pl['items']
                                    for it in items_rec:
                                        pf = rev_nom.get(it['producto'], it['producto'])
                                        if pf in q_dict:
                                            m = MEDIDAS.get(pf, "kg")
                                            cant = float(it['cantidad'])
                                            if m == "un": q_dict[pf]['kg_un'] = int(cant)
                                            else:
                                                q_dict[pf]['kg_un'] = int(cant)
                                                q_dict[pf]['gr'] = (cant - int(cant)) * 1000
                                except: pass
                                st.session_state.q_loc = q_dict
                                
                                st.success("✅ Pedido devuelto a 'Tomar Pedido'.")
                                st.rerun()
            except Exception as e: st.error(f"Error: {e}")

        with sub_caja_2:
            try:
                pedidos_web_caja = agrupar_pedidos(ventas_data_global, ["Web - En Caja"])
                if not pedidos_web_caja:
                    st.info("No hay pedidos web armados esperando en caja.")
                else:
                    sel_w = st.selectbox("Seleccionar pedido web armado:", ["Seleccionar..."] + [f"{p['fecha']} | {p['cliente']} (${p['total']}) (ID {p['filas'][0]})" for p in pedidos_web_caja], key="sel_web_box")
                    if sel_w != "Seleccionar...":
                        id_w = int(sel_w.split("(ID ")[1].replace(")", ""))
                        pw = next(x for x in pedidos_web_caja if x['filas'][0] == id_w)
                        
                        st.write(f"👤 **Cliente:** {pw['cliente']} | 📍 **Dir:** {pw['direccion']} | **Total Est.:** ${pw['total']:,.1f}")
                        st.write(f"📦 **Detalle:** {pw['detalle']}")
                        
                        msg_cuenta = f"👋 Hola {pw['cliente']}, tu pedido de *{nombre_empresa}* ya está listo y pesado. El total de tu cuenta es *${pw['total']:,.1f}*. ¡Vamos en camino a entregártelo! 💚"
                        st.link_button("📲 Enviar Cuenta del Pedido por WhatsApp", f"https://wa.me/{limpiar_y_formatear_celular(pw['celular'])}?text={urllib.parse.quote(msg_cuenta)}", type="primary", use_container_width=True)
            except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 3: CUENTAS A COBRAR
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 💳 Cuentas A Cobrar (Saldos Pendientes)")
        
        col_ref1, col_ref2 = st.columns([1, 3])
        with col_ref1:
            if st.button("🔄 Refrescar Cuentas"):
                limpiar_cache_ventas()
                st.rerun()
                
        try:
            ventas_data_cuentas = obtener_ventas(st.session_state.link_feria)
            todas_o = agrupar_pedidos(ventas_data_cuentas)
            fiados_activos = [o for o in todas_o if "fiado" in o['pago'].lower() or "fiado" in o['estado'].lower() or "cuenta" in o['pago'].lower() or "cuenta" in o['estado'].lower() or "abono" in o['estado'].lower() or "abono" in o['detalle'].lower() or "pendiente pago" in o['estado'].lower()]
            
            clientes_fiado = {}
            for f_ord in fiados_activos:
                cli = f_ord['cliente']
                if cli not in clientes_fiado: 
                    clientes_fiado[cli] = {"total": 0.0, "pagado": 0.0, "celular": f_ord['celular'], "pedidos": [], "tipos": set()}
                if "cancelado" not in f_ord['estado'].lower():
                    if "abono" in f_ord['estado'].lower() or "abono" in f_ord['detalle'].lower():
                        clientes_fiado[cli]["pagado"] += abs(f_ord['total'])
                    else:
                        clientes_fiado[cli]["total"] += f_ord['total']
                        if "fiado" in f_ord['estado'].lower() or "cuenta" in f_ord['estado'].lower() or "fiado" in f_ord['pago'].lower():
                            clientes_fiado[cli]["tipos"].add("Fiado/A Cuenta")
                        elif "pendiente pago" in f_ord['estado'].lower():
                            clientes_fiado[cli]["tipos"].add("Pendiente Web")
                    clientes_fiado[cli]["pedidos"].append(f_ord)
                    
            if not clientes_fiado:
                st.info("ℹ️ No hay clientes con saldos pendientes a cobrar.")
            else:
                tabla_fiados = []
                for c_name, c_info in clientes_fiado.items():
                    saldo = c_info["total"] - c_info["pagado"]
                    if saldo > 0.01: 
                        origenes = set(["Web" if "Web" in p['estado'] else "Local" for p in c_info["pedidos"] if p['total'] > 0])
                        origen_str = " + ".join(list(origenes))
                        detalle_deuda = " / ".join(list(c_info["tipos"]))
                        
                        tabla_fiados.append({
                            "Cliente": c_name,
                            "Celular": c_info["celular"],
                            "Origen": origen_str,
                            "Motivo Deuda": detalle_deuda,
                            "Total Pedido": f"${c_info['total']:,.1f}",
                            "Pagado/Abonado": f"${c_info['pagado']:,.1f}",
                            "Saldo Pendiente": f"${saldo:,.1f}"
                        })
                
                if tabla_fiados:
                    st.dataframe(pd.DataFrame(tabla_fiados), use_container_width=True)
                    st.divider()
                    st.write("#### Gestionar Cuenta de Cliente:")
                    cliente_elegido = st.selectbox("Seleccionar cliente:", ["Seleccionar..."] + [c['Cliente'] for c in tabla_fiados], key="sel_cli_cta")
                    
                    if cliente_elegido != "Seleccionar...":
                        info_c = clientes_fiado[cliente_elegido]
                        saldo_actual = info_c["total"] - info_c["pagado"]
                        st.write(f"👤 **{cliente_elegido}** | Saldo Pendiente: **${saldo_actual:,.1f}**")
                        
                        msg_rec = f"👋 Hola {cliente_elegido}, desde *{nombre_empresa}* te recordamos que tu saldo pendiente de pago es de *${saldo_actual:,.1f}*. ¡Muchas gracias!"
                        st.link_button("📲 Enviar Recordatorio de Deuda (WhatsApp)", f"https://wa.me/{limpiar_y_formatear_celular(info_c['celular'])}?text={urllib.parse.quote(msg_rec)}", use_container_width=True)
                        
                        with st.form(key=f"form_pago_{cliente_elegido}"):
                            pago_parcial = st.number_input("Monto que paga el cliente ($):", min_value=0.0, max_value=float(saldo_actual), step=100.0, key="pago_parc_input")
                            submit_pago = st.form_submit_button("💵 Registrar Pago / Saldar Cuenta", type="primary")
                            
                            if submit_pago:
                                if pago_parcial > 0:
                                    nuevo_saldo = saldo_actual - pago_parcial
                                    gc = conectar_google()
                                    ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                                    
                                    if nuevo_saldo <= 0.01:
                                        msg_wsp = f"👋 Hola {cliente_elegido}, registramos tu pago de ${pago_parcial:,.1f}. ✅ ¡Tu cuenta ha sido saldada por completo! Muchas gracias."
                                        upds = []
                                        for pd_fiado in info_c["pedidos"]:
                                            if "abono" not in pd_fiado['estado'].lower() and "abono" not in pd_fiado['detalle'].lower():
                                                col_e = chr(65 + pd_fiado['idx_est'])
                                                new_est_f = "Web - Cobrado" if "Web" in pd_fiado['estado'] else "Cobrado"
                                                for fi in pd_fiado['filas']:
                                                    upds.append({'range': f'{col_e}{fi}', 'values': [[new_est_f]]})
                                        if upds: ws.batch_update(upds)
                                    else:
                                        msg_wsp = f"👋 Hola {cliente_elegido}, registramos tu pago de ${pago_parcial:,.1f}. ⚠️ Te queda un saldo pendiente de ${nuevo_saldo:,.1f}."
                                        ahora = datetime.now(TZ_UY)
                                        ws.append_row([
                                            ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S"), 
                                            st.session_state.usuario_logueado, cliente_elegido, 
                                            "Abono a Cuenta", 1, -pago_parcial, info_c['celular'], 
                                            "Efectivo", "Cuenta Corriente", "", 0, "[]"
                                        ])
                                    
                                    limpiar_cache_ventas()
                                    time.sleep(1.5)
                                    
                                    st.session_state.msg_cobro = "✅ ¡Pago registrado con éxito!"
                                    st.session_state.link_cobro = f"https://wa.me/{limpiar_y_formatear_celular(info_c['celular'])}?text={urllib.parse.quote(msg_wsp)}"
                                    st.rerun()
                                else:
                                    st.warning("⚠️ Ingresa un monto mayor a 0 para registrar el pago.")
            
            if st.session_state.get('msg_cobro'):
                st.success(st.session_state.msg_cobro)
                st.link_button("📲 Enviar WhatsApp de Confirmación", st.session_state.link_cobro, type="primary", use_container_width=True)
                if st.button("✅ Cerrar Aviso"):
                    st.session_state.msg_cobro = ""
                    st.session_state.link_cobro = ""
                    st.rerun()

        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 4: ESTADO DE LOS PEDIDOS WEB
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 🌐 Estado de los Pedidos Web (Pendientes)")
        try:
            p_web = agrupar_pedidos(ventas_data_global, ["Web - Pendiente"])
            if not p_web: st.info("No hay pedidos web pendientes de armado.")
            else:
                for pw in p_web:
                    with st.container():
                        st.markdown(f"#### 🟡 {pw['cliente']}")
                        st.write(f"📅 **Fecha:** {pw['fecha']} {pw['hora']} | 📍 **Dirección:** {pw['direccion']}")
                        st.write(f"💰 **Total Estimado:** ${pw['total']:,.1f}")
                        
                        msg_ack = f"👋 Hola {pw['cliente']}, hemos recibido tu pedido. A la brevedad lo armaremos y te lo enviaremos. Gracias por elegirnos 💚.\n\n📦 *Tu Pedido:*\n{pw['detalle']}"
                        st.link_button("📲 Confirmar Recepción al Cliente (WhatsApp)", f"https://wa.me/{limpiar_y_formatear_celular(pw['celular'])}?text={urllib.parse.quote(msg_ack)}", type="primary", use_container_width=True)
                        st.divider()
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 5: ENTREGAS A DOMICILIO
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero"]:
    with tabs[idx]:
        st.write("### 🛵 Control de Entregas a Domicilio (Logística)")
        
        col_ent1, col_ent2 = st.columns([1, 3])
        with col_ent1:
            if st.button("🔄 Refrescar Entregas"):
                limpiar_cache_ventas()
                st.rerun()

        try:
            todas = agrupar_pedidos(ventas_data_global)
            
            ent_pendientes = [e for e in todas if "entregado" not in e['estado'].lower() and "cancelado" not in e['estado'].lower() and e["direccion"].strip() != ""]
            
            hoy_str = datetime.now(TZ_UY).strftime("%d/%m/%Y")
            ent_hoy = [e for e in todas if "entregado" in e['estado'].lower() and e["direccion"].strip() != "" and e['fecha'] == hoy_str]

            st.write("#### 🚚 Pendientes de Llevar")
            if not ent_pendientes: st.info("No hay entregas pendientes por llevar.")
            else:
                tabla_ent = []
                for ent in ent_pendientes:
                    tabla_ent.append({
                        "Cliente": ent['cliente'],
                        "Dirección": ent['direccion'],
                        "Monto": f"${ent['total']:,.1f}"
                    })
                st.dataframe(pd.DataFrame(tabla_ent), use_container_width=True)
                
                st.write("#### Acciones de Logística:")
                sel_ent = st.selectbox("Seleccionar entrega:", ["Seleccionar..."] + [f"{e['cliente']} - {e['direccion']} (ID {e['filas'][0]})" for e in ent_pendientes], key="sel_ent_box")
                if sel_ent != "Seleccionar...":
                    id_e = int(sel_ent.split("(ID ")[1].replace(")", ""))
                    ent_sel = next(x for x in ent_pendientes if x['filas'][0] == id_e)
                    
                    c_e1, c_e2 = st.columns(2)
                    with c_e1:
                        if st.button("🛵 Marcar como Entregado", type="primary", use_container_width=True):
                            gc = conectar_google()
                            ws = gc.open_by_url(st.session_state.link_feria).worksheet("Registro de Ventas")
                            col_e = chr(65 + ent_sel['idx_est'])
                            
                            nuevo_est = "Entregado"
                            if "Pendiente Pago" in ent_sel['estado']: nuevo_est = "Entregado (Pendiente Pago)"
                            elif "Cuenta" in ent_sel['estado'] or "Fiado" in ent_sel['estado']: nuevo_est = "Entregado (A Cuenta)"
                            if "Web" in ent_sel['estado']: nuevo_est = "Web - " + nuevo_est
                            
                            ws.batch_update([{'range': f'{col_e}{f}', 'values': [[nuevo_est]]} for f in ent_sel["filas"]])
                            limpiar_cache_ventas()
                            time.sleep(1)
                            st.success("✅ Marcado como Entregado en el sistema.")
                            st.rerun()
                    with c_e2:
                        cli_nombre = ent_sel['cliente']
                        link_wsp = f"https://wa.me/{limpiar_y_formatear_celular(ent_sel['celular'])}?text={urllib.parse.quote('Hola ' + cli_nombre + '. Tu pedido va en camino a tu domicilio.')}"
                        st.link_button("📲 Avisar 'Va en Camino'", link_wsp, use_container_width=True)

            st.divider()
            st.write(f"#### ✅ Resumen Entregados Hoy ({hoy_str})")
            if not ent_hoy: st.info("Aún no has registrado entregas hoy.")
            else:
                tabla_hoy = []
                for eh in ent_hoy:
                    tabla_hoy.append({
                        "Cliente": eh['cliente'],
                        "Dirección": eh['direccion'],
                        "Estado Final": eh['estado']
                    })
                st.dataframe(pd.DataFrame(tabla_hoy), use_container_width=True)

        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 6: PANEL ADMIN
# =======================================================
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📊 Panel Admin y Arqueo de Caja")
        
        with st.expander("🔒 Arqueo y Auditoría de Caja (Efectivo Inicial y Final)"):
            ef_inicial = st.number_input("Efectivo Inicial en Caja (Fondo de cambio $):", min_value=0.0, step=100.0, value=st.session_state.get('ef_inicial', 0.0))
            st.session_state.ef_inicial = ef_inicial
            efectivo_sistema = 0.0
            try:
                for row in ventas_data_global[1:]:
                    if len(row) > 9 and row[0] == datetime.now(TZ_UY).strftime("%d/%m/%Y"):
                        pago_v = str(row[8]).lower() if len(row) > 8 else ""
                        est_v = str(row[10]).lower() if len(row) > 10 else ""
                        if "efectivo" in pago_v and "cancelado" not in est_v:
                            try: efectivo_sistema += float(str(row[6]).replace("$","").replace(",","."))
                            except: pass
            except: pass
            
            esperado_en_caja = ef_inicial + efectivo_sistema
            st.write(f"💵 **Efectivo esperado en caja (Inicial + Ventas Efectivo):** ${esperado_en_caja:,.1f}")
            ef_final = st.number_input("Efectivo Final (Conteo físico en caja $):", min_value=0.0, step=100.0, key="ef_fin_input")
            if ef_final > 0:
                diferencia = ef_final - esperado_en_caja
                if diferencia == 0: st.success("✅ ¡Caja cuadrada perfectamente!")
                elif diferencia > 0: st.warning(f"⚠️ Sobrante en caja: +${diferencia:,.1f}")
                else: st.error(f"❌ Faltante en caja: ${diferencia:,.1f}")

        st.divider()
        try:
            ordenes_admin = agrupar_pedidos(ventas_data_global, None)
            tot_neto = sum(p['total'] for p in ordenes_admin if "cancelado" not in p['estado'].lower() and "caja" not in p['estado'].lower() and "pendiente" not in p['estado'].lower() and "fiado" not in p['pago'].lower() and "cuenta" not in p['pago'].lower() and "abono" not in p['estado'].lower())
            st.metric("Recaudación Neta (Cobrada)", f"${tot_neto:,.1f}")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 7: REPORTES PRO (CON MÓDULO DE STOCK ORDENADO)
# =======================================================
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📈 Reportes Pro y Analítica Financiera")
        try:
            ordenes_admin = agrupar_pedidos(ventas_data_global, None)
            pagos_resumen, vendedores_resumen, stock_resumen = {}, {}, {}
            
            for p in ordenes_admin:
                est = p['estado'].lower()
                if "cancelado" not in est and "caja" not in est and "pendiente" not in est and "abono" not in est:
                    pago_bruto = str(p['pago']).strip().title() if p['pago'] else "No especificado"
                    origen = " (Web)" if "web" in est else " (Local)"
                    concepto = pago_bruto + origen
                    pagos_resumen[concepto] = pagos_resumen.get(concepto, 0.0) + p['total']
                    vend = str(p['vendedor']).strip().title() if p['vendedor'] else "Desconocido"
                    vendedores_resumen[vend] = vendedores_resumen.get(vend, 0.0) + p['total']
                    
                if "cancelado" not in est:
                    items_to_process = p['items']
                    try:
                        js = json.loads(p['json'])
                        if js and isinstance(js, list): items_to_process = js
                    except: pass
                    
                    for item in items_to_process:
                        prod_raw = str(item.get('producto', ''))
                        prod_clean = prod_raw.replace("(Web Ajustado)", "").replace("(Propio)", "").replace("(Ajeno)", "").strip()
                        if " | " in prod_clean:
                            partes = prod_clean.split(" | ")
                            for parte in partes:
                                if ":" in parte:
                                    p_name_raw = parte.split(":")[0].strip()
                                    qty_raw = parte.split(":")[1].replace("kg/un", "").replace("kg", "").replace("un", "").replace("gr", "").strip()
                                    p_name_clean = NOMBRES.get(p_name_raw, p_name_raw)
                                    try: stock_resumen[p_name_clean] = stock_resumen.get(p_name_clean, 0.0) + float(qty_raw)
                                    except: pass
                        else:
                            if ":" in prod_clean: prod_clean = prod_clean.split(":")[0].strip()
                            p_name_clean = NOMBRES.get(prod_clean, prod_clean)
                            c_val = str(item.get('cantidad', '0')).replace("kg", "").replace("un", "").replace("gr", "").strip()
                            try: stock_resumen[p_name_clean] = stock_resumen.get(p_name_clean, 0.0) + float(c_val)
                            except: pass
            
            st.subheader("📦 Control de Stock y Alertas")
            
            tabla_stock = []
            for p_name in productos_ord_loc:
                nombre_plano = NOMBRES.get(p_name, p_name)
                vendido = stock_resumen.get(nombre_plano, 0.0)
                s_ini = STOCK_INICIAL.get(p_name, 0.0)
                s_fin = s_ini - vendido
                tabla_stock.append({
                    "Producto": p_name,
                    "Stock Inicial": s_ini,
                    "Vendido": vendido,
                    "Stock Final": s_fin
                })
            
            df_stock_ctrl = pd.DataFrame(tabla_stock)
            df_alertas = df_stock_ctrl[(df_stock_ctrl["Stock Inicial"] > 0) & (df_stock_ctrl["Stock Final"] <= 5)]
            
            if not df_alertas.empty:
                st.error("⚠️ **¡ATENCIÓN! PRODUCTOS CON STOCK BAJO (5 o menos):**")
                st.dataframe(df_alertas[["Producto", "Stock Final"]], use_container_width=True, hide_index=True)
                
            st.write("📊 **Inventario Completo:**")
            st.dataframe(df_stock_ctrl, use_container_width=True, hide_index=True)
            
            st.divider()
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.subheader("💳 Por Forma de Pago y Origen")
                if pagos_resumen: 
                    df_pagos = pd.DataFrame(list(pagos_resumen.items()), columns=["Concepto / Forma", "Total"]).sort_values("Concepto / Forma")
                    st.dataframe(df_pagos.assign(Total=lambda x: x["Total"].map(lambda v: f"${v:,.1f}")), use_container_width=True, hide_index=True)
            with col_r2:
                st.subheader("👨‍💼 Por Vendedor")
                if vendedores_resumen: 
                    df_vend = pd.DataFrame(list(vendedores_resumen.items()), columns=["Vendedor", "Total"]).sort_values("Vendedor")
                    st.dataframe(df_vend.assign(Total=lambda x: x["Total"].map(lambda v: f"${v:,.1f}")), use_container_width=True, hide_index=True)
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 8: REPORTES PRO (SALDOS PENDIENTES)
# =======================================================
if st.session_state.rol_logueado == "Admin":
    with tabs[idx]:
        st.write("### 📥 Reporte de Saldos Pendientes (Descargable)")
        col_ref1, _ = st.columns([1, 3])
        with col_ref1:
            if st.button("🔄 Refrescar Reporte"):
                limpiar_cache_ventas()
                st.rerun()

        try:
            todas_w = agrupar_pedidos(ventas_data_global)
            fiados_activos = [o for o in todas_w if ("fiado" in o['pago'].lower() or "fiado" in o['estado'].lower() or "cuenta" in o['pago'].lower() or "cuenta" in o['estado'].lower() or "abono" in o['estado'].lower() or "abono" in o['detalle'].lower() or "pendiente pago" in o['estado'].lower()) and "cancelado" not in o['estado'].lower()]
            
            resumen_saldos = {}
            for o in fiados_activos:
                cli = str(o['cliente']).strip().title()
                if cli not in resumen_saldos:
                    resumen_saldos[cli] = {"Total": 0.0, "Pagado": 0.0, "Tipos": set(), "EsWeb": False}
                amt = o['total']
                is_web = "web" in o['estado'].lower() or "web" in o['vendedor'].lower()
                is_abono = "abono" in o['estado'].lower() or "abono" in o['detalle'].lower()
                if is_web: resumen_saldos[cli]["EsWeb"] = True
                if is_abono: resumen_saldos[cli]["Pagado"] += abs(amt)
                else:
                    resumen_saldos[cli]["Total"] += amt
                    if "fiado" in o['estado'].lower() or "cuenta" in o['estado'].lower() or "fiado" in o['pago'].lower():
                        resumen_saldos[cli]["Tipos"].add("Fiado/A Cuenta")
                    if "pendiente pago" in o['estado'].lower():
                        resumen_saldos[cli]["Tipos"].add("Pendiente Web")
            
            tabla_w = []
            tabla_l = []
            for cli, d in resumen_saldos.items():
                saldo = d["Total"] - d["Pagado"]
                if saldo > 0.01:
                    row = {"Cliente": cli, "Detalle Deuda": " + ".join(list(d["Tipos"])), "Total Pedido": f"${d['Total']:,.1f}", "Pagado": f"${d['Pagado']:,.1f}", "Saldo Pendiente": f"${saldo:,.1f}"}
                    if d["EsWeb"]: tabla_w.append(row)
                    else: tabla_l.append(row)
            
            df_w = pd.DataFrame(tabla_w).sort_values("Cliente") if tabla_w else pd.DataFrame(columns=["Cliente", "Detalle Deuda", "Total Pedido", "Pagado", "Saldo Pendiente"])
            df_l = pd.DataFrame(tabla_l).sort_values("Cliente") if tabla_l else pd.DataFrame(columns=["Cliente", "Detalle Deuda", "Total Pedido", "Pagado", "Saldo Pendiente"])
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🌐 Saldos Web")
                st.dataframe(df_w, use_container_width=True, hide_index=True)
                if not df_w.empty:
                    st.download_button("📥 Descargar Saldos Web (CSV)", df_w.to_csv(index=False).encode('utf-8'), "saldos_web.csv", "text/csv")
            with c2:
                st.subheader("🏪 Saldos Locales")
                st.dataframe(df_l, use_container_width=True, hide_index=True)
                if not df_l.empty:
                    st.download_button("📥 Descargar Saldos Locales (CSV)", df_l.to_csv(index=False).encode('utf-8'), "saldos_locales.csv", "text/csv")
        except Exception as e: st.error(f"Error: {e}")
    idx += 1

# =======================================================
# PESTAÑA 9: CÓMO FUNCIONA (MANUAL DE USO)
# =======================================================
if st.session_state.rol_logueado in ["Admin", "Cajero", "Vendedor"]:
    with tabs[idx]:
        st.write("### 📖 Guía Rápida de la App")
        st.info("Esta aplicación sincroniza a todo el equipo en tiempo real. ¡Si todos cumplen su rol, el negocio vuela!")
        st.markdown("""
        **1. 🛍️ VENDEDOR (Tomar Pedido):**
        * Busca al cliente, anota las cantidades y presiona **Enviar a Caja**.
        * **Importante:** Apenas se envía, te aparecerá un botón verde para mandarle un WhatsApp al Cajero. ¡Tócalo siempre para avisar que hay un nuevo pedido esperando!
        
        **2. 🌐 PEDIDOS WEB (Clientes):**
        * Los clientes entran por tu enlace web, eligen sus verduras y envían el pedido. 
        * En **Estado Pedidos Web**, el cajero puede ver esos pedidos al instante y mandarles un WhatsApp de "Pedido Recibido" al cliente para que se queden tranquilos de que ya se está procesando.
        * En **Ajustar Pedido Web**, el vendedor toma ese pedido original, pesa la mercadería en la balanza y ajusta los gramos exactos antes de enviarlo a Caja para cobrar.
        
        **3. 💰 CAJERO (Cobrar):**
        * En **Caja y Cobro**, el cajero ve todos los pedidos listos (físicos y web).
        * Cierra el cobro en Efectivo, Tarjeta o "A Cuenta" (Fiado) y le envía el recibo al cliente por WhatsApp.
        
        **4. 🛵 REPARTIDOR / LOGÍSTICA:**
        * En **Entregas a Domicilio**, verán todos los pedidos que tienen dirección asignada.
        * Una vez que lo entregan, presionan "Marcar como Entregado".
        
        **5. 💳 SALDOS Y DEUDAS:**
        * Los pedidos "A Cuenta" aparecen aquí. El cajero puede enviar recordatorios de pago y registrar cuando el cliente viene a saldar su deuda.
        """)
