import streamlit as st
import requests
import json
import os
import uuid
from datetime import datetime, date 
import pandas as pd 
import io 

# --- Configuration ---
COMPANIES_FILE = "companies.json"
ALERTS_FILE = "alerts.json"
RANSOMWARE_API_URL = "https://api.ransomware.live/v2/recentcyberattacks" 

# --- Helper Functions for Data Persistence ---

def load_data(file_path):
    """Loads data from a JSON file."""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            st.error(f"Error decoding JSON from {file_path}. Starting with empty data.")
            return []
        except Exception as e:
            st.error(f"Error loading {file_path}: {e}")
            return []
    return []

def save_data(file_path, data):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        st.error(f"Error saving data to {file_path}: {e}")

# --- Initialize Session State ---
if 'companies' not in st.session_state:
    st.session_state.companies = load_data(COMPANIES_FILE)

if 'alerts' not in st.session_state:
    st.session_state.alerts = load_data(ALERTS_FILE)

if 'selected_alerts' not in st.session_state: 
    st.session_state.selected_alerts = {}

if 'ui_selected_date_range_label' not in st.session_state:
    st.session_state.ui_selected_date_range_label = "Last 7 Days" 

if 'editing_company_id' not in st.session_state: # To track which company is being edited
    st.session_state.editing_company_id = None

