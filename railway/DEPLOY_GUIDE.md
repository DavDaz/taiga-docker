# Taiga Lite en Railway - Guia Completa de Despliegue

Despliegue minimo de Taiga 6.9.0 en Railway con **4 servicios**.

---

## Arquitectura

```
Internet
   |
   v
+------------------+
|  taiga-gateway   |  <-- nginx (unico servicio publico con dominio)
|  (nginx:1.19)    |
+--------+---------+
         |
         |--- / ------------> taiga-front (UI)           :80
         |--- /api/ ---------> taiga-back  (API)         :8000
         |--- /admin/ -------> taiga-back  (API)         :8000
         |--- /static/ ------> taiga-back  (WhiteNoise)  :8000
         |--- /media/ -------> taiga-back  (Django)      :8000
         |
         +---> Postgres (DB gestionada por Railway)      :5432
```

### Que se quito del docker-compose original (9 servicios -> 4)

| Servicio quitado | Por que |
|------------------|---------|
| taiga-events | WebSocket para notificaciones en tiempo real. No necesario para uso individual |
| taiga-events-rabbitmq | RabbitMQ para events. Sin events no se necesita |
| taiga-async | Worker Celery. Las tareas se ejecutan de forma sincrona con `CELERY_TASK_ALWAYS_EAGER` |
| taiga-async-rabbitmq | RabbitMQ para async. Sin worker no se necesita |
| taiga-protected | Proteccion por token de archivos media. Media se sirve directo por Django |

### Problema clave resuelto: sin volumenes compartidos

En Docker Compose, nginx y el backend comparten volumenes para static/media. Railway **NO soporta volumenes compartidos** entre servicios.

**Solucion:**
- **Static files** -> WhiteNoise middleware en Django (sirve estaticos directamente)
- **Media files** -> Django `serve` view via URL pattern custom (`urls_railway.py`)
- **Gateway** -> Proxea `/static/` y `/media/` al backend en vez de servir desde disco local

---

## Archivos necesarios

```
railway/
├── taiga-back/
│   ├── Dockerfile
│   ├── config.py
│   └── urls_railway.py
├── taiga-front/
│   ├── Dockerfile
│   └── 99-disable-events.sh
└── taiga-gateway/
    ├── Dockerfile
    └── taiga.conf.template
```

### `railway/taiga-back/Dockerfile`

```dockerfile
FROM taigaio/taiga-back:latest
RUN pip install whitenoise
COPY config.py /taiga-back/settings/config.py
COPY urls_railway.py /taiga-back/settings/urls_railway.py
```

### `railway/taiga-back/config.py`

Este archivo es **el mas critico**. Sobreescribe la configuracion de `settings/common.py` que viene en la imagen Docker. Sin este archivo:
- La DB apunta a `127.0.0.1` (hardcodeado en common.py)
- Celery intenta conectar a `localhost:5672` (RabbitMQ que no existe)
- Los eventos buscan el modulo `rabbitmq` (que necesita RabbitMQ)

