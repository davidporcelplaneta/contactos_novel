# app.py
import io
import re
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

# ------------------------------------------------------
# Configuración de página
# ------------------------------------------------------
st.set_page_config(page_title="Deduplicador Contactos", page_icon="🧹", layout="wide")

# ------------------------------------------------------
# Utilidades de normalización
# ------------------------------------------------------
def normalize_text(s: pd.Series) -> pd.Series:
    """Minúsculas, trim, colapsa espacios y trata vacíos comunes."""
    s = s.astype(str).str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.replace({"": np.nan, "nan": np.nan, "none": np.nan, "nat": np.nan})

def normalize_link(s: pd.Series) -> pd.Series:
    """Normaliza URLs (quita http/https, www, barra final, minúsculas)."""
    s = s.astype(str).str.strip().str.lower()
    s = s.str.replace(r"^https?://(www\.)?", "", regex=True)
    s = s.str.replace(r"/+$", "", regex=True)
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.replace({"": np.nan, "nan": np.nan, "none": np.nan, "nat": np.nan})

# ------------------------------------------------------
# Estandarización de columnas para el matching
# ------------------------------------------------------
def standardize_for_matching(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Crea columnas estandarizadas para emparejar:
      - empresa_std
      - nombre_std
      - puesto_std
      - enlace_std

    source:
      - 'blacklist': columnas de entrada esperadas: 'empresa', 'nombre', 'puesto', 'enlace'
      - 'reparto'  : columnas de entrada esperadas: 'empresa' (EMPRESA), 'nombre' (Nombre),
                     'puesto' (PUESTO), 'enlace linkedin' (ENLACE LINKEDIN)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["empresa_std","nombre_std","puesto_std","enlace_std"])

    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]

    if source == "blacklist":
        col_empresa = "empresa"
        col_nombre  = "nombre"
        col_puesto  = "puesto"
        col_enlace  = "enlace"
    elif source == "reparto":
        col_empresa = "empresa"              # en Excel: EMPRESA
        col_nombre  = "nombre"               # en Excel: Nombre
        col_puesto  = "puesto"               # en Excel: PUESTO
        col_enlace  = "enlace linkedin"      # en Excel: ENLACE LINKEDIN
    else:
        raise ValueError("source debe ser 'blacklist' o 'reparto'.")

    out["empresa_std"] = normalize_text(out[col_empresa])  if col_empresa in out.columns else np.nan
    out["nombre_std"]  = normalize_text(out[col_nombre])   if col_nombre  in out.columns else np.nan
    out["puesto_std"]  = normalize_text(out[col_puesto])   if col_puesto  in out.columns else np.nan
    out["enlace_std"]  = normalize_link(out[col_enlace])   if col_enlace  in out.columns else np.nan

    return out

# ------------------------------------------------------
# Lógica de deduplicación: OR en 4 campos (empresa, nombre, puesto, enlace)
# ------------------------------------------------------
def remove_blacklisted_any_field(df_reparto: pd.DataFrame, df_black: pd.DataFrame) -> pd.DataFrame:
    """
    Elimina de df_reparto las filas que coinciden con df_black en
    cualquiera de: empresa, nombre, puesto, enlace (normalizados).
    """
    if df_black is None or df_black.empty:
        return df_reparto.copy()

    rep = standardize_for_matching(df_reparto, source="reparto")
    blk = standardize_for_matching(df_black,  source="blacklist")

    # Sets de la lista negra (ignorando NaN)
    set_empresa = set(blk["empresa_std"].dropna().unique()) if "empresa_std" in blk.columns else set()
    set_nombre  = set(blk["nombre_std"].dropna().unique())  if "nombre_std"  in blk.columns else set()
    set_puesto  = set(blk["puesto_std"].dropna().unique())  if "puesto_std"  in blk.columns else set()
    set_enlace  = set(blk["enlace_std"].dropna().unique())  if "enlace_std"  in blk.columns else set()

    # Máscara de baneados por OR
    ban_mask = pd.Series(False, index=rep.index)
    if "empresa_std" in rep.columns and set_empresa:
        ban_mask |= rep["empresa_std"].isin(set_empresa)
    if "nombre_std" in rep.columns and set_nombre:
        ban_mask |= rep["nombre_std"].isin(set_nombre)
    if "puesto_std" in rep.columns and set_puesto:
        ban_mask |= rep["puesto_std"].isin(set_puesto)
    if "enlace_std" in rep.columns and set_enlace:
        ban_mask |= rep["enlace_std"].isin(set_enlace)

    # Devuelve los no baneados, quitando columnas *_std auxiliares
    cols_drop = [c for c in ["empresa_std","nombre_std","puesto_std","enlace_std"] if c in rep.columns]
    return rep.loc[~ban_mask].drop(columns=cols_drop, errors="ignore").copy()

