import json
import os
import re
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.db.repositories import company_repo, product_repo
from app.services.rag.rag import query_rag as rag_query_service
from app.core.config import settings
from app.db.mongodb_models import Company

class ChatAgent:
    def __init__(self, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_company_profile",
                    "description": "Get structured company profile data including description, contacts, and social media. Use this when the user asks about 'who is this company', 'contact info', 'emails', or 'social media'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "The domain of the company (e.g., 'example.com')."
                            }
                        },
                        "required": ["domain"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_company_products",
                    "description": "Get a list of products offered by the company. Use this when the user asks for 'what products do they sell', 'product list', or specific product details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "The domain of the company."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of products to return (default 10).",
                                "default": 10
                            }
                        },
                        "required": ["domain"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Semantic search over crawled pages and unstructured data. Use this for specific questions that aren't covered by structured profile or product lists, like 'what is their return policy?', 'do they ship to canada?', 'history of the company', or broad market questions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query."
                            },
                            "domain": {
                                "type": "string",
                                "description": "Optional domain to filter results. Omit for global/cross-company search."
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_available_companies",
                    "description": "List available companies in the database. Use this for GLOBAL market queries to find which companies to sample data from (e.g., 'What is the most common cut across all brands?').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of companies to return (default 5).",
                                "default": 5
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "provide_final_response",
                    "description": "Submit the final answer to the user along with suggested follow-up questions. YOU MUST USE THIS TOOL TO END THE CONVERSATION.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The comprehensive markdown answer to the user's question. Do NOT include the suggested questions in this text field."
                            },
                            "suggested_questions": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "3 short, relevant follow-up questions for a B2B Analyst/Procurement persona. Focus on competitor analysis, pricing tiers, specs, or supply chain. NO consumer/retail questions."
                            }
                        },
                        "required": ["answer", "suggested_questions"],
                        "additionalProperties": False
                    }
                }
            }
        ]

    async def get_company_profile(self, domain: str) -> str:
        """Tool implementation: Fetch company profile"""
        company = await company_repo.get_company_by_domain(domain)
        if not company:
            return json.dumps({"error": "Company not found"})
        
        data = {
            "name": company.company_name,
            "description": company.description,
            "contacts": company.contacts,
            "social_media": company.social_media,
            "smykm_notes": company.smykm_notes
        }
        return json.dumps(data)

    async def list_company_products(self, domain: str, limit: int = 10) -> str:
        """Tool implementation: Fetch products"""
        products = await product_repo.get_products_by_domain(domain)
        if not products:
            return json.dumps({"error": "No products found"})
        
        # Format for context window efficiency
        results = []
        for p in products[:limit]:
            results.append({
                "name": p.name,
                "price": p.price,
                "category": p.category,
                "description": p.description[:200] + "..." if p.description else ""
            })
        
        return json.dumps({"products": results, "total_found": len(products)})

    async def search_knowledge_base(self, query: str, domain: Optional[str] = None) -> str:
        """Tool implementation: RAG search"""
        filters = {"domain": domain} if domain else None
        chunks = rag_query_service(query, filters=filters, top_k=5)
        
        results = []
        for c in chunks:
            # Include domain in source string so agent knows where it came from
            source_domain = c['metadata'].get('domain', 'unknown')
            results.append(f"[Source: {c['collection']} | Domain: {source_domain}] {c['content']}")
        
        if not results:
            return json.dumps({"result": "No relevant information found in knowledge base."} )
            
        return "\n\n".join(results)

    async def list_available_companies(self, limit: int = 5) -> str:
        """Tool implementation: List recent companies"""
        # Fetch recent companies
        companies = await Company.find_all().sort("-updated_at").limit(limit).to_list()
        
        results = []
        for c in companies:
            results.append({
                "domain": c.domain,
                "name": c.company_name,
                "description": c.description[:100] + "..." if c.description else ""
            })
            
        return json.dumps(results)

    async def update_summary(self, current_summary: str, new_messages: List[Dict[str, str]]) -> str:
        """Update conversation summary with new messages"""
        if not new_messages:
            return current_summary

        prompt = f"""Update the conversation summary by incorporating the new messages.
Keep the summary concise but retain key details like constraints, preferences, or specific facts found.

Current Summary:
{current_summary or "No summary yet."} 

New Messages to Add:
{json.dumps(new_messages, indent=2)}

Updated Summary:"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Summary update failed: {e}")
            return current_summary

    async def run_chat(
        self, 
        user_query: str, 
        company_domain: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        current_summary: str = "",
        msgs_to_summarize: List[Dict[str, str]] = []
    ) -> Dict[str, Any]:
        """
        Main entry point for chat. Handles the ReAct loop (Think -> Act -> Observe).
        """
        
        # 1. Update Summary (Parallel Step)
        new_summary = current_summary
        if msgs_to_summarize:
            new_summary = await self.update_summary(current_summary, msgs_to_summarize)

        # 2. Build Context String
        history_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
        context_str = f"Summary of past conversation:\n{new_summary}\n\nRecent Chat History:\n{history_str}"

        if company_domain:
            # === COMPANY SPECIFIC MODE ===
            system_prompt = f"""You are an expert analyst for the company: {company_domain}.
