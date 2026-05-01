# Restaurar Taiga en Railway desde backup local

Este documento describe cómo volver a levantar este Taiga en Railway después de borrar el proyecto anterior.

## Backup actual

Backup creado localmente en:

```text
backups/taiga-railway-2026-05-01/
```

Contenido esperado:

```text
taiga-postgres-2026-05-01.dump              # Dump PostgreSQL custom format
taiga-postgres-2026-05-01.pg_restore.list   # Verificación de contenido del dump
postgres-table-row-estimates.txt            # Conteo estimado de tablas al momento del backup
SHA256SUMS.txt                              # Checksum SHA-256 del dump
postgres.variables.json                     # Variables Railway del Postgres anterior (secreto)
taiga-back.variables.json                   # Variables Railway del backend anterior (secreto)
taiga-front.variables.json                  # Variables Railway del frontend anterior
taiga-gateway.variables.json                # Variables Railway del gateway anterior
```

> **Importante:** `backups/` está ignorado por git porque contiene secretos. No lo subas al repo.

## 1. Crear proyecto y servicios nuevos

Desde la raíz del repo:

```bash
railway init --name Taiga
railway add --database postgres
railway add --service taiga-back
railway add --service taiga-front
railway add --service taiga-gateway
```

Si Railway no deja nombrar el Postgres desde CLI, renombralo desde el dashboard a `Postgres`. Si Railway cambia el nombre exacto de algún comando, hacelo desde el dashboard: crear un proyecto `Taiga`, agregar un PostgreSQL y tres servicios vacíos con esos nombres.

## 2. Configurar variables

Primero obtené las variables nuevas del Postgres recién creado:

```bash
railway variables --service Postgres --json > /tmp/new-postgres.variables.json
```

Después configurá `taiga-back` usando las variables antiguas no relacionadas a Railway y apuntando al Postgres nuevo. Ejemplo seguro con Python:

```bash
python3 - <<'PY'
import json, subprocess

old_back = json.load(open('backups/taiga-railway-2026-05-01/taiga-back.variables.json'))
new_pg = json.load(open('/tmp/new-postgres.variables.json'))

keep = {
    'DEFAULT_FROM_EMAIL', 'EMAIL_BACKEND', 'EMAIL_HOST', 'EMAIL_HOST_PASSWORD',
    'EMAIL_HOST_USER', 'EMAIL_PORT', 'EMAIL_USE_SSL', 'EMAIL_USE_TLS',
    'ENABLE_TELEMETRY', 'R2_ACCESS_KEY_ID', 'R2_ACCOUNT_ID', 'R2_BUCKET_NAME',
    'R2_PUBLIC_URL', 'R2_SECRET_ACCESS_KEY', 'TAIGA_SECRET_KEY',
    'TAIGA_SITES_DOMAIN', 'TAIGA_SITES_SCHEME',
}

vars_to_set = {k: old_back[k] for k in keep if k in old_back}
vars_to_set.update({
    'POSTGRES_DB': new_pg.get('PGDATABASE', 'railway'),
    'POSTGRES_HOST': new_pg.get('RAILWAY_TCP_PROXY_DOMAIN'),
    'POSTGRES_PASSWORD': new_pg.get('PGPASSWORD'),
    'POSTGRES_PORT': new_pg.get('RAILWAY_TCP_PROXY_PORT'),
    'POSTGRES_USER': new_pg.get('PGUSER', 'postgres'),
})

cmd = ['railway', 'variable', 'set', '--service', 'taiga-back'] + [f'{k}={v}' for k, v in vars_to_set.items() if v]
subprocess.check_call(cmd)
PY
```

Configurar frontend y gateway:

```bash
python3 - <<'PY'
import json, subprocess

front = json.load(open('backups/taiga-railway-2026-05-01/taiga-front.variables.json'))
gateway = json.load(open('backups/taiga-railway-2026-05-01/taiga-gateway.variables.json'))

if 'TAIGA_URL' in front:
    subprocess.check_call(['railway', 'variable', 'set', '--service', 'taiga-front', f"TAIGA_URL={front['TAIGA_URL']}"])

# Normalmente Railway genera RAILWAY_* automáticamente; no se restauran manualmente.
print('Gateway no necesita variables manuales salvo dominio custom.')
PY
```

## 3. Restaurar PostgreSQL

Usar el dump custom format contra el Postgres nuevo:

```bash
python3 - <<'PY'
import json, pathlib, subprocess

base = pathlib.Path('backups/taiga-railway-2026-05-01').resolve()
pg = json.load(open('/tmp/new-postgres.variables.json'))

subprocess.check_call([
    'docker', 'run', '--rm',
    '-e', f"PGPASSWORD={pg['PGPASSWORD']}",
    '-v', f'{base}:/backup',
    'postgres:17',
    'pg_restore',
    '-h', pg['RAILWAY_TCP_PROXY_DOMAIN'],
    '-p', pg['RAILWAY_TCP_PROXY_PORT'],
    '-U', pg.get('PGUSER', 'postgres'),
    '-d', pg.get('PGDATABASE', 'railway'),
    '--clean', '--if-exists', '--no-owner', '--no-acl',
    '/backup/taiga-postgres-2026-05-01.dump',
])
PY
```

## 4. Desplegar servicios

Este repo no corre local. Todos los deploys son a Railway y `--path-as-root` es obligatorio:

```bash
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d
railway service restart --service taiga-gateway --yes
```

## 5. Dominio

El proyecto anterior usaba:

```text
taiga.xsidian.dev
```

Al recrear el proyecto, reconfigurá el custom domain en `taiga-gateway`. Después verificá que:

- `TAIGA_SITES_DOMAIN` en `taiga-back` coincida con el dominio sin `https://`.
- `TAIGA_URL` en `taiga-front` sea `https://<dominio>`.
- El DNS apunte al nuevo target de Railway.

## 6. Verificación mínima

```bash
railway logs --service taiga-back --lines 200
railway logs --service taiga-gateway --lines 200
curl -I https://taiga.xsidian.dev
curl -I https://taiga.xsidian.dev/api/v1/
```

Si aparece un 504 después de redeployar back/front, reiniciá `taiga-gateway`: nginx cachea IPs internas al arrancar.

## Nota sobre media/R2

Los archivos de usuario están configurados con Cloudflare R2 mediante las variables `R2_*` del backend. Borrar el proyecto Railway no borra el bucket R2. Mientras conserves esas credenciales y el bucket exista, los adjuntos deberían seguir disponibles.
