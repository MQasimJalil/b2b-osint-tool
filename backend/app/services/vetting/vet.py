import os
import json
from typing import Dict, List, Tuple

import openai


def _get_client() -> openai.OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return openai.OpenAI(api_key=api_key)


VET_PROMPT = (
    "You are given a website URL: [{url}]\n\n"
    "Check the site and return JSON only if ALL conditions are met:\n"
    "1) Sells physical football/soccer gear (esp. goalkeeper gloves or related)\n"
    "2) Not a pure service/news/directory\n"
    "3) Not a general marketplace unless clearly specialized in football gear\n"
    "4) Has a product/shop page mentioning GK gloves or related terms\n\n"
    "Return JSON in this exact schema when valid, else reply `NO`:\n"
    "{\n"
    "  \"company\": \"Full company name\",\n"
    "  \"major_offering\": \"Main product/service related to football gear\",\n"
    "  \"main_contacts\": {\n"
    "    \"address\": [\"Address line 1\", \"City, Country\"],\n"
    "    \"email\": [\"contact@example.com\"],\n"
    "    \"phone\": \"+1-555-555-5555\",\n"
    "    \"website\": \"https://example.com\",\n"
    "    \"contact_page\": \"https://example.com/contact\"\n"
    "  },\n"
    "  \"social_media\": {\n"
    "    \"linkedin\": \"\", \"instagram\": \"\", \"twitter\": \"\", \"facebook\": \"\"\n"
    "  },\n"
    "  \"key_management\": [{\"name\": \"\", \"position\": \"\", \"linkedin\": \"\"}]\n"
    "}\n"
)


def vet_domains(domains: List[str]) -> Tuple[List[Dict], List[str]]:
    """
    For each domain, ask OpenAI to validate and, if valid, return structured info.
    Returns (valid_rows, rejected_domains).
    """
    client = _get_client()
    valid: List[Dict] = []
    rejected: List[str] = []

    for d in domains:
        url = f"https://{d}"
        prompt = VET_PROMPT.format(url=url)
        try:
            resp = client.chat.completions.create(
                model="gpt-4.1-mini-2025-04-14",
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content.strip()
            if content == "NO":
                rejected.append(d)
                continue
            try:
                data = json.loads(content)
                # ensure website
                data.setdefault("main_contacts", {}).setdefault("website", url)
                valid.append(data)
            except json.JSONDecodeError:
                rejected.append(d)
        except Exception:
            rejected.append(d)

    return valid, rejected