Your goal is to answer user queries using ONLY data related to {company_domain}.

CONTEXT:
{context_str}

# CORE PROTOCOL
1. **Analyze**: Understand what data point about {company_domain} is needed.
2. **Retrieve**: Use `get_company_profile`, `list_company_products`, or `search_knowledge_base`.
3. **Synthesize**: Formulate a comprehensive answer.
4. **Finalize**: YOU MUST call `provide_final_response` to deliver the answer and B2B follow-up questions.
   - **IMPORTANT**: Do NOT write the suggested questions in the 'answer' text. Put them ONLY in the 'suggested_questions' array.

# RULES & EXCEPTIONS
- **Primary Focus**: Always start with data about {company_domain}.
- **Competitor/Market Queries**: IF the user explicitly asks for **Comparisons**, **Competitors**, **Market Trends**, or **Pricing Analysis**:
  - You ARE ALLOWED to use `list_available_companies` to find rivals.
  - You ARE ALLOWED to query `list_company_products` for those rivals.
  - You MUST tie the findings back to {company_domain} (e.g., "Compared to Brand X, {company_domain} offers...").
"""
        else:
            # === KNOWLEDGE BASE / GLOBAL MODE ===
            system_prompt = f"""You are an expert B2B Data Analyst and Market Researcher.
Your goal is to answer user queries by retrieving and synthesizing data from the ENTIRE database.

CONTEXT:
{context_str}

# CORE PROTOCOL: CHAIN OF THOUGHT
1. **Analyze Request**: 
   - Is this about a specific company or the broader market?
2. **Formulate Plan**:
   - Identify key players or data sources.
3. **Execute Tools**:
   - Use `list_available_companies` to sample the market.
   - Use `list_company_products` or `search_knowledge_base` to gather facts.
4. **Synthesize**: Formulate a comprehensive answer.
5. **Finalize**: YOU MUST call `provide_final_response` to deliver the answer and B2B follow-up questions.
   - **IMPORTANT**: Do NOT write the suggested questions in the 'answer' text. Put them ONLY in the 'suggested_questions' array.

