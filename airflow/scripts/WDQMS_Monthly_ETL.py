#!/usr/bin/env python
# coding: utf-8

# In[1]:


get_ipython().system('pip install mysql-connector-python')


# ## Imports

# In[2]:


import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import mysql.connector
import numpy as np
import os
from dotenv import load_dotenv

# ## Dynamic dates and parameters

# In[3]:


variables = [
    "humidity",
    "pressure",
    "meridional_wind",
    "zonal_wind",
    "temperature"
]
# Monthly = previous month
first_day_this_month = datetime.today().replace(day=1)
previous_month = first_day_this_month - timedelta(days=1)
monthly_date = previous_month.strftime("%Y-%m")

periods = {
    "monthly": monthly_date
}

base_url = "https://wdqms.wmo.int/wdqmsapi/v1/download/nwp/synop/{period}/availability/"

print("Monthly date:", monthly_date)


# ## Extract function

# In[ ]:


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


# ## Extract monthly function

# In[ ]:


def extract_monthly_data(variables, monthly_date):
    monthly_data = []

    for variable in variables:
        df = extract_wdqms_data(
            period="monthly",
            variable=variable,
            date_value=monthly_date
        )

        if not df.empty:
            monthly_data.append(df)

    if monthly_data:
        monthly_df = pd.concat(monthly_data, ignore_index=True)
    else:
        monthly_df = pd.DataFrame()

    return monthly_df


# ## Run extraction

# In[ ]:


monthly_raw_df = extract_monthly_data(variables, monthly_date)

print("Monthly shape:", monthly_raw_df.shape)


# ## Transform stations table

# In[ ]:


def fix_encoding(text):
    if pd.isna(text):
        return None

    try:
        return text.encode("latin1").decode("utf-8")
    except Exception:
        return text


# In[ ]:


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


# In[ ]:


monthly_stations_df = transform_stations(monthly_raw_df)


# In[ ]:


stations_df = transform_stations(monthly_raw_df).drop_duplicates(subset=["wigos_id"])


# In[ ]:


stations_df.head()


# ## Transform Monthly Fact Function

# In[ ]:


