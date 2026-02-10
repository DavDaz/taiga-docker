# Guía: Almacenamiento Persistente con Cloudflare R2

## El Problema

Railway usa **almacenamiento efímero**: cuando redespliegas un servicio, el filesystem del contenedor se destruye y se crea uno nuevo desde cero. Esto significa que cualquier archivo subido por usuarios (adjuntos, avatares, imágenes en tarjetas) **desaparece** en el siguiente deploy.

```
Usuario sube archivo → se guarda en /taiga-back/media/
Deploy nuevo          → contenedor nuevo → /taiga-back/media/ vacío
Usuario intenta abrir → 404 Not Found
```

## La Solución: Cloudflare R2

R2 es el servicio de object storage de Cloudflare, compatible con la API de Amazon S3. Los archivos se guardan en la nube de Cloudflare, **independientemente del ciclo de vida del contenedor**.

**Por qué R2 y no otras opciones:**
- Gratuito hasta 10 GB de almacenamiento
- Sin costo por transferencia de salida (egress), a diferencia de S3
- Compatible con S3 API (usa las mismas librerías de Python)
- Volúmenes de Railway cuestan ~$0.25/GB/mes

### Cómo funciona con Taiga

Sin R2 (problema):
```
Usuario sube PNG → Django guarda en /media/attachments/... (filesystem local)
Browser pide /media/attachments/... → nginx → Django serve → OK (hasta el próximo deploy)
```

Con R2 (solución):
```
Usuario sube PNG → Django sube directamente a R2 bucket
Browser pide adjunto → URL apunta a https://pub-xxx.r2.dev/attachments/... → R2 directo
```

El browser descarga los archivos **directamente desde R2**, sin pasar por nginx ni Django. Más rápido y sin dependencia del estado del contenedor.

---

## Parte 1: Configurar Cloudflare R2

### 1.1 Crear el bucket

