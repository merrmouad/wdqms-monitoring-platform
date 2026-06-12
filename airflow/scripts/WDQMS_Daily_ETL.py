#!/usr/bin/env python
# coding: utf-8

# In[48]:


# get_ipython().system('pip install mysql-connector-python')


# ## Imports

# In[1]:


import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import mysql.connector
import numpy as np
import os
from dotenv import load_dotenv

# ## Dynamic dates and parameters

# In[2]:


variables = [
    "humidity",
    "pressure",
    "meridional_wind",
    "zonal_wind",
    "temperature"
]

# Daily = yesterday
daily_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

periods = {
    "daily": daily_date
}

base_url = "https://wdqms.wmo.int/wdqmsapi/v1/download/nwp/synop/{period}/availability/"

print("Daily date:", daily_date)


# ## Extract function

# In[3]:


def extract_wdqms_data(period, variable, date_value):
    params = {
        "date": date_value,
        "variable": variable,
        "centers": "COMBINED",
        "baseline": "OSCAR"
    }

    url = base_url.format(period=period)
    response = requests.get(url, params=params)

    print(f"{period} | {variable} | {date_value} | Status: {response.status_code}")

    if response.status_code != 200:
        print(response.text[:300])
        return pd.DataFrame()

    df = pd.read_csv(StringIO(response.text))

    if df.empty:
        print(f"No data for {period} - {variable}")
        return pd.DataFrame()

    df["period"] = period
    return df


# ## Extract daily function

# In[4]:


def extract_daily_data(variables, daily_date):
    daily_data = []

    for variable in variables:
        df = extract_wdqms_data(
            period="daily",
            variable=variable,
            date_value=daily_date
        )

        if not df.empty:
            daily_data.append(df)

    if daily_data:
        daily_df = pd.concat(daily_data, ignore_index=True)
    else:
        daily_df = pd.DataFrame()

    return daily_df


# ## Run extraction

# In[5]:


daily_raw_df = extract_daily_data(variables, daily_date)

print("Daily shape:", daily_raw_df.shape)


# ## Transform stations table

# In[6]:


def fix_encoding(text):
    if pd.isna(text):
        return None

    try:
        return text.encode("latin1").decode("utf-8")
    except Exception:
        return text


# In[7]:


def transform_stations(raw_df):

    stations_df = raw_df[[
        "wigosid",
        "name",
        "country code",
        "longitude",
        "latitude"
    ]].drop_duplicates()

    stations_df = stations_df.rename(columns={
        "wigosid": "wigos_id",
        "name": "station_name",
        "country code": "country_code"
    })

    stations_df["station_name"] = stations_df["station_name"].apply(fix_encoding)

    stations_df = stations_df.drop_duplicates(subset=["wigos_id"])

    return stations_df


# In[8]:


daily_stations_df = transform_stations(daily_raw_df)


# In[9]:


stations_df = transform_stations(daily_raw_df).drop_duplicates(subset=["wigos_id"])


# In[10]:


stations_df.head()


# ## Transform daily fact table

# In[11]:


def transform_daily_fact(daily_raw_df):

    daily_fact_df = daily_raw_df[[
        "date",
        "wigosid",
        "variable",
        "#received",
        "#expected",
        "default schedule",
        "color code",
        "description",
        "center"
    ]].copy()

    daily_fact_df = daily_fact_df.rename(columns={
        "date": "observation_date",
        "wigosid": "wigos_id",
        "variable": "variable_name",
        "#received": "received_observations",
        "#expected": "expected_observations",
        "default schedule": "default_schedule",
        "color code": "color_code",
        "description": "status_description",
        "center": "center_name"
    })

    daily_fact_df["observation_date"] = pd.to_datetime(
        daily_fact_df["observation_date"]
    ).dt.date

    daily_fact_df["availability_rate"] = np.where(
        daily_fact_df["expected_observations"] > 0,
        (
            daily_fact_df["received_observations"]
            / daily_fact_df["expected_observations"]
            * 100
        ).round(2),
        None
)
    return daily_fact_df


