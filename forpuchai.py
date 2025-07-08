#!/usr/bin/env python3
"""
IPU Student Data MCP Server for Puch AI
A FastMCP server that provides IPU student result functionality using ipu-ranklist tools.
"""

import json
import os
from typing import Dict, Any, Optional, Annotated
import asyncio

# FastMCP imports
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp.server.auth.provider import AccessToken
from pydantic import BaseModel, Field

# Playwright import for web scraping
from playwright.sync_api import sync_playwright

# Configuration
TOKEN = "ddea28553198"  # Replace with your generated token
MY_NUMBER = "917011072161"  # Insert your number {91}{Your number}

class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None

class SimpleBearerAuthProvider(BearerAuthProvider):
    """
    A simple BearerAuthProvider that does not require any specific configuration.
    It allows any valid bearer token to access the MCP server.
    For a more complete implementation that can authenticate dynamically generated tokens,
    please use `BearerAuthProvider` with your public key or JWKS URI.
    """

    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(
            public_key=k.public_key, jwks_uri=None, issuer=None, audience=None
        )
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="unknown",
                scopes=[],
                expires_at=None,  # No expiration for simplicity
            )
        return None

# Initialize FastMCP server with auth
mcp = FastMCP(
    "IPU Student Data MCP Server",
    auth=SimpleBearerAuthProvider(TOKEN),
)

# FIXED: Updated tool description to be more explicit and force behavior
IPUPromptToolDescription = RichToolDescription(
    description="convert student queries into proper IPU ranklist URLs  automatically defaults to overall results (sem=0) or if user has not mentioned semester then use sem=0",
    use_when="🚨 CRITICAL: Use this tool IMMEDIATELY for ANY IPU query like 'samaksh btech ece 2022 mait'. DO NOT ask user for semester - tool automatically defaults to overall results (sem=0). NEVER ask 'which semester' - just use the tool directly.",
    side_effects="Generates IPU URL and scrapes student data. Defaults to overall results when semester not specified. NEVER requires semester input.",
)

