import io
import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)


def _generate_attachment_thumbnail(sender, instance, created, **kwargs):
    """Generate a 300x200 crop thumbnail and upload it to S3/R2.

    Taiga computes the thumbnail_card_url as ``<original>.300x200_q85_crop.jpg``
    but does not upload that file when DEFAULT_FILE_STORAGE is S3.
    This signal fills the gap.
    """
    if not created:
        return

    name = getattr(instance.attached_file, 'name', None)
    if not name:
        return

    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    if not any(name.lower().endswith(ext) for ext in IMAGE_EXTS):
        return

    try:
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        # Read original from S3/R2.
        with instance.attached_file.open('rb') as fh:
            content = fh.read()

        img = Image.open(io.BytesIO(content))
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # Pillow < 10

        # Crop-to-fit at 300x200, quality 85 — matches Taiga's naming convention.
        thumb = ImageOps.fit(img, (300, 200), resample)
        buf = io.BytesIO()
        thumb.save(buf, format='JPEG', quality=85)

        thumb_name = f"{name}.300x200_q85_crop.jpg"
        default_storage.save(thumb_name, ContentFile(buf.getvalue()))
        log.info("Thumbnail uploaded: %s", thumb_name)

    except Exception:
        log.warning(
            "Thumbnail generation failed for %s", name, exc_info=True
        )


class TaigaRailwayConfig(AppConfig):
    name = 'taiga_railway'
    verbose_name = 'Taiga Railway Overrides'

    def ready(self):
        from django.db.models.signals import post_save
        try:
            from taiga.projects.attachments.models import Attachment
            post_save.connect(
                _generate_attachment_thumbnail,
                sender=Attachment,
                dispatch_uid='railway_attachment_thumbnail',
            )
            log.info("Attachment thumbnail signal connected.")
        except ImportError as exc:
            log.warning("Could not connect thumbnail signal: %s", exc)
