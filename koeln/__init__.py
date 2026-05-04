import datetime as dt
import os
import json
import urllib
import logging
from threading import Lock
import string
import re

from requests import RequestException

try:
    from util import StyledLazyBuilder, meta_from_xsl, now_local, xml_str_param
    from koeln.cloudmensa import (
        get_organization_data,
        DEFAULT_API_KEY,
        DEFAULT_DEDUP_FIELDS,
        DEFAULT_ORGANIZATION_ID,
        custom_fields_to_dict,
        fetch_week_menu,
        monday_for,
        build_allergens
    )
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from util import StyledLazyBuilder, meta_from_xsl, now_local, xml_str_param
    from cloudmensa import (
        get_organization_data,
        DEFAULT_API_KEY,
        DEFAULT_DEDUP_FIELDS,
        DEFAULT_ORGANIZATION_ID,
        custom_fields_to_dict,
        fetch_week_menu,
        monday_for,
        build_allergens
    )

metaJson = os.path.join(os.path.dirname(__file__), "koeln.json")

metaTemplateFile = os.path.join(
    os.path.dirname(__file__), "metaTemplate_koeln.xml")


with open(metaJson, 'r', encoding='utf8') as meta_file:
    canteenDict = json.load(meta_file)

sourceUrl = "https://www.kstw.de/speiseplan"

weekSpanDays = 14

genericNames = {
    "beilage",
    "dessert",
    "salat",
    "tagesrestproduktion",
}

defaultFoodIconLabels = {
    "A": "mit Alkohol",
    "F": "mit Fisch",
    "G": "mit Gefluegel",
    "L": "mit Lamm",
    "NL": "Neuland Fleisch",
    "R": "mit Rind",
    "RK": "Rettet die Knolle!",
    "S": "mit Schwein",
    "VGN": "Vegan",
    "VGT": "Vegetarisch",
    "W": "mit Wild",
}

allAllergens = {}

_apiConfigLock = Lock()
_apiConfigCache = None

_menuDataLock = Lock()
_menuDataCache = {}


def _normalize_text(value):
    text = str(value or "").strip().lower()
    return " ".join(text.replace("straße", "strasse").replace("-", " ").split())


def _normalize_category(menuType, dishInfo=None):
    value = str(menuType or "").strip()
    if not value:
        return "Speiseplan"

    if value.lower().startswith("x") and len(value) > 1 and value[1].isalpha():
        value = value[1:]

    tokens = value.replace("_", " ").split()
    while len(tokens) > 1 and tokens[-1].upper() in {"ST", "SOZIAL", "ABENDESSEN", "1", "2"}:
        tokens.pop()

    normalized = " ".join(tokens)

    prefix = "" if not dishInfo or not str(dishInfo).strip() else f"{dishInfo.strip()} - "

    return prefix + (string.capwords(normalized.lower()) if normalized else "Speiseplan")


def _clean_custom_name(name):
    custom = str(name or "").strip()
    for prefix in ("extrabeilage/", "extrabeilagen/"):
        if custom.lower().startswith(prefix):
            custom = custom[len(prefix):].strip()
            break
    return custom


def _pick_meal_name(dish, customFields):
    nameDe = ""
    names = [
        customFields.get("dish_ger_1"),
        customFields.get("dish_ger_2"),
        customFields.get("dish_ger_3"),
        customFields.get("dish_ger_4"),
        customFields.get("dish_ger_5"),
    ]
    for name in names:
        if name is not None:
            nameDe = nameDe + re.sub(r'\(.*?\)', '', name).strip() + ", "
    nameDe = re.sub(r'[,\s]+$', '', nameDe)

    custom = _clean_custom_name(customFields.get("CUSTOM_DPNAME"))

    if not nameDe:
        return custom

    if nameDe.lower() in genericNames and custom and _normalize_text(custom) != _normalize_text(nameDe):
        return custom

    return nameDe


