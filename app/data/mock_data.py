"""
Mock climate data for Ghana districts
Based on realistic projections from CORDEX-Africa models
"""

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
        "unit": "°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "annual_max_temp",
        "name": "Annual Maximum Temperature",
        "description": "Average of daily maximum temperatures over the year",
        "unit": "°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "very_hot_days",
        "name": "Very Hot Days",
        "description": "Number of days per year with maximum temperature above 35°C",
        "unit": "days",
        "category": "temperature",
        "color_scale": "hot_days",
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
        "id": "annual_min_temp",
        "name": "Annual Minimum Temperature",
        "description": "Average of daily minimum temperatures over the year",
        "unit": "°C",
        "category": "temperature",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_4",
        "name": "Growing Degree Days (Base 4 °C)",
        "description": "Accumulated thermal units above 4°C base temperature",
        "unit": "°C·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_5",
        "name": "Growing Degree Days (Base 5 °C)",
        "description": "Accumulated thermal units above 5°C base temperature",
        "unit": "°C·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_10",
        "name": "Growing Degree Days (Base 10 °C)",
        "description": "Accumulated thermal units above 10°C base temperature",
        "unit": "°C·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "gdd_base_15",
        "name": "Growing Degree Days (Base 15 °C)",
        "description": "Accumulated thermal units above 15°C base temperature",
        "unit": "°C·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
    {
        "id": "maize_heat_units",
        "name": "Maize Heat Units",
        "description": "Growing degree days with base 10°C for maize cultivation",
        "unit": "°C·days",
        "category": "agriculture",
        "color_scale": "temperature",
    },
]

# GDD variable IDs and their base temperatures
GDD_VARIABLES = {
    "gdd_base_4": 4,
    "gdd_base_5": 5,
    "gdd_base_10": 10,
    "gdd_base_15": 15,
    "maize_heat_units": 10,  # base_temp used only as fallback; MHU uses its own formula
}


def compute_maize_heat_units(tmax: float, tmin: float) -> float:
    """
    Compute annual Maize Heat Units using the Ontario MHU formula.
    Ymax = 3.33(Tmax-10) - 0.084(Tmax-10)^2  (capped at 0)
    Ymin = 1.8(Tmin-4.4)                       (capped at 0)
    Daily MHU = (Ymax + Ymin) / 2
    Annual MHU = Daily MHU * 365
    """
    ymax = max(0, 3.33 * (tmax - 10) - 0.084 * (tmax - 10) ** 2)
    ymin = max(0, 1.8 * (tmin - 4.4))
    daily_mhu = (ymax + ymin) / 2
    return daily_mhu * 365


def compute_gdd_ghana(tmax: float, tmin: float, base_temp: float) -> float:
    """
    Compute annual Growing Degree Days with Ghana-appropriate seasonal modelling.

    Ghana has distinct seasonal temperature patterns:
    - Coastal/Forest zones: relatively stable year-round (±1.5°C)
    - Savanna/Northern zones: hot dry season (Feb-Apr) and cooler rainy season

    Uses monthly temperature simulation with a sinusoidal model and applies
    the standard GDD formula with upper cap: GDD = max(0, min(Tmax, cap) + Tmin) / 2 - base)
    The upper cap prevents unrealistically high GDD contributions on extreme days.
    """
    import math

    # Seasonal amplitude: northern Ghana has ~3°C swing, south ~1.5°C
    amplitude = 1.5 if tmax < 33 else 3.0

    # Upper temperature cap (above this, no additional GDD benefit)
    cap = base_temp + 30  # standard cap rule

    annual_gdd = 0.0
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    for month in range(12):
        # Sinusoidal seasonal cycle: peak in March (month=2), coolest in August (month=7)
        seasonal_offset = amplitude * math.cos(2 * math.pi * (month - 2) / 12)

        month_tmax = tmax + seasonal_offset
        month_tmin = tmin + seasonal_offset * 0.6  # Min temp varies less

        # Apply upper cap to Tmax
        capped_tmax = min(month_tmax, cap)

        # Daily GDD = max(0, (capped_Tmax + Tmin) / 2 - base)
        daily_gdd = max(0, (capped_tmax + month_tmin) / 2 - base_temp)
        annual_gdd += daily_gdd * days_per_month[month]

    return annual_gdd

# Baseline climate values by region (realistic for Ghana)
# Northern regions are hotter and drier, southern coastal regions cooler and wetter
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

# Climate change factors by scenario and period
# These represent multipliers/additions based on CORDEX-Africa projections
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
    """Generate a unique district ID"""
    region_code = region.upper().replace(" ", "_")[:3]
    district_code = district.upper().replace(" ", "_").replace("-", "_")[:5]
    return f"GH-{region_code}-{district_code}"


def get_climate_value(baseline: float, variable: str, scenario: str, period: str) -> float:
    """Calculate projected climate value based on baseline and change factors"""
    if period == "baseline":
        return baseline

    factors = CLIMATE_CHANGE_FACTORS.get(scenario, {}).get(period, {})

    if variable in ["annual_mean_temp", "annual_max_temp", "annual_min_temp"]:
        return round(baseline + factors.get("temp_add", 0), 1)
    elif variable in ["annual_precipitation", "wet_season_precipitation"]:
        return round(baseline * factors.get("precip_mult", 1), 0)
    elif variable == "very_hot_days":
        return round(baseline * factors.get("hot_days_mult", 1), 0)
    elif variable == "dry_days":
        return round(baseline + factors.get("dry_days_add", 0), 0)

    return baseline


def generate_all_districts():
    """Generate list of all districts with IDs"""
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
    """Get full climate data for a district"""
    baseline = REGIONAL_BASELINES.get(region, REGIONAL_BASELINES["Greater Accra"])

    climate_data = {}
    for var in CLIMATE_VARIABLES:
        var_id = var["id"]
        # Skip GDD variables — they are computed on the fly from projected temps
        if var_id in GDD_VARIABLES:
            continue
        var_data = {
            "baseline": get_climate_value(baseline[var_id], var_id, "baseline", "baseline"),
        }
        for scenario in ["rcp45", "rcp85"]:
            for period in ["2030", "2050", "2080"]:
                key = f"{period}_{scenario}"
                var_data[key] = get_climate_value(baseline[var_id], var_id, scenario, period)
        climate_data[var_id] = var_data

    return climate_data
