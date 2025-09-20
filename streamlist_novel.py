# app.py
import io
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Deduplicador Contactos", page_icon="🧹", layout="wide")

EXPECTED_COLUMNS = ['ENLACE LINKEDIN', 'Nombre', 'Numero', 'NUMERO DATO', 'TITULACION']


# --------------------------
# Normalización
# --------------------------
def normalize_phone(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.replace(r"\D+", "", regex=True)
    return s.replace({"": np.nan})

def normalize_text(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.replace({"nan": np.nan, "none": np.nan, "nat": np.nan})

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]
    missing = set(EXPECTED_COLUMNS) - set(out.columns)
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(missing)}")
    out = out[EXPECTED_COLUMNS]
    for col in ['ENLACE LINKEDIN', 'Nombre', 'Numero', 'NUMERO DATO', 'TITULACION']:
        out[col] = normalize_text(out[col])
    out['telefono'] = normalize_phone(out['telefono'])
    return out

# --------------------------
# Anti-join exacto (lista negra)
# --------------------------
def anti_join_all_columns(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if right is None or right.empty:
        return left.copy()
    merged = left.merge(right, on=EXPECTED_COLUMNS, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge")

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return buf.read()

# --------------------------
# UI
# --------------------------
st.title("🧹 Depurador de Contactos (solo Lista Negra)")
st.write("Elimina coincidencias **exactas en todas las columnas** contra la *Lista negra*.")

c1, c2 = st.columns(2)
with c1:
    up_reparto = st.file_uploader("📥 Reparto (.xlsx)", type=["xlsx"])
with c2:
    up_black = st.file_uploader("🗑️ Lista negra (.xlsx)", type=["xlsx"])

preview = st.checkbox("👁️ Previsualizar (primeras 10 filas)", value=True)

def read_first_sheet(uploaded):
    if not uploaded:
        return None
    try:
        return pd.read_excel(uploaded)  # primera hoja
    except Exception as e:
        st.error(f"Error leyendo el Excel: {e}")
        return None

# Previsualización
pa, pb = st.columns(2)
with pa:
    if up_reparto:
        raw = read_first_sheet(up_reparto)
        if raw is not None:
            st.caption(f"**Reparto** ({len(raw)} filas)")
            if preview: st.dataframe(raw.head(10))
with pb:
    if up_black:
        raw = read_first_sheet(up_black)
        if raw is not None:
            st.caption(f"**Lista negra** ({len(raw)} filas)")
            if preview: st.dataframe(raw.head(10))

st.markdown("---")

# Ejecutar
if st.button("🚀 Ejecutar limpieza (Lista Negra)"):
    if not up_reparto or not up_black:
        st.error("Sube los dos archivos: Reparto y Lista negra.")
        st.stop()
    try:
        # 1) Leer primera hoja
        df_rep_raw = read_first_sheet(up_reparto)
        df_blk_raw = read_first_sheet(up_black)

        # 2) Normalizar
        df_rep = normalize_df(df_rep_raw)
        df_blk = normalize_df(df_blk_raw)

        # 3) Anti-join exacto (lista negra)
        before = len(df_rep)
        df_final = anti_join_all_columns(df_rep, df_blk)
        removed_ln = before - len(df_final)

        # 4) Formato salida PN
        fecha_str = datetime.today().strftime('%d%m%Y')
        base_nombre = 'Novel_' + datetime.today().strftime('%Y-%m-%d')
        df_final["tipo_registro"] = "Novel"
        df_final["marca"]= "EAE"
        df_final["subcanal"] ="Empresas"
        df_final_PN = pd.DataFrame({
            'ID Integrador': df_final['NUMERO DATO'],	
            'Fecha Captación': '',
            'Nombre de pila': df_final['nombre'],
            'Primer Apellido':'',
            'Correo electrónico':'',	
            'Teléfono móvil': df_final['Numero'],
            'Origen Del Dato':'',
            'Guia/Webinar/Curso Descargado':'',
            'Ciudad':'',
            'Tipo De Registro':df_final['tipo_registro'],
            'Subtipo De Registro':'',
            'Marca': df_final['marca'],
            'Sub canal': df_final['subcanal'],
            'Código Postal':'',
            'Link Linkedin': df_final['ENLACE LINKEDIN'],
            'Nivel De Estudios': df_final['TITULACION'],
            'Base De Datos': base_nombre,
            'Zona comercial':''
        })        

        # 5) Métricas y resultados
        st.metric("Filas iniciales", before)
        st.metric("Eliminadas por Lista Negra", removed_ln)
        st.metric("Filas finales", len(df_final_PN))

        st.subheader("✅ Resultado final (formato PN)")
        st.dataframe(df_final_PN.head(50))

        # 6) Descarga (formato PN mostrado)
        st.download_button(
            "⬇️ Descargar resultado final (PN)",
            data=to_excel_bytes(df_final_PN),
            file_name="contactos_reparto_final_PN.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except ValueError as ve:
        st.error(f"Validación de columnas: {ve}")
    except Exception as e:
        st.exception(e)
