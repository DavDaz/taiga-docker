# Guía de Despliegue de Taiga 6.9.0 en Railway

## Arquitectura

Despliegue mínimo con **4 servicios** (en lugar de los 9 del docker-compose original):

```
Internet
   │
   ▼
┌──────────────────┐
│  taiga-gateway   │  ← nginx (único servicio público)
│  (nginx:1.19)    │
└──────┬───────────┘
       │
       ├──► taiga-front (UI)          → puerto 80
       ├──► taiga-back  (API)         → puerto 8000
       │      ├── /api/
       │      ├── /admin/
       │      ├── /static/ (WhiteNoise)
       │      └── /media/  (Django serve)
       │
       └──► Postgres (DB)            → puerto 5432
```

### Servicios excluidos (no necesarios para 1 usuario):
- **taiga-events** - WebSocket para notificaciones en tiempo real
- **taiga-events-rabbitmq** - RabbitMQ para events
- **taiga-async** - Worker Celery para tareas asíncronas
- **taiga-async-rabbitmq** - RabbitMQ para async
- **taiga-protected** - Protección por token de archivos media
- **Redis** - No lo usa Taiga directamente

### Problema resuelto: Sin volúmenes compartidos

En Docker Compose, nginx y el backend comparten volúmenes para static/media. Railway **NO soporta** volúmenes compartidos entre servicios.

**Solución:**
- **Static files** → WhiteNoise middleware en Django (sirve archivos estáticos directamente)
- **Media files** → Django `serve` view via URL pattern custom
- **Gateway** → Proxea `/static/` y `/media/` al backend en vez de servir archivos locales

---

## Archivos creados

```
railway/
├── taiga-back/
│   ├── Dockerfile          # Imagen base + WhiteNoise + config custom
│   ├── config.py           # Settings Django para Railway
│   └── urls_railway.py     # URLs con media serving
├── taiga-async/            # (opcional, no usado en despliegue mínimo)
│   ├── Dockerfile
│   ├── config.py
│   └── urls_railway.py
├── taiga-front/
│   └── Dockerfile          # Solo FROM taigaio/taiga-front:latest
└── taiga-gateway/
    ├── Dockerfile          # nginx + template
    └── taiga.conf.template # Config nginx con ${PORT} de Railway
```

### Archivo clave: `railway/taiga-back/config.py`

Este archivo es **crítico**. El `settings/common.py` de Taiga hardcodea la base de datos a `127.0.0.1`. Este config lo sobreescribe para leer de variables de entorno:

```python
from .common import *  # noqa
import os

# IMPORTANTE: common.py hardcodea HOST=127.0.0.1, hay que sobreescribir
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

# WhiteNoise para servir static files sin volumen compartido
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + [m for m in MIDDLEWARE if m not in (
    "django.middleware.security.SecurityMiddleware",
)]

# URLs custom con media serving
ROOT_URLCONF = "settings.urls_railway"

# Taiga settings desde env vars
SECRET_KEY = os.getenv("TAIGA_SECRET_KEY")
SITES = { ... }  # lee de TAIGA_SITES_SCHEME y TAIGA_SITES_DOMAIN
ALLOWED_HOSTS = ["*"]
# Email, telemetry, etc.
```

---

## Pasos de despliegue

### 1. Prerequisitos

