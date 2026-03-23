import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURAZIONE ---
BASE_URL_SCRUTINI = "https://eleapi.interno.gov.it/siel/PX/scrutiniFI/DE/20260322/TE/09/SK/01"
URL_VOTANTI = "https://eleapi.interno.gov.it/siel/PX/votantiFI/DE/20260322/TE/09/SK/01"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://elezioni.interno.gov.it/",
    "Origin": "https://elezioni.interno.gov.it"
}
REGION_IDS = [str(i).zfill(2) for i in range(1, 21)]

st.set_page_config(page_title="Referendum 2026 Live", layout="wide")

@st.cache_data
def load_geojson():
    url = "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_IT_regions.geojson"
    try:
        return requests.get(url).json()
    except Exception as e:
        st.error("Impossibile caricare i confini della mappa.")
        return None

def fetch_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def get_all_data():
    # 1. Recupero Dati Nazionali (Scrutini e Votanti)
    nazionale_scrutini = fetch_json(BASE_URL_SCRUTINI)
    dati_votanti = fetch_json(URL_VOTANTI)
    
    # 2. Recupero Scrutini Regionali in parallelo
    with ThreadPoolExecutor(max_workers=10) as executor:
        urls = [f"{BASE_URL_SCRUTINI}/RE/{rid}" for rid in REGION_IDS]
        regioni_scrutini = list(executor.map(fetch_json, urls))
        
    return nazionale_scrutini, [r for r in regioni_scrutini if r], dati_votanti

# --- INTERFACCIA ---
geojson_italia = load_geojson()
st.title("🗳️ Live Dashboard: Referendum Costituzionale 2026")
container = st.empty()

while True:
    with container.container():
        naz, reg_list, votanti = get_all_data()
        
        if naz and votanti:
            res_n = naz['scheda'][0]
            
            # Parsing Dati Votanti Nazionali (Prende l'ultimo elemento dell'array com_vot)
            dati_naz_votanti = votanti['enti']['ente_p']
            ultimo_agg_votanti = dati_naz_votanti['com_vot'][-1]
            tot_votanti = ultimo_agg_votanti['vot_t']
            perc_affluenza = ultimo_agg_votanti['perc']
            tot_elettori = dati_naz_votanti['ele_t']

            # Calcolo percentuale di sezioni scrutinate
            progresso_sezioni = (res_n['sz_perv'] / naz['int']['sz_tot']) * 100 if naz['int']['sz_tot'] > 0 else 0

            # KPI Nazionali Riorganizzati
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Progresso Scrutinio", f"{progresso_sezioni:.2f}%", f"{res_n['sz_perv']:,} su {naz['int']['sz_tot']:,} sezioni", delta_color="off")
            c2.metric("SÌ", f"{res_n['perc_si']}%", f"{res_n['voti_si']:,} voti", delta_color="off")
            c3.metric("NO", f"{res_n['perc_no']}%", f"{res_n['voti_no']:,} voti", delta_color="off")
            c4.metric("Affluenza", f"{perc_affluenza}%", f"{tot_votanti:,} votanti", delta_color="off")

        if reg_list and votanti:
            # Creazione dizionario veloce per incrociare i votanti per ID regione
            mappa_votanti_reg = {}
            for reg_v in votanti['enti']['enti_f']:
                cod_reg = int(reg_v['cod'])
                ultimo_agg = reg_v['com_vot'][-1]
                mappa_votanti_reg[cod_reg] = {
                    "votanti": ultimo_agg['vot_t'],
                    "affluenza_perc": ultimo_agg['perc']
                }

            # Costruzione Tabella Unificata
            rows = []
            for r in reg_list:
                s = r['scheda'][0]
                cod_reg = int(r['int']['cod_reg'])
                elettori_reg = r['int']['ele_t']
                
                # Recupera i dati di affluenza per la regione corrente
                voti_reg = mappa_votanti_reg.get(cod_reg, {"votanti": 0, "affluenza_perc": "0"})
                
                voti_si = s['voti_si']
                voti_no = s['voti_no']
                
                # Calcolo del peso reale sull'intero corpo elettorale
                peso_si = (voti_si / elettori_reg * 100) if elettori_reg > 0 else 0
                peso_no = (voti_no / elettori_reg * 100) if elettori_reg > 0 else 0
                
                rows.append({
                    "ID": cod_reg,
                    "Regione": r['int']['desc_reg'],
                    "NO (%)": float(s['perc_no'].replace(',', '.')),
                    "SÌ (%)": float(s['perc_si'].replace(',', '.')),
                    "Peso NO su Elettori (%)": round(peso_no, 2),
                    "Peso SÌ su Elettori (%)": round(peso_si, 2),
                    "Voti NO": voti_no,
                    "Voti SÌ": voti_si,
                    "Sezioni": f"{s['sz_perv']}/{r['int']['sz_tot']}",
                    "Votanti": voti_reg['votanti'],
                    "Affluenza (%)": float(str(voti_reg['affluenza_perc']).replace(',', '.')) if voti_reg['affluenza_perc'] else 0.0
                })
            
            df = pd.DataFrame(rows)

            # Mappa Italia (Focalizzata sul NO)
            st.subheader("Mappa Distribuzione Voti (NO)")
            if geojson_italia:
                fig = px.choropleth(df, 
                                    geojson=geojson_italia,
                                    locations="ID", 
                                    featureidkey="properties.reg_istat_code_num", 
                                    color="NO (%)",
                                    hover_name="Regione",
                                    hover_data={
                                        "NO (%)": True,
                                        "SÌ (%)": True,
                                        "Affluenza (%)": True, # Aggiunta l'affluenza nel tooltip della mappa
                                        "ID": False
                                    },
                                    color_continuous_scale="Reds")
                
                fig.update_geos(fitbounds="locations", visible=False) 
                st.plotly_chart(fig, width='stretch')

            # Tabella Riepilogativa (Ordinata per NO discendente)
            st.subheader("Dettaglio Regionale")
            st.dataframe(df.sort_values("NO (%)", ascending=False), width='stretch', hide_index=True)

        st.caption(f"Ultimo aggiornamento: {time.strftime('%H:%M:%S')}")
        time.sleep(120)
        st.rerun()