# ## Execute transformations

# In[12]:


daily_fact_df = transform_daily_fact(daily_raw_df)

daily_fact_df.head()


# ## Final verification

# In[13]:


print(stations_df.head())
print(daily_fact_df.head())

print("Stations:", stations_df.shape)
print("Daily:", daily_fact_df.shape)


# In[14]:


print("Stations columns:")
print(stations_df.columns)

print("\nDaily columns:")
print(daily_fact_df.columns)


# ## Quality verification

# In[15]:


# ======================================================
# clean stations_df,daily_fact_df and monthly_fact_df by Replacing all NaN values with None before inserting
# ======================================================
stations_df = stations_df.replace({np.nan: None})

daily_fact_df = daily_fact_df.replace({np.nan: None})


# In[16]:


# ======================================================
# Data Quality Check - Duplicate Stations
# ======================================================

duplicate_stations = stations_df[
    stations_df.duplicated(subset=["wigos_id"], keep=False)
].sort_values("wigos_id")

print("Number of duplicated station IDs:", duplicate_stations["wigos_id"].nunique())
print(duplicate_stations.head(50))


# In[17]:


# ======================================================
# Data Quality Check - Same WIGOS ID with different station names
# ======================================================

station_name_conflicts = (
    stations_df.groupby("wigos_id")["station_name"]
    .nunique()
    .reset_index()
)

station_name_conflicts = station_name_conflicts[
    station_name_conflicts["station_name"] > 1
]

print("Stations with multiple names:", station_name_conflicts.shape[0])
print(station_name_conflicts.head())


# In[18]:


# ======================================================
# Data Quality Check - Suspicious Station Names
# ======================================================

suspicious_names = stations_df[
    stations_df["station_name"].astype(str).str.contains("Ã|Â|�", regex=True, na=False)
]

print("Suspicious station names:", suspicious_names.shape[0])
print(suspicious_names[["wigos_id", "station_name", "country_code"]].head(50))


# In[19]:


# ======================================================
# Cleaning - Fix Station Name Encoding
# ======================================================

def fix_encoding(text):
    if pd.isna(text):
        return None

    try:
        return text.encode("latin1").decode("utf-8")
    except:
        return text

stations_df["station_name"] = stations_df["station_name"].apply(fix_encoding)

print(stations_df.head())


# In[20]:


# ======================================================
# Data Quality Check - Suspicious Station Names
# ======================================================

suspicious_names = stations_df[
    stations_df["station_name"].astype(str).str.contains("Ã|Â|�", regex=True, na=False)
]

print("Suspicious station names:", suspicious_names.shape[0])
print(suspicious_names[["wigos_id", "station_name", "country_code"]].head(50))


# In[21]:


# ======================================================
# Data Quality Check - Missing Values
# ======================================================

print("Stations missing values:")
print(stations_df.isna().sum())

print("Daily fact missing values:")
print(daily_fact_df.isna().sum())


# In[22]:


# ======================================================
# Data Quality Check - Duplicate Fact Rows
# ======================================================

daily_duplicates = daily_fact_df[
    daily_fact_df.duplicated(
        subset=["observation_date", "wigos_id", "variable_name", "center_name"],
        keep=False
    )
]

print("Daily duplicated rows:", daily_duplicates.shape[0])

print(daily_duplicates.head(20))


# In[23]:


# ======================================================
# Data Quality Check - Availability Rate
# ======================================================

print("Daily availability min:", daily_fact_df["availability_rate"].min())
print("Daily availability max:", daily_fact_df["availability_rate"].max())

print(
    daily_fact_df[daily_fact_df["availability_rate"] > 100]
    .sort_values("availability_rate", ascending=False)
    .head(20)
)


# In[24]:


