from scanner import SHARED_CACHE

print("Available URLs in SHARED_CACHE:")

if not SHARED_CACHE:
    print("⚠️ SHARED_CACHE is empty.")
else:
    for k in SHARED_CACHE.keys():
        print("-", k)