import boto3
from botocore.exceptions import ClientError
from typing import BinaryIO
import uuid
from app.config import settings


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self.bucket_name = settings.s3_bucket_name
        self.cloudfront_domain = settings.cloudfront_domain

    def upload_image(self, image_data: bytes, story_id: str, image_id: str = None) -> str:
        """
        Upload an image to S3 and return the CloudFront URL.
        
        Args:
            image_data: Binary image data
            story_id: UUID of the story
            image_id: Optional UUID for the image (generated if not provided)
            
        Returns:
            CloudFront URL of the uploaded image
        """
        if image_id is None:
            image_id = str(uuid.uuid4())
        
        key = f"stories/{story_id}/{image_id}.png"
        
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=image_data,
            ContentType="image/png",
            ACL="public-read",  # Make images publicly accessible
        )
        
        # Return CloudFront URL if configured, otherwise S3 URL
        if self.cloudfront_domain:
            # Remove trailing slash if present
            domain = self.cloudfront_domain.rstrip("/")
            return f"{domain}/{key}"
        else:
            # Fallback to S3 URL
            return f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"

    def upload_file(self, file_path: str, story_id: str, filename: str = None) -> str:
        """
        Upload a file from local path to S3.
        
        Args:
            file_path: Local file path
            story_id: UUID of the story
            filename: Optional filename (extracted from path if not provided)
            
        Returns:
            CloudFront URL of the uploaded file
        """
        if filename is None:
            filename = file_path.split("/")[-1]
        
        key = f"stories/{story_id}/{filename}"
        
        self.s3_client.upload_file(
            file_path,
            self.bucket_name,
            key,
            ExtraArgs={"ACL": "public-read"},
        )
        
        if self.cloudfront_domain:
            domain = self.cloudfront_domain.rstrip("/")
            return f"{domain}/{key}"
        else:
            return f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"


# Singleton instance
s3_service = S3Service()
