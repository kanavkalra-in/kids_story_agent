# API Reference

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All endpoints require API key authentication via Bearer token:

```http
Authorization: Bearer your_api_key_here
```

**Note**: If `API_KEY` is not set in environment, authentication is disabled (development only).

## Rate Limiting

- **Default**: 100 requests per minute per IP address
- **Configurable**: Set via `RATE_LIMIT_PER_MINUTE` environment variable
- **Response**: `429 Too Many Requests` when limit exceeded

## Stories API

### Generate Story

Create a new story generation job.

```http
POST /stories/generate
Content-Type: application/json
Authorization: Bearer {api_key}
```

**Request Body**:
```json
{
  "prompt": "A brave little mouse goes on an adventure to find a magical cheese",
  "age_group": "6-8",
  "num_illustrations": 3,
  "generate_images": true,
  "generate_videos": false,
  "webhook_url": "https://example.com/webhook"  // optional
}
```

**Request Fields**:
- **prompt** (string, required): Story prompt (max 10MB, sanitized to 5000 chars)
- **age_group** (string, required): Target age group (`"3-5"`, `"6-8"`, or `"9-12"`)
- **num_illustrations** (integer, required): Number of images to generate (1-10)
- **generate_images** (boolean, required): Whether to generate images
- **generate_videos** (boolean, required): Whether to generate videos
- **webhook_url** (string, optional): Webhook URL to notify on completion (must be valid, no SSRF)

**Response** (202 Accepted):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Story generation started. Use the job_id to check status."
}
```

**Error Responses**:
- **400 Bad Request**: Invalid age_group, empty prompt, invalid webhook URL
- **401 Unauthorized**: Missing or invalid API key
- **429 Too Many Requests**: Rate limit exceeded

### Get Job Status

Check the status of a story generation job.

```http
GET /stories/jobs/{job_id}
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **job_id** (UUID): Job identifier from generate response

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:31:00Z",
  "error": null
}
```

**Status Values**:
- `pending`: Job is queued, not yet started
- `processing`: Generation in progress
- `pending_review`: Awaiting human approval
- `completed`: Story ready
- `failed`: Generation failed (check `error` field)
- `rejected`: Story rejected during review

**Error Responses**:
- **404 Not Found**: Job not found
- **401 Unauthorized**: Missing or invalid API key

### Get Story

Retrieve a completed story with all details.

```http
GET /stories/{story_id}
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **story_id** (UUID): Story identifier

