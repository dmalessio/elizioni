import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURAZIONE ---
BASE_URL = "https://eleapi.interno.gov.it/siel/PX/scrutiniFI/DE/20260322/TE/09/SK/01"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://elezioni.interno.gov.it/",
    "Origin": "https://elezioni.interno.gov.it"
}
# Lista ID regioni ISTAT/Eligendo
REGION_IDS = [str(i).zfill(2) for i in range(1, 21)]

st.set_page_config(page_title="Referendum 2026 Live", layout="wide")

def fetch_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def get_all_data():
    # 1. Recupero Totale Nazionale
    nazionale = fetch_json(BASE_URL)
    
    # 2. Recupero Regioni in parallelo (per velocità)
    with ThreadPoolExecutor(max_workers=10) as executor:
        urls = [f"{BASE_URL}/RE/{rid}" for rid in REGION_IDS]
        results = list(executor.map(fetch_json, urls))
    
    return nazionale, [r for r in results if r]

@st.cache_data
def load_geojson():
    url = "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_IT_regions.geojson"
    try:
        return requests.get(url).json()
    except Exception as e:
        st.error("Impossibile caricare i confini della mappa.")
        return None

geojson_italia = load_geojson()    

# --- INTERFACCIA ---
st.title("🗳️ Live Dashboard: Referendum Costituzionale 2026")
container = st.empty()

while True:
    with container.container():
        naz, reg_list = get_all_data()
        
        if naz:
            res_n = naz['scheda'][0]
            # KPI Nazionali
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Scrutinio Nazionale", f"{res_n['perc_si']}% SÌ", f"{res_n['sz_perv']:,} sezioni")
            c2.metric("Voti SÌ", f"{res_n['voti_si']:,}")
            c3.metric("Voti NO", f"{res_n['voti_no']:,}")
            c4.metric("Elettori Totali", f"{naz['int']['ele_t']:,}")

        if reg_list:
            # Creazione Tabella
            rows = []
            for r in reg_list:
                s = r['scheda'][0]
                rows.append({
                    "ID": int(r['int']['cod_reg']),  # <-- AGGIUNTA FONDAMENTALE (Codice ISTAT)
                    "Regione": r['int']['desc_reg'],
                    "SÌ (%)": float(s['perc_si'].replace(',', '.')),
                    "NO (%)": float(s['perc_no'].replace(',', '.')),
                    "Voti SÌ": s['voti_si'],
                    "Voti NO": s['voti_no'],
                    "Sezioni": f"{s['sz_perv']}/{r['int']['sz_tot']}"
                })
            
            df = pd.DataFrame(rows)

            # Mappa Italia
            st.subheader("Mappa Distribuzione Voti (SÌ)")
            # Nota: richiede geojson regioni italiane per visualizzazione corretta
            fig = px.choropleth(df, 
                                geojson=geojson_italia,
                                locations="ID", 
                                featureidkey="properties.reg_istat_code_num", 
                                color="SÌ (%)",
                                hover_name="Regione",
                                hover_data={
                                    "NO (%)": True,   # Mostra la percentuale del NO
                                    "ID": False,      # Nasconde il codice ISTAT
                                    "SÌ (%)": True    # (Opzionale) conferma la visualizzazione del SÌ
                                },
                                color_continuous_scale="RdYlGn")
            
            fig.update_geos(fitbounds="locations", visible=False) 
            st.plotly_chart(fig, use_container_width=True)

            # Tabella Riepilogativa
            st.subheader("Dettaglio Regionale")
            st.dataframe(df.sort_values("SÌ (%)", ascending=False), use_container_width=True, hide_index=True)

        st.caption(f"Ultimo aggiornamento: {time.strftime('%H:%M:%S')}")
        time.sleep(120) # 2 minuti
        st.rerun()