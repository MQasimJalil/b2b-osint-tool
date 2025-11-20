import os
import json
import time
from typing import List, Dict, Any
from openai import OpenAI
from pipeline.agent_tools import (
    get_company_profile,
    get_product_catalog,
    analyze_pricing_strategy,
    find_competitors
)

class OutreachAgent:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_company_profile",
                    "description": "Get structured company information (description, contacts, social media, SMYKM notes).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "The domain of the company (e.g., example.com)"}
                        },
                        "required": ["domain"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_catalog",
                    "description": "Get the full list of products extracted from the company's website.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "The domain of the company"}
                        },
                        "required": ["domain"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_pricing_strategy",
                    "description": "Calculate average price, min/max price, and price range from the product catalog.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "The domain of the company"}
                        },
                        "required": ["domain"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_competitors",
                    "description": "Find similar companies in the database using semantic search.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "The domain of the target company"},
                            "industry": {"type": "string", "description": "The industry to search within (default: goalkeeper gloves)"}
                        },
                        "required": ["domain"]
                    }
                }
            }
        ]

    def run(self, domain: str) -> str:
        """
        Run the agentic flow to draft an email for the given domain.
        """
        print(f"[{domain}] Starting Agentic Email Flow...")
        
        system_prompt = """You are an expert B2B Sales Development Rep (SDR). 
Your goal is to write a hyper-personalized cold email to a prospect.

PROCESS:
1. RESEARCH: Use the available tools to understand the prospect's business, products, pricing, and competitors.
   - Always check their company profile first.
   - Analyze their pricing to see if they are budget, mid-range, or premium.
   - Check their product catalog to mention specific items.
   - Find competitors to see where they fit in the market.

2. REASONING: Before writing, briefly explain your strategy. 
   - "I see they sell premium gloves ($80+). I will pitch our high-end manufacturing quality."
   - "I see they use Shopify and have a small catalog. I will pitch our low MOQ and fast prototyping."

3. DRAFTING: Write the email.
   - Subject Line: Catchy and relevant.
   - Opening: "Show Me You Know Me" (SMYKM) - reference a specific fact/product.
   - Value Prop: Tailored to their pricing/market position.
   - Call to Action: Soft ask (e.g., "Worth a chat?").
   - Sign-off.

CRITICAL RULES:
- Do NOT make up facts. Only use data from the tools.
- If data is missing, acknowledge it and make a best-guess based on what you have.
- Keep the email under 150 words.
- Tone: Professional but conversational.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Draft an outreach email for {domain}. My company offers 'Premium Manufacturing Services for Sports Brands'."}
        ]

        # ReAct Loop
        max_steps = 10
        for step in range(max_steps):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                messages.append(msg)

                # If the model wants to call a tool
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        
                        print(f"  -> Agent calling: {func_name}({args})")
                        
                        # Execute tool
                        result = self._execute_tool(func_name, args)
                        
                        # Add result to history
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps(result)
                        })
                else:
                    # No tool calls, this is the final answer
                    print(f"[{domain}] Agent finished.")
                    return msg.content

            except Exception as e:
                print(f"Error in agent loop: {e}")
                return f"Error generating email: {e}"
        
        return "Agent exceeded max steps without generating a final email."

    def _execute_tool(self, func_name: str, args: Dict) -> Any:
        if func_name == "get_company_profile":
            return get_company_profile(args["domain"])
        elif func_name == "get_product_catalog":
            return get_product_catalog(args["domain"])
        elif func_name == "analyze_pricing_strategy":
            return analyze_pricing_strategy(args["domain"])
        elif func_name == "find_competitors":
            return find_competitors(args["domain"], args.get("industry", "goalkeeper gloves"))
        else:
            return {"error": "Unknown function"}