def transform_monthly_fact(monthly_raw_df):

    monthly_fact_df = monthly_raw_df[[
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

    monthly_fact_df = monthly_fact_df.rename(columns={
        "date": "observation_month",
        "wigosid": "wigos_id",
        "variable": "variable_name",
        "#received": "received_observations",
        "#expected": "expected_observations",
        "default schedule": "default_schedule",
        "color code": "color_code",
        "description": "status_description",
        "center": "center_name"
    })

    monthly_fact_df["observation_month"] = pd.to_datetime(
        monthly_fact_df["observation_month"]
    ).dt.date

    monthly_fact_df["availability_rate"] =np.where(
        monthly_fact_df["expected_observations"] > 0,
        (
            monthly_fact_df["received_observations"]
            / monthly_fact_df["expected_observations"]
            * 100
        ).round(2),
        None

    return monthly_fact_df


# ## Execute transformations

# In[ ]:


monthly_fact_df = transform_monthly_fact(monthly_raw_df)

monthly_fact_df.head()


# ## Final verification

# In[ ]:


display(stations_df.head())
display(monthly_fact_df.head())

print("Stations:", stations_df.shape)
print("Monthly:", monthly_fact_df.shape)


# In[ ]:


print("Stations columns:")
print(stations_df.columns)

print("\nMonthly columns:")
print(monthly_fact_df.columns)


# ## Quality verification

# In[ ]:


# ======================================================
# clean stations_df,daily_fact_df and monthly_fact_df by Replacing all NaN values with None before inserting
# ======================================================
stations_df = stations_df.replace({np.nan: None})

monthly_fact_df = monthly_fact_df.replace({np.nan: None})


# In[ ]:


# ======================================================
# Data Quality Check - Duplicate Stations
# ======================================================

duplicate_stations = stations_df[
    stations_df.duplicated(subset=["wigos_id"], keep=False)
].sort_values("wigos_id")

print("Number of duplicated station IDs:", duplicate_stations["wigos_id"].nunique())
display(duplicate_stations.head(50))


# In[ ]:


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
display(station_name_conflicts.head())


# In[ ]:


# ======================================================
# Data Quality Check - Suspicious Station Names
# ======================================================

suspicious_names = stations_df[
    stations_df["station_name"].astype(str).str.contains("Ã|Â|�", regex=True, na=False)
]

print("Suspicious station names:", suspicious_names.shape[0])
display(suspicious_names[["wigos_id", "station_name", "country_code"]].head(50))


# In[ ]:


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

display(stations_df.head())


# In[ ]:


# ======================================================
# Data Quality Check - Missing Values
# ======================================================

print("Stations missing values:")
display(stations_df.isna().sum())

print("Monthly fact missing values:")
display(monthly_fact_df.isna().sum())


# In[ ]:


# ======================================================
# Data Quality Check - Duplicate Fact Rows
# ======================================================

monthly_duplicates = monthly_fact_df[
    monthly_fact_df.duplicated(
        subset=["observation_month", "wigos_id", "variable_name", "center_name"],
        keep=False
    )
]

print("Monthly duplicated rows:", monthly_duplicates.shape[0])

display(monthly_duplicates.head(20))


# In[ ]:


# ======================================================
# Data Quality Check - Availability Rate
# ======================================================
print("Monthly availability min:", monthly_fact_df["availability_rate"].min())
print("Monthly availability max:", monthly_fact_df["availability_rate"].max())

display(
    monthly_fact_df[monthly_fact_df["availability_rate"] > 100]
    .sort_values("availability_rate", ascending=False)
    .head(20)
)


# In[ ]:


# ======================================================
# Data Quality Check - Availability Rate
# ======================================================
monthly_fact_df["availability_rate_capped"] = np.where(
    monthly_fact_df["expected_observations"] > 0,
    np.minimum(
        monthly_fact_df["received_observations"]
        / monthly_fact_df["expected_observations"]
        * 100,
        100
    ).round(2),
    None
)


# In[ ]:


print("Monthly availability min:", monthly_fact_df["availability_rate_capped"].min())
print("Monthly availability max:", monthly_fact_df["availability_rate_capped"].max())


# In[ ]:


# ======================================================
# Final Cleaning Before MySQL Load
# ======================================================

stations_df = stations_df.drop_duplicates(subset=["wigos_id"])

monthly_fact_df = monthly_fact_df.drop_duplicates(
    subset=["observation_month", "wigos_id", "variable_name", "center_name"]
)

stations_df = stations_df.replace([np.inf, -np.inf], None).replace({np.nan: None})
monthly_fact_df = monthly_fact_df.replace([np.inf, -np.inf], None).replace({np.nan: None})

print("Stations:", stations_df.shape)
print("Monthly:", monthly_fact_df.shape)


# ## Connect to MySQL

# In[ ]:
load_dotenv()

conn = mysql.connector.connect(
    host="host.docker.internal",
    port=3306,
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
    auth_plugin='mysql_native_password'
)

cursor = conn.cursor()

print("Connected to MySQL")


# ## Load stations into MySQL

# In[ ]:


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


# ## Load monthly fact table

# In[ ]:


# Reorder columns correctly
monthly_fact_df = monthly_fact_df[[
    "observation_month",
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
monthly_fact_df = monthly_fact_df.replace([np.inf, -np.inf], None)
monthly_fact_df = monthly_fact_df.replace({np.nan: None})

# Prepare insert query
monthly_insert_query = """
INSERT INTO fact_monthly_observations (
    observation_month,
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
monthly_data = list(
    monthly_fact_df.itertuples(index=False, name=None)
)

# Insert data
cursor.executemany(
    monthly_insert_query,
    monthly_data
)

# Commit transaction
conn.commit()

print(f"{cursor.rowcount} monthly rows inserted.")


# ## Final verification in MySQL

# In[ ]:


cursor.execute("SELECT COUNT(*) FROM dim_station")
print("Stations:", cursor.fetchone()[0])
cursor.execute("SELECT COUNT(*) FROM fact_monthly_observations")
print("Monthly rows:", cursor.fetchone()[0])


# In[ ]:


cursor.execute("""
SELECT observation_month, COUNT(*)
FROM fact_monthly_observations
GROUP BY observation_month
ORDER BY observation_month DESC;
""")

for row in cursor.fetchall():
    print(row)

