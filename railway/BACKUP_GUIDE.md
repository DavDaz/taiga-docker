# Backup y Migracion desde Railway

Guia para respaldar todo lo que tienes en Railway y restaurarlo en otro lugar.

---

## Que hay que respaldar?

| Dato | Donde esta | Importancia |
|------|-----------|-------------|
| **Base de datos** | Postgres en Railway | CRITICA - contiene todos los proyectos, usuarios, tareas, etc. |
| **Archivos media** | Volumen de taiga-back | ALTA - avatares, adjuntos subidos a tareas |
| **Variables de entorno** | Configuracion de cada servicio | MEDIA - se pueden recrear |
| **Archivos de deploy** | Carpeta `railway/` en tu repo git | YA RESPALDADOS en git |

---

## 1. Backup de la base de datos

### Opcion A: Desde Railway SSH (recomendado)

```bash
# Exportar la base de datos completa
railway ssh --service taiga-back -- \
  bash -c 'pg_dump -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -F c -f /tmp/taiga_backup.dump'

# Descargar el dump a tu maquina local
railway ssh --service taiga-back -- cat /tmp/taiga_backup.dump > taiga_backup.dump
```

> Si `pg_dump` no esta disponible dentro del contenedor, usar Opcion B.

### Opcion B: Desde tu maquina local con la URL publica

```bash
# Usar las credenciales del Postgres de Railway
# (las puedes ver con: railway variables --service Postgres --kv)

pg_dump -h trolley.proxy.rlwy.net \
        -p 53109 \
        -U postgres \
        -d railway \
        -F c \
        -f taiga_backup.dump

# Te pedira el password de Postgres
```

### Opcion C: Dump en formato SQL (mas portable)

```bash
pg_dump -h trolley.proxy.rlwy.net \
        -p 53109 \
        -U postgres \
        -d railway \
        --no-owner \
        --no-privileges \
        -f taiga_backup.sql
```

### Verificar que el backup no esta vacio

```bash
# Para formato custom (.dump)
pg_restore --list taiga_backup.dump | head -20

# Para formato SQL
head -50 taiga_backup.sql
```

---

## 2. Backup de archivos media

Los archivos media (adjuntos, avatares, exportaciones) estan en `/taiga-back/media/` dentro del contenedor.

```bash
# Crear un tar.gz de toda la carpeta media
railway ssh --service taiga-back -- \
  tar czf /tmp/taiga_media.tar.gz -C /taiga-back media/

# Descargar a tu maquina local
railway ssh --service taiga-back -- cat /tmp/taiga_media.tar.gz > taiga_media.tar.gz

# Verificar contenido
tar tzf taiga_media.tar.gz | head -20
```

---

## 3. Backup de variables de entorno

```bash
# Guardar las variables de cada servicio
railway variables --service taiga-back --kv > backup_vars_taiga_back.env
railway variables --service taiga-front --kv > backup_vars_taiga_front.env
railway variables --service taiga-gateway --kv > backup_vars_taiga_gateway.env
railway variables --service Postgres --kv > backup_vars_postgres.env
```

> CUIDADO: estos archivos contienen passwords. No subirlos a git.
> Agregarlos a `.gitignore`:
> ```
> backup_vars_*.env
> taiga_backup.*
> taiga_media.tar.gz
> ```

---

## 4. Script de backup completo

Crea este script para hacer todo de una vez:

```bash
#!/bin/bash
# backup_taiga.sh - Backup completo de Taiga desde Railway

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/taiga_$DATE"
mkdir -p "$BACKUP_DIR"

echo "=== 1/3 Backup de base de datos ==="
pg_dump -h trolley.proxy.rlwy.net \
        -p 53109 \
        -U postgres \
        -d railway \
        -F c \
        -f "$BACKUP_DIR/taiga_db.dump"

echo "=== 2/3 Backup de archivos media ==="
railway ssh --service taiga-back -- \
  tar czf /tmp/taiga_media.tar.gz -C /taiga-back media/ 2>/dev/null
railway ssh --service taiga-back -- \
  cat /tmp/taiga_media.tar.gz > "$BACKUP_DIR/taiga_media.tar.gz"

echo "=== 3/3 Backup de variables ==="
railway variables --service taiga-back --kv > "$BACKUP_DIR/vars_taiga_back.env"
railway variables --service taiga-front --kv > "$BACKUP_DIR/vars_taiga_front.env"
railway variables --service taiga-gateway --kv > "$BACKUP_DIR/vars_taiga_gateway.env"
railway variables --service Postgres --kv > "$BACKUP_DIR/vars_postgres.env"

echo ""
echo "=== Backup completo en: $BACKUP_DIR ==="
ls -lh "$BACKUP_DIR"
```

Uso:
```bash
chmod +x backup_taiga.sh
./backup_taiga.sh
# Te pedira el password de Postgres una vez
```