# WEIGHTING RULES
- **Inventory/Product Data** (Reality) > **Blog/Content** (Marketing Claims).
- **Multiple Sources** > **Single Source**.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: Company Domain = {company_domain}\nQuestion: {user_query}" if company_domain else user_query}
        ]

        # First LLM call to decide on tools
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools,
            tool_choice="auto"
        )

        response_message = response.choices[0].message
        sources = []
        final_answer_data = None

        # Multi-turn Loop
        max_turns = 5
        turn = 0
        
        while turn < max_turns:
            turn += 1
            
            # Check if model wants to use tools
            if response_message.tool_calls:
                messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    # === INTERCEPT FINAL RESPONSE ===
                    if function_name == "provide_final_response":
                        raw_answer = function_args.get("answer", "")
                        
                        # Clean up the answer text to remove duplicate suggestions
                        # This removes "Suggested Questions..." block if the model included it in the text
                        clean_pattern = r"(?:\n|^)(?:Suggested|Follow-up|Recommended)(?:.*)(?:Questions|Queries|Topics)(?:[:\s]*)(?:[\s\S]*)$"
                        clean_answer = re.sub(clean_pattern, "", raw_answer, flags=re.IGNORECASE | re.MULTILINE).strip()
                        
                        final_answer_data = {
                            "answer": clean_answer,
                            "suggested_questions": function_args.get("suggested_questions", [])
                        }
                        # We found the exit condition. 
                        # We don't need to append tool output for this, we just return.
                        break

                    # Normal Tool Execution
                    if company_domain and "domain" in function_args and not function_args["domain"]:
                        function_args["domain"] = company_domain

                    function_response = "{}"
                    
                    try:
                        if function_name == "get_company_profile":
                            function_response = await self.get_company_profile(
                                domain=function_args.get("domain") or company_domain
                            )
                            sources.append({"type": "tool", "name": f"Profile: {function_args.get('domain')}"})
                            
                        elif function_name == "list_company_products":
                            target_domain = function_args.get("domain") or company_domain
                            function_response = await self.list_company_products(
                                domain=target_domain,
                                limit=function_args.get("limit", 10)
                            )
                            sources.append({"type": "tool", "name": f"Products: {target_domain}"})
                            
                        elif function_name == "search_knowledge_base":
                            target_domain = function_args.get("domain") or company_domain
                            function_response = await self.search_knowledge_base(
                                query=function_args.get("query"),
                                domain=target_domain
                            )
                            sources.append({"type": "tool", "name": "RAG Search"})
                        
                        elif function_name == "list_available_companies":
                            function_response = await self.list_available_companies(
                                limit=function_args.get("limit", 5)
                            )
                            sources.append({"type": "tool", "name": "Company List"})

                    except Exception as e:
                        function_response = json.dumps({"error": str(e)})

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })

                if final_answer_data:
                    break

                # Next LLM call
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto"
                )
                response_message = response.choices[0].message
            else:
                # No tool calls - Model outputted plain text
                # Fallback: Parse output to see if it includes suggestions textually
                content = response_message.content
                suggestions = []
                
                # Try to extract suggestions from text if tool wasn't used
                # Look for "Suggested ... Questions:" pattern
                split_pattern = r"(?:\n|^)(?:Suggested|Follow-up|Recommended)(?:.*)(?:Questions|Queries|Topics)(?:[:\s]*)(?:\n|$)"
                parts = re.split(split_pattern, content, flags=re.IGNORECASE)
                
                if len(parts) > 1:
                    # Part 0 is answer, Part 1 is questions text
                    answer_text = parts[0].strip()
                    questions_text = parts[1].strip()
                    
                    # Extract lines that look like questions
                    for line in questions_text.split('\n'):
                        line = line.strip()
                        # Remove bullet points or numbers
                        clean_line = re.sub(r"^[\d\-\.\•\*\s]+", "", line)
                        if clean_line and len(clean_line) > 5 and "?" in clean_line:
                            suggestions.append(clean_line)
                    
                    final_answer_data = {
                        "answer": answer_text,
                        "suggested_questions": suggestions[:3] # Limit to 3
                    }
                else:
                    # No suggestions found in text
                    final_answer_data = {
                        "answer": content,
                        "suggested_questions": [] 
                    }
                break

        # Fallback if loop finishes without final_answer
        if not final_answer_data:
             final_answer_data = {
                "answer": "I apologize, but I couldn't retrieve the information efficiently. Please try asking again.",
                "suggested_questions": []
            }

        return {
            "answer": final_answer_data["answer"],
            "sources": sources,
            "new_summary": new_summary,
            "suggested_questions": final_answer_data["suggested_questions"]
        }