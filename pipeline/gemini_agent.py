import os
import time
import re
import json
from typing import Dict, List, Optional
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# Import all tools from agent_tools (single source of truth)
# Gemini needs unwrapped functions, not MCP-decorated ones
from pipeline.agent_tools import (
    # Domain-specific research tools
    get_company_profile,
    get_smykm_notes,
    get_product_catalog,
    analyze_pricing_strategy,
    find_competitors,
    # RAG & database query tools
    market_search,
    filter_search,
    get_domains,
    get_contacts,
    get_stats,
    get_recent_crawls
)


def extract_subject_lines(text: str) -> List[str]:
    """Extract subject lines from text, handling various formats."""
    subjects = []

    # Pattern 1: Numbered list (1. Subject, 2. Subject)
    numbered_pattern = r'^\s*\d+\.\s*(.+?)$'
    for line in text.split('\n'):
        match = re.match(numbered_pattern, line.strip())
        if match and len(match.group(1)) > 10:  # At least 10 chars
            subjects.append(match.group(1).strip())

    # Pattern 2: Bulleted list (* Subject, - Subject)
    if not subjects:
        bullet_pattern = r'^\s*[\*\-]\s*(.+?)$'
        for line in text.split('\n'):
            match = re.match(bullet_pattern, line.strip())
            if match and len(match.group(1)) > 10:
                subjects.append(match.group(1).strip())

    # Pattern 3: Lines that look like subject lines (short, no periods at end)
    if not subjects:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines[:10]:  # Check first 10 lines
            if 15 < len(line) < 100 and not line.endswith('.') and not line.startswith('#'):
                subjects.append(line)

    # Clean up subjects - remove annotations like "(Concise)", "(Personal)", etc.
    cleaned = []
    for subj in subjects:
        # Remove parenthetical annotations
        subj = re.sub(r'\s*\([^)]+\)\s*', '', subj)
        # Remove markdown bold
        subj = re.sub(r'\*\*(.+?)\*\*', r'\1', subj)
        # Remove quotes
        subj = subj.strip('"\'')
        # Remove prefixes like "Subject:", "Option 1:", etc.
        subj = re.sub(r'^(Subject|Option\s*\d+):\s*', '', subj, flags=re.IGNORECASE)
        if subj and len(subj) > 10:
            cleaned.append(subj.strip())

    return cleaned[:5]  # Return max 5


