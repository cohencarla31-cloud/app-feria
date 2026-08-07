import streamlit as st
import pandas as pd
from datetime import date, datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
import json

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(page_title="Punto de Venta Feria", layout="centered")

LINK_CSV_BALANCE = "https://docs.google.com/spreadsheets/d/1ThaFo2wH9r-jbly0rwqfv3921uVRch3W7U_nXe-PLEU/edit?gid=832040050#gid=832040050" 
LINK_NORMAL_DEL_EXCEL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQM5gsQcK0_77hP18d98tevZ2IaCmEahb8k3J-2Ey7ma5xb5L-YLc-NHQCUKxo8WJBY9Aw8Px5RV3kY/pub?gid=832040050&single=true&output=csv"

@st.cache_data(ttl=30)
def cargar_inventario():
    try:
        # Quitamos el sep=None para que lea estándar, pero esquivando las filas rotas
        df = pd.read_csv(LINK_CSV_BALANCE, encoding='utf-8', on_bad_lines='skip')
        df.columns = df.columns.str.strip()
        
        # 1. Buscador inteligente de la columna Producto
        col_prod = next((c for c in df.columns if "roducto" in c.lower()), None)
        
        if not col_prod:
            # Si no la encuentra, nos avisa qué columnas está viendo realmente
            raise ValueError(f"No encuentro la columna 'Producto'. Lo que veo en el Excel es: {list(df.columns)}")
            
        if 'Emoji' in df.columns:
            df['Prod_Full'] = df['Emoji'].astype(str) + " " + df[col_prod].astype(str)
        else:
            df['Prod_Full'] = df[col_prod].astype(str)
            
        nombres_planos = dict(zip(df['Prod_Full'], df[col_prod].astype(str).str.strip()))
            
        # 2. Buscador inteligente de Precios
        col_precio = next((c for c in df.columns if "recio" in c.lower()), None)
        if col_precio:
            df['Precio_Num'] = df[col_precio].astype(str).str.replace('$', '', regex=False).str.replace(',', '.', regex=False)
            precios = dict(zip(df['Prod_Full'], pd.to_numeric(df['Precio_Num'], errors='coerce').fillna(0)))
        else:
            precios = {p: 0 for p in df['Prod_Full']}
        
        # 3. Buscador inteligente de Stock
        col_stock = next((c for c in df.columns if "tock" in c.lower()), None)
        stock = dict(zip(df['Prod_Full'], pd.to_numeric(df[col_stock], errors='coerce').fillna(99999))) if col_stock else {}
        
        # 4. Buscador inteligente de Descuentos
        col_desc = next((c for c in df.columns if "escuento" in c.lower()), None)
        descuentos = dict(zip(df['Prod_Full'], pd.to_numeric(df[col_desc], errors='coerce').fillna(0))) if col_desc else {p: 0 for p in df['Prod_Full']}
            
        # 5. Buscador inteligente de Categorías
        col_cat = next((c for c in df.columns if "ategor" in c.lower()), None)
        if col_cat:
            cats = df[col_cat].astype(str).str.strip().replace(['nan', 'None', ''], 'General')
            categorias = dict(zip(df['Prod_Full'], cats))
        else:
            categorias = {p: "General" for p in df['Prod_Full']}
            
        return df['Prod_Full'].tolist(), precios, stock, descuentos, nombres_planos, categorias
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return [], {}, {}, {}, {}, {}

PRODUCTOS, PRECIOS, STOCK, DESCUENTOS, NOMBRES_PLANOS, CATEGORIAS = cargar_inventario()

productos_por_cat = {}
for p in PRODUCTOS:
    cat = CATEGORIAS.get(p, "General")
    if cat not in productos_por_cat:
        productos_por_cat[cat] = []
    productos_por_cat[cat].append(p)

# ==========================================
# 2. INTERFAZ Y DATOS
# ==========================================
st.title("🛒 Toma de Pedidos")

col_datos1, col_datos2 = st.columns(2)
with col_datos1:
    vendedor = st.selectbox("Vendedor:", ["Seleccionar...", "Juan", "Pedro", "María", "Carlos"])
    cliente = st.text_input("Nombre del Cliente:")
with col_datos2:
    caja = st.selectbox("¿A qué Caja se envía?", ["Caja 1", "Caja 2"])
    tel_cliente = st.text_input("Celular del Cliente (Ej: 598...):")

st.divider()

# ==========================================
# 3. BUSCADOR Y CATEGORÍAS
# ==========================================
pedidos = {}
total_general = 0.0
total_ahorro = 0.0

st.write("### 🔍 Catálogo de Productos")
nombres_cats = sorted(list(productos_por_cat.keys()))
productos_seleccionados = []

nombres_tabs = ["🔍 Todo el Catálogo"] + nombres_cats
tabs = st.tabs(nombres_tabs)

with tabs[0]:
    sel_todo = st.multiselect(
        "Escribe aquí para buscar en cualquier rubro:", 
        options=PRODUCTOS, 
        key="ms_todo",
        placeholder="Ej: Orégano, Papa, Queso..."
    )
    productos_seleccionados.extend(sel_todo)

for i, cat in enumerate(nombres_cats):
    with tabs[i+1]:
        sel = st.multiselect(f"Seleccionar dentro de {cat}:", options=productos_por_cat[cat], key=f"ms_{cat}")
        productos_seleccionados.extend(sel)

productos_seleccionados = list(dict.fromkeys(productos_seleccionados))

if productos_seleccionados:
    st.write("### 📝 Detalle del Pedido")

