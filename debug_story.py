#!/usr/bin/env python3
"""Debug script to check why images weren't generated for a story"""

import sys
from app.db.session import SessionLocal
from app.models.story import Story, StoryJob, StoryImage, JobStatus
import uuid

def debug_story(story_id_str: str):
    """Debug a story by ID"""
    story_id = uuid.UUID(story_id_str)
    
    db = SessionLocal()
    try:
        # Get the story
        story = db.query(Story).filter(Story.id == story_id).first()
        
        if not story:
            print(f"Story {story_id} not found")
            return
        
        print(f"\n=== Story Info ===")
        print(f"Story ID: {story.id}")
        print(f"Title: {story.title}")
        print(f"Age Group: {story.age_group}")
        print(f"Created At: {story.created_at}")
        print(f"Content Length: {len(story.content)} chars")
        
        # Get the job
        job = db.query(StoryJob).filter(StoryJob.id == story.job_id).first()
        if job:
            print(f"\n=== Job Info ===")
            print(f"Job ID: {job.id}")
            print(f"Status: {job.status}")
            print(f"Num Illustrations Requested: {job.num_illustrations}")
            print(f"Error Message: {job.error_message}")
            print(f"Created At: {job.created_at}")
            print(f"Updated At: {job.updated_at}")
        
        # Get images
        images = db.query(StoryImage).filter(StoryImage.story_id == story.id).all()
        print(f"\n=== Images Info ===")
        print(f"Number of images found: {len(images)}")
        
        if len(images) == 0:
            print("\n⚠️  NO IMAGES FOUND!")
            print("\nPossible causes:")
            print("1. Image prompts were not generated (image_prompter_node failed)")
            print("2. Image generation failed for all images (image_generator_node errors)")
            print("3. image_urls or image_metadata were empty when assembler_node ran")
            print("4. Error occurred during image creation in assembler_node")
        else:
            for idx, img in enumerate(images, 1):
                print(f"\nImage {idx}:")
                print(f"  ID: {img.id}")
                print(f"  URL: {img.image_url}")
                print(f"  Display Order: {img.display_order}")
                print(f"  Prompt Used: {img.prompt_used[:100]}..." if len(img.prompt_used) > 100 else f"  Prompt Used: {img.prompt_used}")
                print(f"  Scene Description: {img.scene_description}")
        
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_story.py <story_id>")
        sys.exit(1)
    
    story_id = sys.argv[1]
    debug_story(story_id)