def _parse_price(value):
    if value is None:
        return None
    text = str(value).strip().replace("€", "").replace(",", ".")
    if not text:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _extract_prices(defaultPrice, customFields):
    values = [
        defaultPrice, # default price, seems to be used as students price.
        _parse_price(customFields.get("price_1")), # "Students price"
        _parse_price(customFields.get("price_2")), # "Employees price"
        _parse_price(customFields.get("price_4")), # "Externals price"
        _parse_price(customFields.get("price_3"))  # "Visitors price" -> last so that "price_4" is preferred over "price_3" for openmensa "other" role
    ]
    rolesOrder = ('student', 'student', 'employee', 'other', 'other')

    prices = []
    roles = []
    for role, value in zip(rolesOrder, values):
        if value is not None and role not in roles:
            prices.append(value)
            roles.append(role)

    return prices[0:3], roles[0:3]


def _parse_allergen_notes(rawAllergens):
    raw = str(rawAllergens or "").strip()
    if not raw:
        return []

    if "=" not in raw:
        return [raw]

    notes = []
    for part in raw.split(","):
        token = part.strip()
        if "=" not in token:
            continue

        explanation = token.split("=", 1)[1].strip()
        if "|" in explanation:
            explanation = explanation.split("|", 1)[0].strip()

        if explanation:
            notes.append(explanation)

    return notes if notes else [raw]


def _extract_food_icon_notes(customFields, iconLabels):
    rawIcons = str(customFields.get("food_icon") or "").strip()
    if not rawIcons:
        return []

    notes = []
    for icon in [item.strip() for item in rawIcons.split(",") if item.strip()]:
        notes.append(iconLabels.get(icon, icon))
    return notes


def _deduplicate_items(values):
    seen = set()
    unique = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value)
    return unique


def _get_food_icon_labels(settings):
    labels = dict(defaultFoodIconLabels)
    for icon in settings.get("public_menu_food_icon_legend", []):
        iconId = str(icon.get("icon_id") or "").strip()
        if not iconId:
            continue
        label = str(icon.get("label_de") or icon.get("label_en") or "").strip()
        if label:
            labels[iconId] = label
    return labels


def _get_api_config():
    global _apiConfigCache

    if _apiConfigCache is not None:
        return _apiConfigCache

    with _apiConfigLock:
        if _apiConfigCache is not None:
            return _apiConfigCache

        apiKey = os.environ.get("KOELN_SUPABASE_API_KEY")
        organizationId = os.environ.get("KOELN_ORGANIZATION_ID")
        dedupFields = list(DEFAULT_DEDUP_FIELDS)
        foodIconLabels = dict(defaultFoodIconLabels)

        try:
            org = get_organization_data("kstw")
            settings = org.get("settings") if isinstance(org, dict) else {}

            apiKey = apiKey or org.get("api_key")
            organizationId = organizationId or org.get("organization_id")

            if settings:
                dedupFields = settings.get("public_menu_dedup_custom_fields") or dedupFields
                foodIconLabels = _get_food_icon_labels(settings)
        except (RequestException, RuntimeError, ValueError) as exc:
            logging.warning("Failed to refresh CloudMensa API metadata: %s", exc)

        _apiConfigCache = {
            "api_key": apiKey or DEFAULT_API_KEY,
            "organization_id": organizationId or DEFAULT_ORGANIZATION_ID,
            "dedup_fields": dedupFields,
            "food_icon_labels": foodIconLabels,
        }
        return _apiConfigCache


