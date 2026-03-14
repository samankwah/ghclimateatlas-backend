"""
Mock climate data for Ghana districts
Based on realistic projections from CORDEX-Africa models
"""

from __future__ import annotations

import math

MONTHS = [
    ("jan", "January"),
    ("feb", "February"),
    ("mar", "March"),
    ("apr", "April"),
    ("may", "May"),
    ("jun", "June"),
    ("jul", "July"),
    ("aug", "August"),
    ("sep", "September"),
    ("oct", "October"),
    ("nov", "November"),
    ("dec", "December"),
]

MONTHLY_TEMP_BASE_OFFSETS = {
    "jan": 0.6,
    "feb": 1.0,
    "mar": 1.2,
    "apr": 0.9,
    "may": 0.4,
    "jun": 0.0,
    "jul": -0.3,
    "aug": -0.2,
    "sep": 0.2,
    "oct": 0.5,
    "nov": 0.4,
    "dec": 0.1,
}

MONTHLY_PRECIP_WEIGHTS = {
    "jan": 0.02,
    "feb": 0.03,
    "mar": 0.05,
    "apr": 0.10,
    "may": 0.13,
    "jun": 0.14,
    "jul": 0.12,
    "aug": 0.10,
    "sep": 0.10,
    "oct": 0.10,
    "nov": 0.07,
    "dec": 0.04,
}

