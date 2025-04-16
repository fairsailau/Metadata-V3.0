import streamlit as st
import pandas as pd
import time
import threading
import concurrent.futures
from typing import Dict, List, Any
import json
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def apply_metadata():
    """
    Apply extracted metadata to Box files with batch processing capabilities
    """
    st.title("Apply Metadata")
    
    # Validate session state
    if not hasattr(st.session_state, "authenticated") or not hasattr(st.session_state, "client") or not st.session_state.authenticated or not st.session_state.client:
        st.error("Please authenticate with Box first")
        return
    
    # Ensure extraction_results is initialized
    if not hasattr(st.session_state, "extraction_results"):
        st.session_state.extraction_results = {}
        logger.info("Initialized extraction_results in apply_metadata")
    
    # Ensure selected_result_ids is initialized
    if not hasattr(st.session_state, "selected_result_ids"):
        st.session_state.selected_result_ids = []
        logger.info("Initialized selected_result_ids in apply_metadata")
    
    # Ensure application_state is initialized
    if not hasattr(st.session_state, "application_state"):
        st.session_state.application_state = {
            "is_applying": False,
            "applied_files": 0,
            "total_files": 0,
            "current_batch": [],
            "results": {},
            "errors": {}
        }
        logger.info("Initialized application_state in apply_metadata")
    
    # Ensure metadata_config is initialized
    if not hasattr(st.session_state, "metadata_config"):
        st.session_state.metadata_config = {
            "extraction_method": "freeform",
            "freeform_prompt": "Extract key metadata from this document.",
            "use_template": False,
            "template_id": "",
            "custom_fields": [],
            "ai_model": "azure__openai__gpt_4o_mini",
            "batch_size": 5
        }
        logger.info("Initialized metadata_config in apply_metadata")
    
    if not hasattr(st.session_state, "extraction_results") or not st.session_state.extraction_results:
        st.warning("No extraction results available. Please process files first.")
        if st.button("Go to Process Files", key="go_to_process_files_btn"):
            st.session_state.current_page = "Process Files"
            st.rerun()
        return
    
    # ENHANCED: Comprehensive approach to extract file IDs from various sources
    available_file_ids = []
    file_id_to_composite_key = {}
    file_id_to_file_name = {}
    
    # Debug the structure of extraction_results
    logger.info(f"Extraction results keys: {list(st.session_state.extraction_results.keys())}")
    logger.info(f"Extraction results structure: {json.dumps({str(k): str(type(v)) for k, v in st.session_state.extraction_results.items()}, indent=2)}")
    
    # Check if we have any selected files in session state
    if hasattr(st.session_state, "selected_files") and st.session_state.selected_files:
        logger.info(f"Found {len(st.session_state.selected_files)} selected files in session state")
        for file_info in st.session_state.selected_files:
            if "id" in file_info and file_info["id"]:
                file_id = file_info["id"]
                file_name = file_info.get("name", "Unknown")
                available_file_ids.append(file_id)
                file_id_to_file_name[file_id] = file_name
                logger.info(f"Added file ID {file_id} from selected_files")
    
    # Check if we have any processing results in session state
    if hasattr(st.session_state, "processing_state") and "results" in st.session_state.processing_state:
        processing_results = st.session_state.processing_state["results"]
        logger.info(f"Found {len(processing_results)} results in processing_state")
        for file_id, result in processing_results.items():
            if file_id not in available_file_ids:
                available_file_ids.append(file_id)
                file_id_to_file_name[file_id] = result.get("file_name", "Unknown")
                logger.info(f"Added file ID {file_id} from processing_state results")
    
    # Now check extraction_results for file IDs
    for key, result in st.session_state.extraction_results.items():
        # Skip if not a dictionary
        if not isinstance(result, dict):
            logger.warning(f"Skipping non-dictionary result for key {key}: {type(result)}")
            continue
            
        # Try to get file_id directly from the result object
        if "file_id" in result and result["file_id"]:
            file_id = result["file_id"]
            if file_id not in available_file_ids:
                available_file_ids.append(file_id)
                file_id_to_composite_key[file_id] = key
                file_id_to_file_name[file_id] = result.get("file_name", "Unknown")
                logger.info(f"Added file ID {file_id} from result object for key {key}")
        
        # Try to extract file_id from the key if it's a string
        elif isinstance(key, str):
            # First check if the key itself is a file ID (all digits)
            if key.isdigit():
                file_id = key
                if file_id not in available_file_ids:
                    available_file_ids.append(file_id)
                    file_id_to_composite_key[file_id] = key
                    file_id_to_file_name[file_id] = result.get("file_name", "Unknown")
                    logger.info(f"Added file ID {file_id} (key is the file ID)")
            else:
                # Try to extract file_id from composite key
                match = re.match(r'([^_]+)_', key)
                if match:
                    file_id = match.group(1)
                    if file_id not in available_file_ids:
                        available_file_ids.append(file_id)
                        file_id_to_composite_key[file_id] = key
                        file_id_to_file_name[file_id] = result.get("file_name", "Unknown")
                        logger.info(f"Added file ID {file_id} extracted from composite key {key}")
    
    # If we still don't have file IDs, try to extract them from the result content
    if not available_file_ids:
        logger.info("No file IDs found yet, trying to extract from result content")
        for key, result in st.session_state.extraction_results.items():
            if not isinstance(result, dict):
                continue
                
            # Look for file_id in nested dictionaries
            for k, v in result.items():
                if k == "file_id" and v:
                    file_id = v
                    if file_id not in available_file_ids:
                        available_file_ids.append(file_id)
                        file_id_to_composite_key[file_id] = key
                        file_id_to_file_name[file_id] = result.get("file_name", "Unknown")
                        logger.info(f"Added file ID {file_id} from nested dictionary for key {key}")
                
                # Check if there's a nested dictionary that might contain file_id
                if isinstance(v, dict) and "file_id" in v and v["file_id"]:
                    file_id = v["file_id"]
                    if file_id not in available_file_ids:
                        available_file_ids.append(file_id)
                        file_id_to_composite_key[file_id] = key
                        file_id_to_file_name[file_id] = result.get("file_name", v.get("file_name", "Unknown"))
                        logger.info(f"Added file ID {file_id} from deeply nested dictionary for key {key}")
    
    # If we still don't have file IDs, check if there are any in processing_state
    if not available_file_ids and hasattr(st.session_state, "processing_state"):
        logger.info("No file IDs found yet, checking processing_state")
        # Check current_file_index
        if "current_file_index" in st.session_state.processing_state and st.session_state.processing_state["current_file_index"] >= 0:
            idx = st.session_state.processing_state["current_file_index"]
            if hasattr(st.session_state, "selected_files") and idx < len(st.session_state.selected_files):
                file_info = st.session_state.selected_files[idx]
                if "id" in file_info and file_info["id"]:
                    file_id = file_info["id"]
                    available_file_ids.append(file_id)
                    file_id_to_file_name[file_id] = file_info.get("name", "Unknown")
                    logger.info(f"Added file ID {file_id} from current_file_index in processing_state")
    
    # Remove duplicates while preserving order
    available_file_ids = list(dict.fromkeys(available_file_ids))
    
    # Debug logging
    logger.info(f"Available file IDs: {available_file_ids}")
    logger.info(f"File ID to composite key mapping: {file_id_to_composite_key}")
    logger.info(f"File ID to file name mapping: {file_id_to_file_name}")
    
    # CRITICAL: If we still don't have any file IDs, try to recover from selected_files
    if not available_file_ids and hasattr(st.session_state, "selected_files") and st.session_state.selected_files:
        st.warning("No file IDs found in extraction results. Using selected files as fallback.")
        logger.warning("No file IDs found in extraction results. Using selected files as fallback.")
        
        for file_info in st.session_state.selected_files:
            if "id" in file_info and file_info["id"]:
                file_id = file_info["id"]
                available_file_ids.append(file_id)
                file_id_to_file_name[file_id] = file_info.get("name", "Unknown")
                # Create a synthetic key for mapping
                synthetic_key = f"{file_id}_fallback"
                file_id_to_composite_key[file_id] = synthetic_key
                # Create a synthetic result if needed
                if synthetic_key not in st.session_state.extraction_results:
                    st.session_state.extraction_results[synthetic_key] = {
                        "file_id": file_id,
                        "file_name": file_info.get("name", "Unknown"),
                        "result": {"note": "This is a fallback entry with no extracted metadata"}
                    }
                logger.info(f"Added fallback file ID {file_id} from selected_files")
    
    st.write("Apply extracted metadata to your Box files.")
    
    # Update total files count based on available_file_ids
    if hasattr(st.session_state, "application_state"):
        st.session_state.application_state["total_files"] = len(available_file_ids)
    
    # Display selected files
    st.subheader("Selected Files")
    
    if not available_file_ids:
        st.error("No file IDs available for metadata application. Please process files first.")
        if st.button("Go to Process Files", key="go_to_process_files_error_btn"):
            st.session_state.current_page = "Process Files"
            st.rerun()
        return
    
    st.write(f"You have selected {len(available_file_ids)} files for metadata application.")
    
    with st.expander("View Selected Files"):
        for file_id in available_file_ids:
            file_name = file_id_to_file_name.get(file_id, "Unknown")
            st.write(f"- {file_name} ({file_id})")
    
    # Metadata application options
    st.subheader("Application Options")
    
    # Determine if we're using structured or freeform extraction
    is_structured = st.session_state.metadata_config.get("extraction_method") == "structured"
    
    if is_structured:
        # For structured extraction
        if st.session_state.metadata_config.get("use_template", False):
            # Using existing template
            st.write(f"Metadata will be applied using template ID: {st.session_state.metadata_config['template_id']}")
            
            # Option to overwrite existing metadata
            overwrite = st.checkbox(
                "Overwrite existing metadata",
                value=True,
                help="If checked, existing metadata will be overwritten. Otherwise, it will be merged.",
                key="overwrite_checkbox"
            )
        else:
            # Using custom fields
            st.write(f"Metadata will be applied using custom fields.")
            
            # Option to create a new template
            create_template = st.checkbox(
                "Create a new metadata template",
                value=False,
                help="If checked, a new metadata template will be created based on your custom fields.",
                key="create_template_checkbox"
            )
            
            if create_template:
                template_name = st.text_input(
                    "Template Name",
                    value=f"Extraction Template {time.strftime('%Y-%m-%d')}",
                    key="template_name_input"
                )
    else:
        # For freeform extraction
        st.write("Freeform extraction results will be applied as properties metadata.")
        
        # Option to normalize keys
        normalize_keys = st.checkbox(
            "Normalize keys",
            value=True,
            help="If checked, keys will be normalized (lowercase, spaces replaced with underscores).",
            key="normalize_keys_checkbox"
        )
    
    # Batch processing options
    st.subheader("Batch Processing Options")
    
    batch_size = st.slider(
        "Batch Size",
        min_value=1,
        max_value=25,
        value=5,
        help="Number of files to process in parallel. Maximum is 25.",
        key="batch_size_slider"
    )
    
    # Apply metadata button
    col1, col2 = st.columns(2)
    
    with col1:
        apply_button = st.button(
            "Apply Metadata",
            disabled=st.session_state.application_state["is_applying"],
            use_container_width=True,
            key="apply_metadata_btn"
        )
    
    with col2:
        cancel_button = st.button(
            "Cancel",
            disabled=not st.session_state.application_state["is_applying"],
            use_container_width=True,
            key="cancel_btn"
        )
    
    # Progress tracking
    progress_container = st.container()
    
    # Apply metadata to a single file using Box's recommended approach
    def apply_metadata_to_file(file_id):
        try:
            # Get the composite key for this file_id
            composite_key = file_id_to_composite_key.get(file_id)
            
            # If we don't have a composite key, try to find any result with this file_id
            if not composite_key:
                for key, result in st.session_state.extraction_results.items():
                    if isinstance(result, dict) and result.get("file_id") == file_id:
                        composite_key = key
                        break
            
            # If we still don't have a composite key or it's not in extraction_results
            if not composite_key or composite_key not in st.session_state.extraction_results:
                logger.warning(f"Composite key for file ID {file_id} not found in extraction_results")
                
                # Try to find the file in processing_state results
                if hasattr(st.session_state, "processing_state") and "results" in st.session_state.processing_state:
                    if file_id in st.session_state.processing_state["results"]:
                        result_data = st.session_state.processing_state["results"][file_id]
                        logger.info(f"Found result for file ID {file_id} in processing_state results")
                    else:
                        return {
                            "file_id": file_id,
                            "file_name": file_id_to_file_name.get(file_id, "Unknown"),
                            "success": False,
                            "error": "File ID not found in extraction results or processing results"
                        }
                else:
                    return {
                        "file_id": file_id,
                        "file_name": file_id_to_file_name.get(file_id, "Unknown"),
                        "success": False,
                        "error": "File ID not found in extraction results"
                    }
            else:
                result_data = st.session_state.extraction_results[composite_key]
                
            file_name = result_data.get("file_name", file_id_to_file_name.get(file_id, "Unknown"))
            
            # Get Box client
            client = st.session_state.client
            
            # Extract the metadata to apply
            metadata_values = {}
            
            # Debug logging
            logger.info(f"Applying metadata for file: {file_name} ({file_id})")
            logger.info(f"Result data structure: {json.dumps(result_data, default=str)}")
            
            # Check if result_data contains a nested 'result' field (from processing.py)
            if "result" in result_data and result_data["result"]:
                result_content = result_data["result"]
                logger.info(f"Found result field in result_data: {json.dumps(result_content, default=str)}")
                
                if isinstance(result_content, dict):
                    # Extract all fields from the result that aren't internal fields
                    for key, value in result_content.items():
                        if not key.startswith("_"):
                            metadata_values[key] = value
                    logger.info(f"Extracted metadata from result field: {len(metadata_values)} fields")
                elif isinstance(result_content, str):
                    # If result is a string, use it as a single metadata value
                    metadata_values["extracted_text"] = result_content
                    logger.info("Extracted metadata from result string")
            
            # Try multiple approaches to extract metadata values if we didn't get any from the result field
            if not metadata_values:
                # 1. Check for result_data field (preferred format)
                if "result_data" in result_data and result_data["result_data"]:
                    if isinstance(result_data["result_data"], dict):
                        # Extract all fields from the result_data that aren't internal fields
                        for key, value in result_data["result_data"].items():
                            if not key.startswith("_"):
                                metadata_values[key] = value
                        logger.info(f"Extracted metadata from result_data: {len(metadata_values)} fields")
                    elif isinstance(result_data["result_data"], str):
                        # If result_data is a string, use it as a single metadata value
                        metadata_values["extracted_text"] = result_data["result_data"]
                        logger.info("Extracted metadata from result_data string")
                
                # 2. Check for api_response field
                if not metadata_values and "api_response" in result_data:
                    api_response = result_data["api_response"]
                    if isinstance(api_response, dict) and "answer" in api_response:
                        if isinstance(api_response["answer"], dict):
                            # Use answer field directly
                            for key, value in api_response["answer"].items():
                                metadata_values[key] = value
                            logger.info(f"Extracted metadata from api_response.answer: {len(metadata_values)} fields")
                        elif isinstance(api_response["answer"], str):
                            # Try to parse answer as JSON
                            try:
                                answer_data = json.loads(api_response["answer"])
                                if isinstance(answer_data, dict):
                                    for key, value in answer_data.items():
                                        metadata_values[key] = value
                                    logger.info(f"Extracted metadata from parsed api_response.answer: {len(metadata_values)} fields")
                            except json.JSONDecodeError:
                                # Use as a single metadata value
                                metadata_values["answer"] = api_response["answer"]
                                logger.info("Extracted metadata from api_response.answer string")
                
                # 3. Try to extract from any string field in the result_data
                if not metadata_values:
                    for key, value in result_data.items():
                        if isinstance(value, str) and not key.startswith("_") and key not in ["file_name", "file_id"]:
                            metadata_values[key] = value
                    logger.info(f"Extracted metadata from string fields: {len(metadata_values)} fields")
            
            # If no metadata values, log warning and return
            if not metadata_values:
                logger.warning(f"No metadata values found for file {file_name} ({file_id})")
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "success": False,
                    "error": "No metadata values found"
                }
            
            # Convert all values to strings for Box metadata
            for key, value in metadata_values.items():
                if not isinstance(value, (str, int, float, bool)):
                    metadata_values[key] = str(value)
            
            # Apply metadata using Box's recommended approach
            try:
                # Get file object
                file_obj = client.file(file_id=file_id)
                
                # Apply as global properties (simplest approach)
                logger.info(f"Applying metadata values: {json.dumps(metadata_values, default=str)}")
                metadata = file_obj.metadata("global", "properties").create(metadata_values)
                
                logger.info(f"Successfully applied metadata to file {file_name} ({file_id})")
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "success": True,
                    "metadata": metadata
                }
            except Exception as e:
                if "already exists" in str(e).lower():
                    # If metadata already exists, update it
                    try:
                        # Create update operations
                        operations = []
                        for key, value in metadata_values.items():
                            operations.append({
                                "op": "replace",
                                "path": f"/{key}",
                                "value": value
                            })
                        
                        # Update metadata
                        logger.info(f"Metadata already exists, updating with operations: {json.dumps(operations, default=str)}")
                        metadata = file_obj.metadata("global", "properties").update(operations)
                        
                        logger.info(f"Successfully updated metadata for file {file_name} ({file_id})")
                        return {
                            "file_id": file_id,
                            "file_name": file_name,
                            "success": True,
                            "metadata": metadata
                        }
                    except Exception as update_error:
                        logger.error(f"Error updating metadata for file {file_name} ({file_id}): {str(update_error)}")
                        return {
                            "file_id": file_id,
                            "file_name": file_name,
                            "success": False,
                            "error": f"Error updating metadata: {str(update_error)}"
                        }
                else:
                    logger.error(f"Error creating metadata for file {file_name} ({file_id}): {str(e)}")
                    return {
                        "file_id": file_id,
                        "file_name": file_name,
                        "success": False,
                        "error": f"Error creating metadata: {str(e)}"
                    }
        
        except Exception as e:
            logger.exception(f"Unexpected error applying metadata to file {file_id}: {str(e)}")
            return {
                "file_id": file_id,
                "file_name": file_id_to_file_name.get(file_id, "Unknown"),
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }
    
    # Apply metadata with batch processing
    def apply_metadata_batch():
        # Validate available_file_ids
        if not available_file_ids:
            logger.error("No file IDs available for metadata application")
            if hasattr(st.session_state, "application_state"):
                st.session_state.application_state["is_applying"] = False
            st.error("No files available for metadata application")
            return
            
        total_files = len(available_file_ids)
        logger.info(f"Starting metadata application for {total_files} files")
        
        # Reset application state
        if not hasattr(st.session_state, "application_state"):
            st.session_state.application_state = {}
            
        st.session_state.application_state = {
            "is_applying": True,
            "applied_files": 0,
            "total_files": total_files,
            "current_batch": [],
            "results": {},
            "errors": {}
        }
        
        # Process files in batches
        for i in range(0, total_files, batch_size):
            if not hasattr(st.session_state, "application_state") or not st.session_state.application_state["is_applying"]:
                # Application was cancelled
                logger.info("Metadata application cancelled")
                break
            
            # Get current batch
            batch_end = min(i + batch_size, total_files)
            current_batch = available_file_ids[i:batch_end]
            
            # Update current batch in state
            st.session_state.application_state["current_batch"] = []
            for file_id in current_batch:
                file_name = file_id_to_file_name.get(file_id, "Unknown")
                st.session_state.application_state["current_batch"].append(file_name)
            
            # Process batch in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                # Submit all files in the batch
                future_to_file = {executor.submit(apply_metadata_to_file, file_id): file_id for file_id in current_batch}
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_file):
                    if not hasattr(st.session_state, "application_state") or not st.session_state.application_state["is_applying"]:
                        # Application was cancelled
                        executor.shutdown(wait=False)
                        break
                    
                    file_id = future_to_file[future]
                    try:
                        result = future.result()
                        
                        if result["success"]:
                            # Store success result
                            st.session_state.application_state["results"][file_id] = {
                                "file_name": result["file_name"],
                                "file_id": file_id,
                                "metadata": result.get("metadata", {})
                            }
                        else:
                            # Store error result
                            st.session_state.application_state["errors"][file_id] = {
                                "file_name": result["file_name"],
                                "file_id": file_id,
                                "error": result["error"]
                            }
                        
                        # Update progress
                        st.session_state.application_state["applied_files"] += 1
                    
                    except Exception as e:
                        # Handle unexpected errors
                        file_name = file_id_to_file_name.get(file_id, "Unknown")
                            
                        st.session_state.application_state["errors"][file_id] = {
                            "file_name": file_name,
                            "file_id": file_id,
                            "error": f"Unexpected error: {str(e)}"
                        }
                        
                        # Update progress
                        st.session_state.application_state["applied_files"] += 1
        
        # Application complete
        if hasattr(st.session_state, "application_state"):
            st.session_state.application_state["is_applying"] = False
            st.session_state.application_state["current_batch"] = []
    
    # Handle apply button click
    if apply_button:
        # Start application in a separate thread
        application_thread = threading.Thread(target=apply_metadata_batch)
        application_thread.start()
    
    # Handle cancel button click
    if cancel_button:
        if hasattr(st.session_state, "application_state"):
            st.session_state.application_state["is_applying"] = False
        st.warning("Metadata application cancelled.")
    
    # Display progress
    with progress_container:
        if hasattr(st.session_state, "application_state") and st.session_state.application_state["is_applying"]:
            st.write("#### Applying Metadata")
            
            # Progress bar
            progress = st.session_state.application_state["applied_files"] / st.session_state.application_state["total_files"]
            st.progress(progress)
            
            # Current batch
            if st.session_state.application_state["current_batch"]:
                st.write("**Current batch:**")
                for file_name in st.session_state.application_state["current_batch"]:
                    st.write(f"- {file_name}")
            
            # Stats
            st.write(f"**Progress:** {st.session_state.application_state['applied_files']} of {st.session_state.application_state['total_files']} files processed")
        
        elif hasattr(st.session_state, "application_state") and st.session_state.application_state["applied_files"] > 0:
            # Application complete
            st.write("#### Metadata Application Complete")
            
            # Success count
            success_count = len(st.session_state.application_state["results"])
            error_count = len(st.session_state.application_state["errors"])
            
            st.write(f"**Results:** {success_count} successful, {error_count} failed")
            
            # Display errors if any
            if error_count > 0:
                with st.expander("View Errors"):
                    for file_id, error_data in st.session_state.application_state["errors"].items():
                        st.write(f"**{error_data['file_name']}:** {error_data['error']}")
            
            # Reset button
            if st.button("Reset", key="reset_btn"):
                st.session_state.application_state = {
                    "is_applying": False,
                    "applied_files": 0,
                    "total_files": len(available_file_ids),
                    "current_batch": [],
                    "results": {},
                    "errors": {}
                }
                st.rerun()
