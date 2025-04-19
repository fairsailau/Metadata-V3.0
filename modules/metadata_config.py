import streamlit as st
from typing import Dict, List, Any
import json

def metadata_config():
    """
    Configure metadata extraction parameters
    """
    st.title("Metadata Configuration")
    
    if not st.session_state.authenticated or not st.session_state.client:
        st.error("Please authenticate with Box first")
        return
    
    if not st.session_state.selected_files:
        st.warning("No files selected. Please select files in the File Browser first.")
        if st.button("Go to File Browser"):
            st.session_state.current_page = "File Browser"
            st.rerun()
        return
    
    st.write("Configure how metadata should be extracted from your selected files.")
    
    # Initialize session state for metadata configuration
    if "metadata_config" not in st.session_state:
        st.session_state.metadata_config = {
            "extraction_method": "structured",
            "use_template": False,
            "template_id": "",
            "custom_fields": []
        }
    
    # Extraction method selection
    st.subheader("Extraction Method")
    extraction_method = st.radio(
        "Select extraction method:",
        options=["Structured", "Freeform"],
        index=0 if st.session_state.metadata_config["extraction_method"] == "structured" else 1,
        help="Structured extraction uses predefined fields. Freeform extraction uses a prompt to extract metadata."
    )
    
    st.session_state.metadata_config["extraction_method"] = extraction_method.lower()
    
    # Structured extraction configuration
    if st.session_state.metadata_config["extraction_method"] == "structured":
        st.subheader("Structured Extraction Configuration")
        
        # Option to use existing template or custom fields
        use_template = st.checkbox(
            "Use existing metadata template",
            value=st.session_state.metadata_config["use_template"],
            help="Select an existing metadata template or define custom fields"
        )
        
        st.session_state.metadata_config["use_template"] = use_template
        
        if use_template:
            # Template selection
            st.write("#### Select Metadata Template")
            
            # In a real app, we would fetch templates from Box
            # For now, we'll use a placeholder dropdown
            template_options = [
                {"id": "template1", "name": "Invoice Template"},
                {"id": "template2", "name": "Contract Template"},
                {"id": "template3", "name": "Employee Record"}
            ]
            
            template_names = [t["name"] for t in template_options]
            selected_template_index = 0
            
            for i, template in enumerate(template_options):
                if template["id"] == st.session_state.metadata_config["template_id"]:
                    selected_template_index = i
                    break
            
            selected_template = st.selectbox(
                "Select a template:",
                options=template_names,
                index=selected_template_index
            )
            
            # Update template ID in session state
            for template in template_options:
                if template["name"] == selected_template:
                    st.session_state.metadata_config["template_id"] = template["id"]
                    break
            
            # Display template details (placeholder)
            st.write(f"Template: {selected_template}")
            st.write("Template fields would be displayed here in a real app.")
            
        else:
            # Custom fields definition
            st.write("#### Define Custom Fields")
            st.write("Define the fields you want to extract from your files.")
            
            # Add new field button
            if st.button("Add Field"):
                st.session_state.metadata_config["custom_fields"].append({
                    "key": f"field_{len(st.session_state.metadata_config['custom_fields'])}",
                    "display_name": "",
                    "description": "",
                    "prompt": "",
                    "type": "string",
                    "options": []
                })
            
            # Display and edit fields
            for i, field in enumerate(st.session_state.metadata_config["custom_fields"]):
                with st.expander(f"Field {i+1}: {field['display_name'] or 'New Field'}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        field["key"] = st.text_input("Field Key (unique identifier)", 
                                                    value=field["key"], 
                                                    key=f"key_{i}")
                        
                        field["display_name"] = st.text_input("Display Name", 
                                                            value=field["display_name"], 
                                                            key=f"display_{i}")
                    
                    with col2:
                        field["type"] = st.selectbox("Field Type", 
                                                    options=["string", "date", "float", "multiSelect"], 
                                                    index=["string", "date", "float", "multiSelect"].index(field["type"]),
                                                    key=f"type_{i}")
                    
                    field["description"] = st.text_area("Description", 
                                                      value=field["description"], 
                                                      key=f"desc_{i}")
                    
                    field["prompt"] = st.text_area("Extraction Prompt (instructions for AI)", 
                                                 value=field["prompt"], 
                                                 key=f"prompt_{i}")
                    
                    # Options for multiSelect type
                    if field["type"] == "multiSelect":
                        st.write("Options (one per line):")
                        options_text = "\n".join([opt["key"] for opt in field["options"]])
                        new_options_text = st.text_area("Options", 
                                                      value=options_text, 
                                                      key=f"options_{i}")
                        
                        # Update options if changed
                        if new_options_text != options_text:
                            field["options"] = [{"key": opt.strip()} for opt in new_options_text.split("\n") if opt.strip()]
                    
                    # Remove field button
                    if st.button("Remove Field", key=f"remove_{i}"):
                        st.session_state.metadata_config["custom_fields"].pop(i)
                        st.rerun()
    
    # Freeform extraction configuration
    else:
        st.subheader("Freeform Extraction Configuration")
        
        if "freeform_prompt" not in st.session_state.metadata_config:
            st.session_state.metadata_config["freeform_prompt"] = ""
        
        st.session_state.metadata_config["freeform_prompt"] = st.text_area(
            "Extraction Prompt",
            value=st.session_state.metadata_config["freeform_prompt"],
            height=150,
            help="Provide instructions for the AI on what metadata to extract from the files."
        )
        
        st.info("Example prompt: Extract the following information from this document: vendor name, invoice number, date, total amount, and line items.")
    
    # AI model configuration
    st.subheader("AI Model Configuration")
    
    if "ai_model" not in st.session_state.metadata_config:
        st.session_state.metadata_config["ai_model"] = "azure__openai__gpt_4o_mini"
    
    st.session_state.metadata_config["ai_model"] = st.selectbox(
        "Select AI Model",
        options=["azure__openai__gpt_4o_mini", "azure__openai__gpt_4o", "anthropic__claude_3_haiku"],
        index=["azure__openai__gpt_4o_mini", "azure__openai__gpt_4o", "anthropic__claude_3_haiku"].index(st.session_state.metadata_config["ai_model"])
    )
    
    # Batch processing configuration
    st.subheader("Batch Processing Configuration")
    
    if "batch_size" not in st.session_state.metadata_config:
        st.session_state.metadata_config["batch_size"] = 5
    
    st.session_state.metadata_config["batch_size"] = st.slider(
        "Batch Size",
        min_value=1,
        max_value=25,
        value=st.session_state.metadata_config["batch_size"],
        help="Number of files to process in parallel. Maximum is 25."
    )
    
    # Continue button
    st.write("---")
    if st.button("Continue to Processing", use_container_width=True):
        # Validate configuration
        if st.session_state.metadata_config["extraction_method"] == "structured" and not st.session_state.metadata_config["use_template"] and not st.session_state.metadata_config["custom_fields"]:
            st.error("Please define at least one field for structured extraction.")
        elif st.session_state.metadata_config["extraction_method"] == "freeform" and not st.session_state.metadata_config["freeform_prompt"]:
            st.error("Please provide a prompt for freeform extraction.")
        else:
            st.session_state.current_page = "Process Files"
            st.rerun()
    
    # Debug information (can be removed in production)
    with st.expander("Debug: Current Configuration"):
        st.json(st.session_state.metadata_config)
