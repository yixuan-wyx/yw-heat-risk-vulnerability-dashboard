import os
import requests
import geopandas as gpd
from datetime import datetime
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import folium
from io import BytesIO
import pytz

# def load_data(selected_day, data_dir, today):
#     """
#     Load NWS Heat Risk x CDC Heat and Health Index data for the selected day.

#     Args:
#         selected_day (str): The selected day (e.g., 'Day 1')
#         data_dir (str): Directory to store the data files
#         today (datetime): The current date

#     Returns:
#         GeoDataFrame: The loaded dataset or None if there was an error
#     """
#     os.makedirs(data_dir, exist_ok=True)
#     formatted_day = selected_day.replace(' ', '+')
#     current_date = today.strftime("%Y%m%d")
#     local_file = os.path.join(data_dir, f'heat_risk_analysis_{selected_day}.geoparquet')

#     # Check if the file exists and if it was created today
#     if os.path.exists(local_file):
#         file_mod_time = datetime.fromtimestamp(os.path.getmtime(local_file))
#         if file_mod_time.date() == today.date():
#             print(f"{local_file} is up to date.")
#             return gpd.read_parquet(local_file)

#     # Download the file if it's outdated or doesn't exist
#     url = f'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{formatted_day}_{current_date}.geoparquet'
#     try:
#         print(f"Downloading {url}...")
#         response = requests.get(url)
#         response.raise_for_status()
#         with open(local_file, 'wb') as file:
#             file.write(response.content)
#         print(f"Saved to {local_file}")
#     except requests.exceptions.RequestException as e:
#         print(f"Failed to download data: {e}")
#         return None

#     # Load and return the GeoDataFrame
#     return gpd.read_parquet(local_file)

@st.cache_data(ttl=86400)  # Cache the data for 24 hours
def load_data(selected_day):
    """
    Load NWS Heat Risk x CDC Heat and Health Index data for the selected day directly into memory.

    Args:
        selected_day (str): The selected day (e.g., 'Day 1').

    Returns:
        GeoDataFrame: The loaded dataset or None if there was an error.
    """
    # Set the timezone to your desired timezone (e.g., 'America/New_York')
    tz = pytz.timezone('America/New_York')
    formatted_day = selected_day.replace(' ', '+')
    current_date = datetime.now(tz).strftime("%Y%m%d")
    url = f'https://heat-risk-dashboard.s3.amazonaws.com/heat_risk_analysis_{formatted_day}_{current_date}.geoparquet'

    try:
        print(f"Downloading {url}...")
        response = requests.get(url)
        response.raise_for_status()

        # Load the data directly from the response content into a GeoDataFrame
        data = BytesIO(response.content)
        gdf = gpd.read_parquet(data)
        return gdf

    except requests.exceptions.RequestException as e:
        st.error(f'{current_date},{url}')
        st.error(f"Failed {current_date} to download data: {e}")
        return None
    
    except Exception as e:
        st.error(f"An error occurred while loading the data: {e}")
        return None

st.cache_data
def load_state_county_zip_data():
    """
    Load state, county, and ZIP Code boundary data from pre-downloaded Parquet files.
    county boundary url: "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip"
    state boundary url: "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_state_500k.zip"
    zipcodes url: "https://www2.census.gov/geo/tiger/TIGER2020/ZCTA5/tl_2020_us_zcta510.zip"

    Returns:
        tuple: A tuple containing three GeoDataFrames: states, counties, and zipcodes.
    """
    states_file = "streamlit-app/data/us_states_reduced.parquet"
    counties_file = "streamlit-app/data/us_counties_reduced.parquet"
    zipcodes_file = "streamlit-app/data/us_zipcodes_reduced.parquet"

    # Load the GeoDataFrames
    states = gpd.read_parquet(states_file)
    counties = gpd.read_parquet(counties_file)
    zipcodes = gpd.read_parquet(zipcodes_file)

    # Ensure the GeoDataFrames are in a geographic CRS (WGS84)
    if not states.crs.is_geographic:
        states = states.to_crs(epsg=4326, inplace=True)
    if not counties.crs.is_geographic:
        counties = counties.to_crs(epsg=4326, inplace=True)
    if not zipcodes.crs.is_geographic:
        zipcodes = zipcodes.to_crs(epsg=4326, inplace=True)

    return states, counties, zipcodes

def get_zipcode_boundary(zip_code, zipcodes_gdf):
    """
    Get the boundary for a given ZIP Code.

    Args:
        zip_code (str): The ZIP Code to search for.
        zipcodes_gdf (GeoDataFrame): The GeoDataFrame containing ZIP Code boundaries.

    Returns:
        GeoDataFrame or None: The boundary of the ZIP Code as a GeoDataFrame, or None if not found.
    """
    column_name = 'ZCTA5CE10'
    zipcode_boundary = zipcodes_gdf[zipcodes_gdf[column_name] == str(zip_code)]
    if zipcode_boundary.empty:
        return None
    return zipcode_boundary

