import streamlit as st
import logging
import time
import threading
import concurrent.futures
from typing import Dict, List, Any
import json
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
    
    # Initialize session state variables if they don't exist
    initialize_session_state()
    
    # CRITICAL FIX: Verify client authentication before proceeding
    if not verify_client_authentication():
        st.error("Box client authentication is required. Please authenticate first.")
        if st.button("Go to Authentication", key="go_to_auth_btn"):
            st.session_state.current_page = "Home"  # Assuming Home page has authentication
            st.rerun()
        return
    
    # Check if extraction results exist
    if "extraction_results" not in st.session_state or not st.session_state.extraction_results:
        st.warning("No extraction results available. Please process files first.")
        if st.button("Go to Process Files", key="go_to_process_files_btn"):
            st.session_state.current_page = "Process Files"
            st.rerun()
        return
    
    # Debug the structure of extraction_results
    extraction_results = st.session_state.extraction_results
    logger.info(f"Extraction results keys: {list(extraction_results.keys())}")
    logger.info(f"Extraction results structure: {json.dumps({str(k): str(type(v)) for k, v in extraction_results.items()}, indent=2)}")
    
    # Extract file IDs and metadata from extraction_results
    available_file_ids = []
    file_id_to_file_name = {}
    file_id_to_metadata = {}
    
    # Check if we have any selected files in session state
    if "selected_files" in st.session_state and st.session_state.selected_files:
        selected_files = st.session_state.selected_files
        logger.info(f"Found {len(selected_files)} selected files in session state")
        for file_info in selected_files:
            if isinstance(file_info, dict) and "id" in file_info and file_info["id"]:
                file_id = file_info["id"]
                file_name = file_info.get("name", "Unknown")
                available_file_ids.append(file_id)
                file_id_to_file_name[file_id] = file_name
                logger.info(f"Added file ID {file_id} from selected_files")
    
    # Extract metadata directly from extraction_results
    for key, result in extraction_results.items():
        logger.info(f"Checking extraction result key: {key}")
        
        # Check if the key itself is a file ID (direct match)
        if isinstance(key, str) and key.isdigit():
            file_id = key
            if file_id not in available_file_ids:
                available_file_ids.append(file_id)
                
                # Extract file name if available
                if isinstance(result, dict) and "file_name" in result:
                    file_id_to_file_name[file_id] = result["file_name"]
                
                # Extract metadata
                if isinstance(result, dict):
                    if "result" in result and result["result"]:
                        file_id_to_metadata[file_id] = result["result"]
                    elif "api_response" in result and "answer" in result["api_response"]:
                        file_id_to_metadata[file_id] = result["api_response"]["answer"]
                    else:
                        # Use the entire result as metadata
                        file_id_to_metadata[file_id] = {k: v for k, v in result.items() 
                                                      if k not in ["file_id", "file_name"] and not k.startswith("_")}
                
                logger.info(f"Added file ID {file_id} as direct key match")
        
        # Check if the result contains a file_id field
        elif isinstance(result, dict) and "file_id" in result:
            file_id = result["file_id"]
            if file_id not in available_file_ids:
                available_file_ids.append(file_id)
                
                # Extract file name if available
                if "file_name" in result:
                    file_id_to_file_name[file_id] = result["file_name"]
                
                # Extract metadata
                if "result" in result and result["result"]:
                    file_id_to_metadata[file_id] = result["result"]
                elif "api_response" in result and "answer" in result["api_response"]:
                    file_id_to_metadata[file_id] = result["api_response"]["answer"]
                else:
                    # Use the entire result as metadata
                    file_id_to_metadata[file_id] = {k: v for k, v in result.items() 
                                                  if k not in ["file_id", "file_name"] and not k.startswith("_")}
                
                logger.info(f"Added file ID {file_id} from result object")
    
    # Check if we have any processing results in session state
    if "processing_state" in st.session_state and "results" in st.session_state.processing_state:
        processing_results = st.session_state.processing_state["results"]
        logger.info(f"Found {len(processing_results)} results in processing_state")
        for file_id, result in processing_results.items():
            if file_id not in available_file_ids:
                available_file_ids.append(file_id)
                if "file_name" in result:
                    file_id_to_file_name[file_id] = result["file_name"]
                logger.info(f"Added file ID {file_id} from processing_state results")
                
                # Extract metadata
                if "result" in result:
                    file_id_to_metadata[file_id] = result["result"]
    
    # Remove duplicates while preserving order
    available_file_ids = list(dict.fromkeys(available_file_ids))
    
    # Debug logging
    logger.info(f"Available file IDs: {available_file_ids}")
    logger.info(f"File ID to file name mapping: {file_id_to_file_name}")
    logger.info(f"File ID to metadata mapping: {json.dumps({k: str(v) for k, v in file_id_to_metadata.items()})}")
    
    st.write("Apply extracted metadata to your Box files.")
    
    # Update total files count based on available_file_ids
    if "application_state" not in st.session_state:
        st.session_state.application_state = {
            "is_applying": False,
            "applied_files": 0,
            "total_files": 0,
            "current_batch": [],
            "results": {},
            "errors": {}
        }
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
    if "metadata_config" in st.session_state:
        metadata_config = st.session_state.metadata_config
        is_structured = metadata_config.get("extraction_method") == "structured"
    else:
        is_structured = False
    
    if is_structured:
        # For structured extraction
        if "metadata_config" in st.session_state and st.session_state.metadata_config.get("use_template", False):
            # Using existing template
            st.write(f"Metadata will be applied using template ID: {st.session_state.metadata_config.get('template_id', '')}")
            
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
            disabled=st.session_state.application_state.get("is_applying", False),
            use_container_width=True,
            key="apply_metadata_btn"
        )
    
    with col2:
        cancel_button = st.button(
            "Cancel",
            disabled=not st.session_state.application_state.get("is_applying", False),
            use_container_width=True,
            key="cancel_btn"
        )
    
    # Progress tracking
    progress_container = st.container()
    
    # Apply metadata to a single file using Box's recommended approach
    def apply_metadata_to_file(file_id):
        try:
            file_name = file_id_to_file_name.get(file_id, "Unknown")
            
            # CRITICAL FIX: Verify client authentication before using client
            if not verify_client_authentication():
                logger.error(f"Box client not authenticated when applying metadata to file {file_id}")
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "success": False,
                    "error": "Box client not authenticated. Please authenticate and try again."
                }
            
            # Get Box client - now we know it exists
            client = st.session_state.client
            
            # Get metadata directly from file_id_to_metadata mapping
            metadata_values = {}
            
            if file_id in file_id_to_metadata:
                metadata_content = file_id_to_metadata[file_id]
                logger.info(f"Found metadata for file ID {file_id}: {json.dumps(metadata_content, default=str)}")
                
                if isinstance(metadata_content, dict):
                    # Extract all fields from the metadata that aren't internal fields
                    for key, value in metadata_content.items():
                        if not key.startswith("_"):
                            metadata_values[key] = value
                elif isinstance(metadata_content, str):
                    # If metadata is a string, try to parse it as JSON
                    try:
                        parsed_metadata = json.loads(metadata_content)
                        if isinstance(parsed_metadata, dict):
                            for key, value in parsed_metadata.items():
                                metadata_values[key] = value
                        else:
                            # Use as a single metadata value
                            metadata_values["extracted_text"] = metadata_content
                    except json.JSONDecodeError:
                        # Use as a single metadata value
                        metadata_values["extracted_text"] = metadata_content
            else:
                # If no metadata found, check extraction_results directly
                logger.warning(f"No metadata found for file ID {file_id} in file_id_to_metadata mapping")
                
                # Try to find metadata in extraction_results
                for key, result in st.session_state.extraction_results.items():
                    if isinstance(result, dict):
                        if "file_id" in result and result["file_id"] == file_id:
                            if "result" in result and result["result"]:
                                if isinstance(result["result"], dict):
                                    for k, v in result["result"].items():
                                        if not k.startswith("_"):
                                            metadata_values[k] = v
                                else:
                                    metadata_values["extracted_text"] = str(result["result"])
                            elif "api_response" in result and "answer" in result["api_response"]:
                                if isinstance(result["api_response"]["answer"], dict):
                                    for k, v in result["api_response"]["answer"].items():
                                        metadata_values[k] = v
                                else:
                                    metadata_values["answer"] = str(result["api_response"]["answer"])
            
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
            
            # Debug logging
            logger.info(f"Applying metadata for file: {file_name} ({file_id})")
            logger.info(f"Metadata values: {json.dumps(metadata_values, default=str)}")
            
            # Apply metadata using Box's recommended approach
            try:
                # Get file object
                file_obj = client.file(file_id=file_id)
                
                # Apply as global properties (simplest approach)
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
            st.session_state.application_state["is_applying"] = False
            st.error("No files available for metadata application")
            return
            
        total_files = len(available_file_ids)
        logger.info(f"Starting metadata application for {total_files} files")
        
        # Reset application state
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
            if not st.session_state.application_state["is_applying"]:
                # Application was cancelled
                logger.info("Metadata application cancelled")
                break
            
            # CRITICAL FIX: Verify client authentication before processing batch
            if not verify_client_authentication():
                logger.error("Box client not authenticated when processing batch")
                st.session_state.application_state["is_applying"] = False
                st.error("Box client not authenticated. Please authenticate and try again.")
                return
            
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
                    if not st.session_state.application_state["is_applying"]:
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
        st.session_state.application_state["is_applying"] = False
        st.session_state.application_state["current_batch"] = []
    
    # Handle apply button click
    if apply_button:
        # CRITICAL FIX: Verify client authentication before starting application
        if not verify_client_authentication():
            st.error("Box client not authenticated. Please authenticate and try again.")
        else:
            # Start application in a separate thread
            application_thread = threading.Thread(target=apply_metadata_batch)
            application_thread.start()
    
    # Handle cancel button click
    if cancel_button:
        st.session_state.application_state["is_applying"] = False
        st.warning("Metadata application cancelled.")
    
    # Display progress
    with progress_container:
        if st.session_state.application_state["is_applying"]:
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
        
        elif st.session_state.application_state["applied_files"] > 0:
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

