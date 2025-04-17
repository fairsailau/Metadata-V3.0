import streamlit as st
# Set page config (must be the first Streamlit command)
st.set_page_config(
    page_title="Box AI Metadata Extraction",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

import os
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Import modules
from modules.authentication import authenticate
from modules.file_browser import file_browser
from modules.metadata_config import metadata_config
from modules.processing import process_files
from modules.results_viewer import view_results
#from modules.metadata_application import apply_metadata
from modules.direct_metadata_application_enhanced import apply_metadata_direct as apply_metadata


# Centralized session state initialization
def initialize_session_state():
    """
    Initialize all session state variables in a centralized function
    to ensure consistency across the application
    """
    # Core session state variables
    if not hasattr(st.session_state, "authenticated"):
        st.session_state.authenticated = False
        logger.info("Initialized authenticated in session state")
    
    if not hasattr(st.session_state, "client"):
        st.session_state.client = None
        logger.info("Initialized client in session state")
    
    if not hasattr(st.session_state, "current_page"):
        st.session_state.current_page = "Home"
        logger.info("Initialized current_page in session state")
    
    # File selection and processing variables
    if not hasattr(st.session_state, "selected_files"):
        st.session_state.selected_files = []
        logger.info("Initialized selected_files in session state")
    
    # Metadata configuration
    if not hasattr(st.session_state, "metadata_config"):
        st.session_state.metadata_config = {
            "extraction_method": "freeform",
            "freeform_prompt": "Extract key metadata from this document including dates, names, amounts, and other important information.",
            "use_template": False,
            "template_id": "",
            "custom_fields": [],
            "ai_model": "azure__openai__gpt_4o_mini",
            "batch_size": 5
        }
        logger.info("Initialized metadata_config in session state")
    
    # Extraction results
    if not hasattr(st.session_state, "extraction_results"):
        st.session_state.extraction_results = {}
        logger.info("Initialized extraction_results in session state")
    
    # Selected results for metadata application - FIXED: Use direct attribute assignment
    if not hasattr(st.session_state, "selected_result_ids"):
        st.session_state.selected_result_ids = []
        logger.info("Initialized selected_result_ids in session state")
    
    # Application state for metadata application
    if not hasattr(st.session_state, "application_state"):
        st.session_state.application_state = {
            "is_applying": False,
            "applied_files": 0,
            "total_files": 0,
            "current_batch": [],
            "results": {},
            "errors": {}
        }
        logger.info("Initialized application_state in session state")
    
    # Processing state for file processing
    if not hasattr(st.session_state, "processing_state"):
        st.session_state.processing_state = {
            "is_processing": False,
            "processed_files": 0,
            "total_files": 0,
            "current_file_index": -1,
            "current_file": "",
            "results": {},
            "errors": {},
            "retries": {},
            "max_retries": 3,
            "retry_delay": 2,
            "visualization_data": {}
        }
        logger.info("Initialized processing_state in session state")
    
    # Debug information
    if not hasattr(st.session_state, "debug_info"):
        st.session_state.debug_info = []
        logger.info("Initialized debug_info in session state")
    
    # Metadata templates
    if not hasattr(st.session_state, "metadata_templates"):
        st.session_state.metadata_templates = {}
        logger.info("Initialized metadata_templates in session state")
    
    # Feedback data
    if not hasattr(st.session_state, "feedback_data"):
        st.session_state.feedback_data = {}
        logger.info("Initialized feedback_data in session state")

# Initialize session state
initialize_session_state()

# Navigation function
def navigate_to(page):
    st.session_state.current_page = page
    logger.info(f"Navigated to page: {page}")

# Sidebar navigation
with st.sidebar:
    st.title("Box AI Metadata")
    
    # Show navigation only if authenticated
    if hasattr(st.session_state, "authenticated") and st.session_state.authenticated:
        st.subheader("Navigation")
        
        if st.button("Home", use_container_width=True):
            navigate_to("Home")
        
        if st.button("File Browser", use_container_width=True):
            navigate_to("File Browser")
            
        if st.button("Metadata Configuration", use_container_width=True):
            navigate_to("Metadata Configuration")
            
        if st.button("Process Files", use_container_width=True):
            navigate_to("Process Files")
            
        if st.button("View Results", use_container_width=True):
            navigate_to("View Results")
            
        if st.button("Apply Metadata", use_container_width=True):
            navigate_to("Apply Metadata")
        
        # Logout button
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.client = None
            navigate_to("Home")
            st.rerun()
    
    # Show app info
    st.subheader("About")
    st.info(
        "This app connects to Box.com and uses Box AI API "
        "to extract metadata from files and apply it at scale."
    )

# Main content area
if not hasattr(st.session_state, "authenticated") or not st.session_state.authenticated:
    # Authentication page
    authenticate()
else:
    # Display current page based on navigation
    if not hasattr(st.session_state, "current_page") or st.session_state.current_page == "Home":
        st.title("Box AI Metadata Extraction")
        
        st.write("""
        ## Welcome to Box AI Metadata Extraction App
        
        This application helps you extract metadata from your Box files using Box AI API 
        and apply it at scale. Follow these steps to get started:
        
        1. Use the **File Browser** to select files for processing
        2. Configure metadata extraction parameters in **Metadata Configuration**
        3. Process your files in the **Process Files** section
        4. Review the results in the **View Results** section
        5. Apply the extracted metadata in the **Apply Metadata** section
        """)
        
        # Quick actions
        st.subheader("Quick Actions")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Browse Files", use_container_width=True):
                navigate_to("File Browser")
                st.rerun()
        
        with col2:
            if st.button("Configure Metadata", use_container_width=True):
                navigate_to("Metadata Configuration")
                st.rerun()
        
        with col3:
            if st.button("View Results", use_container_width=True):
                navigate_to("View Results")
                st.rerun()
    
    elif st.session_state.current_page == "File Browser":
        file_browser()
    
    elif st.session_state.current_page == "Metadata Configuration":
        metadata_config()
    
    elif st.session_state.current_page == "Process Files":
        process_files()
    
    elif st.session_state.current_page == "View Results":
        view_results()
    
    elif st.session_state.current_page == "Apply Metadata":
        apply_metadata()
