import boto3
import uuid
from app.config import settings
from typing import Optional


class S3Service:
    def __init__(self):
        self._s3_client: Optional[object] = None
        self.bucket_name = settings.s3_bucket_name
        self.cloudfront_domain = settings.cloudfront_domain
    
    @property
    def s3_client(self):
        """Lazy-initialize S3 client on first access."""
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
        return self._s3_client

    def _upload_media(
        self, media_data: bytes, key: str, content_type: str
    ) -> str:
        """
        Internal method to upload media to S3 and return the URL.
        
        Args:
            media_data: Binary media data
            key: S3 key (path) for the object
            content_type: MIME type (e.g., "image/png", "video/mp4")
            
        Returns:
            CloudFront URL if configured, otherwise S3 URL
        """
        # Only set ACL if explicitly enabled in settings
        put_kwargs = {
            "Bucket": self.bucket_name,
            "Key": key,
            "Body": media_data,
            "ContentType": content_type,
        }
        if settings.s3_public_read:
            put_kwargs["ACL"] = "public-read"
        
        self.s3_client.put_object(**put_kwargs)
        
        # Return CloudFront URL if configured, otherwise S3 URL
        if self.cloudfront_domain:
            # Remove trailing slash if present
            domain = self.cloudfront_domain.rstrip("/")
            return f"{domain}/{key}"
        else:
            # Fallback to S3 URL
            return f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"

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
        return self._upload_media(image_data, key, "image/png")

    def upload_video(self, video_data: bytes, story_id: str, video_id: str = None) -> str:
        """
        Upload a video to S3 and return the CloudFront URL.
        
        Args:
            video_data: Binary video data
            story_id: UUID of the story
            video_id: Optional UUID for the video (generated if not provided)
            
        Returns:
            CloudFront URL of the uploaded video
        """
        if video_id is None:
            video_id = str(uuid.uuid4())
        
        key = f"videos/stories/{story_id}/{video_id}.mp4"
        return self._upload_media(video_data, key, "video/mp4")



# Singleton instance
s3_service = S3Service()