# Ghana's 16 Regions with sample districts
REGIONS = {
    "Greater Accra": ["Accra Metropolitan", "Tema Metropolitan", "Ga West", "Ga East", "Ga South", "Ga Central", "Ledzokuku", "La Dade-Kotopon", "La Nkwantanang-Madina", "Adentan", "Kpone Katamanso", "Ada East", "Ada West", "Ningo Prampram", "Shai Osudoku", "Krowor"],
    "Ashanti": ["Kumasi Metropolitan", "Obuasi Municipal", "Ejisu", "Asokore Mampong", "Atwima Nwabiagya", "Bekwai", "Adansi North", "Adansi South", "Amansie Central", "Amansie West", "Ahafo Ano North", "Ahafo Ano South", "Asante Akim North", "Asante Akim South", "Asante Akim Central", "Bosomtwe", "Atwima Kwanwoma", "Atwima Mponua", "Afigya Kwabre", "Kwabre East", "Sekyere Central", "Sekyere East", "Sekyere Kumawu", "Sekyere South", "Mampong Municipal", "Offinso North", "Offinso South", "Ejura Sekyedumase", "Obuasi East", "Akrofuom"],
    "Western": ["Sekondi-Takoradi Metropolitan", "Effia Kwesimintsim", "Shama", "Ahanta West", "Mpohor", "Tarkwa-Nsuaem", "Prestea-Huni Valley", "Wassa East", "Wassa Amenfi East", "Wassa Amenfi Central", "Wassa Amenfi West", "Ellembelle", "Jomoro", "Nzema East"],
    "Central": ["Cape Coast Metropolitan", "Komenda-Edina-Eguafo-Abrem", "Mfantseman", "Ekumfi", "Ajumako-Enyan-Essiam", "Gomoa West", "Gomoa East", "Gomoa Central", "Effutu", "Awutu Senya East", "Awutu Senya West", "Agona East", "Agona West", "Asikuma-Odoben-Brakwa", "Assin North", "Assin South", "Twifo-Atti Morkwa", "Twifo Hemang Lower Denkyira", "Upper Denkyira East", "Upper Denkyira West", "Abura-Asebu-Kwamankese"],
    "Eastern": ["New Juaben South", "New Juaben North", "Nsawam-Adoagyiri", "Akuapim South", "Akuapim North", "Suhum", "Ayensuano", "Upper West Akim", "Denkyembour", "Kwaebibirem", "Akim Oda", "Birim South", "Birim North", "Birim Central", "Atiwa East", "Atiwa West", "Abuakwa South", "Abuakwa North", "Kwahu East", "Kwahu West", "Kwahu South", "Kwahu Afram Plains North", "Kwahu Afram Plains South", "Fanteakwa North", "Fanteakwa South", "Yilo Krobo", "Lower Manya Krobo", "Upper Manya Krobo", "Akyemansa"],
    "Volta": ["Ho Municipal", "Ho West", "Adaklu", "Agortime-Ziope", "North Dayi", "South Dayi", "Keta", "Ketu South", "Ketu North", "Akatsi South", "Akatsi North", "South Tongu", "North Tongu", "Central Tongu", "Afadzato South", "Hohoe"],
    "Northern": ["Tamale Metropolitan", "Sagnarigu", "Mion", "Nanton", "Kumbungu", "Tolon", "Savelugu", "Karaga", "Gushegu", "Yendi", "Zabzugu", "Tatale Sanguli", "Nanumba North", "Nanumba South", "Kpandai"],
    "Upper East": ["Bolgatanga Municipal", "Bolgatanga East", "Bongo", "Talensi", "Nabdam", "Kassena-Nankana East", "Kassena-Nankana West", "Builsa North", "Builsa South", "Bawku Municipal", "Bawku West", "Binduri", "Garu", "Tempane", "Pusiga"],
    "Upper West": ["Wa Municipal", "Wa East", "Wa West", "Nadowli-Kaleo", "Daffiama-Bussie-Issa", "Jirapa", "Lambussie-Karni", "Lawra", "Nandom", "Sissala East", "Sissala West"],
    "Bono": ["Sunyani Municipal", "Sunyani West", "Dormaa Central", "Dormaa East", "Dormaa West", "Berekum East", "Berekum West", "Jaman North", "Jaman South", "Tain", "Wenchi", "Banda"],
    "Bono East": ["Techiman Municipal", "Techiman North", "Kintampo North", "Kintampo South", "Nkoranza North", "Nkoranza South", "Atebubu-Amantin", "Sene East", "Sene West", "Pru East", "Pru West"],
    "Ahafo": ["Goaso", "Asunafo North", "Asunafo South", "Asutifi North", "Asutifi South", "Tano North", "Tano South"],
    "Western North": ["Sefwi-Wiawso", "Sefwi-Akontombra", "Sefwi-Bibiani-Anhwiaso-Bekwai", "Juaboso", "Bia East", "Bia West", "Bodi", "Suaman", "Aowin"],
    "Oti": ["Dambai", "Krachi East", "Krachi West", "Krachi Nchumuru", "Nkwanta North", "Nkwanta South", "Biakoye", "Jasikan", "Kadjebi"],
    "North East": ["Nalerigu-Gambaga", "East Mamprusi", "West Mamprusi", "Mamprugu Moagduri", "Yunyoo-Nasuan", "Chereponi", "Bunkpurugu-Nakpanduri"],
    "Savannah": ["Damongo", "West Gonja", "Central Gonja", "East Gonja", "North Gonja", "Sawla-Tuna-Kalba", "Bole"],
}