def load_geographic_data():
    """
    Load geographic data and handle user inputs for selecting state, county, and ZIP Code.

    Returns:
        tuple: A tuple containing GeoDataFrames for states and counties, selected state, selected county,
               and ZIP Code boundary GeoDataFrame.
    """
    states, counties, zipcodes = load_state_county_zip_data()

    # State selection
    state_names = ["Select a State"] + sorted(states['NAME'].tolist())
    selected_state = st.sidebar.selectbox("Select State", state_names)

    # Filter counties based on selected state
    filtered_counties = counties[counties['STATE_NAME'] == selected_state] if selected_state != "Select a State" else counties
    county_names = ["Select a County"] + sorted(filtered_counties['NAME'].tolist())
    selected_county = st.sidebar.selectbox("Select County", county_names)

    # ZIP Code input
    zip_code = st.sidebar.text_input("Enter ZIP Code to Zoom In", placeholder="e.g., 10044")
    zipcode_boundary = get_zipcode_boundary(zip_code, zipcodes)

    return states, counties, selected_state, selected_county, zipcode_boundary

def generate_column_mapping(columns, prefix='weighted_', replacement='weighted ', title_case=True):
    """
    Generate a mapping for column names with consistent formatting.
    
    Args:
    columns (list): List of column names.
    prefix (str): The prefix to replace (default is 'weighted_').
    replacement (str): The string to replace the prefix with (default is 'weighted ').
    title_case (bool): If True, convert column names to title case (default is True).
    
    Returns:
    dict: A dictionary with original column names as keys and formatted names as values.
    """
    if title_case:
        return {col: col.replace(prefix, replacement).replace('_', ' ').title() for col in columns if col.startswith(prefix)}
    else:
        return {col: col.replace(prefix, replacement).replace('_', ' ') for col in columns if col.startswith(prefix)}

def move_column_to_front(columns, column_name):
    """
    Ensure a specific column is at the front of the list.
    
    Args:
    columns (list): List of column names.
    column_name (str): The name of the column to move to the front.
    
    Returns:
    list: The modified list of column names.
    """
    if column_name in columns:
        columns.remove(column_name)
        columns.insert(0, column_name)
    return columns

@st.cache_data
def load_hhi_description(file_path='streamlit-app/data/HHI_Data_Dictionary_2024.csv'):
    """
    Load the HHI data dictionary from a CSV file.
    
    Args:
    file_path (str): Path to the CSV file.
    
    Returns:
    pd.DataFrame: DataFrame containing the HHI descriptions.
    """
    return pd.read_csv(file_path)

def get_hhi_indicator_description(hhi_desc_df, indicator_name):
    """
    Fetch the description for a given HHI indicator.
    """
    try:
        return hhi_desc_df.loc[hhi_desc_df['weighted_2024_VARIABLE_NAME'] == indicator_name, '2024_DESCRIPTION'].values[0]
    except IndexError:
        return "No description available for this indicator."

def get_heat_risk_levels_description():
    """
    Return the description of heat risk levels.
    
    Returns:
    str: A formatted string containing the descriptions of heat risk levels.
    """
    return """
    **Heat Risk Levels:**
    
    - **0:** Little to no risk from expected heat.
    - **1:** Minor - This level of heat affects primarily those individuals extremely sensitive to heat, especially when outdoors without effective cooling and/or adequate hydration.
    - **2:** Moderate - This level of heat affects most individuals sensitive to heat, especially those without effective cooling and/or adequate hydration. Impacts possible in some health systems and in heat-sensitive industries.
    - **3:** Major - This level of heat affects anyone without effective cooling and/or adequate hydration. Impacts likely in some health systems, heat-sensitive industries, and infrastructure.
    - **4:** Extreme - This level of rare and/or long-duration extreme heat with little to no overnight relief affects anyone without effective cooling and/or adequate hydration. Impacts likely in most health systems, heat-sensitive industries, and infrastructure.
    """