def extract_email_body(text: str) -> str:
    """Extract email body, removing thinking process and metadata."""
    # Remove everything before the greeting
    greetings = [r'Hi\s+', r'Hello\s+', r'Dear\s+', r'Hey\s+']
    for greeting in greetings:
        match = re.search(greeting, text, re.IGNORECASE)
        if match:
            text = text[match.start():]
            break

    # Remove common thinking markers
    thinking_markers = [
        r'\*\*Greeting:\*\*.*?\n',
        r'\*\*Hook:\*\*.*?\n',
        r'\*\*Bridge:\*\*.*?\n',
        r'\*\*Pitch:\*\*.*?\n',
        r'\*\*CTA:\*\*.*?\n',
        r'\*\*Final Review:\*\*.*',
        r'```json.*?```',
        r'\{.*?\}',  # Remove JSON objects
    ]

    for marker in thinking_markers:
        text = re.sub(marker, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


class GeminiAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")

        genai.configure(api_key=api_key)

        # Load system instructions from playbook
        playbook_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "email_playbook.md")
        try:
            with open(playbook_path, "r", encoding="utf-8") as f:
                self.system_instruction = f.read()
        except Exception as e:
            print(f"Warning: Could not load email_playbook.md: {e}")
            self.system_instruction = "You are an expert B2B Copywriter."

        # Define all available tools (plain functions for Gemini function calling)
        self.tools = [
            # Domain-specific research tools
            get_company_profile,
            get_smykm_notes,
            get_product_catalog,
            analyze_pricing_strategy,
            find_competitors,
            # RAG & database query tools
            market_search,
            filter_search,
            get_domains,
            get_contacts,
            get_stats,
            get_recent_crawls
        ]

        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.tools,
            system_instruction=self.system_instruction,
            generation_config=GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=2048,
            )
        )

    def run(self, domain: str) -> Dict:
        """
        Run the Gemini agent to draft an email for the given domain.

        Returns:
            {
                "domain": str,
                "subject_lines": [str],  # 3-5 highly personalized and detailed subject lines
                "email_body": str,
                "raw_output": str  # Full output for debugging
            }
        """
        print(f"[{domain}] Starting Gemini Agent ({self.model.model_name})...")

        # Retry logic for API errors
        max_retries = 3
        retry_delay = 5  # seconds
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"[RETRY] Attempt {attempt + 1}/{max_retries}...")
                    time.sleep(retry_delay)

                # Initialize chat with automatic function calling enabled
                chat = self.model.start_chat(
                    enable_automatic_function_calling=True
                )

                prompt = f"""Research the company '{domain}' using the available tools.
Then write a highly personalized outreach email following these STRICT rules:

MY IDENTITY (Use EXACTLY as written - NO placeholders):
- Name: Qasim Jalil
- Role: Head of Digital Sales & Marketing
- Company: Raqim International
- Location: Sialkot, Pakistan
- Email: qasim@raqiminternational.com
- Phone: +92 321 8648707
- Website: raqiminternational.com

Target: {domain}

OUTPUT FORMAT (Follow EXACTLY):

SUBJECT LINE OPTIONS:
1. [First subject line]
2. [Second subject line]
3. [Third subject line]
4. [Fourth subject line]
5. [Fifth subject line]

EMAIL BODY:
[Write the complete email starting with greeting]

RULES:
- DO NOT include thinking process, planning, or explanations
- DO NOT use placeholders like [Your Name] - use real identity above
- DO NOT include JSON, markdown code blocks, or metadata
- Subject lines: 5 options, All subject lines should be highly personlized and detailed and on longer side (Use `get_smykm_notes` tool specially to get key insights about the company's unique value proposition, culture, and differentiators.)
- Email body: Complete with greeting, message, signature
- If products found: Be specific about them
- If no products: Focus on their brand/mission
- Follow the playbook's High-Performing Message Structure
"""

                response = chat.send_message(prompt)

                # Get raw text output
                raw_output = response.text
                print(f"[DEBUG] Raw output length: {len(raw_output)} chars")

                # Try to parse as sections
                subject_lines = []
                email_body = ""

                # Split by common section markers
                if "SUBJECT LINE OPTIONS:" in raw_output.upper():
                    parts = re.split(r'SUBJECT LINE OPTIONS?:', raw_output, flags=re.IGNORECASE)
                    if len(parts) > 1:
                        subject_part = parts[1]
                        # Extract email body part
                        email_parts = re.split(r'EMAIL BODY:', subject_part, flags=re.IGNORECASE)
                        if len(email_parts) > 1:
                            subject_lines = extract_subject_lines(email_parts[0])
                            email_body = extract_email_body(email_parts[1])
                        else:
                            subject_lines = extract_subject_lines(subject_part)

                # Fallback: Extract from entire output
                if not subject_lines or not email_body:
                    print(f"[WARN] Section markers not found, using fallback extraction")
                    subject_lines = extract_subject_lines(raw_output)
                    email_body = extract_email_body(raw_output)

                # Ensure we have at least 3 subject lines
                if len(subject_lines) < 3:
                    subject_lines.extend([
                        f"Partnership opportunity with {domain}",
                        f"Elevating {domain}'s production standards",
                        f"Quality manufacturing from Sialkot, Pakistan"
                    ])
                    subject_lines = subject_lines[:5]

                result = {
                    "domain": domain,
                    "subject_lines": subject_lines[:5],
                    "email_body": email_body if email_body else raw_output,
                    "raw_output": raw_output
                }

                print(f"[DEBUG] Extracted {len(result['subject_lines'])} subject lines")
                print(f"[DEBUG] Email body length: {len(result['email_body'])} chars")

                return result

            except Exception as e:
                last_error = e
                print(f"[ERROR] Gemini agent error (attempt {attempt + 1}/{max_retries}): {e}")

                # If it's a 500 error and we have retries left, continue
                if "500" in str(e) and attempt < max_retries - 1:
                    continue

                # For other errors or last attempt, return error
                if attempt == max_retries - 1:
                    print(f"[ERROR] All {max_retries} attempts failed")

        # If we get here, all retries failed
        return {
            "domain": domain,
            "subject_lines": [],
            "email_body": f"Error generating email after {max_retries} attempts: {last_error}",
            "raw_output": "",
            "error": str(last_error)
        }