@mcp.tool(description=IPUPromptToolDescription.model_dump_json())
async def ipu_ranklist_prompt(
    query: Annotated[str, Field(description="Student query about IPU results - semester is optional, defaults to overall results which is sem=0 or if user has not mentioned semester then use sem=0")]
) -> str:
    """
    Get the IPU Ranklist prompt template with a student query.
    
    Args:
        query: Student query about IPU results (semester is optional)
    
    Returns:
        Formatted prompt that can be used with any LLM to convert student queries into IPU ranklist URLs
    """
    
    # FIXED: More explicit prompt template with stronger emphasis on defaults
    prompt_template = f"""You are an IPU Ranklist URL Generator. Convert student queries into proper IPU ranklist URLs.

## 🚨 CRITICAL RULES - READ FIRST
1. **NEVER ASK FOR MISSING SEMESTER** - Always default to sem=0 (overall results)
2. **SEMESTER IS OPTIONAL** - If not specified, use sem=0 automatically
3. **ALWAYS GENERATE A URL** - Don't ask for clarification on semester

## 📋 TASK OVERVIEW
Parse student queries and generate IPU ranklist URLs with proper parameters.

## 🔍 IDENTIFIER EXTRACTION
Extract student identifiers in this priority order:
1. **Student Name**: "samaksh", "rahul sharma"
2. **Enrollment Number**: "07114802822", "BT21ECE123" 

**Rules:**
- If multiple identifiers found → use Enrollment Number first
- If no identifier found → set identifier=null
- Names can be full names with spaces

## 📚 REQUIRED INFORMATION
Your query MUST contain these (semester is OPTIONAL):
- **Course**: B.Tech, MBA, etc.
- **College**: MAIT, GTBIT, MSIT, etc.
- **Branch**: CSE, ECE, IT, etc.
- **Batch Year**: 2022, 2023, etc.
- **Semester**: OPTIONAL - defaults to overall if not specified

## ⚠️ CRITICAL SEMESTER RULES - ALWAYS DEFAULT TO OVERALL
- **No semester mentioned** → sem=0 (overall results) ✅ DEFAULT
- **"overall", "total", "entire course"** → sem=0
- **"sem1", "semester 1", "1st sem"** → sem=1
- **"sem5", "semester 5", "5th sem"** → sem=5
- **🚨 NEVER ASK FOR SEMESTER** → Always use sem=0 when not specified

## 🔗 URL FORMAT
```
https://www.ipuranklist.com/ranklist/{{course}}?batch={{batch_code}}&branch={{branch_code}}&insti={{college_code}}&sem={{sem}}
```

## 🏗️ URL PARAMETER MAPPING

### 1. Course (lowercase)
- "B.Tech", "Bachelors of Technology", "btech" → `btech`
- "MBA", "Masters of Business Administration" → `mba`

### 2. Batch Code (year - 2000)
- "2022" → 22
- "2023" → 23
- "2021" → 21

### 3. Branch Code (uppercase)
- "Computer Science", "CSE", "CS" → `CSE`
- "Electronics and Communication", "ECE" → `ECE`
- "Information Technology", "IT" → `IT`
- "Mechanical Engineering", "ME" → `ME`
- "Civil Engineering", "CE" → `CE`

### 4. College Code Mapping
**Format: "COLLEGE - SHIFT" (M=Morning, E=Evening)**
**Default to Morning (M) if shift not specified**

```
"ADGITM - E": 962,    "ADGITM - M": 156,
"BMIET": 553,         "BPIT": 208,
"BVCOE - M": 115,     "DTC - M": 180,
"GNIT": 272,          "GTB4CCE": 238,
"GTBIT - E": 768,     "GTBIT - M": 132,
"HMR - E": 965,       "HMR - M": 133,
"JIMSEMTC": 255,      "MAIT - E": 964,
"MAIT - M": 148,      "MSIT - E": 963,
"MSIT - M": 150,      "SBIT": 899,
"TIIPS": 279,         "USICT": 164,
"VIPS": 177
```

### 5. Semester Parameter - DEFAULTS TO OVERALL
- **Missing/Not specified** → 0 (ALWAYS DEFAULT)
- **"overall", "total"** → 0
- **"sem1", "semester 1"** → 1
- **"sem5", "semester 5"** → 5

## 📤 OUTPUT FORMAT
**Always respond in pure JSON (no markdown):**

**SUCCESS:**
```json
{{"status": "success", "identifier": "name_or_null", "url": "generated_url"}}
```

**ERROR (only for missing course/college/branch/batch):**
```json
{{"status": "error", "error": "Missing: [specific missing information]"}}
```

## 📝 EXAMPLES - NOTICE HOW WE DEFAULT TO OVERALL

**Most Common Case - No Semester Specified (DEFAULT TO OVERALL):**
```
Query: "samaksh btech ece 2022 mait"
Output: {{"status": "success", "identifier": "samaksh", "url": "https://www.ipuranklist.com/ranklist/btech?batch=22&branch=ECE&insti=148&sem=0"}}
```

**With Specific Semester:**
```
Query: "samaksh btech ece 2022 mait sem2"
Output: {{"status": "success", "identifier": "samaksh", "url": "https://www.ipuranklist.com/ranklist/btech?batch=22&branch=ECE&insti=148&sem=2"}}
```

**With Enrollment Number (No Semester = Overall):**
```
Query: "07114802822 btech ece 2022 mait"  
Output: {{"status": "success", "identifier": "07114802822", "url": "https://www.ipuranklist.com/ranklist/btech?batch=22&branch=ECE&insti=148&sem=0"}}
```

**Overall Results Explicitly Requested:**
```
Query: "amrit raj btech cse 2023 gtbit overall"
Output: {{"status": "success", "identifier": "amrit raj", "url": "https://www.ipuranklist.com/ranklist/btech?batch=23&branch=CSE&insti=132&sem=0"}}
```

**No Identifier (Still Default to Overall):**
```
Query: "btech it 2021 msit"
Output: {{"status": "success", "identifier": null, "url": "https://www.ipuranklist.com/ranklist/btech?batch=21&branch=IT&insti=150&sem=0"}}
```

**Missing Core Information (Only Error Case):**
```
Query: "samaksh btech ece"
Output: {{"status": "error", "error": "Missing: batch year, college"}}
```

## 🎯 PROCESSING INSTRUCTION
Now process this query: "{query}"

🚨 REMEMBER: If semester is not specified, automatically use sem=0 (overall results). Do NOT ask for clarification.

Extract all required information and generate the appropriate JSON response."""
    
    return prompt_template