1. Ir a [dash.cloudflare.com](https://dash.cloudflare.com)
2. En el menú izquierdo: **R2 Object Storage** → **Create Bucket**
3. Nombre del bucket: `taiga-media` (o el que prefieras)
4. Región: Automatic
5. Click **Create Bucket**

### 1.2 Habilitar acceso público

Por defecto los buckets son privados. Para que los browsers puedan descargar los archivos directamente:

1. Abrir el bucket recién creado
2. Ir a **Settings** → **Public Access**
3. Click **Allow Access** → confirmar
4. Copiar la **Public Bucket URL** que aparece (formato: `https://pub-xxxx.r2.dev`)

> **Nota de seguridad**: Con acceso público, cualquier persona con la URL puede descargar el archivo. Equivalente a la configuración anterior con Django serve. Para datos sensibles se pueden usar presigned URLs, pero requiere cambios adicionales en Taiga.

### 1.3 Crear API Token

1. En Cloudflare Dashboard → Click en tu avatar (arriba a la derecha) → **My Profile**
2. Ir a **API Tokens** → **Create Token**
3. Usar la plantilla **R2 Object Storage: Edit**
4. En "Account Resources": seleccionar tu cuenta
5. En "Permissions": asegurarse de tener **Object Read & Write** en el bucket específico
6. Click **Continue to Summary** → **Create Token**
7. **Copiar el token** — solo se muestra una vez, tiene dos partes:
   - **Access Key ID** (string corto)
   - **Secret Access Key** (string largo)

### 1.4 Obtener Account ID

En el Dashboard de Cloudflare, en la página principal, el **Account ID** aparece en el sidebar derecho (un UUID como `626174269d759f71eabf76895a19a6a9`).

---

## Parte 2: Modificar el Código

Se modificaron 3 archivos en `railway/taiga-back/`:

### 2.1 Dockerfile — Instalar dependencias

**Archivo:** `railway/taiga-back/Dockerfile`

```dockerfile
FROM taigaio/taiga-back:latest

# Añadir django-storages[s3] y boto3 a la línea existente
RUN pip install whitenoise django-storages[s3] boto3

COPY config.py /taiga-back/settings/config.py
COPY urls_railway.py /taiga-back/settings/urls_railway.py
```

**Qué hace cada librería:**
- `django-storages[s3]`: añade backends de storage para Django (S3, GCS, Azure, etc.). Con `[s3]` instala solo las dependencias para S3/R2.
- `boto3`: librería oficial de AWS para Python. R2 es compatible con la API de S3, así que funciona igual.

### 2.2 config.py — Configurar el backend de storage

**Archivo:** `railway/taiga-back/config.py`

Reemplazar la sección de media files con lógica condicional:

```python
# --------------------------------------------------------------------------
# Media files - Cloudflare R2 (si R2_ACCESS_KEY_ID definido) o filesystem
# --------------------------------------------------------------------------
if os.getenv("R2_ACCESS_KEY_ID"):
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    AWS_S3_REGION_NAME = "auto"
    AWS_DEFAULT_ACL = None          # R2 usa public access a nivel de bucket
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_AUTH = False    # URLs públicas sin firma

    _r2_public_url = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
    AWS_S3_CUSTOM_DOMAIN = _r2_public_url.replace("https://", "").replace("http://", "")
    MEDIA_URL = f"{_r2_public_url}/"
    MEDIA_ROOT = ""
else:
    # Fallback: filesystem local (efímero, archivos se pierden en redeploy)
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
```

**Qué hace cada variable:**

| Variable Django | Descripción |
|-----------------|-------------|
| `DEFAULT_FILE_STORAGE` | Le dice a Django qué backend usar para guardar archivos. Cambia de filesystem a S3Boto3. |
| `AWS_S3_ENDPOINT_URL` | URL del servidor S3. R2 tiene su propio endpoint por account ID. |
| `AWS_S3_REGION_NAME = "auto"` | R2 no usa regiones como S3, "auto" es el valor correcto. |
| `AWS_DEFAULT_ACL = None` | No aplicar ACLs por objeto (R2 no las soporta igual que S3). |
| `AWS_QUERYSTRING_AUTH = False` | Genera URLs permanentes sin firma. Con `True` generaría URLs firmadas que expiran. |
| `AWS_S3_CUSTOM_DOMAIN` | Dominio para construir las URLs públicas. Se usa la URL pública del bucket de R2. |
| `MEDIA_URL` | Prefijo de las URLs de media. Ahora apunta a R2 en vez de `/media/`. |
| `MEDIA_ROOT = ""` | Con storage externo no se usa el filesystem local, se deja vacío. |

**Por qué el bloque `if/else`:**
Permite que el código funcione sin R2 (usando filesystem local) si las variables de entorno no están definidas. Útil para desarrollo local o si se quiere desactivar R2 temporalmente.

### 2.3 urls_railway.py — Endpoint /media/ condicional

**Archivo:** `railway/taiga-back/urls_railway.py`

```python
from taiga.urls import *  # noqa
from django.conf import settings

# Solo registrar /media/ si NO se usa almacenamiento externo (R2)
if not getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None):
    from django.urls import re_path
    from django.views.static import serve
    import mimetypes

    def secure_media_serve(request, path):
        """Serves media files with correct Content-Type detection."""
        response = serve(request, path, document_root=settings.MEDIA_ROOT)
        content_type, encoding = mimetypes.guess_type(path)
        if content_type:
            response['Content-Type'] = content_type
        return response

    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', secure_media_serve),
    ]
```

**Por qué este cambio:** Antes, `/media/<archivo>` siempre era servido por Django. Con R2, las URLs de media apuntan directamente a `pub-xxx.r2.dev`, nunca pasan por Django. Si se dejara el endpoint `/media/` activo con R2, simplemente no se usaría, pero es más limpio desactivarlo para evitar confusiones.

---

## Parte 3: Configurar Variables en Railway

Las credenciales se pasan como variables de entorno al servicio `taiga-back`:

```bash
railway variables --set "R2_ACCESS_KEY_ID=<tu-access-key-id>" --service taiga-back
railway variables --set "R2_SECRET_ACCESS_KEY=<tu-secret-access-key>" --service taiga-back
railway variables --set "R2_BUCKET_NAME=taiga-media" --service taiga-back
railway variables --set "R2_ACCOUNT_ID=<tu-account-id>" --service taiga-back
railway variables --set "R2_PUBLIC_URL=https://pub-xxxx.r2.dev" --service taiga-back
```

**Dónde encontrar cada valor:**

| Variable | Dónde obtenerla |
|----------|-----------------|
| `R2_ACCESS_KEY_ID` | Cloudflare → My Profile → API Tokens → el token que creaste |
| `R2_SECRET_ACCESS_KEY` | Mismo lugar que el anterior (solo visible al crear) |
| `R2_BUCKET_NAME` | El nombre que le diste al bucket en el paso 1.1 |
| `R2_ACCOUNT_ID` | Cloudflare Dashboard → Home → sidebar derecho |
| `R2_PUBLIC_URL` | Bucket → Settings → Public Access → la URL que aparece |

---

## Parte 4: Desplegar

```bash
# 1. Redesplegar taiga-back (instala los nuevos paquetes y aplica config.py)
railway up --service taiga-back --path-as-root railway/taiga-back -d

# 2. Redesplegar taiga-gateway (nginx necesita la nueva IP de taiga-back)
railway up --service taiga-gateway --path-as-root railway/taiga-gateway -d
```

> **Por qué redesplegar el gateway:** nginx resuelve el DNS de `taiga-back.railway.internal` al arrancar y lo cachea. Si no se reinicia, sigue enviando tráfico a la IP del contenedor anterior → errores 504.

---

## Verificación

### Comprobar que R2 está activo

```bash
# Ver los logs de arranque de taiga-back
railway logs --service taiga-back

# Buscar que Django cargue sin errores de configuración
```

### Subir un archivo de prueba

1. Ir a Taiga → abrir cualquier tarjeta → adjuntar un archivo PNG
2. Click en el adjunto → debe mostrarse directamente (no 404)
3. Inspeccionar la URL del archivo en el browser → debe apuntar a `https://pub-xxx.r2.dev/...`

### Verificar en Cloudflare

Cloudflare Dashboard → R2 → tu bucket → debe mostrar el archivo recién subido.

### Test de persistencia

```bash
# Redesplegar taiga-back
railway up --service taiga-back --path-as-root railway/taiga-back -d

# Volver a Taiga → el adjunto subido antes debe seguir funcionando
```

---

## Cómo Funciona la Integración (Resumen Visual)

```
ANTES (filesystem efímero):
  Taiga UI → POST /api/attachments → Django → guarda en /media/ (local)
  Taiga UI → GET  /media/archivo   → nginx  → Django serve → 200 OK
  [deploy] → contenedor nuevo → /media/ vacío
  Taiga UI → GET  /media/archivo   → nginx  → Django serve → 404

DESPUÉS (R2 persistente):
  Taiga UI → POST /api/attachments → Django → boto3 → sube a R2 bucket
  Taiga UI → recibe URL: https://pub-xxx.r2.dev/attachments/archivo
  Taiga UI → GET  https://pub-xxx.r2.dev/archivo → R2 → 200 OK
  [deploy] → contenedor nuevo → R2 sin cambios
  Taiga UI → GET  https://pub-xxx.r2.dev/archivo → R2 → 200 OK
```

---

## Solución de Problemas

### Error: `botocore.exceptions.NoCredentialsError`
Las variables `R2_ACCESS_KEY_ID` o `R2_SECRET_ACCESS_KEY` no están definidas o tienen typos. Verificar con:
```bash
railway variables --service taiga-back
```

### Error: `botocore.exceptions.EndpointResolutionError`
El `R2_ACCOUNT_ID` es incorrecto. Verificar en Cloudflare Dashboard → sidebar derecho.

### Los archivos se suben pero dan 403 al abrirlos
El bucket no tiene acceso público habilitado. Ir a Cloudflare → R2 → bucket → Settings → Public Access → Allow Access.

### Las URLs siguen apuntando a `/media/` en vez de R2
Django generó las URLs con el storage anterior (filesystem). Esto pasa si el archivo fue subido antes de configurar R2. Los archivos nuevos tendrán URLs de R2; los anteriores (que ya no existen en el filesystem) darán 404 de todos modos.

### `ImportError: No module named 'storages'`
El Dockerfile no se redesployó correctamente. Verificar que el `pip install django-storages[s3] boto3` está en el Dockerfile y redesplegar con `--path-as-root`.
