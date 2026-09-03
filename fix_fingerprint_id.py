import re

# 1. app/database/models.py
with open("app/database/models.py", "r") as f:
    models = f.read()
models = re.sub(r'^\s*fingerprint_id: Mapped\[int\].*\n', '', models, flags=re.MULTILINE)
models = re.sub(r'^\s*"fingerprint_id": self\.fingerprint_id,\n', '', models, flags=re.MULTILINE)
with open("app/database/models.py", "w") as f:
    f.write(models)

# 2. app/api/schemas.py
with open("app/api/schemas.py", "r") as f:
    schemas = f.read()
schemas = re.sub(r'^\s*fingerprint_id: int.*\n', '', schemas, flags=re.MULTILINE)
with open("app/api/schemas.py", "w") as f:
    f.write(schemas)

# 3. app/database/repository.py
with open("app/database/repository.py", "r") as f:
    repo = f.read()
repo = re.sub(r'^\s*fingerprint_id: int,\n', '', repo, flags=re.MULTILINE)
repo = re.sub(r'^\s*fingerprint_id=fingerprint_id,\n', '', repo, flags=re.MULTILINE)
with open("app/database/repository.py", "w") as f:
    f.write(repo)

# 4. app/interfaces/repository.py
with open("app/interfaces/repository.py", "r") as f:
    irepo = f.read()
irepo = re.sub(r'^\s*fingerprint_id: int,\n', '', irepo, flags=re.MULTILINE)
irepo = re.sub(r'^\s*fingerprint_id: Biometric fingerprint template ID.*\n', '', irepo, flags=re.MULTILINE)
with open("app/interfaces/repository.py", "w") as f:
    f.write(irepo)

# 5. app/main.py
with open("app/main.py", "r") as f:
    main = f.read()
main = re.sub(r'^\s*fingerprint_id=1,\n', '', main, flags=re.MULTILINE)
with open("app/main.py", "w") as f:
    f.write(main)

# 6. app/core/engine.py
with open("app/core/engine.py", "r") as f:
    engine = f.read()
engine = re.sub(r'^\s*valid_fingerprint_ids:.*$', '', engine, flags=re.MULTILINE)
with open("app/core/engine.py", "w") as f:
    f.write(engine)

# 7. app/api/routes.py
with open("app/api/routes.py", "r") as f:
    routes = f.read()
routes = routes.replace(",\n        ,", ",")
routes = routes.replace(",\n        \n        ,", ",")
routes = re.sub(r',\s*,', ',', routes)
with open("app/api/routes.py", "w") as f:
    f.write(routes)
