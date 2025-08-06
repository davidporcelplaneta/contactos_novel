import streamlit as st
import pandas as pd
from datetime import datetime
import io

st.set_page_config(page_title="NOVEL - Premium Numbers", layout="wide")
st.title("📥 NOVEL - Carga y limpieza de contactos")

# --- SUBIDA DE ARCHIVOS ---
st.header("1. Subida de archivos")
novel_file = st.file_uploader("Sube el archivo novel_pn.csv", type="csv")
listanegra_file = st.file_uploader("Sube el archivo listanegra.xlsx", type="xlsx")
ventas_file = st.file_uploader("Sube el archivo bbdd_ventas.xlsx", type="xlsx")

if novel_file and listanegra_file and ventas_file:
    # Detectar separador
    sample = novel_file.read(1000).decode("utf-8", errors="replace")
    sep = ";" if ";" in sample else ("\t" if "\t" in sample else ",")
    novel_file.seek(0)
    df = pd.read_csv(novel_file, sep=sep, engine="python", on_bad_lines="skip")
    df_lista_negra = pd.read_excel(listanegra_file)
    df_ventas = pd.read_excel(ventas_file)

    # Normalizar campos
    df['profile_url_lower'] = df['ENLACE LINKEDIN'].astype(str).str.strip().str.lower()
    df['current_company_lower'] = df['EMPRESA'].astype(str).str.strip().str.lower()
    df['current_company_position_lower'] = df['PUESTO'].astype(str).str.strip().str.lower()

    df_lista_negra['enlace'] = df_lista_negra['enlace'].astype(str).str.strip().str.lower()
    df_lista_negra['empresa'] = df_lista_negra['empresa'].astype(str).str.strip().str.lower()
    df_lista_negra['puesto'] = df_lista_negra['puesto'].astype(str).str.strip().str.lower()

    # Deduplicación con lista negra
    con_nombre = df[df['Nombre'].isin(df_lista_negra['nombre'])]
    sin_nombre = df[~df['Nombre'].isin(df_lista_negra['nombre'])]
    con_nombre = con_nombre[~con_nombre['profile_url_lower'].isin(df_lista_negra['enlace'])]
    con_nombre = con_nombre[~con_nombre['current_company_lower'].isin(df_lista_negra['empresa'])]
    con_nombre = con_nombre[~con_nombre['current_company_position_lower'].isin(df_lista_negra['puesto'])]
    df_neto_v1 = pd.concat([con_nombre, sin_nombre], ignore_index=True)

    # Eliminar columnas auxiliares
    df_neto_v2 = df_neto_v1.drop(columns=['profile_url_lower', 'current_company_lower', 'current_company_position_lower'], errors='ignore')

    # Eliminar si ya está en ventas
    df_neto_v2 = df_neto_v2[~df_neto_v2['NUMERO DATO'].isin(df_ventas['Nº-AZ'])]

    # Campos requeridos
    df_neto_v2['Grupo'] = 'Inercia'
    df_neto_v2 = df_neto_v2.rename(columns={'General': 'General (SI/NO/MOD)'})
    df_neto_v2['General (SI/NO/MOD)'] = 'MOD'
    df_neto_v2['GESTION LISTADO PROPIO'] = 'CITAS'
    df_neto_v2['ORIGEN DATO'] = 'NOVEL'
    df_neto_v2['Base de Datos'] = 'NOVEL_' + datetime.today().strftime('%Y-%m-%d')
    df_neto_v2['Agente'] = 'IP: 136 Listado Novel'
    df_neto_v2['CITA'] = 'SI'
    df_neto_v2['BUSQUEDA FECHA'] = datetime.today().strftime('%Y-%m-%d')
    df_neto_v2['FECHA DE CITA'] = datetime.today().strftime('%Y-%m-%d')

    for col in ['Números2', 'Números3']:
        if col in df_neto_v2.columns:
            df_neto_v2[col] = df_neto_v2[col].apply(lambda x: str(int(x)) if isinstance(x, float) and x.is_integer() else (str(x) if pd.notnull(x) else ''))

    columnas_a_borrar = [
        "Agente", "Grupo", "Observaciones", "Fax", "Correo",
        "GESTION LISTADO PROPIO", "TELEOPERADOR", "NUMERO DATO", "FECHA DE CONTACTO",
        "FECHA DE CONTACTO (NO USAR)", "CUALIFICA", "RESULTADO", "",
        "FECHA DE CITA (NO USAR)", "ASESOR", "RESULTADO ASESOR", "OBSERVACIONES ASESOR"
    ]
    for col in columnas_a_borrar:
        if col != "" and col in df_neto_v2.columns:
            df_neto_v2[col] = ""

    # Exportación final
    st.header("2. Descarga del resultado")
    csv = df_neto_v2.to_csv(index=False, sep=';', encoding='utf-8-sig')
    st.download_button("📤 Descargar archivo final NOVEL", csv, file_name="NOVEL Cargar Contactos PN.csv", mime="text/csv")

    st.success(f"✅ Contactos procesados: {len(df_neto_v2)}")
else:
    st.warning("⚠️ Sube los tres archivos para continuar.")