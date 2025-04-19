import streamlit as st
import time
import logging
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Any
import json

# Import metadata extraction functions
from modules.metadata_extraction import metadata_extraction

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_files():
    """
    Process files for metadata extraction with Streamlit-compatible processing
    """
    st.title("Process Files")
    
    # Add debug information
    if "debug_info" not in st.session_state:
        st.session_state.debug_info = []
    
    # Add metadata templates
    if "metadata_templates" not in st.session_state:
        st.session_state.metadata_templates = {}
    
    # Add feedback data
    if "feedback_data" not in st.session_state:
        st.session_state.feedback_data = {}
    
    try:
        if not st.session_state.authenticated or not st.session_state.client:
            st.error("Please authenticate with Box first")
            return
        
        if not st.session_state.selected_files:
            st.warning("No files selected. Please select files in the File Browser first.")
            if st.button("Go to File Browser", key="go_to_file_browser_button"):
                st.session_state.current_page = "File Browser"
                st.rerun()
            return
        
        if "metadata_config" not in st.session_state or (
            st.session_state.metadata_config["extraction_method"] == "structured" and 
            not st.session_state.metadata_config["use_template"] and 
            not st.session_state.metadata_config["custom_fields"]
        ):
            st.warning("Metadata configuration is incomplete. Please configure metadata extraction parameters.")
            if st.button("Go to Metadata Configuration", key="go_to_metadata_config_button"):
                st.session_state.current_page = "Metadata Configuration"
                st.rerun()
            return
        
        # Initialize processing state
        if "processing_state" not in st.session_state:
            st.session_state.processing_state = {
                "is_processing": False,
                "processed_files": 0,
                "total_files": len(st.session_state.selected_files),
                "current_file_index": -1,
                "current_file": "",
                "results": {},
                "errors": {},
                "retries": {},
                "max_retries": 3,
                "retry_delay": 2,  # seconds
                "visualization_data": {}
            }
        
        # Display processing information
        st.write(f"Ready to process {len(st.session_state.selected_files)} files using the configured metadata extraction parameters.")
        
        # Enhanced batch processing controls
        with st.expander("Batch Processing Controls"):
            col1, col2 = st.columns(2)
            
            with col1:
                # Batch size control
                batch_size = st.number_input(
                    "Batch Size",
                    min_value=1,
                    max_value=50,
                    value=st.session_state.metadata_config.get("batch_size", 5),
                    key="batch_size_input"
                )
                st.session_state.metadata_config["batch_size"] = batch_size
                
                # Max retries control
                max_retries = st.number_input(
                    "Max Retries",
                    min_value=0,
                    max_value=10,
                    value=st.session_state.processing_state.get("max_retries", 3),
                    key="max_retries_input"
                )
                st.session_state.processing_state["max_retries"] = max_retries
            
            with col2:
                # Retry delay control
                retry_delay = st.number_input(
                    "Retry Delay (seconds)",
                    min_value=1,
                    max_value=30,
                    value=st.session_state.processing_state.get("retry_delay", 2),
                    key="retry_delay_input"
                )
                st.session_state.processing_state["retry_delay"] = retry_delay
                
                # Processing mode
                processing_mode = st.selectbox(
                    "Processing Mode",
                    options=["Sequential", "Parallel"],
                    index=0,
                    key="processing_mode_input"
                )
                st.session_state.processing_state["processing_mode"] = processing_mode
        
        # Template management
        with st.expander("Metadata Template Management"):
            st.write("#### Save Current Configuration as Template")
            template_name = st.text_input("Template Name", key="template_name_input")
            
            if st.button("Save Template", key="save_template_button"):
                if template_name:
                    st.session_state.metadata_templates[template_name] = st.session_state.metadata_config.copy()
                    st.success(f"Template '{template_name}' saved successfully!")
                else:
                    st.warning("Please enter a template name")
            
            st.write("#### Load Template")
            if st.session_state.metadata_templates:
                template_options = list(st.session_state.metadata_templates.keys())
                selected_template = st.selectbox(
                    "Select Template",
                    options=template_options,
                    key="load_template_select"
                )
                
                if st.button("Load Template", key="load_template_button"):
                    st.session_state.metadata_config = st.session_state.metadata_templates[selected_template].copy()
                    st.success(f"Template '{selected_template}' loaded successfully!")
            else:
                st.info("No saved templates yet")
        
        # Display configuration summary
        with st.expander("Configuration Summary"):
            st.write("#### Extraction Method")
            st.write(f"Method: {st.session_state.metadata_config['extraction_method'].capitalize()}")
            
            if st.session_state.metadata_config["extraction_method"] == "structured":
                if st.session_state.metadata_config["use_template"]:
                    st.write(f"Using template: Template ID {st.session_state.metadata_config['template_id']}")
                else:
                    st.write(f"Using {len(st.session_state.metadata_config['custom_fields'])} custom fields")
                    for i, field in enumerate(st.session_state.metadata_config["custom_fields"]):
                        st.write(f"- {field['display_name']} ({field['type']})")
            else:
                st.write("Freeform prompt:")
                st.write(f"> {st.session_state.metadata_config['freeform_prompt']}")
            
            st.write(f"AI Model: {st.session_state.metadata_config['ai_model']}")
            st.write(f"Batch Size: {st.session_state.metadata_config['batch_size']}")
        
        # Display selected files
        with st.expander("Selected Files"):
            for file in st.session_state.selected_files:
                st.write(f"- {file['name']} (Type: {file['type']})")
        
        # Process files button
        col1, col2 = st.columns(2)
        
        with col1:
            start_button = st.button(
                "Start Processing",
                disabled=st.session_state.processing_state["is_processing"],
                use_container_width=True,
                key="start_processing_button"
            )
        
        with col2:
            cancel_button = st.button(
                "Cancel Processing",
                disabled=not st.session_state.processing_state["is_processing"],
                use_container_width=True,
                key="cancel_processing_button"
            )
        
        # Progress tracking
        progress_container = st.container()
        
        # Get metadata extraction functions
        extraction_functions = metadata_extraction()
        
        # Helper function to extract structured data from API response
        def extract_structured_data_from_response(response):
            """
            Extract structured data from various possible response structures
            
            Args:
                response (dict): API response
                
            Returns:
                dict: Extracted structured data (key-value pairs)
            """
            structured_data = {}
            extracted_text = ""
            
            # Log the response structure for debugging
            logger.info(f"Response structure: {json.dumps(response, indent=2) if isinstance(response, dict) else str(response)}")
            
            if isinstance(response, dict):
                # Check for answer field (contains structured data in JSON format)
                if "answer" in response and isinstance(response["answer"], dict):
                    structured_data = response["answer"]
                    logger.info(f"Found structured data in 'answer' field: {structured_data}")
                    return structured_data
                
                # Check for answer field as string (JSON string)
                if "answer" in response and isinstance(response["answer"], str):
                    try:
                        answer_data = json.loads(response["answer"])
                        if isinstance(answer_data, dict):
                            structured_data = answer_data
                            logger.info(f"Found structured data in 'answer' field (JSON string): {structured_data}")
                            return structured_data
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse 'answer' field as JSON: {response['answer']}")
                
                # Check for key-value pairs directly in response
                for key, value in response.items():
                    if key not in ["error", "items", "response", "item_collection", "entries", "type", "id", "sequence_id"]:
                        structured_data[key] = value
                
                # Check in response field
                if "response" in response and isinstance(response["response"], dict):
                    response_obj = response["response"]
                    if "answer" in response_obj and isinstance(response_obj["answer"], dict):
                        structured_data = response_obj["answer"]
                        logger.info(f"Found structured data in 'response.answer' field: {structured_data}")
                        return structured_data
                
                # Check in items array
                if "items" in response and isinstance(response["items"], list) and len(response["items"]) > 0:
                    item = response["items"][0]
                    if isinstance(item, dict):
                        if "answer" in item and isinstance(item["answer"], dict):
                            structured_data = item["answer"]
                            logger.info(f"Found structured data in 'items[0].answer' field: {structured_data}")
                            return structured_data
            
            # If we couldn't find structured data, return empty dict
            if not structured_data:
                logger.warning("Could not find structured data in response")
            
            return structured_data
        
        # Process a single file
        def process_file(file):
            try:
                file_id = file["id"]
                file_name = file["name"]
                
                logger.info(f"Processing file: {file_name} (ID: {file_id})")
                st.session_state.debug_info.append(f"Processing file: {file_name} (ID: {file_id})")
                
                # Check if we have feedback data for this file
                feedback_key = f"{file_id}_{st.session_state.metadata_config['extraction_method']}"
                has_feedback = feedback_key in st.session_state.feedback_data
                
                if has_feedback:
                    logger.info(f"Using feedback data for file: {file_name}")
                    st.session_state.debug_info.append(f"Using feedback data for file: {file_name}")
                
                # Determine extraction method
                if st.session_state.metadata_config["extraction_method"] == "structured":
                    # Structured extraction
                    if st.session_state.metadata_config["use_template"]:
                        # Template-based extraction
                        template_id = st.session_state.metadata_config["template_id"]
                        metadata_template = {
                            "template_key": template_id,
                            "scope": "enterprise",  # Default to enterprise scope
                            "type": "metadata_template"
                        }
                        
                        logger.info(f"Using template-based extraction with template ID: {template_id}")
                        st.session_state.debug_info.append(f"Using template-based extraction with template ID: {template_id}")
                        
                        # Use real API call
                        api_result = extraction_functions["extract_structured_metadata"](
                            file_id=file_id,
                            metadata_template=metadata_template,
                            ai_model=st.session_state.metadata_config["ai_model"]
                        )
                        
                        # Create a clean result object with the extracted data
                        result = {}
                        
                        # Copy fields from API result to our result object
                        if isinstance(api_result, dict):
                            for key, value in api_result.items():
                                if key not in ["error", "items", "response"]:
                                    result[key] = value
                        
                        # Apply feedback if available
                        if has_feedback:
                            feedback = st.session_state.feedback_data[feedback_key]
                            # Merge feedback with result, prioritizing feedback
                            for key, value in feedback.items():
                                result[key] = value
                    else:
                        # Custom fields extraction
                        logger.info(f"Using custom fields extraction with {len(st.session_state.metadata_config['custom_fields'])} fields")
                        st.session_state.debug_info.append(f"Using custom fields extraction with {len(st.session_state.metadata_config['custom_fields'])} fields")
                        
                        # Use real API call
                        api_result = extraction_functions["extract_structured_metadata"](
                            file_id=file_id,
                            fields=st.session_state.metadata_config["custom_fields"],
                            ai_model=st.session_state.metadata_config["ai_model"]
                        )
                        
                        # Create a clean result object with the extracted data
                        result = {}
                        
                        # Copy fields from API result to our result object
                        if isinstance(api_result, dict):
                            for key, value in api_result.items():
                                if key not in ["error", "items", "response"]:
                                    result[key] = value
                        
                        # Apply feedback if available
                        if has_feedback:
                            feedback = st.session_state.feedback_data[feedback_key]
                            # Merge feedback with result, prioritizing feedback
                            for key, value in feedback.items():
                                result[key] = value
                else:
                    # Freeform extraction
                    logger.info(f"Using freeform extraction with prompt: {st.session_state.metadata_config['freeform_prompt'][:30]}...")
                    st.session_state.debug_info.append(f"Using freeform extraction with prompt: {st.session_state.metadata_config['freeform_prompt'][:30]}...")
                    
                    # Use real API call
                    api_result = extraction_functions["extract_freeform_metadata"](
                        file_id=file_id,
                        prompt=st.session_state.metadata_config["freeform_prompt"],
                        ai_model=st.session_state.metadata_config["ai_model"]
                    )
                    
                    # Extract structured data from the API response
                    structured_data = extract_structured_data_from_response(api_result)
                    
                    # Create a clean result object with the structured data
                    result = structured_data
                    
                    # If no structured data was found, include the raw response for debugging
                    if not structured_data and isinstance(api_result, dict):
                        result["_raw_response"] = api_result
                    
                    # Apply feedback if available
                    if has_feedback:
                        feedback = st.session_state.feedback_data[feedback_key]
                        # For freeform, we might have feedback on key-value pairs
                        for key, value in feedback.items():
                            result[key] = value
                
                # Check for errors
                if isinstance(api_result, dict) and "error" in api_result:
                    logger.error(f"Error processing file {file_name}: {api_result['error']}")
                    st.session_state.debug_info.append(f"Error processing file {file_name}: {api_result['error']}")
                    return {
                        "file_id": file_id,
                        "file_name": file_name,
                        "success": False,
                        "error": api_result["error"]
                    }
                
                # Collect visualization data
                if st.session_state.metadata_config["extraction_method"] == "structured":
                    # For structured extraction, track field extraction success rates
                    if "visualization_data" not in st.session_state.processing_state:
                        st.session_state.processing_state["visualization_data"] = {"field_success": {}}
                    
                    for field_key, value in result.items():
                        if field_key not in st.session_state.processing_state["visualization_data"]["field_success"]:
                            st.session_state.processing_state["visualization_data"]["field_success"][field_key] = {"success": 0, "total": 0}
                        
                        st.session_state.processing_state["visualization_data"]["field_success"][field_key]["total"] += 1
                        if value and value.strip() if isinstance(value, str) else value:
                            st.session_state.processing_state["visualization_data"]["field_success"][field_key]["success"] += 1
                
                logger.info(f"Successfully processed file: {file_name}")
                st.session_state.debug_info.append(f"Successfully processed file: {file_name}")
                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "success": True,
                    "result": result
                }
            
            except Exception as e:
                logger.exception(f"Exception processing file {file['name']}: {str(e)}")
                st.session_state.debug_info.append(f"Exception processing file {file['name']}: {str(e)}")
                return {
                    "file_id": file["id"],
                    "file_name": file["name"],
                    "success": False,
                    "error": str(e)
                }
        
        # Handle start button click
        if start_button:
            logger.info("Start processing button clicked")
            st.session_state.debug_info.append("Start processing button clicked")
            
            # Reset processing state
            st.session_state.processing_state = {
                "is_processing": True,
                "processed_files": 0,
                "total_files": len(st.session_state.selected_files),
                "current_file_index": 0,
                "current_file": st.session_state.selected_files[0]["name"] if st.session_state.selected_files else "",
                "results": {},
                "errors": {},
                "retries": {},
                "max_retries": st.session_state.processing_state.get("max_retries", 3),
                "retry_delay": st.session_state.processing_state.get("retry_delay", 2),
                "processing_mode": st.session_state.processing_state.get("processing_mode", "Sequential"),
                "visualization_data": {}
            }
            st.rerun()
        
        # Handle cancel button click
        if cancel_button:
            logger.info("Cancel processing button clicked")
            st.session_state.debug_info.append("Cancel processing button clicked")
            st.session_state.processing_state["is_processing"] = False
            st.warning("Processing cancelled.")
        
        # Process next file if in processing state
        if st.session_state.processing_state["is_processing"]:
            current_index = st.session_state.processing_state["current_file_index"]
            
            if current_index < len(st.session_state.selected_files):
                # Get current file
                current_file = st.session_state.selected_files[current_index]
                st.session_state.processing_state["current_file"] = current_file["name"]
                
                # Process the file
                logger.info(f"Processing file {current_index + 1} of {len(st.session_state.selected_files)}: {current_file['name']}")
                st.session_state.debug_info.append(f"Processing file {current_index + 1} of {len(st.session_state.selected_files)}: {current_file['name']}")
                
                result = process_file(current_file)
                
                if result["success"]:
                    # Store success result
                    st.session_state.processing_state["results"][result["file_id"]] = {
                        "file_name": result["file_name"],
                        "file_id": result["file_id"],
                        "result": result["result"]
                    }
                else:
                    # Check if we should retry
                    file_id = result["file_id"]
                    if file_id not in st.session_state.processing_state["retries"]:
                        st.session_state.processing_state["retries"][file_id] = 0
                    
                    if st.session_state.processing_state["retries"][file_id] < st.session_state.processing_state["max_retries"]:
                        # Increment retry count
                        st.session_state.processing_state["retries"][file_id] += 1
                        
                        # Log retry
                        retry_count = st.session_state.processing_state["retries"][file_id]
                        logger.info(f"Retrying file {result['file_name']} (Attempt {retry_count} of {st.session_state.processing_state['max_retries']})")
                        st.session_state.debug_info.append(f"Retrying file {result['file_name']} (Attempt {retry_count} of {st.session_state.processing_state['max_retries']})")
                        
                        # Wait before retrying
                        time.sleep(st.session_state.processing_state["retry_delay"])
                        
                        # Don't increment the index, so we'll retry this file
                        st.rerun()
                        return
                    else:
                        # Store error result after max retries
                        st.session_state.processing_state["errors"][file_id] = {
                            "file_name": result["file_name"],
                            "file_id": file_id,
                            "error": result["error"],
                            "retries": st.session_state.processing_state["retries"][file_id]
                        }
                
                # Increment processed files count
                st.session_state.processing_state["processed_files"] += 1
                
                # Move to next file
                st.session_state.processing_state["current_file_index"] += 1
                
                # Check if we're done
                if st.session_state.processing_state["current_file_index"] >= len(st.session_state.selected_files):
                    st.session_state.processing_state["is_processing"] = False
                    logger.info("Processing complete")
                    st.session_state.debug_info.append("Processing complete")
                
                # Update extraction results in session state
                st.session_state.extraction_results = st.session_state.processing_state["results"]
                
                # Rerun to process next file or show results
                st.rerun()
            else:
                # All files processed
                st.session_state.processing_state["is_processing"] = False
        
        # Display progress
        with progress_container:
            if st.session_state.processing_state["is_processing"]:
                # Display progress bar
                progress = st.progress(st.session_state.processing_state["processed_files"] / st.session_state.processing_state["total_files"])
                
                # Display current file
                st.write(f"Processing file {st.session_state.processing_state['current_file_index'] + 1} of {st.session_state.processing_state['total_files']}: {st.session_state.processing_state['current_file']}")
            elif st.session_state.processing_state["processed_files"] > 0:
                # Processing complete
                st.success(f"Processing complete! Processed {st.session_state.processing_state['processed_files']} files.")
                
                # Display success/error counts
                success_count = len(st.session_state.processing_state["results"])
                error_count = len(st.session_state.processing_state["errors"])
                
                st.write(f"Successfully processed: {success_count} files")
                st.write(f"Errors: {error_count} files")
                
                # Display processing complete message
                st.write("Processing complete!")
                
                # Display results summary
                st.subheader("Results Summary")
                
                # Create tabs for different views
                tab1, tab2, tab3 = st.tabs(["Processing Complete", "View Errors", "Provide Feedback on Results"])
                
                with tab1:
                    st.write(f"Successfully processed: {success_count} of {st.session_state.processing_state['total_files']} files")
                
                with tab2:
                    if error_count > 0:
                        for file_id, error_data in st.session_state.processing_state["errors"].items():
                            with st.expander(f"{error_data['file_name']} (Retries: {error_data['retries']})"):
                                st.write(f"**Error:** {error_data['error']}")
                    else:
                        st.info("No errors occurred during processing")
                
                with tab3:
                    st.write("#### Provide Feedback on Results")
                    st.write("Select a file to provide feedback on the extraction results:")
                    
                    if success_count > 0:
                        # Create a selectbox for files
                        file_options = [(file_id, data["file_name"]) for file_id, data in st.session_state.processing_state["results"].items()]
                        selected_file_id, selected_file_name = st.selectbox(
                            "Select File",
                            options=file_options,
                            format_func=lambda x: x[1],
                            key="feedback_file_select"
                        )
                        
                        if selected_file_id:
                            # Display current extraction results
                            st.write(f"**Current extraction results for {selected_file_name}:**")
                            
                            result_data = st.session_state.processing_state["results"][selected_file_id]["result"]
                            
                            # Create a form for feedback
                            with st.form(key="feedback_form"):
                                feedback_data = {}
                                
                                # For all extraction methods, show each field
                                for field_key, field_value in result_data.items():
                                    # Skip internal fields
                                    if field_key.startswith("_"):
                                        continue
                                        
                                    # Create editable fields
                                    if isinstance(field_value, list):
                                        # For multiSelect fields
                                        feedback_data[field_key] = st.multiselect(
                                            field_key,
                                            options=field_value + ["Option 1", "Option 2", "Option 3"],
                                            default=field_value
                                        )
                                    else:
                                        # For other field types
                                        feedback_data[field_key] = st.text_input(field_key, value=field_value)
                                
                                # Allow adding new key-value pairs
                                st.write("**Add new key-value pair:**")
                                new_key = st.text_input("Key")
                                new_value = st.text_input("Value")
                                
                                if new_key and new_value:
                                    feedback_data[new_key] = new_value
                                
                                # Submit button
                                submit_button = st.form_submit_button("Submit Feedback")
                                
                                if submit_button:
                                    # Store feedback
                                    feedback_key = f"{selected_file_id}_{st.session_state.metadata_config['extraction_method']}"
                                    st.session_state.feedback_data[feedback_key] = feedback_data
                                    
                                    # Update results
                                    for field_key, field_value in feedback_data.items():
                                        st.session_state.processing_state["results"][selected_file_id]["result"][field_key] = field_value
                                    
                                    # Update extraction results in session state
                                    st.session_state.extraction_results = st.session_state.processing_state["results"]
                                    
                                    st.success("Feedback submitted successfully!")
                    else:
                        st.info("No successful extractions to provide feedback on")
                
                # Continue button
                if st.button("Continue to View Results", use_container_width=True):
                    st.session_state.current_page = "View Results"
                    st.rerun()
        
        # Debug information
        with st.expander("Debug Information"):
            if st.button("Clear Debug Info"):
                st.session_state.debug_info = []
                st.rerun()
            
            for i, info in enumerate(reversed(st.session_state.debug_info[-50:])):
                st.write(f"{len(st.session_state.debug_info) - i}. {info}")
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.exception(e)