def create_map(layer1_with_weighted_values, selected_hhi_indicator, heat_threshold, heat_health_index_threshold, selected_state, selected_county, states, counties, zipcode_boundary=None):
    """
    Create an interactive map with highlighted areas based on selected HHI indicator and thresholds.
    This function now also includes the ability to highlight a ZIP Code boundary.

    Args:
        layer1_with_weighted_values (GeoDataFrame): The dataset to visualize.
        selected_hhi_indicator (str): The HHI indicator column to visualize.
        heat_threshold (list): The list of heat risk levels to highlight.
        heat_health_index_threshold (float): The HHI percentile threshold.
        selected_state (str): The selected state name.
        selected_county (str): The selected county name.
        states (GeoDataFrame): The GeoDataFrame containing state boundaries.
        counties (GeoDataFrame): The GeoDataFrame containing county boundaries.
        zipcode_boundary (GeoDataFrame, optional): The boundary of the ZIP Code to highlight.

    Returns:
        folium.Map: A Folium map object.
    """
    # Check for empty DataFrame
    if layer1_with_weighted_values.empty:
        st.warning("The data is empty. Please check your inputs.")
        return None

    # Calculate the percentile threshold
    percentile_threshold = np.percentile(layer1_with_weighted_values[selected_hhi_indicator], heat_health_index_threshold)

    # Create a temporary column to flag the records we want to highlight
    highlighted_areas = layer1_with_weighted_values.copy()
    highlighted_areas['highlight'] = (
        (highlighted_areas[selected_hhi_indicator] >= percentile_threshold) & 
        (highlighted_areas['raster_value'].isin(heat_threshold))
    )

    # Ensure the GeoDataFrame is in a geographic CRS (WGS84)
    if not highlighted_areas.crs.is_geographic:
        highlighted_areas = highlighted_areas.to_crs(epsg=4326)

    # Filter state and county geometries
    selected_state_geom = None
    if selected_state != "Select a State":
        selected_state_geom = states.loc[states['NAME'] == selected_state, 'geometry'].values[0]

    selected_county_geom = None
    if selected_county != "Select a County" and selected_state_geom is not None:
        selected_county_geom = counties.loc[(counties['STATE_NAME'] == selected_state) & (counties['NAME'] == selected_county), 'geometry'].values[0]

    # Set initial map location and zoom level
    initial_location = [highlighted_areas.geometry.centroid.y.mean(), highlighted_areas.geometry.centroid.x.mean()]
    initial_zoom = 4

    # Adjust view based on selected state, county, or ZIP Code
    if zipcode_boundary is not None:
        initial_location = [zipcode_boundary.geometry.centroid.y.mean(), zipcode_boundary.geometry.centroid.x.mean()]
        initial_zoom = 13
    elif selected_county_geom is not None:
        initial_location = [selected_county_geom.centroid.y, selected_county_geom.centroid.x]
        initial_zoom = 8
    elif selected_state_geom is not None:
        initial_location = [selected_state_geom.centroid.y, selected_state_geom.centroid.x]
        initial_zoom = 6

    # Create the map
    m = folium.Map(location=initial_location, zoom_start=initial_zoom)

    # Add state boundary to the map
    if selected_state_geom is not None:
        folium.GeoJson(selected_state_geom, name="State Boundary", style_function=lambda x: {'color': 'green', 'weight': 2, 'fillOpacity': 0.1}).add_to(m)

    # Add county boundary to the map
    if selected_county_geom is not None:
        folium.GeoJson(selected_county_geom, name="County Boundary", style_function=lambda x: {'color': 'yellow', 'weight': 2, 'fillOpacity': 0.7}).add_to(m)

    # Add ZIP Code boundary to the map if provided
    if zipcode_boundary is not None:
        folium.GeoJson(zipcode_boundary.geometry, name="ZIP Code Boundary", style_function=lambda x: {'color': 'black', 'weight': 3, 'fillOpacity': 0.5}).add_to(m)

    # Add highlighted areas to the map with tooltips
    folium.GeoJson(
        highlighted_areas,
        style_function=lambda feature: {
            'fillColor': 'red' if feature['properties']['highlight'] else 'blue',
            'color': 'black',
            'weight': 0.1,
            'fillOpacity': 0.7 if feature['properties']['highlight'] else 0.3,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[selected_hhi_indicator, 'raster_value'],
            aliases=[selected_hhi_indicator.replace('weighted_', ''), 'Heat Risk Level:'],
            localize=True,
            sticky=True
        )
    ).add_to(m)

    # Add a legend
    legend_html = f'''
        <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 90px; 
                    border:2px solid grey; z-index:9999; font-size:14px;
                    background-color:white;
                    ">
        &nbsp; Legend <br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:red"></i> Highlighted Areas (Heat Risk {heat_threshold} & HHI {heat_health_index_threshold}th percentile)<br>
        &nbsp; <i class="fa fa-square fa-1x"
                    style="color:blue"></i> Other Areas
        </div>
        '''
    m.get_root().html.add_child(folium.Element(legend_html))

    return m

def create_plot(data, y_column, x_column, color_column, title, y_label, x_label, height=300, width=600):
    """
    Helper function to create a horizontal stacked bar chart.
    
    Args:
        data (pd.DataFrame): The data to plot.
        y_column (str): The column to use for the y-axis.
        x_column (str): The column to use for the x-axis.
        color_column (str): The column to use for color.
        title (str): The title of the chart.
        y_label (str): The label for the y-axis.
        x_label (str): The label for the x-axis.
        height (int): The height of the chart.
        width (int): The width of the chart.
        
    Returns:
        fig (plotly.graph_objs.Figure): The generated Plotly figure.
    """
    fig = px.bar(data, 
                 y=y_column, 
                 x=x_column, 
                 color=color_column,
                 labels={y_column: y_label, x_column: x_label},
                 title=title,
                 orientation='h',
                 height=height,
                 width=width)
    fig.update_layout(barmode='stack')
    return fig