```python
from .common import *  # noqa
import os

# --- Database (OBLIGATORIO: common.py hardcodea HOST=127.0.0.1) ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("POSTGRES_SSLMODE", "disable")},
        "DISABLE_SERVER_SIDE_CURSORS": os.getenv("POSTGRES_DISABLE_SERVER_SIDE_CURSORS", "False") == "True",
    }
}

# --- WhiteNoise (static files sin volumen compartido) ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + [m for m in MIDDLEWARE if m not in (
    "django.middleware.security.SecurityMiddleware",
)]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- URLs custom con media serving ---
ROOT_URLCONF = "settings.urls_railway"

# --- Events via PostgreSQL (NO rabbitmq) ---
# IMPORTANTE: el modulo se llama "postgresql", NO "pg"
EVENTS_PUSH_BACKEND = "taiga.events.backends.postgresql.EventsPushBackend"

# --- Celery DESHABILITADO (sin RabbitMQ) ---
# OBLIGATORIO: common.py define CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
# Sin sobreescribir esto, cada request que dispare una tarea Celery se cuelga 30s
# esperando conectar a localhost:5672 -> WORKER TIMEOUT -> error 500
CELERY_ENABLED = False
CELERY_BROKER_URL = "memory://"
BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# --- Media files (Django los sirve directo) ---
MEDIA_URL = "/media/"
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# --- Taiga settings desde env vars ---
SECRET_KEY = os.getenv("TAIGA_SECRET_KEY")
TAIGA_SITES_SCHEME = os.getenv("TAIGA_SITES_SCHEME", "https")
TAIGA_SITES_DOMAIN = os.getenv("TAIGA_SITES_DOMAIN", "localhost")
FORCE_SCRIPT_NAME = os.getenv("TAIGA_SUBPATH", "")
SITES = {
    "api": {"scheme": TAIGA_SITES_SCHEME, "domain": TAIGA_SITES_DOMAIN, "name": "api"},
    "front": {"scheme": TAIGA_SITES_SCHEME, "domain": f"{TAIGA_SITES_DOMAIN}{FORCE_SCRIPT_NAME}"},
}
ALLOWED_HOSTS = ["*"]

# --- Email ---
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "system@taiga.io")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

# --- Telemetry ---
ENABLE_TELEMETRY = os.getenv("ENABLE_TELEMETRY", "True") == "True"
```

### `railway/taiga-back/urls_railway.py`

```python
from taiga.urls import *  # noqa
from django.urls import re_path
from django.views.static import serve
from django.conf import settings

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
```

### `railway/taiga-front/Dockerfile`

```dockerfile
FROM taigaio/taiga-front:latest
COPY 99-disable-events.sh /docker-entrypoint.d/99-disable-events.sh
RUN chmod +x /docker-entrypoint.d/99-disable-events.sh
```

### `railway/taiga-front/99-disable-events.sh`

Sin esto, el frontend intenta conectar a `wss://dominio/events` en loop, muestra errores en consola y puede bloquear la UI.

```sh
#!/bin/sh
sed -i 's|"eventsUrl":.*|"eventsUrl": null,|' /usr/share/nginx/html/conf.json
echo "Events disabled in conf.json"
```

### `railway/taiga-gateway/Dockerfile`

```dockerfile
FROM nginx:1.19-alpine
COPY taiga.conf.template /etc/nginx/templates/default.conf.template
```

### `railway/taiga-gateway/taiga.conf.template`

Usa `${PORT}` (variable inyectada por Railway) y hostnames internos `*.railway.internal`.

```nginx
server {
    listen ${PORT} default_server;
    client_max_body_size 100M;
    charset utf-8;

    location / {
        proxy_pass http://taiga-front.railway.internal:80/;
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
    }

    location /api/ {
        proxy_pass http://taiga-back.railway.internal:8000/api/;
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
    }

    location /admin/ {
        proxy_pass http://taiga-back.railway.internal:8000/admin/;
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
    }

    location /static/ {
        proxy_pass http://taiga-back.railway.internal:8000/static/;
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
    }

    location /media/ {
        proxy_pass http://taiga-back.railway.internal:8000/media/;
        proxy_pass_header Server;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
        add_header Content-disposition "attachment";
    }
}
```

---

## Paso a paso del despliegue

### 1. Requisitos previos

```bash
npm install -g @railway/cli
railway login
```

### 2. Crear proyecto en Railway

```bash
railway init
# O vincular a uno existente:
railway link -p <PROJECT_ID> -e production
```

### 3. Crear Postgres

```bash
railway add --database postgres
```

Obtener las credenciales (anotar todo):

```bash
railway variables --service Postgres --kv
```

Necesitas:
- `POSTGRES_USER` (normalmente `postgres`)
- `POSTGRES_PASSWORD`
- `POSTGRES_DB` (normalmente `railway`)
- **Host publico TCP proxy**: `trolley.proxy.rlwy.net` + puerto (ej: `53109`)

