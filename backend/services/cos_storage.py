"""Tencent COS access using the CVM's attached CAM role credentials."""

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from qcloud_cos import CosConfig, CosS3Client

from config import (
    COS_ACCELERATE,
    COS_BUCKET,
    COS_METADATA_BASE_URL,
    COS_REGION,
    COS_ROLE_NAME,
    COS_SIGNED_URL_EXPIRE_SECONDS,
)


class CosStorage:
    """Small COS adapter that refreshes temporary role credentials on demand."""

    def __init__(self):
        if not COS_BUCKET or not COS_REGION or not COS_ROLE_NAME:
            raise ValueError("COS_BUCKET、COS_REGION 和 COS_ROLE_NAME 必须配置")
        self.bucket = COS_BUCKET
        self.region = COS_REGION
        self.role_name = COS_ROLE_NAME
        self._lock = threading.Lock()
        self._expires_at = 0
        self._origin_client = None
        self._upload_client = None

    def _metadata_credentials(self) -> dict:
        url = (
            f"{COS_METADATA_BASE_URL}/cam/security-credentials/"
            f"{quote(self.role_name, safe='')}"
        )
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("Code") != "Success":
            raise RuntimeError(f"获取 COS 角色临时凭证失败: {payload.get('Message') or payload.get('Code')}")
        return payload

    def _clients(self):
        # Refresh five minutes early, so a multipart request never starts with a
        # credential that is about to expire.
        if self._origin_client is not None and time.time() < self._expires_at - 300:
            return self._origin_client, self._upload_client
        with self._lock:
            if self._origin_client is not None and time.time() < self._expires_at - 300:
                return self._origin_client, self._upload_client
            credentials = self._metadata_credentials()
            common = {
                "Region": self.region,
                "SecretId": credentials["TmpSecretId"],
                "SecretKey": credentials["TmpSecretKey"],
                "Token": credentials["Token"],
                "Scheme": "https",
            }
            self._origin_client = CosS3Client(CosConfig(**common))
            upload_config = dict(common)
            if COS_ACCELERATE:
                upload_config["Endpoint"] = "cos.accelerate.myqcloud.com"
            self._upload_client = CosS3Client(CosConfig(**upload_config))
            self._expires_at = int(credentials.get("ExpiredTime") or (time.time() + 3600))
            return self._origin_client, self._upload_client

    def create_multipart_upload(self, object_key: str, content_type: str) -> str:
        origin, _ = self._clients()
        response = origin.create_multipart_upload(
            Bucket=self.bucket,
            Key=object_key,
            ContentType=content_type or "application/octet-stream",
        )
        return response["UploadId"]

    def sign_upload_part(self, object_key: str, upload_id: str, part_number: int) -> str:
        _, upload = self._clients()
        return upload.get_presigned_url(
            Bucket=self.bucket,
            Key=object_key,
            Method="PUT",
            Expired=COS_SIGNED_URL_EXPIRE_SECONDS,
            Params={"partNumber": str(part_number), "uploadId": upload_id},
        )

    def complete_multipart_upload(self, object_key: str, upload_id: str, parts: list[dict]):
        origin, _ = self._clients()
        return origin.complete_multipart_upload(
            Bucket=self.bucket,
            Key=object_key,
            UploadId=upload_id,
            MultipartUpload={"Part": parts},
        )

    def abort_multipart_upload(self, object_key: str, upload_id: str):
        origin, _ = self._clients()
        return origin.abort_multipart_upload(
            Bucket=self.bucket,
            Key=object_key,
            UploadId=upload_id,
        )

    def download_file(self, object_key: str, destination: Path):
        origin, _ = self._clients()
        destination.parent.mkdir(parents=True, exist_ok=True)
        return origin.download_file(
            Bucket=self.bucket,
            Key=object_key,
            DestFilePath=str(destination),
        )

    def delete_object(self, object_key: str):
        origin, _ = self._clients()
        return origin.delete_object(Bucket=self.bucket, Key=object_key)
