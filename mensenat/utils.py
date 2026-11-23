#!/usr/bin/env python3

import argparse
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus

import json5
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport


BASE_URL = "https://www.mensen.at"
COUNTRY = "Österreich"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_FILENAME = SCRIPT_DIR / "canteenDict.json"
DEFAULT_OUTPUT_FILENAME = SCRIPT_DIR / "canteenDict.graphql_merged.json5"
DEFAULT_SUMMARY_FILENAME = SCRIPT_DIR / "canteen_sync_summary.json"
DEFAULT_PR_BODY_FILENAME = SCRIPT_DIR / "canteen_sync_pr_body.md"
DAY_ORDER = [
    ("monday", "Mo"),
    ("tuesday", "Di"),
    ("wednesday", "Mi"),
    ("thursday", "Do"),
    ("friday", "Fr"),
    ("saturday", "Sa"),
    ("sunday", "So"),
]
CITY_REFERENCE_PREFIXES = {
    "Wien": "Wi",
    "Linz": "Linz",
    "Graz": "Graz",
    "Innsbruck": "Inn",
    "Salzburg": "Salz",
    "St. Pölten": "Stp",
    "Sankt Pölten": "Stp",
    "Leoben": "Leoben",
    "Krems": "Krems",
    "Kapfenberg": "Kapfenberg",
    "Klagenfurt": "Klagenfurt",
    "Baden": "Baden",
    "Eisenstadt": "Eisenstadt",
    "Maria Enzersdorf": "MariaEnzersdorf",
}

LOCATIONS_QUERY = gql(
    """query Locations {
  locations(
    first: 10000
  ) {
    edges {
      node {
        databaseId
        locationData {
          address {
            city
            line {
              one
              two
            }
            street {
              name
              number
            }
            zipCode
          }
          noticeLocation
        }
        locationServices {
          nodes {
            locationServiceData {
              iconslug
            }
            name
          }
        }
        openingHours {
          monday
          tuesday
          thursday
          wednesday
          friday
          saturday
          sunday
          notice
        }
        slug
        title
        uri
      }
    }
  }
}"""
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync mensen.at canteens from GraphQL into the local JSON5 file."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_FILENAME),
        help="Existing JSON5 file to merge against.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_FILENAME),
        help="Output JSON5 file to write.",
    )
    parser.add_argument(
        "--summary-json",
        default=str(DEFAULT_SUMMARY_FILENAME),
        help="Machine-readable summary file for automation.",
    )
    parser.add_argument(
        "--pr-body",
        default=str(DEFAULT_PR_BODY_FILENAME),
        help="Markdown pull request body to write.",
    )
    return parser.parse_args()


def compact_whitespace(text):
    return " ".join((text or "").split())


def normalize_source(source):
    return compact_whitespace(source).rstrip("/")


def slug_to_source(uri):
    cleaned_uri = (uri or "").strip()
    if not cleaned_uri:
        return ""
    return f"{BASE_URL}{cleaned_uri.rstrip('/')}"


def format_city(city):
    city = compact_whitespace(city)
    if not city:
        return ""
    return f"{city} ({COUNTRY})"


def format_address(address):
    if not address:
        return ""

    street = address.get("street") or {}
    street_name = compact_whitespace(street.get("name"))
    street_number = compact_whitespace(street.get("number"))
    zip_code = compact_whitespace(address.get("zipCode"))
    city = compact_whitespace(address.get("city"))

    street_part = " ".join(part for part in [street_name, street_number] if part)
    city_part = " ".join(part for part in [zip_code, city] if part)
    address_part = ", ".join(part for part in [street_part, city_part] if part)

    if not address_part:
        return ""
    return f"{address_part} ({COUNTRY})"


def normalize_reference_part(text):
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[A-Za-z0-9]+", ascii_text)
    return "".join(word[:1].upper() + word[1:] for word in words)