> **IMPORTANTE**: Usar el host publico TCP proxy, NO `Postgres.railway.internal`.
> El DNS interno puede fallar con `could not translate host name`.

### 4. Generar una clave secreta

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 5. Crear servicio taiga-back

```bash
railway add --service taiga-back \
  --variables "POSTGRES_DB=railway" \
  --variables "POSTGRES_USER=postgres" \
  --variables "POSTGRES_PASSWORD=<password>" \
  --variables "POSTGRES_HOST=<host_tcp_proxy>" \
  --variables "POSTGRES_PORT=<puerto_tcp_proxy>" \
  --variables "TAIGA_SECRET_KEY=<clave_generada>" \
  --variables "TAIGA_SITES_SCHEME=https" \
  --variables "TAIGA_SITES_DOMAIN=PLACEHOLDER" \
  --variables "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend" \
  --variables "EMAIL_HOST=smtp.gmail.com" \
  --variables "EMAIL_PORT=587" \
  --variables "EMAIL_HOST_USER=<tu_gmail>" \
  --variables "EMAIL_HOST_PASSWORD=<app_password>" \
  --variables "DEFAULT_FROM_EMAIL=<tu_gmail>" \
  --variables "EMAIL_USE_TLS=True" \
  --variables "EMAIL_USE_SSL=False" \
  --variables "ENABLE_TELEMETRY=True"
```

> Railway no acepta variables vacias (`KEY=`). Omitir `TAIGA_SUBPATH`.

### 6. Crear servicio taiga-front

```bash
railway add --service taiga-front \
  --variables "TAIGA_URL=PLACEHOLDER"
```

### 7. Crear servicio taiga-gateway

```bash
railway add --service taiga-gateway
```

### 8. Desplegar los 3 servicios

**CRITICO**: Usar `--path-as-root` para que Railway use el Dockerfile de cada subdirectorio. Sin esto, Railway sube el repo completo y usa Railpack (falla).

```bash
cd taiga-docker

railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d
```

Esperar ~2 minutos a que los 3 builds terminen.

### 9. Generar dominio publico

```bash
railway domain --service taiga-gateway
```

Esto genera algo como: `https://taiga-gateway-production.up.railway.app`

### 10. Actualizar variables con el dominio real

```bash
railway variables --set "TAIGA_SITES_DOMAIN=taiga-gateway-production.up.railway.app" \
  --service taiga-back

railway variables --set "TAIGA_URL=https://taiga-gateway-production.up.railway.app" \
  --service taiga-front
```

Esto dispara redeploy automatico. Esperar ~90 segundos.

### 11. Reiniciar gateway

**SIEMPRE reiniciar el gateway** despues de que taiga-back o taiga-front se redesplieguen. Nginx cachea las IPs de los upstreams al arrancar; si un servicio cambia de IP, nginx sigue enviando trafico a la IP vieja -> `504 Gateway Timeout`.

```bash
railway service restart --service taiga-gateway --yes
```

### 12. Crear superusuario

```bash
# Crear usuario
railway ssh --service taiga-back -- \
  python /taiga-back/manage.py createsuperuser \
  --username admin --email tu@email.com --noinput

# Poner password
railway ssh --service taiga-back -- \
  bash -c 'cd /taiga-back && DJANGO_SETTINGS_MODULE=settings.config python -c "
import django; django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(username=\"admin\")
u.set_password(\"tu_password\")
u.save()
print(\"OK\")"'
```

### 13. Verificar

1. Abrir `https://taiga-gateway-production.up.railway.app`
2. Login con admin / tu_password
3. Crear un proyecto de prueba

---

## Dominio custom (opcional)

### Agregar dominio en Railway

```bash
railway domain taiga.tudominio.dev --service taiga-gateway
```

Railway devuelve un registro CNAME, por ejemplo:
```
Type: CNAME   Name: taiga   Value: p5972zk3.up.railway.app
```

