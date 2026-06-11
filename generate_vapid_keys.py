"""
Générer les clés VAPID pour les push notifications PWA
Exécuter une seule fois : python generate_vapid_keys.py
Copier les clés dans le fichier .env
"""
from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()

print("=" * 60)
print("🔑 CLÉS VAPID GÉNÉRÉES")
print("=" * 60)
print()
print("Copier ces lignes dans votre fichier .env :")
print()
print(f'VAPID_PRIVATE_KEY={vapid.private_pem()}')
print(f'VAPID_PUBLIC_KEY={vapid.public_key_urlsafe()}')
print(f'VAPID_EMAIL=admin@bbl-electra.com')
print()
print("=" * 60)
