from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from accounts.models import ProviderProfile
from config.storage import VercelBlobStorage
from services.models import Service


class Command(BaseCommand):
    help = "Copy existing provider and service images from MEDIA_ROOT to Vercel Blob."

    def handle(self, *args, **options):
        if connections["default"].vendor != "postgresql":
            raise CommandError(
                "This command only updates a PostgreSQL deployment database. "
                "Set DATABASE_URL to the target database first."
            )
        if not isinstance(default_storage, VercelBlobStorage):
            raise CommandError(
                "Set BLOB_READ_WRITE_TOKEN to a Vercel Blob store before running this command."
            )

        local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
        media_root = Path(settings.MEDIA_ROOT).resolve()
        copied = 0
        already_remote = 0
        missing = []

        for model in (ProviderProfile, Service):
            for instance in model.objects.exclude(image="").iterator():
                field_file = instance.image
                name = field_file.name
                if default_storage.is_blob_url(name):
                    already_remote += 1
                    continue

                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise CommandError("A stored media path is invalid; no file was uploaded for it.")

                source_path = (media_root / Path(*relative.parts)).resolve()
                if media_root not in source_path.parents or not source_path.is_file():
                    missing.append(name)
                    continue

                with local_storage.open(name, "rb") as source:
                    upload = File(source, name=name)
                    remote_url = default_storage.upload_existing(name, upload)

                instance.image = remote_url
                instance.save(update_fields=["image"])
                copied += 1

        if missing:
            self.stderr.write(
                self.style.ERROR(
                    f"Copied {copied} image(s); {len(missing)} referenced local file(s) are missing. "
                    "The original files were not deleted. Restore them and run this command again."
                )
            )
            raise CommandError("Media migration is incomplete.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Copied {copied} image(s); skipped {already_remote} already migrated image(s). "
                "Original local files were kept."
            )
        )
