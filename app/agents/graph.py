from langgraph.graph import StateGraph, END
from app.agents.state import StoryState
from app.agents.story_writer import story_writer_node
from app.agents.image_prompter import image_prompter_node
from app.agents.image_generator import image_generator_node
from app.agents.assembler import assembler_node
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def create_single_image_generator_node(image_index: int):
    """
    Create a node function for generating a single image at a specific index.
    This will be used to create multiple parallel nodes dynamically.
    """
    def image_generator_node_for_index(state: StoryState) -> Dict:
        """Generate a single image based on the image_index"""
        image_prompts = state.get("image_prompts", [])
        original_metadata = state.get("image_metadata", [])
        job_id = state.get("job_id", "unknown")
        
        # Check if we have a prompt for this index
        if image_index >= len(image_prompts):
            logger.warning(f"Job {job_id}: No prompt for image index {image_index}, skipping")
            return {}
        
        prompt = image_prompts[image_index]
        logger.info(f"Job {job_id}: Generating image {image_index + 1}/{len(image_prompts)} in parallel node")
        
        # Generate the image
        result = image_generator_node(state, prompt, image_index)
        
        if "error" in result:
            error_msg = result.get('error', 'Unknown error')
            logger.warning(f"Job {job_id}: Image {image_index + 1} generation failed: {error_msg}")
            # Return empty result but don't fail the entire workflow
            return {}
        
        # Merge with original metadata to preserve description
        gen_metadata = result.get("image_metadata", [])
        image_urls = result.get("image_urls", [])
        
        if gen_metadata and image_index < len(original_metadata):
            merged_meta = {
                **original_metadata[image_index],  # Preserve description and prompt from prompter
                "s3_url": gen_metadata[0].get("s3_url", ""),
                "image_index": image_index,
            }
            return {
                "image_urls": image_urls,
                "image_metadata": [merged_meta],
            }
        else:
            return {
                "image_urls": image_urls,
                "image_metadata": gen_metadata,
            }
    
    return image_generator_node_for_index