# ------------------------------------------------------
# Excel utils
# ------------------------------------------------------
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return buf.read()

def read_first_sheet(uploaded):
    if not uploaded:
        return None
    try:
        return pd.read_excel(uploaded)  # primera hoja
    except Exception as e:
        st.error(f"Error leyendo el Excel: {e}")
        return None

# ------------------------------------------------------
# UI
# ------------------------------------------------------
st.title("🧹 Depurador de Contactos (Lista Negra por 4 campos)")
st.write("""
Elimina del **Reparto** las filas que coincidan con la **Lista negra** por **cualquiera** de estos campos:
- **empresa** (lista negra) ↔ **EMPRESA** (reparto)  
- **nombre** (lista negra) ↔ **Nombre** (reparto)  
- **puesto** (lista negra) ↔ **PUESTO** (reparto)  
- **enlace** (lista negra) ↔ **ENLACE LINKEDIN** (reparto)
""")

c1, c2 = st.columns(2)
with c1:
    up_reparto = st.file_uploader("📥 Reparto (.xlsx)", type=["xlsx"])
with c2:
    up_black = st.file_uploader("🗑️ Lista negra (.xlsx)", type=["xlsx"])

preview = st.checkbox("👁️ Previsualizar (primeras 10 filas)", value=True)

# Previsualización
pa, pb = st.columns(2)
with pa:
    if up_reparto:
        raw = read_first_sheet(up_reparto)
        if raw is not None:
            st.caption(f"**Reparto** ({len(raw)} filas)")
            if preview: 
                st.dataframe(raw.head(10))
with pb:
    if up_black:
        raw = read_first_sheet(up_black)
        if raw is not None:
            st.caption(f"**Lista negra** ({len(raw)} filas)")
            if preview: 
                st.dataframe(raw.head(10))

st.markdown("---")

# ------------------------------------------------------
# Ejecutar
# ------------------------------------------------------
if st.button("🚀 Ejecutar limpieza (Lista Negra)"):
    if not up_reparto or not up_black:
        st.error("Sube los dos archivos: Reparto y Lista negra.")
        st.stop()
    try:
        # 1) Leer primera hoja
        df_rep_raw = read_first_sheet(up_reparto)
        df_blk_raw = read_first_sheet(up_black)

        before = len(df_rep_raw) if df_rep_raw is not None else 0

        # 2) Deduplicación OR en (empresa, nombre, puesto, enlace)
        df_final = remove_blacklisted_any_field(df_rep_raw, df_blk_raw)
        removed_ln = before - len(df_final)

        # 3) Formato salida PN
        fecha_str = datetime.today().strftime('%d%m%Y')
        base_nombre = 'Novel_' + datetime.today().strftime('%Y-%m-%d')

        # Asegura minúsculas para acceso robusto
        if df_final is not None and not df_final.empty:
            df_final.columns = [c.strip().lower() for c in df_final.columns]

        df_final["tipo_registro"] = "Novel"
        df_final["marca"] = "EAE"
        df_final["subcanal"] = "Empresas"

        # Construcción robusta (usa .get por si faltan columnas)
        df_final_PN = pd.DataFrame({
            'ID Integrador': df_final.get('numero dato', ''),
            'Fecha Captación': '',
            'Nombre de pila': df_final.get('nombre', ''),
            'Primer Apellido': '',
            'Correo electrónico': '',
            'Teléfono móvil': df_final.get('numero', ''),
            'Origen Del Dato': '',
            'Guia/Webinar/Curso Descargado': '',
            'Ciudad': '',
            'Tipo De Registro': df_final['tipo_registro'],
            'Subtipo De Registro': '',
            'Marca': df_final['marca'],
            'Sub canal': df_final['subcanal'],
            'Código Postal': '',
            'Link Linkedin': df_final.get('enlace linkedin', ''),
            'Nivel De Estudios': df_final.get('titulacion', ''),
            'Base De Datos': base_nombre,
            'Zona comercial': ''
        })

        # 4) Métricas y resultados
        st.metric("Filas iniciales", before)
        st.metric("Eliminadas por Lista Negra", removed_ln)
        st.metric("Filas finales", len(df_final_PN))

        st.subheader("✅ Resultado final (formato PN)")
        st.dataframe(df_final_PN.head(50))

        # 5) Descarga (formato PN mostrado)
        st.download_button(
            "⬇️ Descargar resultado final (PN)",
            data=to_excel_bytes(df_final_PN),
            file_name="contactos_reparto_final_PN.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.exception(e)
