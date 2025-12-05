import os
import time
import re
from typing import Dict, List, Any
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# Import available tools
from app.services.email.agent_tools import (
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
    """Extract subject lines from AI text output."""
    subjects = []
    # Pattern 1: Numbered list "1. Subject"
    numbered_pattern = r'^\s*\d+\.\s*(.+?)$'
    for line in text.split('\n'):
        m = re.match(numbered_pattern, line.strip())
        if m and len(m.group(1)) > 10:
            subjects.append(m.group(1).strip())
            
    # Pattern 2: Bullet points
    if not subjects:
        bullet_pattern = r'^\s*[\*\-]\s*(.+?)$'
        for line in text.split('\n'):
            m = re.match(bullet_pattern, line.strip())
            if m and len(m.group(1)) > 10:
                subjects.append(m.group(1).strip())
                
    # Pattern 3: Just lines if short enough
    if not subjects:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines[:10]:
            if 15 < len(line) < 100 and not line.endswith('.') and not line.startswith('#'):
                subjects.append(line)
                
    cleaned = []
    for subj in subjects:
        # Cleanup artifacts
        subj = re.sub(r'\s*\([^)]+\)\s*', '', subj)
        subj = re.sub(r'\*\*(.+?)\*\*', r'\1', subj)
        subj = subj.strip("'\"")
        subj = re.sub(r'^(Subject|Option\s*\d+):\s*', '', subj, flags=re.IGNORECASE)
        if subj and len(subj) > 10:
            cleaned.append(subj.strip())
            
    return cleaned[:5]


def extract_email_body(text: str) -> str:
    """
    Extract email body from AI text output and format as HTML.
    Handles Markdown bold (**text**), lists (* item), paragraphs, and auto-linking.
    """
    import html

    # 1. Extract Body Content
    greetings = [r'Hi\s+', r'Hello\s+', r'Dear\s+', r'Hey\s+']
    start_idx = 0
    body_content_starts = False
    
    for g in greetings:
        m = re.search(g, text, re.IGNORECASE)
        if m:
            start_idx = m.start()
            body_content_starts = True
            break
            
    body_text_raw = text[start_idx:] if body_content_starts else text
    
    # Remove agent-specific markers
    markers = [
        r'\*\*Greeting:\*\*.*?\n', r'\*\*Hook:\*\*.*?\n', r'\*\*Bridge:\*\*.*?\n',
        r'\*\*Pitch:\*\*.*?\n', r'\*\*CTA:\*\*.*?\n', r'\*\*Final Review:\*\*.*',
        r'```json.*?```', r'\{.*?\}', r'^Subject:.*?\n', r'^DETAILED SUBJECT LINE OPTIONS:.*?\n'
    ]
    for mark in markers:
        body_text_raw = re.sub(mark, '', body_text_raw, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)
    
    body_text_raw = body_text_raw.strip()
    
    if not body_text_raw:
        return ""

    # 2. Escape HTML (Safety first)
    safe_text = html.escape(body_text_raw)

    # 3. Process Markdown Bold (**text**) -> <strong>text</strong>
    safe_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe_text)

    # 4. Auto-link URLs and Emails
    # Helper to avoid double linking
    def linkify(text_chunk):
        # Emails
        text_chunk = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            lambda m: f'<a href="mailto:{m.group(0)}">{m.group(0)}</a>',
            text_chunk
        )
        
        # Full URLs (http/https)
        # Negative lookbehind to avoid matching inside the mailto we just created
        text_chunk = re.sub(
            r'(?<!href=")(https?://[^\s<"]+)',
            lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
            text_chunk
        )
        
        # Simple Domains (www. or .com/.net etc) - stricter to avoid breaking things
        # Exclude if already linked (preceded by " or > or /)
        text_chunk = re.sub(
            r'(?<![/"\w])(www\.[^\s<"]+|[a-zA-Z0-9-]+\.(?:com|net|org|io|co|uk|pk|us|ca)\b(?:/[^\s<"]*)?)',
            lambda m: f'<a href="http://{m.group(1)}">{m.group(1)}</a>',
            text_chunk
        )
        return text_chunk

    # 5. Structure Processing (Paragraphs & Lists)
    blocks = re.split(r'\n{2,}', safe_text)
    final_html_parts = []

    for block in blocks:
        # Check for list
        # Matches lines starting with "* " or "- "
        list_items = re.findall(r'^\s*[\*-]\s+(.+)$', block, re.MULTILINE)
        
        if list_items:
            # This block is (or contains) a list
            html_list = "<ul>"
            for item in list_items:
                html_list += f"<li>{linkify(item.strip())}</li>"
            html_list += "</ul>"
            final_html_parts.append(html_list)
        else:
            # Regular paragraph
            # Convert single newlines to <br> for things like addresses/signatures
            # But first linkify
            linked_block = linkify(block)
            formatted_block = linked_block.replace('\n', '<br>')
            final_html_parts.append(f"<p>{formatted_block}</p>")

    return "".join(final_html_parts)