def image_generation_collector(state: StoryState) -> Dict:
    """
    Collector node that aggregates results from all parallel image generator nodes.
    This node runs after all parallel image generators complete.
    """
    image_prompts = state.get("image_prompts", [])
    image_urls = state.get("image_urls", [])
    image_metadata = state.get("image_metadata", [])
    job_id = state.get("job_id", "unknown")
    
    logger.info(f"Job {job_id}: Collecting results from parallel image generation")
    logger.debug(f"Job {job_id}: Raw collected - {len(image_urls)} image URLs, {len(image_metadata)} metadata entries")
    
    # Filter metadata to only include generated ones (those with image_index set)
    # This removes the original metadata from the prompter that doesn't have image_index
    generated_metadata = [
        meta for meta in image_metadata 
        if "image_index" in meta or "s3_url" in meta or "local_path" in meta
    ]
    
    logger.debug(f"Job {job_id}: After filtering metadata - {len(generated_metadata)} generated metadata entries")
    
    # Deduplicate by image_index - keep only the first occurrence of each index
    # This handles cases where state merging with operator.add created duplicates
    seen_indices = set()
    unique_metadata = []
    for meta in generated_metadata:
        idx = meta.get("image_index")
        if idx is not None and idx not in seen_indices:
            unique_metadata.append(meta)
            seen_indices.add(idx)
        elif idx is None:
            # Metadata without image_index - keep it but assign an index
            # This shouldn't happen normally, but handle it gracefully
            next_idx = len(unique_metadata)
            meta["image_index"] = next_idx
            unique_metadata.append(meta)
    
    # Sort metadata by image_index to ensure correct order
    unique_metadata.sort(key=lambda x: x.get("image_index", 0))
    
    # Pair URLs with metadata and deduplicate
    # Since each node returns one URL and one metadata, they should align by position
    # But we need to handle duplicates and ensure we only keep unique pairs
    deduplicated_urls = []
    deduplicated_metadata = []
    seen_urls = set()  # Track URLs we've already added to avoid duplicates
    
    # Create pairs by matching metadata image_index with URL position
    # Each node at index i should return URL at position i in the merged list
    for meta in unique_metadata:
        idx = meta.get("image_index", 0)
        # Try to get URL at the same index position
        if idx < len(image_urls):
            url = image_urls[idx]
            # Only add if we haven't seen this URL before (deduplicate)
            if url not in seen_urls:
                deduplicated_urls.append(url)
                deduplicated_metadata.append(meta)
                seen_urls.add(url)
                logger.debug(f"Job {job_id}: Paired image_index {idx} with URL (deduplicated)")
        elif len(deduplicated_urls) < len(image_urls):
            # Fallback: use next available URL if index doesn't match
            url_pos = len(deduplicated_urls)
            if url_pos < len(image_urls):
                url = image_urls[url_pos]
                if url not in seen_urls:
                    deduplicated_urls.append(url)
                    deduplicated_metadata.append(meta)
                    seen_urls.add(url)
                    logger.debug(f"Job {job_id}: Paired image_index {idx} with URL at position {url_pos} (fallback)")
    
    logger.info(f"Job {job_id}: After deduplication - {len(deduplicated_urls)} image URLs, {len(deduplicated_metadata)} metadata entries")
    
    # Check if we got the expected number of images
    expected_count = len(image_prompts)
    actual_count = len(deduplicated_urls)
    
    if actual_count == 0:
        error_msg = f"Failed to generate any images. Expected {expected_count} images."
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
        }
    
    if actual_count < expected_count:
        logger.warning(f"Job {job_id}: Generated {actual_count}/{expected_count} images. Some may have failed.")
    
    if actual_count > expected_count:
        logger.warning(f"Job {job_id}: Generated {actual_count} images but only {expected_count} expected. Truncating to first {expected_count}.")
        deduplicated_urls = deduplicated_urls[:expected_count]
        deduplicated_metadata = deduplicated_metadata[:expected_count]
        actual_count = expected_count
    
    # Ensure final metadata has sequential image_index values
    for i, meta in enumerate(deduplicated_metadata):
        meta["image_index"] = i
    
    logger.info(f"Job {job_id}: Successfully collected {actual_count} unique images")
    
    return {
        "image_urls": deduplicated_urls,
        "image_metadata": deduplicated_metadata,
    }


async def image_generation_parallel_executor(state: StoryState) -> Dict:
    """
    Executor node that creates and runs a dynamic subgraph with parallel image generator nodes.
    This node creates multiple parallel nodes based on the number of images requested.
    """
    image_prompts = state.get("image_prompts", [])
    job_id = state.get("job_id", "unknown")
    
    # Check if image prompts were generated
    if not image_prompts:
        error_msg = "No image prompts were generated. Image prompter may have failed."
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
            "image_urls": [],
            "image_metadata": [],
        }
    
    logger.info(f"Job {job_id}: Creating dynamic parallel subgraph for {len(image_prompts)} images")
    logger.debug(f"Job {job_id}: State before subgraph - image_prompts: {len(image_prompts)}, existing image_urls: {len(state.get('image_urls', []))}, existing image_metadata: {len(state.get('image_metadata', []))}")
    
    # Create a fresh state for the subgraph to avoid merging issues
    # We need to preserve image_metadata from prompter but clear image_urls
    subgraph_state = {
        **state,
        "image_urls": [],  # Clear image_urls - subgraph will populate these
        # Keep image_metadata from prompter - nodes will merge with it
    }
    
    # Create and execute the dynamic subgraph with parallel nodes
    try:
        dynamic_subgraph = _create_dynamic_image_subgraph(subgraph_state)
        # Execute the subgraph asynchronously
        result_state = await dynamic_subgraph.ainvoke(subgraph_state)
        
        # Extract results from the subgraph execution
        image_urls = result_state.get("image_urls", [])
        image_metadata = result_state.get("image_metadata", [])
        
        logger.info(f"Job {job_id}: Parallel image generation completed: {len(image_urls)} images generated, {len(image_metadata)} metadata entries")
        logger.debug(f"Job {job_id}: image_urls: {image_urls}, image_metadata count: {len(image_metadata)}")
        
        # Validate that we have the expected number of images
        if len(image_urls) != len(image_prompts):
            logger.warning(f"Job {job_id}: Mismatch! Expected {len(image_prompts)} images but got {len(image_urls)} URLs")
        
        return {
            "image_urls": image_urls,
            "image_metadata": image_metadata,
        }
    except Exception as e:
        error_msg = f"Error in parallel image generation: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        return {
            "error": error_msg,
            "image_urls": [],
            "image_metadata": [],
        }