def build_reference(node):
    address = (node.get("locationData") or {}).get("address") or {}
    city = compact_whitespace(address.get("city"))
    prefix = CITY_REFERENCE_PREFIXES.get(city, normalize_reference_part(city))

    title = compact_whitespace(node.get("title"))
    city_words = {
        normalize_reference_part(part)
        for part in city.replace("-", " ").split()
        if normalize_reference_part(part)
    }
    stopwords = {"M", "Cafe"} | city_words

    title_words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", title)
    filtered_words = [
        normalize_reference_part(word)
        for word in title_words
        if normalize_reference_part(word) and normalize_reference_part(word) not in stopwords
    ]
    suffix = "".join(filtered_words) or normalize_reference_part(node.get("slug"))
    return f"{prefix}{suffix}"


SLOT_PATTERN = re.compile(
    r"(\d{1,2})[:.](\d{2})\s*(?:Uhr)?\s*[-–]\s*(\d{1,2})[:.](\d{2})\s*(?:Uhr)?",
    flags=re.IGNORECASE,
)


def normalize_slot(slot):
    """
    Bring one opening-hours slot into the form "HH:MM-HH:MM".

    Most locations send "11:30-14:00", but the field is typed in by hand
    per location and some write "11:30 - 14:00", "8.00-15.00 Uhr" or free
    text. Returns None for anything that is not a plain time range.
    """
    match = SLOT_PATTERN.fullmatch(compact_whitespace(slot))
    if not match:
        return None
    h1, m1, h2, m2 = (int(x) for x in match.groups())
    if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
        return None
    return "%02d:%02d-%02d:%02d" % (h1, m1, h2, m2)


def irregular_slots(opening_hours):
    """Slots that normalize_slot cannot read, as "Mo: '...'" for the report."""
    found = []
    for key, label in DAY_ORDER:
        for slot in (opening_hours or {}).get(key) or []:
            if compact_whitespace(slot) and normalize_slot(slot) is None:
                found.append(f"{label}: {compact_whitespace(slot)!r}")
    return found


def format_times(opening_hours):
    if not opening_hours:
        return ""

    groups = []
    current_labels = []
    current_value = None

    for key, label in DAY_ORDER:
        slots = opening_hours.get(key) or []
        value = ", ".join(
            normalize_slot(slot) or compact_whitespace(slot)
            for slot in slots if compact_whitespace(slot)
        )

        if not value:
            if current_labels:
                groups.append((current_labels, current_value))
                current_labels = []
                current_value = None
            continue

        if value == current_value:
            current_labels.append(label)
            continue

        if current_labels:
            groups.append((current_labels, current_value))
        current_labels = [label]
        current_value = value

    if current_labels:
        groups.append((current_labels, current_value))

    lines = []
    for labels, value in groups:
        day_label = labels[0] if len(labels) == 1 else f"{labels[0]}-{labels[-1]}"
        lines.append(f"{day_label} {value} Uhr")
    return "\n".join(lines)


def build_name(node):
    address = (node.get("locationData") or {}).get("address") or {}
    city = compact_whitespace(address.get("city"))
    title = compact_whitespace(node.get("title"))
    return ", ".join(part for part in [city, title] if part)


def format_canteen(node, existing=None):
    location_data = node.get("locationData") or {}
    address = location_data.get("address") or {}
    formatted = {
        "reference": existing.get("reference") if existing else build_reference(node),
        "name": existing.get("name") if existing else build_name(node),
        "city": existing.get("city") if existing else format_city(address.get("city")),
        "latitude": existing.get("latitude") if existing else "",
        "longitude": existing.get("longitude") if existing else "",
        "address": existing.get("address") if existing else format_address(address),
        "phone": existing.get("phone") if existing else "",
        "times": existing.get("times") if existing else format_times(node.get("openingHours")),
        "source": existing.get("source") if existing else slug_to_source(node.get("uri")),
    }
    if existing and "openmensa" in existing:
        formatted["openmensa"] = existing["openmensa"]
    return formatted


