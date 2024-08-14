import numpy as np
import folium
import streamlit as st
from streamlit_folium import folium_static
import pandas as pd
from datetime import datetime, timedelta
import utils
import pytz

# Set up the Streamlit app
st.set_page_config(layout="wide")

# Sidebar
st.sidebar.title("Heat Risk and Health Index Dashboard")
st.sidebar.header("Controls")

# Toggle for map size
map_size_option = st.sidebar.radio("Map Size", ("Regular", "Full Page"))

# Encourage the user to collapse the sidebar for full-page view
if map_size_option == "Full Page":
    st.sidebar.info("For a better view, you can hide the sidebar by clicking the arrow at the top-left corner.")

# Day selection
tz = pytz.timezone('America/New_York')
today = datetime.now(tz)

date_options = [(today + timedelta(days=i)).strftime("%m/%d/%Y") for i in range(7)]
day_options = [f"Day {i+1} - {date_options[i]}" for i in range(7)]

selected_day_label = st.sidebar.selectbox("Select Heat Risk Day", day_options)
selected_day = selected_day_label.split(' - ')[0]

# Load the heat risk data
@st.cache_data(ttl=86400) # Cache for 24 hours (86400 seconds)
def cached_load_data(selected_day):
    try:
        data = utils.load_data(selected_day)
        if data is None or data.empty:
            st.error("Data could not be loaded. Please check the data source or network connection.")
            return None
        return data
    except Exception as e:
        st.error(f"An error occurred while loading the data: {e}")
        return None

layer1_with_weighted_values = cached_load_data(selected_day)

# Check if data is loaded successfully
if layer1_with_weighted_values is None:
    st.error("Failed to load data. Please try again later.")
else:
    # Load geographic data using the utility function
    states, counties, selected_state, selected_county, zipcode_boundary = utils.load_geographic_data()

# Generate the column mappings dynamically based on consistent formatting
hhi_column_mapping = utils.generate_column_mapping(layer1_with_weighted_values.columns)

# Get the list of available columns for HHI indicators
hhi_columns = list(hhi_column_mapping.keys())
hhi_columns = utils.move_column_to_front(hhi_columns, "weighted_OVERALL_SCORE")

# Create a list of display names
display_names = [hhi_column_mapping[col] for col in hhi_columns]

# Use the display names in the selectbox
selected_display_name = st.sidebar.selectbox(
    "Select CDC Heat and Health Index Indicator", 
    display_names,
    index=0
)

# Map the selected display name back to the actual column name
selected_hhi_indicator = hhi_columns[display_names.index(selected_display_name)]

# Load the HHI description data
hhi_desc_df = utils.load_hhi_description()

# Get the description for the selected HHI indicator
description_text = utils.get_hhi_indicator_description(hhi_desc_df, selected_hhi_indicator)

# Display the description in the expander
with st.sidebar.expander('Learn more about this HHI Indicator'):
    # make sure description text is on a new line
    st.markdown(f"""
        **{selected_hhi_indicator}**:

        {description_text}
        """)

# Filtering options
heat_threshold = st.sidebar.multiselect("Select Heat Risk Levels", [0, 1, 2, 3, 4], default=[2, 3, 4])

# Expander for learning more about heat risk levels
with st.sidebar.expander('Learn more about heat risk levels'):
    st.markdown(utils.get_heat_risk_levels_description())

heat_health_index_threshold = st.sidebar.slider("Heat Health Index Percentile Threshold", 0, 100, 80)

# Initialize filtered_data as an empty DataFrame
filtered_data = pd.DataFrame()

st.sidebar.write("Please click the button below to download the filtered data as a CSV file.")
st.sidebar.download_button(label="Download", data=filtered_data.to_csv(), mime='text/csv')

# Data source information
st.sidebar.markdown("""
**Data Sources:**
- [NWS Heat Risk](https://www.wpc.ncep.noaa.gov/heatrisk/)
- [CDC Heat and Health Index](https://ephtracking.cdc.gov/Applications/heatTracker/)
""")


# Main dashboard
m = utils.create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county, states, counties, zipcode_boundary)

# Adjust map size based on sidebar toggle
map_width, map_height = (1350, 900) if map_size_option == "Full Page" else (1000, 800)
folium_static(m, width=map_width, height=map_height)