def create_story_graph() -> StateGraph:
    """
    Create and configure the LangGraph workflow with dynamic parallel image generation.
    This creates multiple parallel nodes based on the number of images requested.
    """
    
    # Create the graph
    workflow = StateGraph(StoryState)
    
    # Add core nodes
    workflow.add_node("story_writer", story_writer_node)
    workflow.add_node("image_prompter", image_prompter_node)
    workflow.add_node("image_generation_parallel", image_generation_parallel_executor)
    workflow.add_node("assembler", assembler_node)
    
    # Set entry point
    workflow.set_entry_point("story_writer")
    
    # Add edges
    workflow.add_edge("story_writer", "image_prompter")
    workflow.add_edge("image_prompter", "image_generation_parallel")
    workflow.add_edge("image_generation_parallel", "assembler")
    workflow.add_edge("assembler", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app


def _create_dynamic_image_subgraph(state: StoryState) -> StateGraph:
    """
    Create a subgraph with dynamically created parallel image generator nodes
    based on the number of images in the state.
    This subgraph will be executed as part of the main workflow.
    """
    image_prompts = state.get("image_prompts", [])
    num_images = len(image_prompts)
    job_id = state.get("job_id", "unknown")
    
    logger.info(f"Job {job_id}: Creating {num_images} parallel image generator nodes")
    
    # Create a subgraph for image generation
    subgraph = StateGraph(StoryState)
    
    # Add the collector node
    subgraph.add_node("image_generation_collector", image_generation_collector)
    
    # Dynamically create image generator nodes for each image
    image_node_names = []
    for i in range(num_images):
        node_name = f"image_generator_{i}"
        subgraph.add_node(node_name, create_single_image_generator_node(i))
        image_node_names.append(node_name)
        # Each image generator node connects to the collector
        subgraph.add_edge(node_name, "image_generation_collector")
    
    # Set entry point - all image generator nodes will execute in parallel
    # LangGraph supports multiple entry points for parallel execution
    if image_node_names:
        # Create a fanout node that triggers all image generators
        def fanout_node(state: StoryState) -> Dict:
            logger.info(f"Job {job_id}: Fanning out to {len(image_node_names)} parallel image generator nodes")
            return {}
        
        subgraph.add_node("_fanout", fanout_node)
        subgraph.set_entry_point("_fanout")
        
        # Connect fanout to all image generator nodes (parallel execution)
        for node_name in image_node_names:
            subgraph.add_edge("_fanout", node_name)
        
        subgraph.add_edge("image_generation_collector", END)
    
    return subgraph.compile()


# Create the compiled graph instance
story_graph = create_story_graph()


async def run_story_generation(initial_state: StoryState) -> StoryState:
    """
    Run the story generation workflow.
    
    Args:
        initial_state: Initial state with job_id, prompt, age_group, etc.
        
    Returns:
        Final state with story, images, etc.
    """
    # Run the graph asynchronously
    final_state = await story_graph.ainvoke(initial_state)
    return final_state