---

## 5. Restaurar en Docker Compose (tu maquina local o un VPS)

Si quieres dejar Railway y correr Taiga en tu propia maquina o un VPS:

### Paso 1: Levantar Taiga con docker-compose

Usar el `docker-compose.yml` original del repo (el de 9 servicios, o adaptarlo):

```bash
cd taiga-docker

# Configurar el .env
cp .env.example .env
# Editar .env con tus valores

# Levantar solo la base de datos primero
docker compose up -d taiga-db
sleep 10
```

### Paso 2: Restaurar la base de datos

```bash
# Copiar el dump al contenedor de postgres
docker cp taiga_backup.dump taiga-docker-taiga-db-1:/tmp/

# Restaurar (reemplaza la DB existente)
docker exec -it taiga-docker-taiga-db-1 bash -c \
  'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists /tmp/taiga_backup.dump'
```

Si usaste formato SQL:
```bash
docker cp taiga_backup.sql taiga-docker-taiga-db-1:/tmp/
docker exec -it taiga-docker-taiga-db-1 bash -c \
  'psql -U $POSTGRES_USER -d $POSTGRES_DB < /tmp/taiga_backup.sql'
```

### Paso 3: Restaurar archivos media

```bash
# Extraer media en el volumen de taiga-back
docker cp taiga_media.tar.gz taiga-docker-taiga-back-1:/tmp/
docker exec -it taiga-docker-taiga-back-1 bash -c \
  'tar xzf /tmp/taiga_media.tar.gz -C /taiga-back/'
```

### Paso 4: Levantar todo

```bash
docker compose up -d
```

---

## 6. Restaurar en otro Railway (o mismo Railway desde cero)

### Paso 1: Seguir la guia de DEPLOY_GUIDE.md hasta el paso 8

Crear proyecto, Postgres, servicios, desplegar.

### Paso 2: Restaurar la base de datos

```bash
# Obtener credenciales del nuevo Postgres
railway variables --service Postgres --kv

# Restaurar el dump en el nuevo Postgres
pg_restore -h <nuevo_host_tcp> \
           -p <nuevo_puerto> \
           -U postgres \
           -d railway \
           --clean --if-exists \
           taiga_backup.dump
```

### Paso 3: Restaurar archivos media

```bash
# Subir media al nuevo taiga-back
railway ssh --service taiga-back -- mkdir -p /taiga-back/media
cat taiga_media.tar.gz | railway ssh --service taiga-back -- \
  tar xzf - -C /taiga-back/
```

### Paso 4: Continuar con DEPLOY_GUIDE.md desde el paso 9

Generar dominio, actualizar variables, reiniciar gateway.
No necesitas crear superusuario porque ya viene en el backup de la DB.

---

## 7. Restaurar en un VPS barato (alternativas a Railway)

Si quieres salir de Railway por costos, estas son opciones baratas para correr Docker Compose:

| Proveedor | Precio | RAM | Notas |
|-----------|--------|-----|-------|
| Hetzner Cloud | ~$4/mes | 2 GB | Servidores en EU, muy estable |
| DigitalOcean | $6/mes | 1 GB | Droplets, facil de usar |
| Oracle Cloud | GRATIS | 1 GB | Free tier permanente (ARM) |
| Contabo | ~$5/mes | 4 GB | Mucha RAM por el precio |

En cualquiera de estos:
```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh

# Clonar repo
git clone <tu-repo> && cd taiga-docker

# Configurar .env y levantar
cp .env.example .env
# editar .env...
docker compose up -d

# Restaurar DB y media (pasos 5.2 y 5.3 de arriba)
```

---

## Frecuencia recomendada de backups

| Uso | Frecuencia |
|-----|-----------|
| Uso personal, poco cambio | 1 vez por semana |
| Uso activo diario | 1 vez al dia |
| Antes de cualquier cambio en Railway | Siempre |

> Guarda los backups en un lugar diferente a Railway:
> Google Drive, un disco externo, otro servicio cloud, etc.

---

## Resumen rapido

```bash
# BACKUP (hacer periodicamente)
pg_dump -h trolley.proxy.rlwy.net -p 53109 -U postgres -d railway -F c -f taiga_backup.dump
railway ssh --service taiga-back -- tar czf /tmp/m.tar.gz -C /taiga-back media/
railway ssh --service taiga-back -- cat /tmp/m.tar.gz > taiga_media.tar.gz

# RESTAURAR (en docker-compose local)
docker cp taiga_backup.dump contenedor-postgres:/tmp/
docker exec contenedor-postgres pg_restore -U taiga -d taiga --clean --if-exists /tmp/taiga_backup.dump
docker cp taiga_media.tar.gz contenedor-taiga-back:/tmp/
docker exec contenedor-taiga-back tar xzf /tmp/taiga_media.tar.gz -C /taiga-back/
```