def initialize_session_state():
    """
    Initialize all required session state variables
    """
    # Core session state variables
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        logger.info("Initialized authenticated in session state")
        
    if "client" not in st.session_state:
        st.session_state.client = None
        logger.info("Initialized client in session state")
        
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Home"
        logger.info("Initialized current_page in session state")
    
    # File selection and metadata configuration
    if "selected_files" not in st.session_state:
        st.session_state.selected_files = []
        logger.info("Initialized selected_files in session state")
        
    if "metadata_config" not in st.session_state:
        st.session_state.metadata_config = {
            "extraction_method": "freeform",
            "freeform_prompt": "Extract key metadata from this document.",
            "use_template": False,
            "template_id": "",
            "custom_fields": [],
            "ai_model": "azure__openai__gpt_4o_mini",
            "batch_size": 5
        }
        logger.info("Initialized metadata_config in session state")
    
    # Results and processing state
    if "extraction_results" not in st.session_state:
        st.session_state.extraction_results = {}
        logger.info("Initialized extraction_results in session state")
        
    if "selected_result_ids" not in st.session_state:
        st.session_state.selected_result_ids = []
        logger.info("Initialized selected_result_ids in session state")
        
    if "application_state" not in st.session_state:
        st.session_state.application_state = {
            "is_applying": False,
            "applied_files": 0,
            "total_files": 0,
            "current_batch": [],
            "results": {},
            "errors": {}
        }
        logger.info("Initialized application_state in session state")
        
    if "processing_state" not in st.session_state:
        st.session_state.processing_state = {
            "is_processing": False,
            "current_file_index": -1,
            "total_files": 0,
            "processed_files": 0,
            "results": {},
            "errors": {}
        }
        logger.info("Initialized processing_state in session state")
    
    # Debug and feedback
    if "debug_info" not in st.session_state:
        st.session_state.debug_info = {}
        logger.info("Initialized debug_info in session state")
        
    if "metadata_templates" not in st.session_state:
        st.session_state.metadata_templates = []
        logger.info("Initialized metadata_templates in session state")
        
    if "feedback_data" not in st.session_state:
        st.session_state.feedback_data = {}
        logger.info("Initialized feedback_data in session state")
        
    # CRITICAL FIX: Authentication persistence
    if "auth_credentials" not in st.session_state:
        st.session_state.auth_credentials = {}
        logger.info("Initialized auth_credentials in session state")