def build_existing_source_index(canteen_dict):
    index = {}
    for key, canteen in canteen_dict.items():
        source = normalize_source(canteen.get("source", ""))
        if source:
            index[source] = (key, canteen)
    return index


def build_osm_search_url(address):
    query = compact_whitespace(address).replace(f" ({COUNTRY})", "")
    return f"https://www.openstreetmap.org/search?query={quote_plus(query)}"


def json5_literal(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def serialize_canteens_json5(canteens_by_key, new_keys):
    ordered_keys = list(canteens_by_key.keys())
    lines = ["{"]

    for index, key in enumerate(ordered_keys):
        canteen = canteens_by_key[key]
        lines.append(f'  {json.dumps(key)}: {{')

        field_items = list(canteen.items())
        for field_index, (field_name, value) in enumerate(field_items):
            suffix = "," if field_index < len(field_items) - 1 else ""
            line = f'    {json.dumps(field_name)}: {json5_literal(value)}{suffix}'
            if key in new_keys and field_name == "longitude":
                line += f" // {build_osm_search_url(canteen.get('address', ''))}"
            lines.append(line)

        object_suffix = "," if index < len(ordered_keys) - 1 else ""
        lines.append(f"  }}{object_suffix}")

    lines.append("}")
    return "\n".join(lines) + "\n"


def load_existing_canteens(path):
    with open(path, "r", encoding="utf8") as f:
        return json5.load(f)


def fetch_graphql_nodes():
    transport = RequestsHTTPTransport(url="https://backend.mensen.at/api")
    client = Client(
        transport=transport,
        fetch_schema_from_transport=False,
    )
    result = client.execute(LOCATIONS_QUERY, variable_values={})
    return [edge["node"] for edge in result["locations"]["edges"]]


def build_summary(added_entries, removed_keys, kept_count, output_path,
                  times_changed=None, times_irregular=None):
    """Collect the result of a sync run for the summary JSON and the PR body."""
    return {
        "added_count": len(added_entries),
        "removed_count": len(removed_keys),
        "kept_count": kept_count,
        "output_path": str(output_path),
        "added": added_entries,
        "removed_keys": removed_keys,
        "times_changed": times_changed or [],
        "times_irregular": times_irregular or [],
    }


def write_summary_json(path, summary):
    with open(path, "w", encoding="utf8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_pr_body(summary):
    lines = [
        "## Summary",
        "",
        f"- Added {summary['added_count']} new mensen.at canteen(s)",
        f"- Removed {summary['removed_count']} canteen(s) no longer present in GraphQL",
    ]

    if summary["added"]:
        lines.extend(
            [
                "",
                "## Coordinate follow-up",
                "",
                "The new canteens were added with empty `latitude` and `longitude` fields.",
                "Please look up the coordinates manually and replace the placeholders before merging.",
                "",
                "## New Canteens",
                "",
            ]
        )
        for canteen in summary["added"]:
            lines.append(f"- `{canteen['key']}` - {canteen['name']}")
            lines.append(f"  - Address: {canteen['address']}")
            lines.append(f"  - Source: {canteen['source']}")
            lines.append(f"  - OpenStreetMap search: {canteen['osm_url']}")
        lines.append("")
    else:
        lines.extend(
            [
                "",
                "## Coordinate follow-up",
                "",
                "No new canteens were added in this run, so there are no new coordinate placeholders to fill.",
                "",
            ]
        )

    if summary.get("times_changed"):
        lines.extend(["", "## Opening hours updated from GraphQL", ""])
        for change in summary["times_changed"]:
            lines.append(f"- `{change['key']}` - {change['name']}")
            lines.append(f"  - before: `{change['before']!r}`")
            lines.append(f"  - now: `{change['after']!r}`")

    if summary.get("times_irregular"):
        lines.extend(
            [
                "",
                "## Opening hours left unchanged",
                "",
                "These locations enter their hours in a form that is not a plain time range,",
                "so the existing value was kept. Please check them by hand.",
                "",
            ]
        )
        for entry in summary["times_irregular"]:
            lines.append(f"- `{entry['key']}` - {entry['name']}: " + ", ".join(entry["slots"]))

    return "\n".join(lines).rstrip() + "\n"


def write_pr_body(path, summary):
    with open(path, "w", encoding="utf8") as f:
        f.write(build_pr_body(summary))


def sync_canteens(existing_canteens, graphql_nodes):
    existing_by_source = build_existing_source_index(existing_canteens)
    graphql_nodes_by_source = []
    graphql_sources = set()

    for node in graphql_nodes:
        source = normalize_source(slug_to_source(node["uri"]))
        graphql_nodes_by_source.append((source, node))
        graphql_sources.add(source)

    merged_canteens = {}
    new_keys = set()
    removed_keys = []
    added_entries = []

    nodes_by_source = dict(graphql_nodes_by_source)
    times_changed = []
    times_irregular = []

    for key, canteen in existing_canteens.items():
        source = normalize_source(canteen.get("source", ""))
        if source not in graphql_sources:
            removed_keys.append(key)
            continue

        # Opening hours used to be taken over only for new canteens, so a
        # hand-entered value never changed again. The GraphQL value is the
        # one the location maintains itself; it wins unless it cannot be read.
        opening_hours = nodes_by_source[source].get("openingHours")
        irregular = irregular_slots(opening_hours)
        api_times = format_times(opening_hours)
        if irregular:
            times_irregular.append({"key": key, "name": canteen.get("name", ""), "slots": irregular})
        elif api_times and api_times != canteen.get("times"):
            times_changed.append({"key": key, "name": canteen.get("name", ""),
                                  "before": canteen.get("times", ""), "after": api_times})
            canteen = dict(canteen, times=api_times)
        merged_canteens[key] = canteen

    for source, node in graphql_nodes_by_source:
        existing_entry = existing_by_source.get(source)
        if existing_entry:
            continue

        new_key = f"databaseId:{node['databaseId']}"
        new_canteen = format_canteen(node)
        merged_canteens[new_key] = new_canteen
        new_keys.add(new_key)
        added_entries.append(
            {
                "key": new_key,
                "reference": new_canteen["reference"],
                "name": new_canteen["name"],
                "address": new_canteen["address"],
                "source": new_canteen["source"],
                "osm_url": build_osm_search_url(new_canteen["address"]),
            }
        )

    return merged_canteens, new_keys, added_entries, removed_keys, times_changed, times_irregular


def main():
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary_json)
    pr_body_path = Path(args.pr_body)

    existing_canteens = load_existing_canteens(input_path)
    graphql_nodes = fetch_graphql_nodes()
    merged_canteens, new_keys, added_entries, removed_keys, times_changed, times_irregular = sync_canteens(
        existing_canteens, graphql_nodes
    )

    output_text = serialize_canteens_json5(merged_canteens, new_keys)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf8") as f:
        f.write(output_text)

    summary = build_summary(
        added_entries=added_entries,
        removed_keys=removed_keys,
        kept_count=len(merged_canteens) - len(new_keys),
        output_path=output_path,
        times_changed=times_changed,
        times_irregular=times_irregular,
    )
    write_summary_json(summary_path, summary)
    write_pr_body(pr_body_path, summary)

    print(f"Wrote {output_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {pr_body_path}")
    print(f"Kept {summary['kept_count']} existing canteens")
    print(f"Added {summary['added_count']} new canteens")
    print(f"Removed {summary['removed_count']} canteens no longer present in GraphQL")
    print(f"Updated opening hours of {len(times_changed)} canteens")
    print(f"Kept opening hours of {len(times_irregular)} canteens with irregular entries")

    if added_entries:
        print("New keys:")
        for canteen in added_entries:
            print(f"  {canteen['key']}")

    if removed_keys:
        print("Removed keys:")
        for key in removed_keys:
            print(f"  {key}")


if __name__ == "__main__":
    main()
