import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px

from pathlib import Path
import sys

# Aktuelles Verzeichnis = 3_Streamlit
current_dir = Path(__file__).resolve().parent
# Übergeordnetes Verzeichnis (Projekt-Root)
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))#

from helpers import (
    get_data_dir, list_cities,
    load_and_clean_listings, load_and_clean_neighbourhoods, get_geojson_center,
    compute_overview, compute_room_type_stats, de_format
)
data_dir = get_data_dir()
cities = list_cities(data_dir)

st.set_page_config(page_title="Städtevergleich", layout="wide")
st.sidebar.title("Städteauswahl")

placeholder = "Bitte wählen …"
selected_city_1 = st.sidebar.selectbox("Erste Stadt:", options=[placeholder]+cities, index=0, key="city_1")
use_second_city = st.sidebar.checkbox("Zweite Stadt auswählen", value=False)

selected_city_2 = None
if use_second_city:
    cities_2 = [c for c in cities if c != selected_city_1]
    previous = st.session_state.get("city_2", placeholder)
    index = 0 if previous not in cities_2 else cities_2.index(previous)+1
    selected_city_2 = st.sidebar.selectbox("Zweite Stadt:", options=[placeholder]+cities_2, index=index, key="city_2")

def load_city_data(city):
    if city == placeholder:
        return None, None, None
    folder = data_dir / city
    listings = load_and_clean_listings(folder / "listings.csv")
    geo_df, geo_json = load_and_clean_neighbourhoods(folder)
    return listings, geo_df, geo_json

city1_listings, city1_geo_df, city1_geojson = load_city_data(selected_city_1)
city2_listings, city2_geo_df, city2_geojson = load_city_data(selected_city_2) if selected_city_2 else (None, None, None)

tab_preise, tab_karte = st.tabs(["Preise", "Karte"])
# =======================
# TAB: PREISE
# =======================
with tab_preise:
    st.header("Preise")

    col1, col2 = st.columns(2)

    def display_city_stats(listings, city_name):
        room_order = ["Entire home/apt", "Hotel room", "Private room", "Shared room"]

        overview = compute_overview(listings)
        room_stats = compute_room_type_stats(listings)

        st.subheader(city_name)
        if listings is not None:
            st.write(f"Bereinigter Datensatz: {listings.shape[0]} Unterkünfte, {listings.shape[1]} Kategorien")
        else:
            st.write("Keine Daten geladen.")
        st.write("Überblick Preise/Nacht:")

        if listings is not None and listings.empty:
            st.warning(f"Für {city_name} sind keine Preisdaten vorhanden.")

        # Überblick-Preise
        o = overview.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Niedrigster Wert", de_format(o['min_price']))
        c2.metric("Höchster Wert", de_format(o['max_price']))
        c3.metric("Durchschnitt", de_format(o['avg_price']))
        # ==========================================
        # a) Beschreibende Statistik
        # ==========================================
        st.markdown("### a) Beschreibende Statistik – je Room Type")
        desc = listings.groupby("room_type")["price"].describe().reset_index()
        st.dataframe(
            desc.style.format({
                'count': lambda x: f"{int(x):,}".replace(",", "."),
                'mean': lambda x: de_format(x),
                'std': lambda x: de_format(x),
                'min': lambda x: de_format(x),
                '25%': lambda x: de_format(x),
                '50%': lambda x: de_format(x),
                '75%': lambda x: de_format(x),
                'max': lambda x: de_format(x)
            })
        )
        # ==========================================
        # b) Boxplot
        # ==========================================
        st.markdown("### b) Boxplot – Preisverteilung nach Room Type")
        fig_box = px.box(
            listings,
            x='room_type',
            y='price',
            color='room_type',
            category_orders={"room_type": room_order},
            title="Boxplot – Preisverteilung nach Room Type",
            labels={'room_type': 'Zimmertyp', 'price': 'Preis (€)'}
        )
        st.plotly_chart(fig_box, use_container_width=True)

        # ===============================
        # c) Häufigkeitsverteilung – Preise nach Room Type (Plotly)
        # ===============================
        st.write("### c) Häufigkeitsverteilung – Preise nach Room Type (Plotly)")
        fig = px.histogram(
            listings,
            x="price",
            color="room_type",
            nbins=50,
            barmode="stack",
            category_orders={"room_type": room_order},
            title="Häufigkeitsverteilung der Preise nach Room Type",
            labels={"price": "Preis", "count": "Anzahl Unterkünfte"}
        )
        fig.update_layout(
            xaxis_title="Preis",
            yaxis_title="Anzahl Unterkünfte",
            template="simple_white",
            bargap=0.05,
            legend_title="Room Type",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

        return overview, room_stats

    with col1:
        if city1_listings is not None:
            display_city_stats(city1_listings, selected_city_1)
    with col2:
        if city2_listings is not None:
            display_city_stats(city2_listings, selected_city_2)
# =======================
# TAB: KARTE
# =======================
with tab_karte:
    st.header("Karte")

    def prepare_avg_tooltip(listings):
        return {
            nb: f"<b>{nb}</b><br>"
                f"⌀ Preis: €{de_format(group['price'].mean())}<br>"
                f"⌀ Mindestnächte: {group['minimum_nights'].mean():.1f}<br>"
                f"Höchster Ausreißer: €{de_format(group['price'].max())}"
            for nb, group in listings.groupby("neighbourhood")
        }

    def display_map(geojson, listings, city_name, color, geo_df):
        center = get_geojson_center(geojson)
        m = folium.Map(location=center, zoom_start=9)

        if listings is not None:
            tooltips = prepare_avg_tooltip(listings)
            for feature in geojson["features"]:
                nb = feature["properties"]["neighbourhood"]
                folium.GeoJson(
                    feature,
                    tooltip=folium.Tooltip(tooltips.get(nb, nb), sticky=True, direction='top'),
                    style_function=lambda x, c=color: {"color": c, "weight": 0.4, "fillOpacity": 0.1}
                ).add_to(m)
        else:
            folium.GeoJson(geojson).add_to(m)

        st.subheader(city_name)
        if geo_df is not None:
            st.write(f"**GeoJSON als DataFrame:** {geo_df.shape[0]} Zeilen, {geo_df.shape[1]} Spalten")
        else:
            st.write("GeoJSON nicht geladen.")

        st_folium(m, width=700, height=400)

        if listings is not None:
            st.write(f"**⌀ Preis {city_name}:** {de_format(listings['price'].mean())}")
            st.write(f"**⌀ Mindestnächte {city_name}:** {listings['minimum_nights'].mean():.1f} Nächte")
            st.write(f"**Höchster Ausreißer {city_name}:** {de_format(listings['price'].max())}")

    col1, col2 = st.columns(2)
    with col1:
        if city1_geojson:
            display_map(city1_geojson, city1_listings, selected_city_1, "blue", city1_geo_df)
        else:
            st.write("Keine GeoJSON-Daten für die erste Stadt verfügbar.")
    with col2:
        if city2_geojson:
            display_map(city2_geojson, city2_listings, selected_city_2, "red", city2_geo_df)
        elif selected_city_2:
            st.write("Keine GeoJSON-Daten für die zweite Stadt verfügbar.")