# Climate variable definitions
CLIMATE_VARIABLES = [
    {
        "id": "annual_mean_temp",
        "name": "Annual Mean Temperature",
        "description": "Average of daily mean temperatures over the year",
        "unit": "Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "annual_max_temp",
        "name": "Annual Maximum Temperature",
        "description": "Average of daily maximum temperatures over the year",
        "unit": "Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "annual_min_temp",
        "name": "Annual Minimum Temperature",
        "description": "Average of daily minimum temperatures over the year",
        "unit": "Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "mean_temp_major_south",
        "name": "Major South Mean Temperature",
        "description": "Average daily mean temperature during the major south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "mean_temp_major_north",
        "name": "Major North Mean Temperature",
        "description": "Average daily mean temperature during the major north rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "mean_temp_minor_south",
        "name": "Minor South Mean Temperature",
        "description": "Average daily mean temperature during the minor south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "mean_temp_dry_season",
        "name": "Dry Season Mean Temperature",
        "description": "Average daily mean temperature during the dry season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "max_temp_major_south",
        "name": "Major South Maximum Temperature",
        "description": "Average daily maximum temperature during the major south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "max_temp_major_north",
        "name": "Major North Maximum Temperature",
        "description": "Average daily maximum temperature during the major north rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "max_temp_minor_south",
        "name": "Minor South Maximum Temperature",
        "description": "Average daily maximum temperature during the minor south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "max_temp_dry_season",
        "name": "Dry Season Maximum Temperature",
        "description": "Average daily maximum temperature during the dry season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "min_temp_major_south",
        "name": "Major South Minimum Temperature",
        "description": "Average daily minimum temperature during the major south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "min_temp_major_north",
        "name": "Major North Minimum Temperature",
        "description": "Average daily minimum temperature during the major north rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "min_temp_minor_south",
        "name": "Minor South Minimum Temperature",
        "description": "Average daily minimum temperature during the minor south rainy season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "min_temp_dry_season",
        "name": "Dry Season Minimum Temperature",
        "description": "Average daily minimum temperature during the dry season",
        "unit": "Ã‚Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "very_hot_days",
        "name": "Very Hot Days",
        "description": "Number of days per year with maximum temperature above 35Â°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "warmest_max_temp",
        "name": "Warmest Maximum Temperature",
        "description": "Highest daily maximum temperature recorded during the year",
        "unit": "Â°C",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "heat_wave_count",
        "name": "Number of Heat Waves",
        "description": "Count of heat-wave events per year using a 3-day run of Tmax >= 32Â°C",
        "unit": "events",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "heat_wave_avg_length",
        "name": "Average Length of Heat Waves",
        "description": "Average duration of heat-wave events in days",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "longest_hot_spell",
        "name": "Longest Spell of +30Â°C Days",
        "description": "Longest run of consecutive days with Tmax >= 30Â°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "hot_season",
        "name": "Hot (+30Â°C) Season",
        "description": "Duration between the first and last day with Tmax >= 30Â°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "extreme_hot_32",
        "name": "Extremely Hot Days (+32Â°C)",
        "description": "Number of days per year with Tmax >= 32Â°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "extreme_hot_34",
        "name": "Extremely Hot Days (+34Â°C)",
        "description": "Number of days per year with Tmax >= 34Â°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
    },
    {
        "id": "coldest_min_temp",
        "name": "Coldest Minimum Temperature",
        "description": "Lowest daily minimum temperature recorded during the year",
        "unit": "Â°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "annual_precipitation",
        "name": "Annual Precipitation",
        "description": "Total precipitation over the year",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "wet_season_precipitation",
        "name": "Wet Season Precipitation",
        "description": "Total precipitation during wet season (April-October)",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "dry_days",
        "name": "Dry Days",
        "description": "Number of days per year with less than 1mm precipitation",
        "unit": "days",
        "category": "precipitation",
        "color_scale": "dry_days",
    },
    {
        "id": "precipitation_major_south",
        "name": "Major South Precipitation",
        "description": "Total precipitation during the major south rainy season",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "precipitation_major_north",
        "name": "Major North Precipitation",
        "description": "Total precipitation during the major north rainy season",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "precipitation_minor_south",
        "name": "Minor South Precipitation",
        "description": "Total precipitation during the minor south rainy season",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "precipitation_dry_season",
        "name": "Dry Season Precipitation",
        "description": "Total precipitation during the dry season",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "precipitation_growing_season",
        "name": "Growing Season Precipitation",
        "description": "Total precipitation during the main growing season",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "heavy_precip_10mm",
        "name": "Heavy Precipitation Days (10 mm)",
        "description": "Number of days per year with precipitation at or above 10 mm",
        "unit": "days",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "heavy_precip_20mm",
        "name": "Heavy Precipitation Days (20 mm)",
        "description": "Number of days per year with precipitation at or above 20 mm",
        "unit": "days",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "max_1day_precip",
        "name": "Max 1-Day Precipitation",
        "description": "Maximum daily precipitation total during the year",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "max_3day_precip",
        "name": "Max 3-Day Precipitation",
        "description": "Maximum rolling 3-day precipitation total during the year",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "max_5day_precip",
        "name": "Max 5-Day Precipitation",
        "description": "Maximum rolling 5-day precipitation total during the year",
        "unit": "mm",
        "category": "precipitation",
        "color_scale": "precipitation",
    },
    {
        "id": "gdd_base_4",
        "name": "Growing Degree Days (Base 4 Â°C)",
        "description": "Accumulated thermal units above 4Â°C base temperature",
        "unit": "Â°CÂ·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_5",
        "name": "Growing Degree Days (Base 5 Â°C)",
        "description": "Accumulated thermal units above 5Â°C base temperature",
        "unit": "Â°CÂ·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_10",
        "name": "Growing Degree Days (Base 10 Â°C)",
        "description": "Accumulated thermal units above 10Â°C base temperature",
        "unit": "Â°CÂ·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_15",
        "name": "Growing Degree Days (Base 15 Â°C)",
        "description": "Accumulated thermal units above 15Â°C base temperature",
        "unit": "Â°CÂ·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "maize_heat_units",
        "name": "Maize Heat Units",
        "description": "Growing degree days with base 10Â°C for maize cultivation",
        "unit": "Â°CÂ·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
]

for month_id, month_name in MONTHS:
    CLIMATE_VARIABLES.extend([
        {
            "id": f"mean_temp_{month_id}",
            "name": f"{month_name} Mean Temperature",
            "description": f"Average daily mean temperature during {month_name}",
            "unit": "Ã‚Â°C",
            "category": "temperature",
            "color_scale": "temperature",
        },
        {
            "id": f"max_temp_{month_id}",
            "name": f"{month_name} Maximum Temperature",
            "description": f"Average daily maximum temperature during {month_name}",
            "unit": "Ã‚Â°C",
            "category": "temperature",
            "color_scale": "temperature",
        },
        {
            "id": f"min_temp_{month_id}",
            "name": f"{month_name} Minimum Temperature",
            "description": f"Average daily minimum temperature during {month_name}",
            "unit": "Ã‚Â°C",
            "category": "temperature",
            "color_scale": "temperature",
        },
        {
            "id": f"precipitation_{month_id}",
            "name": f"{month_name} Precipitation",
            "description": f"Total precipitation during {month_name}",
            "unit": "mm",
            "category": "precipitation",
            "color_scale": "precipitation",
        },
    ])

# GDD variable IDs and their base temperatures
GDD_VARIABLES = {
    "gdd_base_4": 4,
    "gdd_base_5": 5,
    "gdd_base_10": 10,
    "gdd_base_15": 15,
    "maize_heat_units": 10,
}

DERIVED_VARIABLES = {
    "mean_temp_major_south",
    "mean_temp_major_north",
    "mean_temp_minor_south",
    "mean_temp_dry_season",
    "max_temp_major_south",
    "max_temp_major_north",
    "max_temp_minor_south",
    "max_temp_dry_season",
    "min_temp_major_south",
    "min_temp_major_north",
    "min_temp_minor_south",
    "min_temp_dry_season",
    "precipitation_major_south",
    "precipitation_major_north",
    "precipitation_minor_south",
    "precipitation_dry_season",
    "precipitation_growing_season",
    "warmest_max_temp",
    "heat_wave_count",
    "heat_wave_avg_length",
    "longest_hot_spell",
    "hot_season",
    "extreme_hot_32",
    "extreme_hot_34",
    "coldest_min_temp",
    "heavy_precip_10mm",
    "heavy_precip_20mm",
    "max_1day_precip",
    "max_3day_precip",
    "max_5day_precip",
    *{f"mean_temp_{month_id}" for month_id, _ in MONTHS},
    *{f"max_temp_{month_id}" for month_id, _ in MONTHS},
    *{f"min_temp_{month_id}" for month_id, _ in MONTHS},
    *{f"precipitation_{month_id}" for month_id, _ in MONTHS},
}

SEASONAL_TEMP_OFFSETS = {
    "mean_temp_major_south": 0.2,
    "mean_temp_major_north": -0.1,
    "mean_temp_minor_south": 0.5,
    "mean_temp_dry_season": 1.2,
    "max_temp_major_south": 0.3,
    "max_temp_major_north": -0.2,
    "max_temp_minor_south": 0.8,
    "max_temp_dry_season": 1.9,
    "min_temp_major_south": 0.2,
    "min_temp_major_north": 0.3,
    "min_temp_minor_south": 0.4,
    "min_temp_dry_season": -0.8,
}


def compute_maize_heat_units(tmax: float, tmin: float) -> float:
    ymax = max(0, 3.33 * (tmax - 10) - 0.084 * (tmax - 10) ** 2)
    ymin = max(0, 1.8 * (tmin - 4.4))
    daily_mhu = (ymax + ymin) / 2
    return daily_mhu * 365


def compute_gdd_ghana(tmax: float, tmin: float, base_temp: float) -> float:
    amplitude = 1.5 if tmax < 33 else 3.0
    cap = base_temp + 30
    annual_gdd = 0.0
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    for month in range(12):
        seasonal_offset = amplitude * math.cos(2 * math.pi * (month - 2) / 12)
        month_tmax = tmax + seasonal_offset
        month_tmin = tmin + seasonal_offset * 0.6
        capped_tmax = min(month_tmax, cap)
        daily_gdd = max(0, (capped_tmax + month_tmin) / 2 - base_temp)
        annual_gdd += daily_gdd * days_per_month[month]

    return annual_gdd


# Baseline climate values by region
REGIONAL_BASELINES = {
    "Greater Accra": {"annual_mean_temp": 27.5, "annual_max_temp": 32.0, "annual_min_temp": 23.0, "very_hot_days": 20, "annual_precipitation": 810, "wet_season_precipitation": 720, "dry_days": 180},
    "Ashanti": {"annual_mean_temp": 26.0, "annual_max_temp": 31.0, "annual_min_temp": 21.0, "very_hot_days": 15, "annual_precipitation": 1400, "wet_season_precipitation": 1200, "dry_days": 140},
    "Western": {"annual_mean_temp": 26.5, "annual_max_temp": 31.5, "annual_min_temp": 21.5, "very_hot_days": 12, "annual_precipitation": 1700, "wet_season_precipitation": 1450, "dry_days": 120},
    "Central": {"annual_mean_temp": 26.8, "annual_max_temp": 31.8, "annual_min_temp": 21.8, "very_hot_days": 18, "annual_precipitation": 1100, "wet_season_precipitation": 950, "dry_days": 160},
    "Eastern": {"annual_mean_temp": 26.2, "annual_max_temp": 31.2, "annual_min_temp": 21.2, "very_hot_days": 14, "annual_precipitation": 1500, "wet_season_precipitation": 1280, "dry_days": 135},
    "Volta": {"annual_mean_temp": 27.0, "annual_max_temp": 32.5, "annual_min_temp": 21.5, "very_hot_days": 22, "annual_precipitation": 1200, "wet_season_precipitation": 1020, "dry_days": 155},
    "Northern": {"annual_mean_temp": 28.5, "annual_max_temp": 35.0, "annual_min_temp": 22.0, "very_hot_days": 85, "annual_precipitation": 1050, "wet_season_precipitation": 980, "dry_days": 200},
    "Upper East": {"annual_mean_temp": 29.0, "annual_max_temp": 36.0, "annual_min_temp": 22.0, "very_hot_days": 110, "annual_precipitation": 950, "wet_season_precipitation": 900, "dry_days": 220},
    "Upper West": {"annual_mean_temp": 28.8, "annual_max_temp": 35.5, "annual_min_temp": 22.1, "very_hot_days": 95, "annual_precipitation": 1000, "wet_season_precipitation": 940, "dry_days": 210},
    "Bono": {"annual_mean_temp": 26.5, "annual_max_temp": 32.0, "annual_min_temp": 21.0, "very_hot_days": 25, "annual_precipitation": 1250, "wet_season_precipitation": 1100, "dry_days": 150},
    "Bono East": {"annual_mean_temp": 27.0, "annual_max_temp": 33.0, "annual_min_temp": 21.0, "very_hot_days": 35, "annual_precipitation": 1200, "wet_season_precipitation": 1050, "dry_days": 165},
    "Ahafo": {"annual_mean_temp": 26.3, "annual_max_temp": 31.5, "annual_min_temp": 21.1, "very_hot_days": 18, "annual_precipitation": 1350, "wet_season_precipitation": 1180, "dry_days": 145},
    "Western North": {"annual_mean_temp": 26.0, "annual_max_temp": 31.0, "annual_min_temp": 21.0, "very_hot_days": 10, "annual_precipitation": 1600, "wet_season_precipitation": 1380, "dry_days": 125},
    "Oti": {"annual_mean_temp": 27.5, "annual_max_temp": 33.5, "annual_min_temp": 21.5, "very_hot_days": 45, "annual_precipitation": 1150, "wet_season_precipitation": 1000, "dry_days": 175},
    "North East": {"annual_mean_temp": 28.8, "annual_max_temp": 35.8, "annual_min_temp": 21.8, "very_hot_days": 100, "annual_precipitation": 980, "wet_season_precipitation": 920, "dry_days": 215},
    "Savannah": {"annual_mean_temp": 28.2, "annual_max_temp": 34.5, "annual_min_temp": 21.9, "very_hot_days": 70, "annual_precipitation": 1080, "wet_season_precipitation": 1000, "dry_days": 195},
}

CLIMATE_CHANGE_FACTORS = {
    "rcp45": {
        "2030": {"temp_add": 0.8, "precip_mult": 0.98, "hot_days_mult": 1.4, "dry_days_add": 5},
        "2050": {"temp_add": 1.4, "precip_mult": 0.95, "hot_days_mult": 1.9, "dry_days_add": 12},
        "2080": {"temp_add": 1.8, "precip_mult": 0.92, "hot_days_mult": 2.3, "dry_days_add": 18},
    },
    "rcp85": {
        "2030": {"temp_add": 1.0, "precip_mult": 0.96, "hot_days_mult": 1.6, "dry_days_add": 8},
        "2050": {"temp_add": 2.0, "precip_mult": 0.90, "hot_days_mult": 2.5, "dry_days_add": 20},
        "2080": {"temp_add": 3.5, "precip_mult": 0.82, "hot_days_mult": 4.0, "dry_days_add": 35},
    },
}


def generate_district_id(region: str, district: str) -> str:
    region_code = region.upper().replace(" ", "_")[:3]
    district_code = district.upper().replace(" ", "_").replace("-", "_")[:5]
    return f"GH-{region_code}-{district_code}"


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def derive_indicator_values(
    annual_mean_temp: float,
    annual_max_temp: float,
    annual_min_temp: float,
    very_hot_days: float,
    annual_precipitation: float,
    wet_season_precipitation: float,
    dry_days: float,
) -> dict[str, float]:
    wet_days = max(1.0, 365.0 - dry_days)
    wet_intensity = annual_precipitation / wet_days
    wet_season_ratio = clamp(wet_season_precipitation / max(annual_precipitation, 1.0), 0.45, 0.95)
    heat_pressure = clamp((annual_max_temp - 30.0) / 6.5, 0.0, 1.4)
    dry_season_precipitation = max(annual_precipitation - wet_season_precipitation, annual_precipitation * 0.05)

    heavy_precip_10mm = clamp(wet_days * (0.16 + 0.018 * wet_intensity), 2.0, wet_days * 0.55)
    heavy_precip_20mm = clamp(heavy_precip_10mm * (0.22 + 0.012 * wet_intensity), 1.0, heavy_precip_10mm * 0.7)
    max_1day_precip = clamp(wet_intensity * (4.2 + 1.5 * wet_season_ratio), 18.0, annual_precipitation * 0.22)
    max_3day_precip = clamp(max_1day_precip * (1.85 + 0.18 * wet_season_ratio), max_1day_precip * 1.5, annual_precipitation * 0.42)
    max_5day_precip = clamp(max_1day_precip * (2.55 + 0.25 * wet_season_ratio), max_3day_precip * 1.15, annual_precipitation * 0.6)

    extreme_hot_34 = clamp(very_hot_days * 0.58, 0.0, 365.0)
    extreme_hot_32 = clamp(very_hot_days * 1.35 + heat_pressure * 14.0, extreme_hot_34, 365.0)
    warmest_max_temp = annual_max_temp + 5.5 + heat_pressure * 2.4
    heat_wave_count = clamp(very_hot_days / (7.5 - heat_pressure * 1.5), 0.0, 40.0)
    heat_wave_avg_length = clamp(3.2 + heat_pressure * 2.8 + very_hot_days / 90.0, 3.0, 14.0)
    longest_hot_spell = clamp(10.0 + very_hot_days * 0.62 + heat_pressure * 12.0, heat_wave_avg_length, 180.0)
    hot_season = clamp(80.0 + extreme_hot_32 * 1.2 + very_hot_days * 0.7, longest_hot_spell, 320.0)
    coldest_min_temp = annual_min_temp - (4.8 - min(heat_pressure, 1.0) * 0.9)
    monthly_values: dict[str, float] = {}

    for month_id, _month_name in MONTHS:
        temp_offset = MONTHLY_TEMP_BASE_OFFSETS[month_id]
        monthly_values[f"mean_temp_{month_id}"] = round(annual_mean_temp + temp_offset, 1)
        monthly_values[f"max_temp_{month_id}"] = round(annual_max_temp + temp_offset * 1.2, 1)
        monthly_values[f"min_temp_{month_id}"] = round(annual_min_temp + temp_offset * 0.8, 1)
        monthly_values[f"precipitation_{month_id}"] = round(annual_precipitation * MONTHLY_PRECIP_WEIGHTS[month_id], 1)

    return {
        "mean_temp_major_south": round(annual_mean_temp + SEASONAL_TEMP_OFFSETS["mean_temp_major_south"], 1),
        "mean_temp_major_north": round(annual_mean_temp + SEASONAL_TEMP_OFFSETS["mean_temp_major_north"], 1),
        "mean_temp_minor_south": round(annual_mean_temp + SEASONAL_TEMP_OFFSETS["mean_temp_minor_south"], 1),
        "mean_temp_dry_season": round(annual_mean_temp + SEASONAL_TEMP_OFFSETS["mean_temp_dry_season"], 1),
        "max_temp_major_south": round(annual_max_temp + SEASONAL_TEMP_OFFSETS["max_temp_major_south"], 1),
        "max_temp_major_north": round(annual_max_temp + SEASONAL_TEMP_OFFSETS["max_temp_major_north"], 1),
        "max_temp_minor_south": round(annual_max_temp + SEASONAL_TEMP_OFFSETS["max_temp_minor_south"], 1),
        "max_temp_dry_season": round(annual_max_temp + SEASONAL_TEMP_OFFSETS["max_temp_dry_season"], 1),
        "min_temp_major_south": round(annual_min_temp + SEASONAL_TEMP_OFFSETS["min_temp_major_south"], 1),
        "min_temp_major_north": round(annual_min_temp + SEASONAL_TEMP_OFFSETS["min_temp_major_north"], 1),
        "min_temp_minor_south": round(annual_min_temp + SEASONAL_TEMP_OFFSETS["min_temp_minor_south"], 1),
        "min_temp_dry_season": round(annual_min_temp + SEASONAL_TEMP_OFFSETS["min_temp_dry_season"], 1),
        "precipitation_major_south": round(wet_season_precipitation * 0.42, 1),
        "precipitation_major_north": round(wet_season_precipitation * 0.33, 1),
        "precipitation_minor_south": round(wet_season_precipitation * 0.25, 1),
        "precipitation_dry_season": round(dry_season_precipitation, 1),
        "precipitation_growing_season": round(wet_season_precipitation * 0.88, 1),
        "warmest_max_temp": round(warmest_max_temp, 1),
        "heat_wave_count": round(heat_wave_count, 1),
        "heat_wave_avg_length": round(heat_wave_avg_length, 1),
        "longest_hot_spell": round(longest_hot_spell, 1),
        "hot_season": round(hot_season, 1),
        "extreme_hot_32": round(extreme_hot_32, 1),
        "extreme_hot_34": round(extreme_hot_34, 1),
        "coldest_min_temp": round(coldest_min_temp, 1),
        "heavy_precip_10mm": round(heavy_precip_10mm, 1),
        "heavy_precip_20mm": round(heavy_precip_20mm, 1),
        "max_1day_precip": round(max_1day_precip, 1),
        "max_3day_precip": round(max_3day_precip, 1),
        "max_5day_precip": round(max_5day_precip, 1),
        **monthly_values,
    }


def get_core_climate_values(baseline_values: dict[str, float], scenario: str, period: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for variable in [
        "annual_mean_temp",
        "annual_max_temp",
        "annual_min_temp",
        "very_hot_days",
        "annual_precipitation",
        "wet_season_precipitation",
        "dry_days",
    ]:
        baseline_value = baseline_values.get(variable, 0.0)
        values[variable] = get_climate_value(baseline_value, variable, scenario, period)
    return values


def get_mock_variable_value(baseline_values: dict[str, float], variable: str, scenario: str, period: str) -> float:
    if variable in GDD_VARIABLES:
        base_temp = GDD_VARIABLES[variable]
        core = get_core_climate_values(baseline_values, scenario, period)
        if variable == "maize_heat_units":
            return compute_maize_heat_units(core["annual_max_temp"], core["annual_min_temp"])
        return compute_gdd_ghana(core["annual_max_temp"], core["annual_min_temp"], base_temp)

    if variable not in DERIVED_VARIABLES:
        baseline_value = baseline_values.get(variable, 0.0)
        return get_climate_value(baseline_value, variable, scenario, period)

    core = get_core_climate_values(baseline_values, scenario, period)
    derived = derive_indicator_values(
        annual_mean_temp=core["annual_mean_temp"],
        annual_max_temp=core["annual_max_temp"],
        annual_min_temp=core["annual_min_temp"],
        very_hot_days=core["very_hot_days"],
        annual_precipitation=core["annual_precipitation"],
        wet_season_precipitation=core["wet_season_precipitation"],
        dry_days=core["dry_days"],
    )
    return derived[variable]


def get_climate_value(baseline: float, variable: str, scenario: str, period: str) -> float:
    if period == "baseline":
        return baseline

    factors = CLIMATE_CHANGE_FACTORS.get(scenario, {}).get(period, {})

    if variable in ["annual_mean_temp", "annual_max_temp", "annual_min_temp"]:
        return round(baseline + factors.get("temp_add", 0), 1)
    if variable in ["annual_precipitation", "wet_season_precipitation"]:
        return round(baseline * factors.get("precip_mult", 1), 1)
    if variable == "very_hot_days":
        return round(baseline * factors.get("hot_days_mult", 1), 1)
    if variable == "dry_days":
        return round(baseline + factors.get("dry_days_add", 0), 1)

    return baseline


def generate_all_districts():
    districts = []
    for region, district_list in REGIONS.items():
        for district in district_list:
            districts.append({
                "id": generate_district_id(region, district),
                "name": district,
                "region": region,
            })
    return districts


def get_district_climate_data(district_id: str, region: str):
    baseline = REGIONAL_BASELINES.get(region, REGIONAL_BASELINES["Greater Accra"])
    climate_data = {}

    for var in CLIMATE_VARIABLES:
        var_id = var["id"]
        var_data = {
            "baseline": round(get_mock_variable_value(baseline, var_id, "historical", "baseline"), 1),
        }
        for scenario in ["rcp45", "rcp85"]:
            for period in ["2030", "2050", "2080"]:
                key = f"{period}_{scenario}"
                var_data[key] = round(get_mock_variable_value(baseline, var_id, scenario, period), 1)
        climate_data[var_id] = var_data

    return climate_data