# --- Page: Add/Manage Company ---
def manage_companies_page():
    st.header("Manage Monitored Companies")

    # --- Section: Add New Company (Only if not editing) ---
    if st.session_state.editing_company_id is None:
        st.subheader("Add New Company")
        with st.form("new_company_form", clear_on_submit=True):
            company_name = st.text_input("Company Name*", help="Unique name for the company.")
            company_description = st.text_area("Description", help="Brief description of the company.")
            keywords_str = st.text_input("Keywords (manual entry)", help="Comma-separated list of keywords.")
            uploaded_file = st.file_uploader("Or Upload Keywords CSV", type="csv", help="CSV file with one keyword per row (uses the first column).")

            submitted_new = st.form_submit_button("Add Company")

            if submitted_new:
                if not company_name:
                    st.error("Company Name is required.")
                else:
                    manual_keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
                    csv_keywords = []
                    if uploaded_file is not None:
                        try:
                            stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
                            df = pd.read_csv(stringio, header=None) 
                            if not df.empty:
                                csv_keywords = [str(kw).strip().lower() for kw in df.iloc[:, 0].tolist() if str(kw).strip()]
                            st.info(f"Read {len(csv_keywords)} keywords from uploaded CSV for new company.")
                        except Exception as e:
                            st.error(f"Error processing CSV file for new company: {e}")
                    
                    all_keywords = sorted(list(set(manual_keywords + csv_keywords)))

                    if not all_keywords:
                        st.error("Please provide at least one keyword (manually or via CSV).")
                    elif any(c['name'].lower() == company_name.lower() for c in st.session_state.companies):
                        st.warning(f"Company '{company_name}' already exists.")
                    else:
                        new_company = {
                            "id": str(uuid.uuid4()), 
                            "name": company_name,
                            "description": company_description,
                            "keywords": all_keywords
                        }
                        st.session_state.companies.append(new_company)
                        save_data(COMPANIES_FILE, st.session_state.companies)
                        st.success(f"Company '{company_name}' added with {len(all_keywords)} keywords.")
                        st.rerun() 

    # --- Section: Edit Existing Company ---
    if st.session_state.editing_company_id is not None:
        company_to_edit_index = next((i for i, c in enumerate(st.session_state.companies) if c['id'] == st.session_state.editing_company_id), None)
        
        if company_to_edit_index is not None:
            company_to_edit = st.session_state.companies[company_to_edit_index]
            st.subheader(f"Edit Company: {company_to_edit['name']}")

            # Display current keywords with delete buttons (outside the main form for edit)
            st.markdown("**Current Keywords:**")
            if company_to_edit['keywords']:
                keywords_copy = list(company_to_edit['keywords']) # Iterate over a copy for safe removal
                for kw_idx, keyword_to_delete in enumerate(keywords_copy):
                    col_kw, col_del_btn = st.columns([0.85, 0.15])
                    with col_kw:
                        st.markdown(f"- `{keyword_to_delete}`")
                    with col_del_btn:
                        if st.button("Del", key=f"del_kw_{company_to_edit['id']}_{keyword_to_delete.replace(' ', '_')}_{kw_idx}"):
                            try:
                                original_list_idx = st.session_state.companies[company_to_edit_index]['keywords'].index(keyword_to_delete)
                                st.session_state.companies[company_to_edit_index]['keywords'].pop(original_list_idx)
                                save_data(COMPANIES_FILE, st.session_state.companies)
                                st.success(f"Keyword '{keyword_to_delete}' removed.")
                                st.rerun()
                            except ValueError:
                                st.warning(f"Keyword '{keyword_to_delete}' already removed or not found.") 
                                st.rerun()
            else:
                st.info("No keywords currently for this company.")
            st.markdown("---")


            # Form for editing name, description, and adding new keywords
            with st.form(key=f"edit_company_details_form_{company_to_edit['id']}"):
                edited_name = st.text_input("Company Name*", value=company_to_edit['name'])
                edited_description = st.text_area("Description", value=company_to_edit.get('description', ''))
                
                st.markdown("**Add New Keywords:**")
                new_keywords_str = st.text_input("Add Keywords (manual entry)", key=f"add_kw_manual_{company_to_edit['id']}")
                new_uploaded_file = st.file_uploader("Or Upload New Keywords CSV", type="csv", key=f"add_kw_csv_{company_to_edit['id']}")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    submitted_save = st.form_submit_button("Save Changes")
                with col_cancel:
                    submitted_cancel = st.form_submit_button("Cancel")
                
                if submitted_save:
                    if not edited_name:
                        st.error("Company Name cannot be empty.")
                    elif edited_name.lower() != company_to_edit['name'].lower() and \
                         any(c['name'].lower() == edited_name.lower() and c['id'] != company_to_edit['id'] for c in st.session_state.companies):
                        st.error(f"Another company with the name '{edited_name}' already exists.")
                    else:
                        st.session_state.companies[company_to_edit_index]['name'] = edited_name
                        st.session_state.companies[company_to_edit_index]['description'] = edited_description
                        
                        manual_new_kws = [kw.strip().lower() for kw in new_keywords_str.split(',') if kw.strip()]
                        csv_new_kws = []
                        if new_uploaded_file is not None:
                            try:
                                stringio_edit = io.StringIO(new_uploaded_file.getvalue().decode("utf-8"))
                                df_edit = pd.read_csv(stringio_edit, header=None)
                                if not df_edit.empty:
                                    csv_new_kws = [str(kw).strip().lower() for kw in df_edit.iloc[:, 0].tolist() if str(kw).strip()]
                                st.info(f"Read {len(csv_new_kws)} new keywords from uploaded CSV for editing.")
                            except Exception as e:
                                st.error(f"Error processing new CSV file during edit: {e}")
                        
                        st.session_state.companies[company_to_edit_index]['keywords'].extend(manual_new_kws)
                        st.session_state.companies[company_to_edit_index]['keywords'].extend(csv_new_kws)
                        st.session_state.companies[company_to_edit_index]['keywords'] = sorted(list(set(st.session_state.companies[company_to_edit_index]['keywords'])))
                        
                        save_data(COMPANIES_FILE, st.session_state.companies)
                        st.success(f"Company '{edited_name}' updated.")
                        st.session_state.editing_company_id = None 
                        st.rerun()

                if submitted_cancel:
                    st.session_state.editing_company_id = None
                    st.rerun()
        else: 
            st.session_state.editing_company_id = None 
            st.rerun()


    # --- Section: Display Current Monitored Companies (if not adding/editing) ---
    if st.session_state.editing_company_id is None:
        st.subheader("Current Monitored Companies")
        if not st.session_state.companies:
            st.info("No companies are currently being monitored. Add one above.")
        else:
            for i, company in enumerate(st.session_state.companies):
                container = st.container()
                col1, col2, col3 = container.columns([0.7, 0.15, 0.15])

                with col1:
                    keywords_display = ", ".join(company['keywords'])
                    if len(keywords_display) > 70: 
                        keywords_display = keywords_display[:70] + "..."
                    st.markdown(f"**{company['name']}**")
                    if company.get('description'):
                        st.caption(f"Desc: {company['description'][:50]}{'...' if len(company['description']) > 50 else ''}")
                    st.caption(f"Keywords: {keywords_display if company['keywords'] else 'None'}")
                
                with col2:
                    if st.button("Edit", key=f"edit_{company['id']}"):
                        st.session_state.editing_company_id = company['id']
                        st.rerun()
                with col3:
                    if st.button("Remove", key=f"remove_{company['id']}"):
                        st.session_state.companies.pop(i)
                        save_data(COMPANIES_FILE, st.session_state.companies)
                        st.session_state.alerts = [
                            alert for alert in st.session_state.alerts
                            if alert['company_id'] != company['id']
                        ]
                        st.session_state.selected_alerts = {
                            k: v for k, v in st.session_state.selected_alerts.items()
                            if not any(a['id'] == k and a['company_id'] == company['id'] for a in st.session_state.alerts) 
                        }
                        save_data(ALERTS_FILE, st.session_state.alerts)
                        st.success(f"Company '{company['name']}' and its alerts removed.")
                        st.rerun()
                st.markdown("---")


