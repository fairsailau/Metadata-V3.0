import streamlit as st
import pandas as pd
import time
import threading
import concurrent.futures
from typing import Dict, List, Any
import json
import logging

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
    if not st.session_state.authenticated or not st.session_state.client:
        st.error("Please authenticate with Box first")
        return
    
    # Ensure extraction_results is initialized - FIXED: Use hasattr check instead of 'in' operator
    if not hasattr(st.session_state, "extraction_results"):
        st.session_state.extraction_results = {}
        logger.info("Initialized extraction_results in apply_metadata")
    
    # Ensure selected_result_ids is initialized - FIXED: Use hasattr check instead of 'in' operator
    if not hasattr(st.session_state, "selected_result_ids"):
        # Initialize with empty list first to avoid KeyError
        st.session_state.selected_result_ids = []
        # Then populate with extraction_results keys if available
        if hasattr(st.session_state, "extraction_results") and st.session_state.extraction_results:
            st.session_state.selected_result_ids = list(st.session_state.extraction_results.keys())
        logger.info(f"Initialized selected_result_ids in apply_metadata with {len(st.session_state.selected_result_ids)} items")
    
    # Ensure application_state is initialized
    if not hasattr(st.session_state, "application_state"):
        st.session_state.application_state = {
            "is_applying": False,
            "applied_files": 0,
            "total_files": len(st.session_state.selected_result_ids) if hasattr(st.session_state, "selected_result_ids") else 0,
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
    
    # If no results are explicitly selected, use all available results
    if not hasattr(st.session_state, "selected_result_ids") or not st.session_state.selected_result_ids:
        logger.info("No results explicitly selected, using all available results")
        st.session_state.selected_result_ids = list(st.session_state.extraction_results.keys())
        st.info("No results explicitly selected, using all available results")
    
    st.write("Apply extracted metadata to your Box files.")
    
    # Update total files count in case selected_result_ids has changed
    if hasattr(st.session_state, "application_state"):
        st.session_state.application_state["total_files"] = len(st.session_state.selected_result_ids)
    
    # Display selected files
    st.subheader("Selected Files")
    st.write(f"You have selected {len(st.session_state.selected_result_ids)} files for metadata application.")
    
    with st.expander("View Selected Files"):
        for file_id in st.session_state.selected_result_ids:
            if file_id in st.session_state.extraction_results:
                result = st.session_state.extraction_results[file_id]
                st.write(f"- {result.get('file_name', 'Unknown')} ({file_id})")
    
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
            # FIXED: Ensure extraction_results exists before accessing it
            if not hasattr(st.session_state, "extraction_results"):
                st.session_state.extraction_results = {}
                logger.info("Initialized extraction_results in apply_metadata_to_file")
                
            # Validate file_id exists in extraction_results
            if file_id not in st.session_state.extraction_results:
                logger.warning(f"File ID {file_id} not found in extraction_results")
                return {
                    "file_id": file_id,
                    "file_name": "Unknown",
                    "success": False,
                    "error": "File ID not found in extraction results"
                }
                
            result_data = st.session_state.extraction_results[file_id]
            file_name = result_data.get("file_name", "Unknown")
            
            # Get Box client
            client = st.session_state.client
            
            # Extract the metadata to apply
            metadata_values = {}
            
            # Debug logging
            logger.info(f"Applying metadata for file: {file_name} ({file_id})")
            logger.info(f"Result data structure: {json.dumps(result_data, default=str)}")
            
            # Try multiple approaches to extract metadata values
            
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
            
            # 2. Check for result field (backward compatibility)
            if not metadata_values and "result" in result_data:
                if isinstance(result_data["result"], dict):
                    # Extract all fields from the result that aren't internal fields
                    for key, value in result_data["result"].items():
                        if not key.startswith("_") and key != "extracted_text":
                            metadata_values[key] = value
                    logger.info(f"Extracted metadata from result: {len(metadata_values)} fields")
                    
                    # Check for key_value_pairs in result
                    if not metadata_values and "key_value_pairs" in result_data["result"]:
                        kv_pairs = result_data["result"]["key_value_pairs"]
                        if isinstance(kv_pairs, dict):
                            metadata_values = kv_pairs
                            logger.info(f"Extracted metadata from key_value_pairs: {len(metadata_values)} fields")
                elif isinstance(result_data["result"], str):
                    # If result is a string, use it as a single metadata value
                    metadata_values["extracted_text"] = result_data["result"]
                    logger.info("Extracted metadata from result string")
            
            # 3. Check for api_response field
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
            
            # 4. Try to extract from any string field in the result_data
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
                "file_name": st.session_state.extraction_results.get(file_id, {}).get("file_name", "Unknown") if hasattr(st.session_state, "extraction_results") else "Unknown",
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }
    
    # Apply metadata with batch processing
    def apply_metadata_batch():
        # FIXED: Ensure session state variables exist before accessing them
        if not hasattr(st.session_state, "extraction_results"):
            st.session_state.extraction_results = {}
            logger.info("Initialized extraction_results in apply_metadata_batch")
            
        if not hasattr(st.session_state, "selected_result_ids"):
            st.session_state.selected_result_ids = list(st.session_state.extraction_results.keys())
            logger.info(f"Initialized selected_result_ids in apply_metadata_batch with {len(st.session_state.selected_result_ids)} items")
        
        # Validate selected_result_ids
        valid_file_ids = []
        for file_id in st.session_state.selected_result_ids:
            if file_id in st.session_state.extraction_results:
                valid_file_ids.append(file_id)
            else:
                logger.warning(f"File ID {file_id} not found in extraction_results, skipping")
                
        if not valid_file_ids:
            logger.error("No valid file IDs found in selected_result_ids")
            if hasattr(st.session_state, "application_state"):
                st.session_state.application_state["is_applying"] = False
            st.error("No valid files selected for metadata application")
            return
            
        total_files = len(valid_file_ids)
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
            current_batch = valid_file_ids[i:batch_end]
            
            # Update current batch in state
            st.session_state.application_state["current_batch"] = []
            for file_id in current_batch:
                if file_id in st.session_state.extraction_results:
                    st.session_state.application_state["current_batch"].append(
                        st.session_state.extraction_results[file_id].get("file_name", "Unknown")
                    )
            
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
                        if hasattr(st.session_state, "extraction_results"):
                            file_name = st.session_state.extraction_results.get(file_id, {}).get("file_name", "Unknown")
                        else:
                            file_name = "Unknown"
                            
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
                    "total_files": len(st.session_state.selected_result_ids) if hasattr(st.session_state, "selected_result_ids") else 0,
                    "current_batch": [],
                    "results": {},
                    "errors": {}
                }
                st.rerun()
