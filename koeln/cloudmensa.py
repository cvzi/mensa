"""Client for theCloudMensa API which is used by kstw.de.

Provides utilities to fetch API key and url from the website
and fetch the weekly menu JSON.
"""

import os
import re
import datetime as dt
import requests

WEBSITE_BASE = "https://app.cloudmensa.io/"
API_URL = "https://axxiebkvmfjmiaanviob.supabase.co/rest/v1/rpc/public_get_week_menu"
DEFAULT_API_KEY = os.environ.get("KOELN_CLOUDMENSA_API_KEY")
DEFAULT_ORGANIZATION_ID = os.environ.get(
    "KOELN_ORGANIZATION_ID",
    "4c89c35f-16ac-413f-af04-ec9ffe610f67",
)
DEFAULT_DEDUP_FIELDS = ["name_de", "location", "ort_id", ""]


def _safe_request(url, timeout=10):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response


def get_organization_data(slug):
    """
    Extract URL and API Key from the CloudMensa website
    """

    if slug.startswith("https://"):
        base_url = slug
    else:
        base_url = f"{WEBSITE_BASE}menu/{slug}"

    response = _safe_request(base_url)
    scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", response.text)

    supabase_url = None
    api_key = None

    pattern = r'"(https://[a-zA-Z0-9-]+\.supabase\.co)",\w+="([a-zA-Z0-9\._-]+)"'

    for script_url in scripts:
        full_script_url = script_url if script_url.startswith('http') else f"{WEBSITE_BASE}{script_url}"
        js_content = _safe_request(full_script_url).text
        match = re.search(pattern, js_content)
        if match:
            supabase_url = match.group(1)
            api_key = match.group(2)
            break

    if not supabase_url or not api_key:
        raise RuntimeError("Could not find Supabase configuration in JavaScript files.")

    # Get organization metadata via the API using the extracted URL and API key
    rpc_endpoint = f"{supabase_url}/rest/v1/rpc/public_get_organization_by_slug"
    headers = {
        "apikey": api_key,
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "x-client-info": "supabase-js-web/2.88.0",
    }
    payload = {"p_slug": slug}

    rpc_response = requests.post(rpc_endpoint, headers=headers, json=payload, timeout=10)
    rpc_response.raise_for_status()
    org_data = rpc_response.json()

    if not isinstance(org_data, dict):
        raise RuntimeError("Organization RPC returned an unexpected payload.")

    return {
        "web": base_url,
        "supabase_url": supabase_url,
        "api_key": api_key,
        "organization_id": org_data.get("id"),
        "organization_name": org_data.get("name"),
        "logo_url": org_data.get("logo_url"),
        "settings": org_data.get("settings") or {},
        "organization": org_data,
    }


def monday_for(day):
    return day - dt.timedelta(days=day.weekday())


def parse_date(value):
    return dt.date.fromisoformat(value)


def custom_fields_to_dict(custom_fields):
    fields = {}
    for item in custom_fields or []:
        field_id = item.get("field_id")
        if field_id and field_id not in fields:
            fields[field_id] = item.get("value")
    return fields


def fetch_week_menu(
    start_date,
    end_date,
    api_key=None,
    organization_id=DEFAULT_ORGANIZATION_ID,
    dedup_fields=None,
    timeout=30,
):
    # Prefer explicit `api_key`, then environment variable. Fail fast if
    # no key is available to avoid accidentally using a public fallback.
    api_key = api_key or os.environ.get("KOELN_CLOUDMENSA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "KOELN_CLOUDMENSA_API_KEY is not set. Provide it as an env var or pass `api_key` to fetch_week_menu()`"
        )

    headers = {
        "apikey": api_key,
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    payload = {
        "p_organization_id": organization_id,
        "p_start_date": start_date.isoformat(),
        "p_end_date": end_date.isoformat(),
    }
    if dedup_fields is not None:
        payload["p_dedup_fields"] = dedup_fields

    response = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()

def build_allergens(menu_json, out_dict):
    allergens = {}
    for day in menu_json:
        for dish in day.get("dishes", []):
            for field in dish.get("custom_fields", []):
                if field.get("field_id") == "allergens_names":
                    valueStr = field.get("value", "") # "1=Mit Farbstoff | contains colorants, 2=Mit Konservierungsstoff | contains preservatives, 3=Mit Antioxidationsmittel | contains antioxidants, 5=Geschwefelt | sulphureted, 11w=Enthält Weizen Gluten | wheat, 11g=Enthält Gerste Gluten | barley, 11=Enthält Gluten | Gluten containing cereals, 13=Enthält Eier | contains eggs, 16=Enthält Soja | contains soya, 17=Enthält Milch | contains milk, 18=Enthält Laktose | contains lactose, 19=Enthält Schalenfrüchte (Nüsse) | contains nuts, 19c=Enthält Schalenfrüchte Kaschunuss | cashew, 19m=Enthält Schalenfrüchte Mandeln | almond, 19w=Enthält Schalenfrüchte Walnuss | walnut, 20=Enthält Sellerie | contains celery, 21=Enthält Senf | contains mustard, 22=Enthält Sesamsamen | contains sesame"
                    for part in valueStr.split(","):
                        if "=" in part:
                            key, value = part.split("=", 1)
                            value = value.split("|", 1)[0].strip()
                            allergens[key.strip()] = value

    out_dict.update(allergens)

