import os
import time
import re
from typing import Dict, List
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# Import available tools
from pipeline.agent_tools import (
    get_company_profile,
    get_smykm_notes,
    get_product_catalog,
    analyze_pricing_strategy,
    find_competitors,
    market_search,
    filter_search,
    get_domains,
    get_contacts,
    get_stats,
    get_recent_crawls,
)

# ----------------------- Utility Functions -----------------------

def extract_subject_lines(text: str) -> List[str]:
    subjects = []
    numbered_pattern = r'^\s*\d+\.\s*(.+?)$'
    for line in text.split('\n'):
        m = re.match(numbered_pattern, line.strip())
        if m and len(m.group(1)) > 10:
            subjects.append(m.group(1).strip())
    if not subjects:
        bullet_pattern = r'^\s*[\*\-]\s*(.+?)$'
        for line in text.split('\n'):
            m = re.match(bullet_pattern, line.strip())
            if m and len(m.group(1)) > 10:
                subjects.append(m.group(1).strip())
    if not subjects:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines[:10]:
            if 15 < len(line) < 100 and not line.endswith('.') and not line.startswith('#'):
                subjects.append(line)
    cleaned = []
    for subj in subjects:
        subj = re.sub(r'\s*\([^)]+\)\s*', '', subj)
        subj = re.sub(r'\*\*(.+?)\*\*', r'\1', subj)
        subj = subj.strip('"\'')
        subj = re.sub(r'^(Subject|Option\s*\d+):\s*', '', subj, flags=re.IGNORECASE)
        if subj and len(subj) > 10:
            cleaned.append(subj.strip())
    return cleaned[:5]


def extract_email_body(text: str) -> str:
    greetings = [r'Hi\s+', r'Hello\s+', r'Dear\s+', r'Hey\s+']
    for g in greetings:
        m = re.search(g, text, re.IGNORECASE)
        if m:
            text = text[m.start():]
            break
    markers = [
        r'\*\*Greeting:\*\*.*?\n', r'\*\*Hook:\*\*.*?\n', r'\*\*Bridge:\*\*.*?\n',
        r'\*\*Pitch:\*\*.*?\n', r'\*\*CTA:\*\*.*?\n', r'\*\*Final Review:\*\*.*',
        r'```json.*?```', r'\{.*?\}'
    ]
    for mark in markers:
        text = re.sub(mark, '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text

# ----------------------- Main Agent -----------------------

class GeminiAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found")

        genai.configure(api_key=api_key)

        base_dir = os.path.dirname(os.path.dirname(__file__))
        playbook_path = os.path.join(base_dir, "email_playbook.md")
        try:
            with open(playbook_path, "r", encoding="utf-8") as f:
                self.system_instruction = f.read()
        except Exception:
            self.system_instruction = "You are an expert B2B Copywriter and Research Analyst."

        # Adaptive system prompt
        self.system_instruction += """ You are a reasoning AI agent with access to specialized tools for research and outreach.
            You may plan, call tools, and decide dynamically which to use based on the goal.

            When asked to perform a task, break it down into reasoning steps:
              1. Identify what information is missing.
              2. Choose the right tool to get that information.
              3. Analyze all gathered data.
              4. Generate the final output.

            You have access to tools for:
              - Company research (get_company_profile, get_smykm_notes, get_product_catalog)
              - Competitive and market analysis (find_competitors, market_search, filter_search)
              - Data enrichment (get_domains, get_contacts, get_stats, get_recent_crawls)

            Always decide tool use logically. Example:
              If researching a company, use get_company_profile.
              If finding competition, use find_competitors. Then use get_company_profile tool and get_product_catalog for all those competitors and use your logic to find lacking areas.
              If analyzing pricing, call analyze_pricing_strategy.

            Output your reasoning concisely but provide complete answers.
            Do not include raw tool call JSONs in final user-facing responses."""

        self.tools = [
            get_company_profile, get_smykm_notes, get_product_catalog,
            analyze_pricing_strategy, find_competitors, market_search,
            filter_search, get_domains, get_contacts, get_stats, get_recent_crawls
        ]

        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.tools,
            system_instruction=self.system_instruction,
            generation_config=GenerationConfig(
                temperature=0.65, top_p=0.9, top_k=40, max_output_tokens=4096,
            ),
        )

    def run(self, domain: str) -> Dict:
        print(f"[{domain}] Running Adaptive Gemini Agent with Reviewer...")
        max_retries, delay = 3, 4
        last_error = None

        for attempt in range(max_retries):
            try:
                chat = self.model.start_chat(enable_automatic_function_calling=True)

                # Step 1: Research phase
                research_prompt = f"""First, gather information about '{domain}'.
                                Use all available tools one by one to understand:
                                - What this company does
                                - Products or services they sell
                                - Market positioning and differentiators
                                - What it lacks compared to similar player in the market
                                - Any public contact info or culture insights

                                Summarize your findings in concise JSON with keys:
                                {{
                                "overview": "...",
                                "smykm (show me you know me) notes": "["..."],
                                "products": ["..."],
                                "insights": ["..."]
                                "market-reseach": ["..."],
                                "can_improve": ["..."]
                                }}"""
                research_resp = chat.send_message(research_prompt)
                research_data = research_resp.text
                print(f"[LOG] Research complete for {domain} ({len(research_data)} chars)")

                # Step 2: Draft email
                compose_prompt = f"""Based on the research below, write a fully personalized outreach email.

                                RESEARCH DATA:
                                {research_data}

                                MY IDENTITY:
                                - Name: Qasim Jalil
                                - Role: Head of Digital Sales & Marketing
                                - Company: Raqim International
                                - Location: Sialkot, Pakistan
                                - Email: qasim@raqiminternational.com
                                - Phone: +92 321 8648707
                                - Website: raqiminternational.com

                                OUTPUT FORMAT:
                                DETAILED SUBJECT LINE OPTIONS using show me you know me notes for personalization:
                                1. ...
                                2. ...
                                3. ...
                                4. ...
                                5. ...

                                EMAIL BODY:
                                [Complete email text]

                                RULES:
                                - No placeholders or explanations
                                - Subject lines: highly personalized and detailed
                                - Email body: natural tone, start with greeting, full signature"""
                compose_resp = chat.send_message(compose_prompt)
                draft_output = compose_resp.text or ""

                subject_lines = extract_subject_lines(draft_output)
                email_body = extract_email_body(draft_output)

                # Step 3: Review phase (Reviewer Agent)
                review_prompt = f"""Review and refine the following email for tone, personalization, and clarity.
                Ensure it sounds human, confident, and relevant. If something is missing like recommendations to improve
                their offer using our research. You can use {research_data} to add that portion in.
                
                EMAIL DRAFT:
                {email_body}

                Provide final, polished version only."""
                review_resp = chat.send_message(review_prompt)
                reviewed_body = extract_email_body(review_resp.text)

                result = {
                    "domain": domain,
                    "subject_lines": subject_lines,
                    "email_body": reviewed_body,
                    "raw_output": draft_output,
                    "review_output": review_resp.text,
                }

                print(f"[LOG] Review complete for {domain}, {len(subject_lines)} subjects.")
                return result

            except Exception as e:
                last_error = e
                print(f"[ERROR] Attempt {attempt+1}/{max_retries}: {e}")
                time.sleep(delay)

        return {
            "domain": domain,
            "subject_lines": [],
            "email_body": f"Error after {max_retries} attempts: {last_error}",
            "raw_output": "",
            "error": str(last_error),
        }