def _get_week_menu_data(startDate, endDate):
    cfg = _get_api_config()
    cacheKey = (
        startDate.isoformat(),
        endDate.isoformat(),
        cfg["organization_id"],
        tuple(cfg["dedup_fields"] or []),
    )

    with _menuDataLock:
        if cacheKey in _menuDataCache:
            return _menuDataCache[cacheKey]

    menuData = fetch_week_menu(
        start_date=startDate,
        end_date=endDate,
        api_key=cfg["api_key"],
        organization_id=cfg["organization_id"],
        dedup_fields=cfg["dedup_fields"],
    )

    # Allergens explanation mapping is not present for all dishes
    # So we build a global mapping for the week to be able to fill
    # in missing explanations later when processing individual dishes
    build_allergens(menuData, allAllergens)

    with _menuDataLock:
        _menuDataCache[cacheKey] = menuData
    return menuData

def _canteen_screen_set(c):
    return {_normalize_text(x) for x in (c.get("screen_locations") or []) if x}

def _dish_screen_set(d, customFields):
    s = set()
    for scr in (d.get("screens") or []) or []:
        loc = scr.get("location")
        if loc:
            s.add(_normalize_text(loc))
    loc_cf = customFields.get("location")
    if loc_cf:
        s.add(_normalize_text(loc_cf))
    return s
    
def _dish_matches_canteen(dish, canteen, customFields=None, outName=None):
    """Return True if `dish` should be assigned to `canteen`.

    This mirrors the matching logic used by `_add_dish` but is kept
    side-effect free so callers can test assignment without building
    meals.
    """
    if customFields is None:
        customFields = custom_fields_to_dict(dish.get("custom_fields"))

    # Match dishes to canteens using ort_id primarily; fall back to screen locations.
    dishOrtId = str(customFields.get("ort_id") or "").strip()
    canteenOrdId = str(canteen.get("ort_id") or "").strip()

    # If the dish provides an ort_id consider it authoritative: only match
    # canteens that have the same ort_id. This prevents matching to canteens
    # that lack an ort_id (but might share similar screen names)
    if dishOrtId:
        if canteenOrdId != dishOrtId:
            return False
    else:
        # Fallback: match dish screen locations
        canteen_screens = _canteen_screen_set(canteen)
        dish_screens = _dish_screen_set(dish, customFields)
        if not (canteen_screens and dish_screens and (canteen_screens & dish_screens)):
            return False

    mealName = _pick_meal_name(dish, customFields)
    if outName is not None:
        outName.append(mealName)
    if not mealName:
        return False

    return True

def _add_dish(builder, dateValue, canteen, dish):
    customFields = custom_fields_to_dict(dish.get("custom_fields"))
    outName = []
    # Use the predicate to determine whether this dish belongs to the canteen
    if not _dish_matches_canteen(dish, canteen, customFields, outName):
        return False

    mealName = outName[0]

    category = _normalize_category(menuType=customFields.get("menu_type") or dish.get("category"), 
                                   dishInfo=customFields.get("dish_info"))
    prices, roles = _extract_prices(dish.get("price", None), customFields)

    cfg = _get_api_config()
    notes = []
    notes.extend(_parse_allergen_notes(customFields.get("allergens_names")))
    notes.extend(_extract_food_icon_notes(customFields, cfg["food_icon_labels"]))
    notes = _deduplicate_items(notes)

    # Extract and remove allergen hints from the meal name
    if "(" in mealName and ")" in mealName:
        start = mealName.find("(")
        end = mealName.find(")", start)
        if end > start:
            allergenHints = mealName[start + 1:end].strip()
            allergens = [hint.strip() for hint in allergenHints.split(",")]
            allergens_in_notes = []
            allergens_in_notes = [allergen for allergen in allergens if any(allergen in note for note in notes)]
            for allergen in allergens:
                explanation = allAllergens.get(allergen)
                if explanation: 
                    if explanation not in notes:
                        notes.append(explanation),
                    allergens_in_notes.append(allergen)
            # remove the remaining allergen hints from the meal name
            if allergens_in_notes:
                remainingHints = [hint for hint in allergens if hint not in allergens_in_notes]
                if remainingHints:
                    mealName = mealName[:start] + "(" + ", ".join(remainingHints) + ")" + mealName[end + 1:]
                else:
                    mealName = mealName[:start] + mealName[end + 1:]

    builder.addMeal(
        dateValue,
        category,
        mealName,
        notes if notes else None,
        prices if prices else None,
        roles if roles else None,
    )
    return True