st.markdown(f'''
<div style="position: relative; width: 400px; height: 150px; padding: 10px;">
    <b>Legend</b> <br>
    <span style="display: inline-block; width: 20px; height: 20px; background-color: red; margin-right: 10px;"></span> Highlighted Areas (Heat Risk {heat_threshold} & HHI {heat_health_index_threshold}th percentile)<br>
    <span style="display: inline-block; width: 20px; height: 20px; background-color: blue; margin-right: 10px;"></span> Other Areas
</div>
''', unsafe_allow_html=True)

if selected_state != "Select a State" or selected_county != "Select a County":
    if selected_county != "Select a County" and selected_state != "Select a State":
        selected_county_geom = counties[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county)].geometry.values
        if selected_county_geom.size > 0:
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_county_geom[0])]
            title_suffix = f" - {selected_state}, {selected_county}"
        else:
            st.warning("Could not find the geometry for the selected county.")
            filtered_data = pd.DataFrame()
    elif selected_state != "Select a State":
        selected_state_geom = states[states['NAME'] == selected_state].geometry.values
        if selected_state_geom.size > 0:
            filtered_data = layer1_with_weighted_values[layer1_with_weighted_values.intersects(selected_state_geom[0])]
            title_suffix = f" - {selected_state}"
        else:
            st.warning("Could not find the geometry for the selected state.")
            filtered_data = pd.DataFrame()
    else:
        filtered_data = layer1_with_weighted_values
        title_suffix = ""
    
    if not filtered_data.empty:
        st.subheader(f"Key Summary {title_suffix}")
        st.markdown("**Sociodemographic**")
        st.markdown(f"Affected population: {filtered_data['weighted_POP'].sum()}")

        with st.expander("See detailed plot for affected population"):
            # Prepare the data for the stacked bar chart
            population_by_risk_level = filtered_data.groupby('raster_value')['weighted_POP'].sum().reset_index()
            population_by_risk_level['raster_value'] = population_by_risk_level['raster_value'].astype(str)

            # Create the chart using the helper function
            fig_population = utils.create_plot(population_by_risk_level, 
                                         y_column='raster_value', 
                                         x_column='weighted_POP', 
                                         color_column='raster_value',
                                         title="Population Affected by Heat Risk Level",
                                         y_label='Heat Risk Level', 
                                         x_label='Affected Population')
            st.plotly_chart(fig_population)

        st.markdown(f"Percentage of persons aged 65 and older estimate: {filtered_data['weighted_P_AGE65'].mean():.2f}%")

        with st.expander("See detailed plot for affected population aged 65 and older"):
            age65_by_risk_level = filtered_data.groupby('raster_value')['weighted_P_AGE65'].mean().reset_index()
            age65_by_risk_level['raster_value'] = age65_by_risk_level['raster_value'].astype(str)

            fig_age65 = utils.create_plot(age65_by_risk_level,
                                    y_column='raster_value',
                                    x_column='weighted_P_AGE65',
                                    color_column='raster_value',
                                    title="Percentage of Persons Aged 65 and Older by Heat Risk Level",
                                    y_label='Heat Risk Level',
                                    x_label='Percentage of Persons Aged 65 and Older')
            st.plotly_chart(fig_age65)
    else:
        st.warning('No data available for the selected state or county.')
else:
    st.subheader('Select a State or County to get key summaries')

# Add the disclaimer to the footer
st.markdown("""
    <style>
    .footer {
        position: fixed;
        right: 0;
        bottom: 0;
        width: 30%;
        background-color: #f1f1f1;
        color: black;
        text-align: center;
        padding: 10px;
    }
    </style>
    <div class="footer">
        This is an experimental prototype provided for informational purposes only by the 
        <a href="https://urbantech.cornell.edu/" target="_blank">Jacobs Urban Tech Hub</a> 
        as part of the 
        <a href="https://agingandadaptation.cornell.edu/" target="_blank">Cornell Initiative on Aging and Adaptation to Extreme Heat</a>.
        Questions? Comments? Contact us at 
        <a href="mailto:urbantech@cornell.edu">urbantech@cornell.edu</a>.
    </div>
""", unsafe_allow_html=True)