def verify_client_authentication():
    """
    Verify that the Box client is authenticated and available in session state.
    If not, attempt to re-authenticate using stored credentials.
    
    Returns:
        bool: True if client is authenticated, False otherwise
    """
    # Check if client exists in session state
    if "client" not in st.session_state or st.session_state.client is None:
        logger.warning("Box client not found in session state")
        
        # Try to re-authenticate using stored credentials
        if "auth_credentials" in st.session_state and st.session_state.auth_credentials:
            try:
                logger.info("Attempting to re-authenticate using stored credentials")
                
                # Import Box SDK
                try:
                    from boxsdk import OAuth2, Client
                except ImportError:
                    logger.error("Failed to import Box SDK")
                    return False
                
                # Get stored credentials
                creds = st.session_state.auth_credentials
                
                if "access_token" in creds and "refresh_token" in creds and "client_id" in creds and "client_secret" in creds:
                    # Create OAuth object
                    oauth = OAuth2(
                        client_id=creds["client_id"],
                        client_secret=creds["client_secret"],
                        access_token=creds["access_token"],
                        refresh_token=creds["refresh_token"],
                        store_tokens=store_tokens
                    )
                    
                    # Create client
                    client = Client(oauth)
                    
                    # Verify client works by getting current user
                    user = client.user().get()
                    
                    # Store client in session state
                    st.session_state.client = client
                    st.session_state.authenticated = True
                    
                    logger.info(f"Successfully re-authenticated as {user.name}")
                    return True
                else:
                    logger.warning("Incomplete credentials in auth_credentials")
                    return False
            except Exception as e:
                logger.error(f"Error re-authenticating: {str(e)}")
                return False
        else:
            logger.warning("No stored credentials found for re-authentication")
            return False
    
    # Client exists, verify it's working
    try:
        # Try to get current user to verify client is working
        user = st.session_state.client.user().get()
        logger.info(f"Verified client authentication as {user.name}")
        return True
    except Exception as e:
        logger.error(f"Error verifying client: {str(e)}")
        
        # Clear invalid client
        st.session_state.client = None
        st.session_state.authenticated = False
        
        # Try to re-authenticate
        return verify_client_authentication()

def store_tokens(access_token, refresh_token):
    """
    Store Box API tokens in session state for authentication persistence.
    This function is passed to the OAuth2 object to handle token refresh.
    
    Args:
        access_token (str): The new access token
        refresh_token (str): The new refresh token
    """
    # Initialize auth_credentials if it doesn't exist
    if "auth_credentials" not in st.session_state:
        st.session_state.auth_credentials = {}
    
    # Update tokens
    st.session_state.auth_credentials["access_token"] = access_token
    st.session_state.auth_credentials["refresh_token"] = refresh_token
    
    logger.info("Updated authentication tokens in session state")
    return access_token, refresh_token
