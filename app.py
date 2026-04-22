import streamlit as st
import clickhouse_connect
import pandas as pd
import time
import altair as alt

st.set_page_config(page_title="ClickHouse Benchmark", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; color: #00d4ff !important; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; color: #888888 !important; }
    div[data-testid="stMetric"] {
        background-color: #1a1c24;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #333;
    }
    /* Stil pentru butoanele din sidebar */
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #262730;
        color: white;
        border: 1px solid #444;
    }
    .stButton>button:hover {
        border-color: #00d4ff;
        color: #00d4ff;
    }
    </style>
    """, unsafe_allow_html=True)

# CONECTARE LA CLICKHOUSE
client = clickhouse_connect.get_client(host='localhost', port=8123, username='****', password='***********', database='default')

# SCENARII 
queries = {
    "1. Scanare Totală": """
        SELECT oras, avg(pret) as medie_pret 
        FROM warehouse_table 
        GROUP BY oras  """,
    "2. Filtrare Array": """
        SELECT oras, avg(pret) as medie_pret, 
        count(distinct(JSONExtractString(metadate_json, 'session_id'))) as sesiuni_unice
        FROM warehouse_table 
        WHERE has(etichete, 'tag_25') 
        GROUP BY oras""",
    "3. Serii de Timp": """
        SELECT toDate(data_eveniment) as Data, count(*) as Numar_Comenzi
        FROM warehouse_table 
        WHERE toYYYYMM(data_eveniment) = toYYYYMM(now())
        GROUP BY Data 
        ORDER BY Data""",
    "4. Activitate Utilizatori (Cardinalitate Mare)": """
        SELECT JSONExtractString(metadate_json, 'ip') as IP, count() as Actiuni,
        count(distinct JSONExtractString(metadate_json, 'session_id')) as Sesiuni
        FROM warehouse_table 
        GROUP BY IP ORDER BY Actiuni
        DESC LIMIT 10"""
}

def run_benchmark(query, label):
    test_id = f"test_{int(time.time())}"
    
    with st.spinner(f"Executând {label}..."):
        start_time = time.time()
        result = client.query(f"/* {test_id} */ " + query)
        end_time = time.time()
        client.command("SYSTEM FLUSH LOGS")
        time.sleep(1.2)
    
    adv_stats = client.query_df(f"""
        SELECT query_duration_ms, read_rows, 
               formatReadableSize(read_bytes) as read_data,
               formatReadableSize(memory_usage) as ram,
               ProfileEvents['ContextSwitches'] as context_switches,
               ProfileEvents['DiskReadElapsedMicroseconds'] / 1000 as disk_io_wait_ms,
               length(thread_ids) as used_threads
        FROM system.query_log 
        WHERE query LIKE '%{test_id}%' AND type = 'QueryFinish' AND event_date >= today()
        ORDER BY event_time DESC LIMIT 1
    """)
    
    if not adv_stats.empty:
        st.subheader(f"📊 Rezultate: {label}")
        
        # Metricile principale
        c1, c2, c3, c4 = st.columns(4)
        timp_total = end_time - start_time
        read_rows = int(adv_stats['read_rows'].iloc[0])
        
        c1.metric("Timp Execuție", f"{timp_total:.3f} s")
        c2.metric("Rânduri Scanate", f"{read_rows:,}")
        c3.metric("Date Citite", adv_stats['read_data'].iloc[0])
        viteza = (read_rows / timp_total / 1000000) if timp_total > 0 else 0
        c4.metric("Viteză", f"{viteza:.2f} Milioane de  randuri /s")

        # Hardware Info
        m1, m2, m3 = st.columns(3)
        m1.info(f"🔄 Context Switches: {int(adv_stats['context_switches'].iloc[0]):,}")
        m2.info(f"💾 Disk Wait: {adv_stats['disk_io_wait_ms'].iloc[0]:.2f} ms")
        m3.info(f"🧠 RAM: {adv_stats['ram'].iloc[0]}")

        # Vizualizare specifică
        if label == "3. Serii de Timp":
            df_chart = pd.DataFrame(result.result_rows, columns=result.column_names)
            chart = alt.Chart(df_chart).mark_line(point=True, color='#00d4ff').encode(
                x='Data:T', y='Numar_Comenzi:Q', tooltip=['Data', 'Numar_Comenzi']
            ).properties(height=350).interactive()
            st.altair_chart(chart, use_container_width=True)
        elif label == "4. Activitate Utilizatori (Cardinalitate Mare)":
            df_users = pd.DataFrame(result.result_rows, columns=result.column_names)
            st.bar_chart(df_users.set_index('IP')['Actiuni'])
            st.dataframe(df_users, use_container_width=True)
        else:
            st.dataframe(pd.DataFrame(result.result_rows, columns=result.column_names), use_container_width=True)
    else:
        st.error("Eroare la recuperarea metricilor. Reîncearcă.")

#  SIDEBAR PENTRU BUTOANE
with st.sidebar:
    st.title("⚙️ Control Panel")
    st.write("Selectează un test de benchmark:")
    
    btn_full = st.button("1. Scanare Totală")
    btn_array = st.button("2. Filtrare Array")
    btn_time = st.button("3. Serii de Timp")
    btn_ip = st.button("4. Activitate Utilizatori (Cardinalitate Mare)")
    
    st.divider()
    st.info("Set date: 10 Milioane rânduri")

# ZONA PRINCIPALĂ 
st.title("📊 ClickHouse: Monitorizare Resurse")

if btn_full:
    run_benchmark(queries["1. Scanare Totală"], "1. Scanare Totală")
elif btn_array:
    run_benchmark(queries["2. Filtrare Array"], "2. Filtrare Array")
elif btn_time:
    run_benchmark(queries["3. Serii de Timp"], "3. Serii de Timp")
elif btn_ip:
    run_benchmark(queries["4. Activitate Utilizatori (Cardinalitate Mare)"], "4. Activitate Utilizatori (Cardinalitate Mare)")
else:
    st.write("### Instrucțiuni")
    st.info("Folosește meniul din stânga pentru a lansa interogările  asupra serverului ClickHouse.")
