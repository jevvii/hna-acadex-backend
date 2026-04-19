from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage

try:
    # django-storages >= 1.14
    from storages.backends.s3 import S3Storage as _S3StorageBase
except ImportError:  # pragma: no cover - compatibility fallback
    try:
        # django-storages < 1.14
        from storages.backends.s3boto3 import S3Boto3Storage as _S3StorageBase
    except ImportError:  # pragma: no cover - local/dev without django-storages installed
        _S3StorageBase = None


class StorjS3Storage(_S3StorageBase or FileSystemStorage):
    def __init__(self, **kwargs):
        from django.conf import settings
        if _S3StorageBase is None:
            raise ImproperlyConfigured(
                "django-storages is required for Storj storage. "
                "Install dependencies from requirements.txt."
            )

        kwargs.setdefault("endpoint_url", settings.STORJ_S3_ENDPOINT_URL)
        kwargs.setdefault("access_key", settings.STORJ_S3_ACCESS_KEY_ID)
        kwargs.setdefault("secret_key", settings.STORJ_S3_SECRET_ACCESS_KEY)
        kwargs.setdefault("bucket_name", settings.STORJ_S3_BUCKET_NAME)
        kwargs.setdefault("region_name", getattr(settings, "STORJ_S3_REGION_NAME", "us1"))
        kwargs.setdefault("custom_domain", getattr(settings, "STORJ_S3_CUSTOM_DOMAIN", None))
        kwargs.setdefault("object_parameters", getattr(settings, "AWS_S3_OBJECT_PARAMETERS", {}))
        kwargs.setdefault("signature_version", getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4"))
        kwargs.setdefault("addressing_style", "path")
        kwargs.setdefault("querystring_expire", 3600)
        super().__init__(**kwargs)

    def path(self, name):
        raise NotImplementedError(
            "StorjS3Storage does not support local filesystem paths. "
            "Use default_storage.open(name) to read the file content."
        )

def get_storage_url(path: str) -> str:
    """Return a URL for a stored file.

    For S3 backends, ``default_storage.url()`` already returns an absolute
    pre-signed URL — calling ``build_absolute_uri`` on it would corrupt it by
    prepending the Django host.  For local filesystem storage the URL is
    relative and can be resolved via the request if needed.
    """
    from django.core.files.storage import default_storage

    url = default_storage.url(path)
    if url.startswith(("http://", "https://")):
        return url
    return url