# ======================================================
# Data Quality Check - Availability Rate
# ======================================================
daily_fact_df["availability_rate_capped"] = np.where(
    daily_fact_df["expected_observations"] > 0,
    np.minimum(
        daily_fact_df["received_observations"]
        / daily_fact_df["expected_observations"]
        * 100,
        100
    ).round(2),
    None
)


# In[25]:


print("Daily availability min:", daily_fact_df["availability_rate_capped"].min())
print("Daily availability max:", daily_fact_df["availability_rate_capped"].max())


# In[26]:


# ======================================================
# Final Cleaning Before MySQL Load
# ======================================================

stations_df = stations_df.drop_duplicates(subset=["wigos_id"])

daily_fact_df = daily_fact_df.drop_duplicates(
    subset=["observation_date", "wigos_id", "variable_name", "center_name"]
)

stations_df = stations_df.replace([np.inf, -np.inf], None).replace({np.nan: None})
daily_fact_df = daily_fact_df.replace([np.inf, -np.inf], None).replace({np.nan: None})

print("Stations:", stations_df.shape)
print("Daily:", daily_fact_df.shape)


# ## Connect to MySQL

# In[27]:

load_dotenv()

conn = mysql.connector.connect(
    host="host.docker.internal",
    port=3306,
    user=os.getenv("MYSQL_USER"),
    password= os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
    auth_plugin='mysql_native_password'
)

cursor = conn.cursor()

print("Connected to MySQL")


# ## Load stations into MySQL

# In[28]:


stations_insert_query = """
INSERT INTO dim_station (
    wigos_id,
    station_name,
    country_code,
    longitude,
    latitude
)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    station_name = VALUES(station_name),
    country_code = VALUES(country_code),
    longitude = VALUES(longitude),
    latitude = VALUES(latitude);
"""

stations_data = list(
    stations_df.itertuples(index=False, name=None)
)

cursor.executemany(stations_insert_query, stations_data)

conn.commit()

print(f"{cursor.rowcount} station rows inserted.")


# ## Load daily fact table

# In[29]:


# Reorder columns correctly
daily_fact_df = daily_fact_df[[
    "observation_date",
    "wigos_id",
    "variable_name",
    "received_observations",
    "expected_observations",
    "availability_rate",
    "availability_rate_capped",
    "default_schedule",
    "color_code",
    "status_description",
    "center_name"
]]

# Replace NaN and inf values
daily_fact_df = daily_fact_df.replace([np.inf, -np.inf], None)
daily_fact_df = daily_fact_df.replace({np.nan: None})

# Prepare insert query
daily_insert_query = """
INSERT INTO fact_daily_observations (
    observation_date,
    wigos_id,
    variable_name,
    received_observations,
    expected_observations,
    availability_rate,
    availability_rate_capped,
    default_schedule,
    color_code,
    status_description,
    center_name
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# Convert dataframe to tuples
daily_data = list(
    daily_fact_df.itertuples(index=False, name=None)
)

# Insert data
cursor.executemany(
    daily_insert_query,
    daily_data
)

conn.commit()

print(f"{cursor.rowcount} daily rows inserted.")


# ## Final verification in MySQL

# In[30]:


cursor.execute("SELECT COUNT(*) FROM dim_station")
print("Stations:", cursor.fetchone()[0])

cursor.execute("SELECT COUNT(*) FROM fact_daily_observations")
print("Daily rows:", cursor.fetchone()[0])


# In[31]:


cursor.execute("""
SELECT observation_date, COUNT(*)
FROM fact_daily_observations
GROUP BY observation_date
ORDER BY observation_date DESC;
""")

for row in cursor.fetchall():
    print(row)


# In[32]:


cursor.execute("""
SELECT wigos_id
FROM dim_station
WHERE station_name REGEXP 'Ã|Â|Ð|�'
""")

bad_station_ids = [row[0] for row in cursor.fetchall()]

print("Bad station IDs:", len(bad_station_ids))
print(bad_station_ids[:10])