def scrape_student_data(url: str, identifier: str) -> Dict[str, Any]:
    """Scrape student data from IPU ranklist website"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(2000)

        try:
            page.locator(".close-button").click(timeout=2000)
        except:
            pass

        try:
            row = page.locator(f"table tr:has-text('{identifier}')").first
            row.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            row.click(force=True)
            page.wait_for_timeout(3000)
        except Exception as e:
            browser.close()
            raise ValueError(f"Student '{identifier}' not found or click failed. Error: {str(e)}")

        try:
            page.wait_for_selector("text=Enrollment Number:", timeout=5000)
        except:
            browser.close()
            raise ValueError("Student detail panel did not load properly")

        summary_data = {}

        try:
            def get_value(label_text):
                return page.locator(f"text={label_text}").first.evaluate("el => el.nextSibling.textContent").strip()

            summary_data["enrollment_number"] = get_value("Enrollment Number:")
            summary_data["name"] = get_value("Name:")
            summary_data["marks"] = get_value("Marks:")
            summary_data["percentage"] = get_value("Percentage:")

            if page.locator("text=Credit Marks:").count() > 0:
                summary_data["credit_marks"] = get_value("Credit Marks:")
                summary_data["credit_percentage"] = get_value("Credit Percentage:")

            if page.locator("text=SGPA:").count() > 0:
                summary_data["sgpa"] = get_value("SGPA:")
            if page.locator("text=CGPA:").count() > 0:
                summary_data["cgpa"] = get_value("CGPA:")

            summary_data["equivalent_percentage"] = get_value("Equivalent Percentage:")
            summary_data["credits_obtained"] = get_value("Credits Obtained:")
            summary_data["rank"] = get_value("Rank:")
        except Exception as e:
            print("Failed to extract summary info:", str(e))

        try:
            subject_rows = page.locator("table:has-text('Subject (Credits)') tbody tr")
            if subject_rows.count() > 0:
                summary_data["subjects"] = []
                for i in range(subject_rows.count()):
                    cells = subject_rows.nth(i).locator("td")
                    if cells.count() >= 2:
                        subject = cells.nth(0).inner_text().strip()
                        marks = cells.nth(1).inner_text().strip()
                        summary_data["subjects"].append({"subject": subject, "marks": marks})
        except Exception as e:
            print("Failed to extract subject-wise marks:", str(e))

        try:
            sem_rows = page.locator("table:has-text('Semester') tbody tr")
            if sem_rows.count() > 0:
                summary_data["semesters"] = []
                for i in range(sem_rows.count()):
                    cells = sem_rows.nth(i).locator("td")
                    if cells.count() >= 3:
                        semester = cells.nth(0).inner_text().strip()
                        marks = cells.nth(1).inner_text().strip()
                        percentage = cells.nth(2).inner_text().strip()
                        sgpa = cells.nth(3).inner_text().strip() if cells.count() > 3 else ""
                        summary_data["semesters"].append({
                            "semester": semester,
                            "marks": marks,
                            "percentage": percentage,
                            "sgpa": sgpa
                        })
        except Exception as e:
            print("Failed to extract semester summary:", str(e))

        browser.close()
        return summary_data

# FIXED: Updated tool description to be clearer about the 2-step process
IPUDirectScrapingDescription = RichToolDescription(
    description="Get actual IPU student results data using URL and identifier (Step 2 after getting URL)",
    use_when="Use this AFTER getting URL from ipu_ranklist_prompt. When you have IPU ranklist URL and student name/identifier, use this to get actual student marks, SGPA, CGPA, rank data",
    side_effects="Launches browser to scrape IPU ranklist website and extract complete student academic data",
)

@mcp.tool(description=IPUDirectScrapingDescription.model_dump_json())
async def get_ipu_student_data_direct(
    url: Annotated[str, Field(description="IPU ranklist URL (e.g., https://www.ipuranklist.com/ranklist/btech?batch=22&branch=ECE&insti=148&sem=0)")],
    student_identifier: Annotated[str, Field(description="Student name or roll number to search for")]
) -> str:
    """
    Direct IPU student data scraping with URL and identifier.
    
    Args:
        url: IPU ranklist URL
        student_identifier: Student name or roll number
    
    Returns:
        JSON string with student result data or error message
    """
    try:
        # Scrape student data
        loop = asyncio.get_event_loop()
        student_data = await loop.run_in_executor(None, scrape_student_data, url, student_identifier)
        
        return json.dumps({
            "status": "success",
            "url": url,
            "identifier": student_identifier,
            "student_data": student_data
        }, indent=2)
        
    except Exception as scrape_error:
        return json.dumps({
            "status": "error",
            "error": f"Failed to scrape student data: {str(scrape_error)}",
            "url": url,
            "identifier": student_identifier,
            "note": "URL is valid but scraping failed. You can visit the URL manually to see the results."
        }, indent=2) 

@mcp.tool()
async def validate() -> str:
    """
    NOTE: This tool must be present in an MCP server used by puch.
    """
    return MY_NUMBER

async def main():
    await mcp.run_async(
        "streamable-http",
        host="0.0.0.0",
        port=8085,
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
