"""
Streamlit UI for B2B OSINT Tool Pipeline Control

Provides full control over:
- Full pipeline execution
- Individual stage execution (discovery, vetting, crawling, extraction, RAG)
- RAG query interface
- Status monitoring
"""

import streamlit as st
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict

# Import pipeline modules
from pipeline.discover import discover_domains
from pipeline.rule_vet import rule_vet
from pipeline.local_vet import vet_domains_locally
from pipeline.crawl import crawl_domains, get_crawl_status
from pipeline.extract import (
    extract_company_profile,
    extract_products,
    save_company_data,
    build_global_indexes,
    get_company_data
)
from pipeline.rag import (
    embed_domain,
    query_rag,
    get_rag_answer,
    _load_embedded_tracker,
    _get_chroma_client
)
from pipeline.rag_cli import embed_all_domains

# Page config
st.set_page_config(
    page_title="B2B OSINT Tool",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'pipeline_running' not in st.session_state:
    st.session_state.pipeline_running = False


def load_discovered_domains() -> List[str]:
    """Load discovered domains from cache"""
    cache_path = os.path.join("pipeline", "cache", "discovered_domains.jsonl")
    domains = set()
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    domain = obj.get("domain")
                    if domain:
                        domains.add(domain)
                except Exception:
                    continue
    return sorted(list(domains))


def load_vetted_domains() -> Dict[str, str]:
    """Load vetted domains and their decisions"""
    path = os.path.join("pipeline", "cache", "local_vet_results.jsonl")
    decisions = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    domain = obj.get("domain")
                    decision = obj.get("decision", "")
                    if domain:
                        decisions[domain] = decision
                except Exception:
                    continue
    return decisions


def get_yes_domains() -> List[str]:
    """Get domains that passed vetting (YES)"""
    decisions = load_vetted_domains()
    return [d for d, decision in decisions.items() if decision.upper() == "YES"]


def main():
    st.title("🔍 B2B OSINT Tool - Pipeline Control")
    st.markdown("---")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Full Pipeline", "Individual Stages", "RAG Query", "Status & Monitoring"]
    )
    
    if page == "Full Pipeline":
        show_full_pipeline()
    elif page == "Individual Stages":
        show_individual_stages()
    elif page == "RAG Query":
        show_rag_query()
    elif page == "Status & Monitoring":
        show_status_monitoring()