# --- Page: Check Ransomware API & Manage Alerts ---
def check_api_page():
    st.header("Check for Compromises & Manage Alerts")

    date_range_options = {
        "Last 7 Days": 7,
        "Last 30 Days": 30,
        "Last 60 Days": 60,
        "Last 90 Days": 90,
        "All Time": None 
    }

    def date_filter_changed_callback():
        st.session_state.ui_selected_date_range_label = st.session_state.actual_date_filter_selector_key
    
    st.selectbox(
        "Filter Alerts by Date Range:",
        options=list(date_range_options.keys()),
        index=list(date_range_options.keys()).index(st.session_state.ui_selected_date_range_label),
        key="actual_date_filter_selector_key", 
        on_change=date_filter_changed_callback
    )
    days_to_filter_for_new_and_display = date_range_options[st.session_state.ui_selected_date_range_label]


    if not st.session_state.companies:
        st.warning("No companies configured to monitor. Please add companies on the 'Manage Companies' page.")
        return

    if st.button("Fetch New Ransomware Data & Check for Matches", type="primary"):
        response = None 
        with st.spinner("Fetching data from ransomware.live API... (This may take a moment)"):
            try:
                response = requests.get(RANSOMWARE_API_URL, timeout=60) 
                response.raise_for_status() 
                api_data = response.json()
                st.success(f"Successfully fetched {len(api_data)} entries from the API.")

                new_alerts_found = 0
                for company in st.session_state.companies:
                    for keyword in company['keywords']:
                        for entry in api_data:
                            api_entry_date_str = entry.get("date")
                            if not api_entry_date_str or api_entry_date_str == "N/A":
                                if days_to_filter_for_new_and_display is not None:
                                    continue 
                            else:
                                try:
                                    api_entry_date_obj = datetime.strptime(api_entry_date_str, "%Y-%m-%d").date()
                                    if days_to_filter_for_new_and_display is not None:
                                        cutoff_date = date.today() - pd.Timedelta(days=days_to_filter_for_new_and_display)
                                        if api_entry_date_obj < cutoff_date:
                                            continue 
                                except ValueError:
                                    st.warning(f"Could not parse date '{api_entry_date_str}' for new alert from entry: {entry.get('title', 'Unknown')}. Skipping date filter for this entry.")
                                    if days_to_filter_for_new_and_display is not None:
                                         continue


                            victim_name_api = entry.get("victim", "").lower()
                            article_title_api = entry.get("title", "").lower()
                            domain_api = entry.get("domain", "").lower() 

                            match_found_in_victim = keyword in victim_name_api if victim_name_api else False
                            match_found_in_title = keyword in article_title_api if article_title_api else False
                            match_found_in_domain = keyword in domain_api if domain_api else False 
                            
                            display_victim_name = entry.get("victim", entry.get("title", "N/A"))

                            if match_found_in_victim or match_found_in_title or match_found_in_domain: 
                                entry_identifier = entry.get("link", str(uuid.uuid4())) 

                                alert_exists = False
                                for existing_alert in st.session_state.alerts:
                                    if (existing_alert['company_id'] == company['id'] and
                                        existing_alert['matched_keyword'] == keyword and
                                        existing_alert['api_entry_id'] == entry_identifier):
                                        alert_exists = True
                                        break
                                
                                if not alert_exists:
                                    alert_id = str(uuid.uuid4())
                                    gang_name = entry.get("claim_gang")
                                    if gang_name is False: 
                                        gang_name = "N/A"
                                    elif not gang_name: 
                                        gang_name = "Unknown"

                                    new_alert = {
                                        "id": alert_id,
                                        "company_id": company['id'],
                                        "company_name": company['name'],
                                        "matched_keyword": keyword,
                                        "api_entry_id": entry_identifier, 
                                        "api_data": {
                                            "victim_name_api": entry.get("victim", "N/A"),
                                            "article_title_api": entry.get("title", "N/A"),
                                            "domain_api": entry.get("domain", "N/A"), 
                                            "display_victim_name": display_victim_name,
                                            "date": entry.get("date", "N/A"), 
                                            "group_name": gang_name,
                                            "source_url": entry.get("url", "N/A"),
                                            "internal_link": entry.get("link", "N/A"),
                                            "summary": entry.get("summary", "N/A"), 
                                        },
                                        "status": "Open",
                                        "timestamp": datetime.now().isoformat() 
                                    }
                                    st.session_state.alerts.append(new_alert)
                                    new_alerts_found += 1
                
                if new_alerts_found > 0:
                    save_data(ALERTS_FILE, st.session_state.alerts)
                    st.success(f"Found {new_alerts_found} new potential compromises (within selected date range if applicable)!")
                    st.rerun() 
                else:
                    st.info("No new compromises found based on your current keywords and date range.")

            except requests.exceptions.HTTPError as e:
                st.error(
                    f"HTTP error occurred while fetching data from API: {e}. "
                    f"Status Code: {e.response.status_code}. "
                    f"Response text (first 500 chars): '{e.response.text[:500]}...'" 
                )
            except requests.exceptions.Timeout:
                st.error(
                    "The request to the ransomware.live API timed out. "
                    "The API might be slow or temporarily unavailable. Please try again later."
                )
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching data from API (RequestException): {e}")
            except json.JSONDecodeError as e:
                error_message = (
                    f"Error decoding API response (JSONDecodeError): {e}. "
                )
                if response is not None:
                    error_message += (
                        f"Status Code: {response.status_code}. "
                        f"Response text (first 500 chars): '{response.text[:500]}'"
                    )
                else:
                    error_message += "Response object was not available for inspection."
                st.error(error_message)
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

    st.subheader("Monitored Alerts")
    if not st.session_state.alerts:
        st.info("No alerts to display. Click the button above to fetch and check for compromises.")
    else:
        status_order = {"Open": 0, "In Progress": 1, "Complete": 2, "False Positive": 3}
        
        sorted_alerts_all = sorted(st.session_state.alerts, key=lambda x: x.get('timestamp', ''), reverse=True) 
        sorted_alerts_all = sorted(sorted_alerts_all, key=lambda x: status_order.get(x['status'], 99))
        
        filter_cols_display = st.columns(2) 
        company_options = ["All"] + sorted(list(set(c['name'] for c in st.session_state.companies if 'name' in c)))
        filter_company_name = filter_cols_display[0].selectbox(
            "Filter by Company:", 
            options=company_options,
            key="filter_company_display" 
        )
        filter_status = filter_cols_display[1].selectbox(
            "Filter by Status:", 
            options=["All", "Open", "In Progress", "Complete", "False Positive"],
            key="filter_status_display" 
        )
        
        alerts_to_display = []
        for alert in sorted_alerts_all:
            if days_to_filter_for_new_and_display is not None:
                alert_api_date_str = alert['api_data'].get('date')
                if not alert_api_date_str or alert_api_date_str == "N/A":
                    continue 
                try:
                    alert_api_date_obj = datetime.strptime(alert_api_date_str, "%Y-%m-%d").date()
                    cutoff_display_date = date.today() - pd.Timedelta(days=days_to_filter_for_new_and_display)
                    if alert_api_date_obj < cutoff_display_date:
                        continue 
                except ValueError:
                    continue
            
            if filter_company_name != "All" and alert['company_name'] != filter_company_name:
                continue
            if filter_status != "All" and alert['status'] != filter_status:
                continue
            
            alerts_to_display.append(alert)

        if alerts_to_display:
            st.markdown("---")
            st.subheader("Bulk Actions for Visible Alerts")
            
            all_visible_are_selected = False
            if alerts_to_display: 
                all_visible_are_selected = all(st.session_state.selected_alerts.get(a['id'], False) for a in alerts_to_display)

            if st.checkbox("Select / Deselect All Visible Alerts", value=all_visible_are_selected, key="select_all_visible_alerts_cb"):
                if not all_visible_are_selected: 
                    for alert_disp in alerts_to_display:
                        st.session_state.selected_alerts[alert_disp['id']] = True
                    st.rerun()
            else: 
                if all_visible_are_selected: 
                    for alert_disp in alerts_to_display:
                        st.session_state.selected_alerts[alert_disp['id']] = False
                    st.rerun()

            bulk_status_options = ["Open", "In Progress", "Complete", "False Positive"]
            col1, col2 = st.columns([3,1])
            new_bulk_status = col1.selectbox(
                "Set status for selected alerts to:",
                options=bulk_status_options,
                key="bulk_status_select"
            )
            if col2.button("Apply Status to Selected", key="bulk_apply_status"):
                selected_ids_for_update = [id for id, selected in st.session_state.selected_alerts.items() if selected and any(a['id'] == id for a in alerts_to_display)] 
                if not selected_ids_for_update:
                    st.warning("No visible alerts selected for bulk update.")
                else:
                    updated_count = 0
                    for alert_idx, alert_item in enumerate(st.session_state.alerts):
                        if alert_item['id'] in selected_ids_for_update:
                            st.session_state.alerts[alert_idx]['status'] = new_bulk_status
                            updated_count +=1
                    
                    if updated_count > 0:
                        save_data(ALERTS_FILE, st.session_state.alerts)
                        for id_updated in selected_ids_for_update:
                            st.session_state.selected_alerts[id_updated] = False 
                        st.success(f"{updated_count} alerts updated to '{new_bulk_status}'.")
                        st.rerun()
            st.markdown("---")


        if not alerts_to_display:
            st.info("No alerts match your current filter criteria or no alerts exist.")
        
        for i, alert in enumerate(alerts_to_display):
            original_alert_index = next((idx for idx, original_alert in enumerate(st.session_state.alerts) if original_alert['id'] == alert['id']), None)
            if original_alert_index is None: continue 

            is_selected = st.session_state.selected_alerts.get(alert['id'], False)
            
            col_check, col_expander = st.columns([0.1, 0.9])

            with col_check:
                 # Corrected: Provide a non-empty label, keep it collapsed
                 new_selection_state = st.checkbox(
                     label=f"Select alert {alert['id']}", # Non-empty label
                     value=is_selected, 
                     key=f"select_{alert['id']}", 
                     label_visibility="collapsed"
                 )
            if new_selection_state != is_selected:
                st.session_state.selected_alerts[alert['id']] = new_selection_state
                st.rerun() 

            with col_expander:
                expander_title = (
                    f"ALERT: {alert['company_name']} - Keyword: '{alert['matched_keyword']}' - "
                    f"Victim: '{alert['api_data'].get('display_victim_name', 'N/A')}' (Status: {alert['status']})"
                )
                with st.expander(expander_title):
                    st.markdown(f"**Monitored Company:** {alert['company_name']}")
                    st.markdown(f"**Matched Keyword:** `{alert['matched_keyword']}`")
                    alert_timestamp = alert.get('timestamp') 
                    api_reported_date = alert['api_data'].get('date', 'N/A')
                    
                    detected_on_str = "N/A"
                    if alert_timestamp:
                        try:
                            detected_on_str = datetime.fromisoformat(alert_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            detected_on_str = "Invalid app detection timestamp"
                    
                    st.markdown(f"**Date Reported (API):** {api_reported_date}")
                    st.markdown(f"**Date Detected (App):** {detected_on_str}")
                    
                    st.markdown("---")
                    st.markdown("**Ransomware API Information:**")
                    st.markdown(f"  - **Victim Name (API `victim`):** {alert['api_data'].get('victim_name_api', 'N/A')}")
                    st.markdown(f"  - **Article Title (API `title`):** {alert['api_data'].get('article_title_api', 'N/A')}")
                    st.markdown(f"  - **Domain (API `domain`):** {alert['api_data'].get('domain_api', 'N/A')}")
                    st.markdown(f"  - **Ransomware Group:** {alert['api_data'].get('group_name', 'N/A')}")
                    st.markdown(f"  - **Source Article URL:** {alert['api_data'].get('source_url', 'N/A')}")
                    st.markdown(f"  - **Ransomware.live Link:** {alert['api_data'].get('internal_link', 'N/A')}")
                    if alert['api_data'].get('summary'):
                        st.markdown(f"  - **Summary:**")
                        st.caption(f"{alert['api_data']['summary']}")
                    st.markdown("---")

                    status_options_individual = ["Open", "In Progress", "Complete", "False Positive"]
                    current_status_index_individual = status_options_individual.index(alert['status']) if alert['status'] in status_options_individual else 0
                    
                    new_status_individual = st.selectbox(
                        "Update Status (Individual):",
                        options=status_options_individual,
                        index=current_status_index_individual,
                        key=f"status_individual_{alert['id']}" 
                    )

                    if new_status_individual != st.session_state.alerts[original_alert_index]['status']:
                        st.session_state.alerts[original_alert_index]['status'] = new_status_individual
                        save_data(ALERTS_FILE, st.session_state.alerts)
                        st.success(f"Status for alert regarding '{alert['api_data']['display_victim_name']}' updated to '{new_status_individual}'.")
                        st.rerun() 

                    if st.button(f"Delete Alert for {alert['api_data']['display_victim_name']}", key=f"delete_alert_{alert['id']}"):
                        if alert['id'] in st.session_state.selected_alerts:
                            del st.session_state.selected_alerts[alert['id']]
                        st.session_state.alerts.pop(original_alert_index)
                        save_data(ALERTS_FILE, st.session_state.alerts)
                        st.success(f"Alert for '{alert['api_data']['display_victim_name']}' deleted.")
                        st.rerun()


# --- Main App Navigation ---
st.set_page_config(page_title="Ransomware Monitor", layout="wide")
st.title("🎯 Ransomware Compromise Monitor")
st.markdown("Monitor potential supplier or company compromises using the ransomware.live API.")

PAGES = {
    "Manage Monitored Companies": manage_companies_page,
    "Check API & Manage Alerts": check_api_page
}

st.sidebar.title("Navigation")
selection = st.sidebar.radio("Go to", list(PAGES.keys()))

page = PAGES[selection]
page()

st.sidebar.markdown("---")
st.sidebar.info(
    "This app uses the ransomware.live API (v2/recentcyberattacks). "
    "Ensure you comply with their terms of service. "
    "Data is stored locally in `companies.json` and `alerts.json`."
)
