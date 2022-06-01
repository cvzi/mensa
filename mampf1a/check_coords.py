import json


with open("mampf1a/canteenDict.json", 'r', encoding='utf8') as f:
    canteens = json.load(f)

latitude = set()
longitude = set()
for ref in canteens:
    if canteens[ref]["latitude"] in latitude:
        print(ref + " lat exists")
    if canteens[ref]["longitude"] in longitude:
        print(ref + " lng exists")

    latitude.add(canteens[ref]["latitude"])
    longitude.add(canteens[ref]["longitude"])

    if not canteens[ref]["name"].startswith(canteens[ref]["city"]):
        print(f"`{canteens[ref]['name']}` in `{canteens[ref]['city']}`")

print("Ok")
