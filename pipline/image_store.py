"""
MinIO image storage for menu images.
Downloads images from Google and stores them permanently in MinIO.
"""

import io
import uuid
import requests
from minio import Minio
from minio.error import S3Error

from logging_config import get_logger
from config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, MINIO_PUBLIC_URL

logger = get_logger(__name__, service="image_store")


class ImageStore:
    def __init__(self):
        self.client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist, with public read policy."""
        try:
            if not self.client.bucket_exists(MINIO_BUCKET):
                self.client.make_bucket(MINIO_BUCKET)
                # Set public read policy
                import json
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"],
                    }],
                }
                self.client.set_bucket_policy(MINIO_BUCKET, json.dumps(policy))
                logger.info("Created MinIO bucket with public read policy", extra={"extra_data": {"bucket": MINIO_BUCKET}})
        except S3Error as e:
            logger.error("Failed to ensure MinIO bucket", extra={"extra_data": {"error": str(e)}})
            raise

    def download_and_store(self, image_url: str, place_id: str) -> str | None:
        """
        Download image from URL and store in MinIO.
        Returns the public URL of the stored image, or None on failure.
        """
        try:
            resp = requests.get(image_url, timeout=15)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            ext = "jpg"
            if "png" in content_type:
                ext = "png"
            elif "webp" in content_type:
                ext = "webp"

            filename = f"{place_id}/menu/{uuid.uuid4()}.{ext}"
            data = io.BytesIO(resp.content)

            self.client.put_object(
                MINIO_BUCKET,
                filename,
                data,
                length=len(resp.content),
                content_type=content_type,
            )

            public_url = f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{filename}"
            return public_url

        except requests.RequestException as e:
            logger.warning("Failed to download image", extra={"extra_data": {"url": image_url[:100], "error": str(e)}})
            return None
        except S3Error as e:
            logger.warning("Failed to store image in MinIO", extra={"extra_data": {"error": str(e)}})
            return None

    def download_menu_images(self, image_urls: list[str], place_id: str) -> list[dict]:
        """
        Download multiple menu images and store them.
        Returns list of {image_url, original_url} dicts for successfully stored images.
        """
        results = []
        for url in image_urls:
            stored_url = self.download_and_store(url, place_id)
            if stored_url:
                results.append({
                    "image_url": stored_url,
                    "original_url": url,
                })

        if results:
            logger.info(
                "Stored menu images",
                extra={"extra_data": {"place_id": place_id, "stored": len(results), "total": len(image_urls)}}
            )

        return results
