import os
import json
import time
import html
import re
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def log_to_sheets(left_p, right_p, left_t, right_t, left_v, right_v):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Safely load the Google JSON from GitHub Secrets
    creds_json = json.loads(os.environ.get("GOOGLE_CREDS"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(creds)
    
    # ⚠️ UPDATE THIS TO YOUR EXACT GOOGLE SHEET NAME
    sheet = client.open("Helium Consumption Tracking").sheet1
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([timestamp, left_p, right_p, left_t, right_t, left_v, right_v])

def fetch_airgas_data():
    username = os.environ.get("AIRGAS_USER")
    password = os.environ.get("AIRGAS_PASS")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. Log into Airgas
        page.goto("https://www.airgas.com/login")
        page.fill("input[name='j_username']", username)
        page.fill("input[name='j_password']", password)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        
        # 2. Grab raw layout data from the API endpoint
        api_url = "https://www.airgas.com/ezgaz/getSensorDetails?hwid=00:17:0D:00:00:75:9C:81,00:17:0D:00:00:75:9C:6F"
        page.goto(api_url)
        
        raw_text = page.locator("body").inner_text()
        json_data = json.loads(raw_text)
        
        if json_data.get("status") == "SUCCESS" and "content" in json_data:
            # Decode the HTML characters
            html_content = html.unescape(json_data["content"])
            
            # Split text to prevent left/right cross-contamination
            sections = html_content.split("Right container")
            left_section = sections[0]
            right_section = sections[1] if len(sections) > 1 else ""
            
            # Text patterns to locate readings
            pressure_regex = r'<p>(\d+).*?psig'
            temp_regex = r'class="temp-text">([\d.]+)°F'
            battery_regex = r'class="battery-text">([\d.]+)V'
            
            # Parse Left Tank Data
            lp_m = re.search(pressure_regex, left_section)
            lt_m = re.search(temp_regex, left_section)
            lv_m = re.search(battery_regex, left_section)
            lp = int(lp_m.group(1)) if lp_m else "N/A"
            lt = float(lt_m.group(1)) if lt_m else "N/A"
            lv = float(lv_m.group(1)) if lv_m else "N/A"
            
            # Parse Right Tank Data (Fixed syntax bug here!)
            rp_m = re.search(pressure_regex, right_section)
            rt_m = re.search(temp_regex, right_section)
            rv_m = re.search(battery_regex, right_section)
            rp = int(rp_m.group(1)) if rp_m else "N/A"
            rt = float(rt_m.group(1)) if rt_m else "N/A"
            rv = float(rv_m.group(1)) if rv_m else "N/A"
            
            log_to_sheets(lp, rp, lt, rt, lv, rv)
            print(f"Logged successfully! Left: {lp} PSI | Right: {rp} PSI")
        else:
            print("Failed to pull content from Airgas API.")
            
        browser.close()

if __name__ == "__main__":
    fetch_airgas_data()
