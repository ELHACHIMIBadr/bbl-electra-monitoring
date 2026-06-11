from fusion_solar_py.client import FusionSolarClient

c = FusionSolarClient("PRIMARIOSBBL", "ELHACHIMIBadr3015", huawei_subdomain="uni001eu5")
ids = c.get_plant_ids()
print(f"Plant ID: {ids[1]}")

data = c.get_plant_stats(ids[1])
last = c.get_last_plant_data(data)

print("\n=== Tous les champs avec valeurs ===")
for k, v in sorted(last.items()):
    print(f"  {k}: {v}")

c.log_out()