def show_full_pipeline():
    st.header("🚀 Full Pipeline Execution")
    st.markdown("Run the complete discovery → vetting → crawling → extraction → RAG pipeline")
    
    with st.form("full_pipeline_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            industry = st.text_input("Industry", value="goalkeeper gloves", help="Target industry to discover")
            max_discovery = st.number_input("Max Discovery Results", min_value=1, max_value=1000, value=100)
            max_crawl_pages = st.number_input("Max Pages per Site", min_value=1, max_value=10000, value=200)
            depth = st.number_input("Max Crawl Depth", min_value=1, max_value=5, value=2)
        
        with col2:
            skip_discovery = st.checkbox("Skip Discovery", help="Use cached discovered domains")
            concurrency = st.number_input("Page Concurrency", min_value=1, max_value=20, value=5, help="Pages to fetch in parallel per domain")
            max_parallel_domains = st.number_input("Max Parallel Domains", min_value=1, max_value=10, value=3, help="Domains to crawl simultaneously")
            auto_embed_rag = st.checkbox("Auto-embed for RAG", help="Automatically embed domains after extraction")
        
        submitted = st.form_submit_button("🚀 Run Full Pipeline", use_container_width=True)
        
        if submitted and not st.session_state.pipeline_running:
            st.session_state.pipeline_running = True
            run_full_pipeline(
                industry, max_discovery, max_crawl_pages, depth,
                skip_discovery, concurrency, max_parallel_domains, auto_embed_rag
            )
            st.session_state.pipeline_running = False


def run_full_pipeline(industry: str, max_discovery: int, max_crawl_pages: int, depth: int,
                     skip_discovery: bool, concurrency: int, max_parallel_domains: int,
                     auto_embed_rag: bool):
    """Run the full pipeline"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Step 1: Discovery
        if not skip_discovery:
            status_text.text("[1/5] Discovering domains...")
            progress_bar.progress(0.1)
            discovered = discover_domains(industry, max_results=max_discovery)
            st.success(f"✅ Discovered {len(discovered)} domains")
        else:
            status_text.text("[1/5] Loading cached domains...")
            progress_bar.progress(0.1)
            discovered = load_discovered_domains()
            st.info(f"📋 Loaded {len(discovered)} cached domains")
        
        # Step 2: Vetting
        status_text.text("[2/5] Vetting domains...")
        progress_bar.progress(0.3)
        
        # Rule-based vetting
        rule_results = rule_vet(discovered)
        auto_yes = rule_results.get("auto_yes", set())
        auto_no = rule_results.get("auto_no", set())
        unclear = rule_results.get("unclear", set())
        
        st.info(f"Rule-based: {len(auto_yes)} YES, {len(auto_no)} NO, {len(unclear)} unclear")
        
        # Local LLM vetting for unclear
        if unclear:
            unclear_list = list(unclear)
            with st.spinner("Running local LLM vetting..."):
                local_results = vet_domains_locally(unclear_list)
                yes_from_llm = [d for d, r in local_results.items() if r.get("decision", "").upper() == "YES"]
                no_from_llm = [d for d, r in local_results.items() if r.get("decision", "").upper() == "NO"]
            
            final_yes = list(auto_yes) + yes_from_llm
            st.success(f"✅ Final vetted YES: {len(final_yes)} domains")
        else:
            final_yes = list(auto_yes)
            st.success(f"✅ Final vetted YES: {len(final_yes)} domains")
        
        progress_bar.progress(0.4)
        
        # Step 3: Crawling
        status_text.text("[3/5] Crawling domains...")
        progress_bar.progress(0.5)
        
        crawl_status = get_crawl_status(final_yes, "crawled_data")
        fully_crawled = [d for d, s in crawl_status.items() if s.get("fully_crawled")]
        to_crawl = [d for d in final_yes if d not in fully_crawled]
        
        if to_crawl:
            st.info(f"Crawling {len(to_crawl)} domains ({len(fully_crawled)} already crawled)")
            crawl_domains(
                to_crawl,
                output_dir="crawled_data",
                max_pages=max_crawl_pages,
                max_depth=depth,
                skip_crawled=True,
                concurrency=concurrency,
                max_parallel_domains=max_parallel_domains
            )
            st.success(f"✅ Crawled {len(to_crawl)} domains")
        else:
            st.info("✅ All domains already crawled")
        
        progress_bar.progress(0.7)
        
        # Step 4: Extraction
        status_text.text("[4/5] Extracting company profiles and products...")
        progress_bar.progress(0.8)
        
        extracted_count = 0
        for domain in st.progress_bar(final_yes, desc="Extracting"):
            profile = extract_company_profile(domain, "crawled_data")
            if profile:
                products = extract_products(domain, "crawled_data", industry=industry)
                save_company_data(domain, profile, products, "extracted_data")
                extracted_count += 1
        
        build_global_indexes("extracted_data")
        st.success(f"✅ Extracted data from {extracted_count} domains")
        
        progress_bar.progress(0.9)
        
        # Step 5: RAG Embedding (optional)
        if auto_embed_rag:
            status_text.text("[5/5] Embedding domains for RAG...")
            progress_bar.progress(0.95)
            
            try:
                embed_all_domains("crawled_data", "extracted_data", force_reembed=False)
                st.success("✅ RAG embedding complete")
            except Exception as e:
                st.error(f"❌ RAG embedding error: {e}")
        else:
            status_text.text("[5/5] Skipping RAG embedding")
        
        progress_bar.progress(1.0)
        status_text.text("✅ Pipeline complete!")
        st.balloons()
        
    except Exception as e:
        st.error(f"❌ Pipeline error: {e}")
        import traceback
        st.code(traceback.format_exc())


def show_individual_stages():
    st.header("🔧 Individual Stage Execution")
    st.markdown("Run individual pipeline stages independently")
    
    stage = st.selectbox(
        "Select Stage",
        ["Discovery", "Vetting", "Crawling", "Extraction", "RAG Embedding"]
    )
    
    if stage == "Discovery":
        show_discovery_stage()
    elif stage == "Vetting":
        show_vetting_stage()
    elif stage == "Crawling":
        show_crawling_stage()
    elif stage == "Extraction":
        show_extraction_stage()
    elif stage == "RAG Embedding":
        show_rag_embedding_stage()


def show_discovery_stage():
    st.subheader("🔍 Discovery Stage")
    
    with st.form("discovery_form"):
        industry = st.text_input("Industry", value="goalkeeper gloves")
        max_results = st.number_input("Max Results", min_value=1, max_value=1000, value=100)
        
        submitted = st.form_submit_button("Run Discovery", use_container_width=True)
        
        if submitted:
            with st.spinner("Discovering domains..."):
                discovered = discover_domains(industry, max_results=max_results)
                st.success(f"✅ Discovered {len(discovered)} domains")
                st.json(discovered[:10])  # Show first 10


def show_vetting_stage():
    st.subheader("✅ Vetting Stage")
    
    discovered = load_discovered_domains()
    if not discovered:
        st.warning("No discovered domains found. Run discovery first.")
        return
    
    st.info(f"Found {len(discovered)} discovered domains")
    
    if st.button("Run Vetting", use_container_width=True):
        with st.spinner("Vetting domains..."):
            # Rule-based
            rule_results = rule_vet(discovered)
            auto_yes = rule_results.get("auto_yes", set())
            auto_no = rule_results.get("auto_no", set())
            unclear = rule_results.get("unclear", set())
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Auto YES", len(auto_yes))
            col2.metric("Auto NO", len(auto_no))
            col3.metric("Unclear", len(unclear))
            
            # Local LLM vetting
            if unclear:
                with st.spinner("Running local LLM vetting..."):
                    unclear_list = list(unclear)
                    local_results = vet_domains_locally(unclear_list)
                    yes_from_llm = [d for d, r in local_results.items() if r.get("decision", "").upper() == "YES"]
                    no_from_llm = [d for d, r in local_results.items() if r.get("decision", "").upper() == "NO"]
                    
                    final_yes = list(auto_yes) + yes_from_llm
                    final_no = list(auto_no) + no_from_llm
                    
                    st.success(f"✅ Final YES: {len(final_yes)}, Final NO: {len(final_no)}")
                    
                    with st.expander("View YES domains"):
                        st.write(final_yes)
            else:
                st.success(f"✅ All domains classified by rules: {len(auto_yes)} YES, {len(auto_no)} NO")


def show_crawling_stage():
    st.subheader("🕷️ Crawling Stage")
    
    yes_domains = get_yes_domains()
    if not yes_domains:
        st.warning("No YES domains found. Run vetting first.")
        return
    
    st.info(f"Found {len(yes_domains)} YES domains")
    
    with st.form("crawling_form"):
        max_pages = st.number_input("Max Pages per Domain", min_value=1, max_value=10000, value=200)
        max_depth = st.number_input("Max Depth", min_value=1, max_value=5, value=2)
        concurrency = st.number_input("Page Concurrency", min_value=1, max_value=20, value=5)
        max_parallel_domains = st.number_input("Max Parallel Domains", min_value=1, max_value=10, value=3)
        
        submitted = st.form_submit_button("Start Crawling", use_container_width=True)
        
        if submitted:
            # Check status
            crawl_status = get_crawl_status(yes_domains, "crawled_data")
            fully_crawled = [d for d, s in crawl_status.items() if s.get("fully_crawled")]
            to_crawl = [d for d in yes_domains if d not in fully_crawled]
            
            st.info(f"Will crawl {len(to_crawl)} domains ({len(fully_crawled)} already crawled)")
            
            if to_crawl:
                with st.spinner("Crawling domains..."):
                    crawl_domains(
                        to_crawl,
                        output_dir="crawled_data",
                        max_pages=max_pages,
                        max_depth=max_depth,
                        skip_crawled=True,
                        concurrency=concurrency,
                        max_parallel_domains=max_parallel_domains
                    )
                    st.success(f"✅ Crawled {len(to_crawl)} domains")
            else:
                st.info("✅ All domains already crawled")


def show_extraction_stage():
    st.subheader("📊 Extraction Stage")
    
    yes_domains = get_yes_domains()
    if not yes_domains:
        st.warning("No YES domains found. Run vetting first.")
        return
    
    st.info(f"Found {len(yes_domains)} YES domains")
    
    with st.form("extraction_form"):
        industry = st.text_input("Industry Filter", value="goalkeeper gloves", help="Filter products by industry")
        
        submitted = st.form_submit_button("Start Extraction", use_container_width=True)
        
        if submitted:
            extracted_count = 0
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, domain in enumerate(yes_domains):
                progress_bar.progress((i + 1) / len(yes_domains))
                status_text.text(f"Processing {i+1}/{len(yes_domains)}: {domain}")
                
                with st.spinner(f"Extracting {domain}..."):
                    profile = extract_company_profile(domain, "crawled_data")
                    if profile:
                        products = extract_products(domain, "crawled_data", industry=industry)
                        save_company_data(domain, profile, products, "extracted_data")
                        extracted_count += 1
            
            build_global_indexes("extracted_data")
            st.success(f"✅ Extracted data from {extracted_count} domains")


def show_rag_embedding_stage():
    st.subheader("🧠 RAG Embedding Stage")
    
    with st.form("rag_embed_form"):
        force_reembed = st.checkbox("Force Re-embed", help="Re-embed all domains even if already embedded")
        specific_domain = st.text_input("Specific Domain (optional)", help="Leave empty to embed all domains")
        
        submitted = st.form_submit_button("Start Embedding", use_container_width=True)
        
        if submitted:
            if specific_domain:
                with st.spinner(f"Embedding {specific_domain}..."):
                    try:
                        result = asyncio.run(embed_domain(specific_domain, force_reembed))
                        st.success(f"✅ Embedded: {result['new_embeddings']} new, {result['skipped_embeddings']} skipped")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
            else:
                with st.spinner("Embedding all domains..."):
                    try:
                        embed_all_domains("crawled_data", "extracted_data", force_reembed)
                        st.success("✅ Embedding complete")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")


def show_rag_query():
    st.header("💬 RAG Query Interface")
    st.markdown("Query your embedded data using natural language")
    
    # Check if embeddings exist
    try:
        chroma_client = _get_chroma_client()
        collections = ["raw_pages", "products", "companies"]
        has_collections = all(
            any(c.name == coll for c in chroma_client.list_collections())
            for coll in collections
        )
        
        if not has_collections:
            st.warning("⚠️ No RAG embeddings found. Run RAG embedding first.")
            if st.button("Go to RAG Embedding"):
                st.session_state.page = "Individual Stages"
                st.rerun()
            return
    except Exception:
        st.warning("⚠️ RAG database not initialized. Run RAG embedding first.")
        return
    
    # Query form
    col1, col2 = st.columns([2, 1])
    
    with col1:
        query = st.text_input("Enter your query", placeholder="e.g., What companies do we have?")
    
    with col2:
        top_k = st.number_input("Top K Results", min_value=1, max_value=20, value=5)
    
    # Filters
    with st.expander("Advanced Filters"):
        col1, col2 = st.columns(2)
        with col1:
            domain_filter = st.text_input("Domain Filter", help="Filter by specific domain")
            brand_filter = st.text_input("Brand Filter", help="Filter by brand name")
        with col2:
            collections = st.multiselect(
                "Collections to Search",
                ["raw_pages", "products", "companies"],
                default=["raw_pages", "products", "companies"]
            )
            use_llm = st.checkbox("Use LLM for Answer", value=True, help="Generate intelligent answer using LLM")
    
    if st.button("🔍 Query", use_container_width=True, type="primary"):
        if not query:
            st.warning("Please enter a query")
            return
        
        filters = {}
        if domain_filter:
            filters["domain"] = domain_filter
        if brand_filter:
            filters["brand"] = brand_filter
        
        # Execute query
        with st.spinner("Searching..."):
            if use_llm:
                answer = get_rag_answer(query, collections, filters, top_k, use_openai=True)
                st.subheader("🤖 Answer")
                st.write(answer)
                st.markdown("---")
            
            # Show raw results
            results = query_rag(query, collections, filters, top_k)
            
            st.subheader(f"📋 Top {len(results)} Results")
            
            for i, result in enumerate(results, 1):
                with st.expander(f"[{i}] {result['collection']} - {result['metadata'].get('domain', 'N/A')}"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write("**Content:**")
                        st.write(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
                    
                    with col2:
                        distance = result.get('distance')
                        if distance is not None:
                            if isinstance(distance, list) and len(distance) > 0:
                                distance_str = f"{distance[0]:.4f}"
                            elif isinstance(distance, (int, float)):
                                distance_str = f"{distance:.4f}"
                            else:
                                distance_str = "N/A"
                        else:
                            distance_str = "N/A"
                        
                        st.metric("Distance", distance_str)
                    
                    # Metadata
                    if result['metadata']:
                        st.write("**Metadata:**")
                        st.json(result['metadata'])


def show_status_monitoring():
    st.header("📊 Status & Monitoring")
    
    # Discovered domains
    st.subheader("🔍 Discovered Domains")
    discovered = load_discovered_domains()
    st.metric("Total Discovered", len(discovered))
    
    if discovered:
        with st.expander("View Discovered Domains"):
            st.write(discovered)
    
    # Vetted domains
    st.subheader("✅ Vetted Domains")
    decisions = load_vetted_domains()
    yes_domains = [d for d, decision in decisions.items() if decision.upper() == "YES"]
    no_domains = [d for d, decision in decisions.items() if decision.upper() == "NO"]
    
    col1, col2 = st.columns(2)
    col1.metric("YES", len(yes_domains))
    col2.metric("NO", len(no_domains))
    
    # Crawl status
    if yes_domains:
        st.subheader("🕷️ Crawl Status")
        crawl_status = get_crawl_status(yes_domains, "crawled_data")
        
        fully_crawled = [d for d, s in crawl_status.items() if s.get("fully_crawled")]
        in_progress = [d for d, s in crawl_status.items() if s.get("in_progress")]
        not_started = [d for d in yes_domains if d not in fully_crawled and d not in in_progress]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Fully Crawled", len(fully_crawled))
        col2.metric("In Progress", len(in_progress))
        col3.metric("Not Started", len(not_started))
        
        # Total pages
        total_pages = sum(s.get("pages", 0) for s in crawl_status.values())
        st.metric("Total Pages Crawled", total_pages)
    
    # Extraction status
    st.subheader("📊 Extraction Status")
    extracted_dir = os.path.join("extracted_data", "companies")
    if os.path.exists(extracted_dir):
        extracted_domains = [d for d in os.listdir(extracted_dir) 
                            if os.path.isdir(os.path.join(extracted_dir, d))]
        st.metric("Domains Extracted", len(extracted_domains))
        
        # Count products
        total_products = 0
        for domain in extracted_domains:
            products_file = os.path.join(extracted_dir, domain, "products.jsonl")
            if os.path.exists(products_file):
                with open(products_file, 'r', encoding='utf-8') as f:
                    total_products += sum(1 for _ in f)
        
        st.metric("Total Products Extracted", total_products)
    else:
        st.info("No extracted data yet")
    
    # RAG status
    st.subheader("🧠 RAG Status")
    try:
        tracker = _load_embedded_tracker()
        chroma_client = _get_chroma_client()
        
        st.metric("Domains Embedded", len(tracker))
        
        # Collection stats
        for collection_name in ["raw_pages", "products", "companies"]:
            try:
                collection = chroma_client.get_collection(collection_name)
                count = collection.count()
                st.metric(f"{collection_name} chunks", count)
            except Exception:
                st.info(f"{collection_name}: Not created yet")
    except Exception as e:
        st.warning(f"RAG database not available: {e}")


if __name__ == "__main__":
    main()