**Response** (200 OK):
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "The Brave Little Mouse",
  "text": "Once upon a time, there was a brave little mouse...",
  "age_group": "6-8",
  "created_at": "2024-01-15T10:35:00Z",
  "evaluation": {
    "overall_score": 8.05,
    "moral_score": 8.0,
    "theme_appropriateness": 7.5,
    "emotional_positivity": 9.0,
    "age_appropriateness": 8.5,
    "educational_value": 6.0,
    "evaluation_summary": "This story effectively teaches..."
  },
  "guardrail_summary": "All guardrails passed. No violations detected.",
  "guardrail_violations": [],
  "images": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "url": "https://storage.example.com/images/story-123/image-1.png",
      "prompt": "A brave little mouse standing at the edge of a magical forest",
      "description": "Opening scene showing the mouse",
      "display_order": 0
    }
  ],
  "videos": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "url": "https://storage.example.com/videos/story-123/video-1.mp4",
      "prompt": "A brave little mouse walking through a magical forest",
      "description": "Mouse exploring the forest",
      "display_order": 0
    }
  ],
  "review": {
    "decision": "approved",
    "comment": "Looks great!",
    "reviewer_id": "reviewer_123",
    "reviewed_at": "2024-01-15T11:00:00Z"
  }
}
```

**Error Responses**:
- **404 Not Found**: Story not found
- **401 Unauthorized**: Missing or invalid API key

### List Stories

List all completed stories with pagination.

```http
GET /stories?limit=20&offset=0
Authorization: Bearer {api_key}
```

**Query Parameters**:
- **limit** (integer, optional): Number of stories per page (default: 20, max: 100)
- **offset** (integer, optional): Number of stories to skip (default: 0)

**Response** (200 OK):
```json
{
  "stories": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "title": "The Brave Little Mouse",
      "age_group": "6-8",
      "overall_score": 8.05,
      "created_at": "2024-01-15T10:35:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### Get Story Image

Retrieve a story image file.

```http
GET /stories/{story_id}/images/{image_id}
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **story_id** (UUID): Story identifier
- **image_id** (UUID): Image identifier

**Response** (200 OK):
- **Content-Type**: `image/png` or `image/jpeg`
- **Body**: Image file bytes

**Error Responses**:
- **404 Not Found**: Story or image not found
- **401 Unauthorized**: Missing or invalid API key

### Get Story Video

Retrieve a story video file.

```http
GET /stories/{story_id}/videos/{video_id}
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **story_id** (UUID): Story identifier
- **video_id** (UUID): Video identifier

**Response** (200 OK):
- **Content-Type**: `video/mp4`
- **Body**: Video file bytes

**Error Responses**:
- **404 Not Found**: Story or video not found
- **401 Unauthorized**: Missing or invalid API key

## Reviews API

### List Pending Reviews

Get all stories awaiting human review.

```http
GET /reviews/pending?limit=50&offset=0
Authorization: Bearer {api_key}
```

**Query Parameters**:
- **limit** (integer, optional): Number of reviews per page (default: 50, max: 100)
- **offset** (integer, optional): Number of reviews to skip (default: 0)

**Response** (200 OK):
```json
{
  "pending_reviews": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "story_title": "The Brave Little Mouse",
      "age_group": "6-8",
      "prompt": "A brave little mouse goes on an adventure...",
      "overall_eval_score": 8.05,
      "guardrail_passed": true,
      "hard_violation_count": 0,
      "soft_violation_count": 0,
      "num_images": 3,
      "num_videos": 0,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 5,
  "limit": 50,
  "offset": 0
}
```

### Get Review Details

Get full review package for a specific story.

```http
GET /reviews/{job_id}
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **job_id** (UUID): Job identifier

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "story_title": "The Brave Little Mouse",
  "story_text": "Once upon a time, there was a brave little mouse...",
  "age_group": "6-8",
  "prompt": "A brave little mouse goes on an adventure...",
  "evaluation_scores": {
    "overall_score": 8.05,
    "moral_score": 8.0,
    "theme_appropriateness": 7.5,
    "emotional_positivity": 9.0,
    "age_appropriateness": 8.5,
    "educational_value": 6.0,
    "evaluation_summary": "This story effectively teaches..."
  },
  "guardrail_passed": true,
  "guardrail_summary": "All guardrails passed. No violations detected.",
  "guardrail_violations": [],
  "image_urls": [
    "https://storage.example.com/images/story-123/image-1.png",
    "https://storage.example.com/images/story-123/image-2.png"
  ],
  "video_urls": [],
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error Responses**:
- **404 Not Found**: Job not found or not in pending_review status
- **401 Unauthorized**: Missing or invalid API key

### Submit Review Decision

Approve or reject a story (resumes the LangGraph workflow).

```http
POST /reviews/{job_id}/decision
Content-Type: application/json
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **job_id** (UUID): Job identifier

**Request Body**:
```json
{
  "decision": "approved",
  "comment": "Looks great! Approved for publication.",
  "reviewer_id": "reviewer_123"
}
```

**Request Fields**:
- **decision** (string, required): `"approved"` or `"rejected"`
- **comment** (string, optional): Reviewer comment explaining decision
- **reviewer_id** (string, optional): Identifier for the reviewer

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Review decision submitted. Story generation will continue."
}
```

**Error Responses**:
- **400 Bad Request**: Invalid decision value, job already reviewed, or job not in pending_review status
- **404 Not Found**: Job not found
- **401 Unauthorized**: Missing or invalid API key
- **500 Internal Server Error**: Failed to resume graph

### Regenerate Story

Regenerate a rejected story with the same prompt.

```http
POST /reviews/{job_id}/regenerate
Authorization: Bearer {api_key}
```

**Path Parameters**:
- **job_id** (UUID): Job identifier of rejected story

**Response** (202 Accepted):
```json
{
  "job_id": "990e8400-e29b-41d4-a716-446655440004",
  "status": "pending",
  "message": "Story regeneration started. Use the job_id to check status.",
  "original_job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Error Responses**:
- **400 Bad Request**: Job not rejected or already regenerated
- **404 Not Found**: Job not found
- **401 Unauthorized**: Missing or invalid API key

## Health Check

### Health

Check API health status.

```http
GET /health
```

**Response** (200 OK):
```json
{
  "status": "healthy"
}
```

**Note**: No authentication required.

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes**:
- **200 OK**: Request successful
- **202 Accepted**: Request accepted, processing asynchronously
- **400 Bad Request**: Invalid request (validation error, invalid parameters)
- **401 Unauthorized**: Missing or invalid API key
- **404 Not Found**: Resource not found
- **413 Request Entity Too Large**: Request body exceeds size limit
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server error (check logs)

## Webhooks

### Webhook Notification

If `webhook_url` is provided in the generate request, a POST request is sent when the story is completed:

```http
POST {webhook_url}
Content-Type: application/json

{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "story_id": "660e8400-e29b-41d4-a716-446655440001",
  "error": null
}
```

**Webhook Fields**:
- **job_id** (UUID): Job identifier
- **status** (string): Final status (`completed`, `failed`, `rejected`)
- **story_id** (UUID, optional): Story identifier (if completed)
- **error** (string, optional): Error message (if failed)

**Security**: Webhook URLs are validated to prevent SSRF attacks (private/reserved IPs blocked).

## Examples

### Complete Workflow

```bash
# 1. Generate story
curl -X POST http://localhost:8000/api/v1/stories/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "prompt": "A brave little mouse goes on an adventure",
    "age_group": "6-8",
    "num_illustrations": 3,
    "generate_images": true,
    "generate_videos": false
  }'

# Response: {"job_id": "550e8400-...", "status": "pending", ...}

# 2. Check status
curl http://localhost:8000/api/v1/stories/jobs/550e8400-... \
  -H "Authorization: Bearer your_api_key"

# 3. When status is "pending_review", get review details
curl http://localhost:8000/api/v1/reviews/550e8400-... \
  -H "Authorization: Bearer your_api_key"

# 4. Submit review decision
curl -X POST http://localhost:8000/api/v1/reviews/550e8400-.../decision \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "decision": "approved",
    "comment": "Looks great!",
    "reviewer_id": "reviewer_123"
  }'

# 5. Get completed story
curl http://localhost:8000/api/v1/stories/660e8400-... \
  -H "Authorization: Bearer your_api_key"
```

## SDK Examples

### Python

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "your_api_key"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Generate story
response = requests.post(
    f"{BASE_URL}/stories/generate",
    json={
        "prompt": "A brave little mouse goes on an adventure",
        "age_group": "6-8",
        "num_illustrations": 3,
        "generate_images": True,
        "generate_videos": False
    },
    headers=headers
)
job_id = response.json()["job_id"]

# Check status
status_response = requests.get(
    f"{BASE_URL}/stories/jobs/{job_id}",
    headers=headers
)
print(status_response.json()["status"])

# Get story (when completed)
story_response = requests.get(
    f"{BASE_URL}/stories/{story_id}",
    headers=headers
)
story = story_response.json()
print(story["title"])
```

### JavaScript

```javascript
const BASE_URL = "http://localhost:8000/api/v1";
const API_KEY = "your_api_key";

const headers = {
  "Authorization": `Bearer ${API_KEY}`,
  "Content-Type": "application/json"
};

// Generate story
const generateResponse = await fetch(`${BASE_URL}/stories/generate`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    prompt: "A brave little mouse goes on an adventure",
    age_group: "6-8",
    num_illustrations: 3,
    generate_images: true,
    generate_videos: false
  })
});
const { job_id } = await generateResponse.json();

// Check status
const statusResponse = await fetch(`${BASE_URL}/stories/jobs/${job_id}`, {
  headers
});
const status = await statusResponse.json();
console.log(status.status);
```