- Cuenta en [Railway](https://railway.app)
- Railway CLI instalado: `npm install -g @railway/cli`
- Login: `railway login`

### 2. Crear proyecto y Postgres

```bash
# Crear proyecto (o usar uno existente)
railway init

# Agregar Postgres
railway add --database postgres
```

Anotar las credenciales de Postgres:
- `POSTGRES_USER` (normalmente `postgres`)
- `POSTGRES_PASSWORD`
- `POSTGRES_DB` (normalmente `railway`)
- Host público: `trolley.proxy.rlwy.net:XXXXX`

### 3. Vincular proyecto

```bash
cd taiga-docker
railway link -p <PROJECT_ID> -e production
```

### 4. Crear servicios

```bash
# taiga-back
railway add --service taiga-back \
  --variables "POSTGRES_DB=railway" \
  --variables "POSTGRES_USER=postgres" \
  --variables "POSTGRES_PASSWORD=<password_de_postgres>" \
  --variables "POSTGRES_HOST=<host_publico_tcp_proxy>" \
  --variables "POSTGRES_PORT=<puerto_tcp_proxy>" \
  --variables "TAIGA_SECRET_KEY=<clave_secreta_generada>" \
  --variables "TAIGA_SITES_SCHEME=https" \
  --variables "TAIGA_SITES_DOMAIN=PLACEHOLDER" \
  --variables "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend" \
  --variables "EMAIL_HOST=smtp.gmail.com" \
  --variables "EMAIL_PORT=587" \
  --variables "EMAIL_HOST_USER=<tu_gmail>" \
  --variables "EMAIL_HOST_PASSWORD=<app_password_gmail>" \
  --variables "DEFAULT_FROM_EMAIL=<tu_gmail>" \
  --variables "EMAIL_USE_TLS=True" \
  --variables "EMAIL_USE_SSL=False" \
  --variables "ENABLE_TELEMETRY=True"

# taiga-front
railway add --service taiga-front \
  --variables "TAIGA_URL=PLACEHOLDER"

# taiga-gateway (sin variables)
railway add --service taiga-gateway
```

> **Nota:** Railway no acepta variables vacías (`KEY=`). Omitir `TAIGA_SUBPATH` y `TAIGA_WEBSOCKETS_URL`.

### 5. Desplegar servicios

**Importante:** Usar `--path-as-root` para que Railway use el Dockerfile de cada subdirectorio:

```bash
cd taiga-docker

# Desplegar los 3 servicios
railway up --service taiga-back --path-as-root railway/taiga-back -d
railway up --service taiga-front --path-as-root railway/taiga-front -d
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d
```

> Sin `--path-as-root`, Railway sube el directorio raíz del repo y Railpack no encuentra los Dockerfiles.

### 6. Generar dominio público

```bash
railway domain --service taiga-gateway
```

Esto genera una URL tipo: `https://taiga-gateway-production.up.railway.app`

### 7. Actualizar variables con el dominio real

```bash
# En taiga-back
railway variables --set "TAIGA_SITES_DOMAIN=taiga-gateway-production.up.railway.app" \
  --service taiga-back

# En taiga-front
railway variables --set "TAIGA_URL=https://taiga-gateway-production.up.railway.app" \
  --service taiga-front
```

Esto dispara un redeploy automático de ambos servicios.

### 8. Reiniciar gateway

Después de que taiga-back esté corriendo, reiniciar el gateway para que nginx resuelva el DNS interno:

```bash
railway service restart --service taiga-gateway --yes
```

### 9. Crear superusuario

```bash
# Crear usuario
railway ssh --service taiga-back -- \
  python /taiga-back/manage.py createsuperuser \
  --username admin --email tu@email.com --noinput

# Establecer contraseña
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

### 10. Verificar

1. Abrir `https://taiga-gateway-production.up.railway.app`
2. Login con admin / tu_password
3. Crear un proyecto de prueba
4. Verificar que `/api/v1/` responde

---

## Errores comunes y soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `connection to 127.0.0.1 refused` | `config.py` no sobreescribe DATABASES | Agregar bloque DATABASES con `os.getenv("POSTGRES_HOST")` |
| `Railpack could not determine how to build` | Falta `--path-as-root` en `railway up` | Usar `railway up --path-as-root railway/<servicio>` |
| `host not found in upstream` en nginx | Gateway arrancó antes que el backend | Reiniciar gateway: `railway service restart --service taiga-gateway --yes` |
| `could not translate host name "Postgres.railway.internal"` | DNS interno no resuelve (mayúscula) | Usar TCP proxy público en su lugar |
| `Invalid variable format: KEY=` | Railway no acepta valores vacíos | Omitir la variable o poner un valor placeholder |

---

## Gmail App Password

Para enviar emails desde Taiga necesitas un **App Password** de Gmail:

1. Tener **2FA activado** en tu cuenta de Google
2. Ir a https://myaccount.google.com/apppasswords
3. Generar contraseña para "Correo"
4. Usar esa contraseña (16 caracteres) en `EMAIL_HOST_PASSWORD`

---

## Costos estimados

Con 4 servicios para un solo usuario: **~$3-5 USD/mes** en el plan Hobby de Railway ($5/mes incluye créditos).