# ----------------------- Main Agent ----------------------- 

class GeminiAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            # Fallback for dev/docker
            api_key = os.getenv("GEMINI_API_KEY")
            
        if not api_key:
             print("Warning: GOOGLE_API_KEY not found. Agent may fail.")

        genai.configure(api_key=api_key)

        # Load system instruction from playbook if available
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) # backend root
        playbook_path = os.path.join(base_dir, "email_playbook.md")
        
        self.system_instruction = "You are an expert B2B Copywriter and Research Analyst."
        if os.path.exists(playbook_path):
            try:
                with open(playbook_path, "r", encoding="utf-8") as f:
                    self.system_instruction = f.read()
            except Exception:
                pass

        # Adaptive system prompt
        self.system_instruction += """
            You are a reasoning AI agent with access to specialized tools for research and outreach.
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
            Do not include raw tool call JSONs in final user-facing responses.
        """

        self.tools = [
            get_company_profile, get_smykm_notes, get_product_catalog,
            analyze_pricing_strategy, find_competitors, market_search,
            filter_search, get_domains, get_contacts, get_stats, get_recent_crawls
        ]

        # Initialize model
        # Note: model_name must be supported by API. "gemini-1.5-pro-latest" or similar is safer if 2.5 not public.
        # User specified 2.5, keeping it.
        self.model = genai.GenerativeModel(
            model_name=model_name,
            tools=self.tools,
            system_instruction=self.system_instruction,
            generation_config=GenerationConfig(
                temperature=0.7, top_p=0.9, top_k=40, max_output_tokens=4096,
            ),
        )

    def run(self, domain: str) -> Dict[str, Any]:
        """
        Run the agent to research a domain and generate an email draft.
        """
        print(f"[{domain}] Running Gemini Agent...")
        max_retries = 3
        delay = 2
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
                                "smykm_notes": ["..."],
                                "products_summary": "...",
                                "market_insights": "...",
                                "can_improve": "..."
                                }}"""
                
                research_resp = chat.send_message(research_prompt)
                research_data = research_resp.text
                print(f"[{domain}] Research complete.")

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
                                DETAILED SUBJECT LINE OPTIONS (Show Me You Know Me):
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

                # Step 3: Review phase (Reviewer Agent)
                review_prompt = f"""Review and refine the following email for tone, personalization, and clarity.
                Ensure it sounds human, confident, and relevant. If something is missing like recommendations to improve
                their offer using our research. You can use {research_data} to add that portion in.
                
                EMAIL DRAFT:
                {draft_output}

                Output ONLY the final polished email body."""
                
                review_resp = chat.send_message(review_prompt)
                reviewed_body = review_resp.text
                
                # Extract structured data
                subject_lines = extract_subject_lines(draft_output)
                final_body = extract_email_body(reviewed_body)

                result = {
                    "domain": domain,
                    "subject_lines": subject_lines,
                    "email_body": final_body,
                    "raw_output": draft_output,
                    "research_summary": research_data
                }

                print(f"[{domain}] Draft generated successfully.")
                return result

            except Exception as e:
                last_error = e
                print(f"[{domain}] Agent error (Attempt {attempt+1}): {e}")
                time.sleep(delay * (attempt + 1))

        return {
            "domain": domain,
            "subject_lines": [],
            "email_body": f"Generation failed after {max_retries} attempts. Error: {str(last_error)}",
            "raw_output": "",
            "error": str(last_error),
        }