### Configurar DNS en Porkbun (u otro proveedor)

Agregar registro DNS:
```
Type:   CNAME
Host:   taiga
Answer: <valor que dio Railway>
TTL:    600
```

Verificar propagacion:
```bash
dig taiga.tudominio.dev CNAME +short
```

### Esperar certificado SSL

Railway genera el certificado SSL automaticamente despues de que el DNS propague. Puede tomar de 5 a 15 minutos. Mientras tanto, usar la URL de Railway default.

### Cambiar a dominio custom

Solo cuando `https://taiga.tudominio.dev` cargue sin error de certificado:

```bash
railway variables --set "TAIGA_SITES_DOMAIN=taiga.tudominio.dev" --service taiga-back
railway variables --set "TAIGA_URL=https://taiga.tudominio.dev" --service taiga-front
# Esperar 90 segundos
railway service restart --service taiga-gateway --yes
```

### Volver a dominio Railway (fallback)

```bash
railway variables --set "TAIGA_SITES_DOMAIN=taiga-gateway-production.up.railway.app" --service taiga-back
railway variables --set "TAIGA_URL=https://taiga-gateway-production.up.railway.app" --service taiga-front
# Esperar 90 segundos
railway service restart --service taiga-gateway --yes
```

> **IMPORTANTE**: Las 2 variables (TAIGA_SITES_DOMAIN y TAIGA_URL) DEBEN coincidir con el dominio que estas usando. Si no coinciden, Taiga muestra: *"Algo no va bien, y la Taiga ha capturado el error"*.

---

## Gmail App Password

Para enviar emails necesitas un **App Password** de Gmail (no la password normal):

1. Tener **2FA activado** en la cuenta de Google
2. Ir a https://myaccount.google.com/apppasswords
3. Generar password para "Correo"
4. Usar esa password (16 caracteres) en `EMAIL_HOST_PASSWORD`

---

## Errores conocidos y soluciones

| Error | Causa | Solucion |
|-------|-------|----------|
| `connection to 127.0.0.1 refused` | `config.py` no sobreescribe DATABASES | El bloque DATABASES en config.py es OBLIGATORIO |
| `WORKER TIMEOUT` + error 500 al crear proyecto | Celery intenta conectar a `localhost:5672` | Agregar `CELERY_BROKER_URL = "memory://"` y `CELERY_TASK_ALWAYS_EAGER = True` |
| `ModuleNotFoundError: taiga.events.backends.pg` | Nombre de modulo incorrecto | Usar `taiga.events.backends.postgresql.EventsPushBackend` (NO `.pg`) |
| `504 Gateway Timeout` | nginx tiene IP vieja cacheada | `railway service restart --service taiga-gateway --yes` |
| `Railpack could not determine how to build` | Falta `--path-as-root` | `railway up --path-as-root railway/<servicio>` |
| `could not translate host name "Postgres.railway.internal"` | DNS interno falla | Usar TCP proxy publico en su lugar |
| `wss://dominio/events` en loop + UI bloqueada | Frontend intenta WebSocket sin servidor | Agregar `99-disable-events.sh` al Dockerfile de taiga-front |
| *"Algo no va bien"* en la UI | TAIGA_SITES_DOMAIN no coincide con URL actual | Las 2 variables deben apuntar al mismo dominio |
| `Invalid variable format: KEY=` | Railway no acepta valores vacios | Omitir la variable |
| Error 404 en `/api/v1/user-storage/...` | Normal: usuario nuevo sin preferencias guardadas | Ignorar, desaparece con el uso |

---

## Costos

Con 4 servicios para un solo usuario: **~$3-5 USD/mes** en el plan Hobby de Railway ($5/mes incluye creditos).

---

## Regla de oro

Cada vez que redespliegues taiga-back o taiga-front:

```bash
# SIEMPRE despues de un redeploy:
railway service restart --service taiga-gateway --yes
```

Nginx no recarga DNS automaticamente. Sin este restart, todo da `504`.