def _parse_menu(builder, canteen, days=None):
    today = now_local().date()
    if days is None:
        # Two week range similar to website
        startDate = monday_for(today)
        endDate = startDate + dt.timedelta(days=weekSpanDays - 1)
    else:
        # Days from today
        startDate = today
        endDate = startDate + dt.timedelta(days=days)

    menuData = _get_week_menu_data(startDate, endDate)
    hasMealsByDate = set()
    lastDateWithMeals = None

    for day in menuData:
        dayDate = str(day.get("date") or "").strip()
        if not dayDate:
            continue

        addedForDate = False
        for dish in day.get("dishes", []):
            if _add_dish(builder, dayDate, canteen, dish):
                addedForDate = True

        if addedForDate:
            lastDateWithMeals = dayDate
            if dayDate:
                hasMealsByDate.add(dayDate)

    # mark days without meals as closed until the last date with meals
    # don't mark days after the last date with meals as closed
    for offset in range((endDate - startDate).days + 1):
        current = startDate + dt.timedelta(days=offset)
        isoDate = current.isoformat()

        if isoDate == lastDateWithMeals:
            break

        if isoDate not in hasMealsByDate:
            builder.setDayClosed(isoDate)

class Parser:
    def __init__(self, urlTemplate):
        self.urlTemplate = urlTemplate
        self.meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")
        self.canteens = {key: dict(value) for key, value in canteenDict.items()}

    def verify_menu_usage(self, menuData):
        """Verify which canteens would consume each dish in `menuData`.

        Returns a dict mapping `dish_id` -> list of canteen keys that match it.
        `menuData` should be the list of day dicts returned by `fetch_week_menu`.
        """
        usage = {}
        for day in menuData:
            for dish in day.get("dishes", []):
                dish_id = dish.get("id") or dish.get("dish_id")
                if dish_id is None:
                    # skip unidentifiable
                    continue
                usage.setdefault(dish_id, [])
                for canteen_key, canteen in self.canteens.items():
                    try:
                        if _dish_matches_canteen(dish, canteen):
                            usage[dish_id].append(canteen_key)
                    except Exception:
                        logging.exception("Error matching dish %s against canteen %s", dish_id, canteen_key)
        return usage

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)

    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]

        data = {
            "name": xml_str_param(mensa["name"]),
            "address": xml_str_param("%s, %s %s" % (mensa["strasse"], mensa["plz"], mensa["ort"])),
            "city": xml_str_param(mensa["ort"]),
            "latitude": xml_str_param(mensa["latitude"]),
            "longitude": xml_str_param(mensa["longitude"]),
            "phone": xml_str_param(mensa["phone"]),
            "times": mensa["infokurz"],
            "feed_today": xml_str_param(self.urlTemplate.format(metaOrFeed='today', mensaReference=urllib.parse.quote(ref))),
            "feed_full": xml_str_param(self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": xml_str_param(sourceUrl),
        }

        return meta_from_xsl(self.meta_xslt, data)

    def feed_all(self, ref):
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]
        lazyBuilder = StyledLazyBuilder()
        _parse_menu(lazyBuilder, mensa)
        return lazyBuilder.toXMLFeed()


    def feed_today(self, ref):
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]
        lazyBuilder = StyledLazyBuilder()
        _parse_menu(lazyBuilder, mensa, days=1) # today and tomorrow
        return lazyBuilder.toXMLFeed()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = Parser("http://localhost/{metaOrFeed}/koeln_{mensaReference}.xml")
    # print(p.meta("iwz-deutz"))
    # print(p.feed_today("unimensa"))
    print(p.feed_all("unimensa"))