# ==========================================
# 4. INGRESO RÁPIDO DE KILOS/GRAMOS O UNIDADES
# ==========================================
for p in productos_seleccionados:
    desc_pct = DESCUENTOS.get(p, 0)
    label_producto = f"🔥 {p} ({int(desc_pct)}% OFF)" if desc_pct > 0 else f"{p}"
    
    st.write(f"**{label_producto}**")
    
    # Lógica inteligente para saber si es por peso o por unidad
    if "unidad" in p.lower() or "(u)" in p.lower():
        cant = st.number_input("Unidades:", min_value=0, step=1, key=f"uni_{p}")
        if cant > 0:
            st.caption(f"📦 *Entendí:* **{int(cant)} unidad(es)**")
    else:
        # Partimos la pantalla en dos columnas para Kilos y Gramos
        col_kilos, col_gramos = st.columns(2)
        with col_kilos:
            kilos = st.number_input("Kilos:", min_value=0, step=1, key=f"kilos_{p}")
        with col_gramos:
            # Los gramos suman de a 50 (es muy útil en la balanza)
            gramos = st.number_input("Gramos:", min_value=0, max_value=999, step=50, key=f"gramos_{p}")
            
        # Unimos las dos cajas en un solo número matemático
        cant = kilos + (gramos / 1000.0)
        
        if cant > 0:
            if kilos > 0 and gramos > 0:
                st.caption(f"⚖️ *Entendí:* **{int(kilos)} Kilo(s) y {int(gramos)} gramos**")
            elif kilos > 0 and gramos == 0:
                st.caption(f"⚖️ *Entendí:* **{int(kilos)} Kilo(s) exactos**")
            elif kilos == 0 and gramos > 0:
                st.caption(f"⚖️ *Entendí:* **{int(gramos)} gramos**")
    
    # Calcular precios solo si ingresó alguna cantidad
    if cant > 0:
        precio_orig = PRECIOS.get(p, 0)
        precio_final = precio_orig * (1 - (desc_pct / 100))
        
        sub_final = cant * precio_final
        ahorro = (cant * precio_orig) - sub_final
        
        pedidos[p] = {"cant": cant, "sub_final": sub_final, "desc_pct": desc_pct}
        total_general += sub_final
        total_ahorro += ahorro

st.divider()

st.write(f"### TOTAL A COBRAR: ${total_general:,.1f}")
if total_ahorro > 0:
    st.caption(f"*(El cliente ahorró ${total_ahorro:,.1f} en descuentos)*")

st.divider()

# ==========================================
# 5. BOTONES DE ACCIÓN Y REGISTRO
# ==========================================
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🧹 Limpiar Pedido"):
        st.session_state.clear()
        st.rerun()

with col_btn2:
    if st.button("📝 Enviar Venta"):
        if vendedor == "Seleccionar..." or not cliente or total_general == 0:
            st.warning("⚠️ Falta completar Vendedor, Cliente o ingresar cantidades.")
        else:
            try:
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(json.loads(st.secrets["llave_google"]), scopes=scopes)
                gc = gspread.authorize(creds)
                sheet = gc.open_by_url(LINK_NORMAL_DEL_EXCEL).worksheet("Registro de Ventas")
                
                for p, d in pedidos.items():
                    nombre_limpio = NOMBRES_PLANOS.get(p, p)
                    sheet.append_row([str(date.today()), datetime.now().strftime("%H:%M:%S"), vendedor, cliente, nombre_limpio, d['cant'], d['sub_final']])
                
                st.success("✅ Venta registrada correctamente en el Excel.")
                
                msg_caja = f"🛒 NUEVO PEDIDO\n👤 Vendedor: {vendedor}\n🗣️ Cliente: {cliente}\n-------------------\n"
                for p, d in pedidos.items():
                    if d['desc_pct'] > 0:
                        msg_caja += f" • {d['cant']} x {p} = ${d['sub_final']:,.1f} (Aplica {int(d['desc_pct'])}% OFF)\n"
                    else:
                        msg_caja += f" • {d['cant']} x {p} = ${d['sub_final']:,.1f}\n"
                
                msg_caja += f"-------------------\n💰 TOTAL A COBRAR: ${total_general:,.1f}"
                
                num_caja = "59893343092" if caja == "Caja 1" else "59899111222"
                url_caja = f"https://wa.me/{num_caja}?text={urllib.parse.quote(msg_caja)}"
                
                msg_cliente = f"👋 Hola {cliente}, aquí tienes el detalle de tu compra:\n-------------------\n"
                for p, d in pedidos.items():
                    if d['desc_pct'] > 0:
                        msg_cliente += f" • {d['cant']} x {p} = ${d['sub_final']:,.1f} (🔥 {int(d['desc_pct'])}% OFF)\n"
                    else:
                        msg_cliente += f" • {d['cant']} x {p} = ${d['sub_final']:,.1f}\n"
                
                msg_cliente += f"-------------------\n💰 TOTAL: ${total_general:,.1f}\n"
                if total_ahorro > 0:
                    msg_cliente += f"🎁 Hoy ahorraste ${total_ahorro:,.1f}\n"
                msg_cliente += f"\n¡Muchas gracias por elegirnos! 🍎"
                
                num_cliente = tel_cliente.replace(" ", "").replace("+", "")
                url_cliente = f"https://wa.me/{num_cliente}?text={urllib.parse.quote(msg_cliente)}"
                
                st.info("👇 Haz clic en los botones para enviar los mensajes:")
                st.link_button(f"📲 Enviar Resumen a {caja}", url_caja)
                
                if tel_cliente:
                    st.link_button("📲 Enviar Ticket al Cliente", url_cliente)
                else:
                    st.caption("*(No se ingresó celular del cliente)*")
                
            except Exception as e:
                st.error(f"❌ Error al registrar: {e}")
