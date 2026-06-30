import os
import json
import time
import html
import re
import sys
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def log_to_sheets(left_p, right_p, left_t, right_t, left_v, right_v):
    try:
        print("-> Connecting to Google Sheets API...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_json = json.loads(os.environ.get("GOOGLE_CREDS"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        # ⚠️ MAKE SURE THIS MATCHES YOUR SHEET NAME EXACTLY
        sheet_name = "Helium Consumption Tracking"
        
        print(f"-> Attempting to open sheet named: '{sheet_name}'...")
        sheet = client.open(sheet_name).sheet1
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, left_p, right_p, left_t, right_t, left_v, right_v])
        print("[✓] Google Sheet updated successfully!")
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"[X] ERROR: Could not find a Google Sheet named '{sheet_name}'. Check your spelling and spacing!")
        sys.exit(1)
    except Exception as e:
        print(f"[X] ERROR writing to Google Sheets: {str(e)}")
        sys.exit(1)

def fetch_airgas_data():
    username = os.environ.get("AIRGAS_USER")
    password = os.environ.get("AIRGAS_PASS")
    
    if not username or not password:
        print("[X] ERROR: Airgas credentials missing from GitHub Secrets.")
        sys.exit(1)
        
    try:
        with sync_playwright() as p:
            print("-> Launching background browser...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = context.new_page()
            
            print("-> Navigating to Airgas Login page...")
            page.goto("https://www.airgas.com/login", timeout=60000)
            
            print("-> Typing credentials...")
            page.fill("input[name='j_username']", username)
            page.fill("input[name='j_password']", password)
            
            print("-> Submitting login form...")
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")
            
            print("-> Accessing sensor details API...")
            api_url = "https://www.airgas.com/ezgaz/getSensorDetails?hwid=00:17:0D:00:00:75:9C:81,00:17:0D:00:00:75:9C:6F"
            page.goto(api_url, timeout=60000)
            
            raw_text = page.locator("body").inner_text()
            json_data = json.loads(raw_text)
            
            if json_data.get("status") == "SUCCESS" and "content" in json_data:
                print("[✓] Successfully retrieved tank data from Airgas!")
                html_content = html.unescape(json_data["content"])
                
                sections = html_content.split("Right container")
                left_section = sections[0]
                right_section = sections[1] if len(sections) > 1 else ""
                
                pressure_regex = r'<p>(\d+).*?psig'
                temp_regex = r'class="temp-text">([\d.]+)°F'
                battery_regex = r'class="battery-text">([\d.]+)V'
                
                lp_m = re.search(pressure_regex, left_section)
                lt_m = re.search(temp_regex, left_section)
                lv_m = re.search(battery_regex, left_section)
                lp = int(lp_m.group(1)) if lp_m else "N/A"
                lt = float(lt_m.group(1)) if lt_m else "N/A"
                lv = float(lv_m.group(1)) if lv_m else "N/A"
                
                rp_m = re.search(pressure_regex, right_section)
                rt_m = re.search(temp_regex, right_section)
                rv_m = re.search(battery_regex, right_section)
                rp = int(rp_m.group(1)) if rp_m else "N/A"
                rt = float(rt_m.group(1)) if rt_m else "N/A"
                rv = float(rv_m.group(1)) if rv_m else "N/A"
                
                browser.close()
                
                # Pass data to the sheet logging function
                log_to_sheets(lp, rp, lt, rt, lv, rv)
            else:
                print("[X] ERROR: Airgas API did not return valid data. Check if your login was blocked by a security prompt.")
                browser.close()
                sys.exit(1)
                
    except Exception as e:
        print(f"[X] CRITICAL BROWSER ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_airgas_data()
