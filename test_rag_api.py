"""
Quick test script for the Agentic RAG API.

Usage:
    python test_rag_api.py
"""
import os
import sys
import django
import json

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce.settings")
django.setup()

from ai_agentic_rag.graph.workflow import run_query


def test_queries():
    """Test various query types through the RAG system."""
    
    test_cases = [
        {
            "name": "Product Search",
            "query": "best gaming laptop under 80000",
        },
        {
            "name": "Stock Check",
            "query": "is iPhone 15 in stock",
        },
        {
            "name": "Recommendation",
            "query": "recommend a phone with good camera",
        },
        {
            "name": "Factual Query",
            "query": "What is the difference between SSD and HDD storage",
        },
    ]

    print("=" * 80)
    print("AGENTIC RAG SYSTEM — TEST SUITE")
    print("=" * 80)

    for i, test in enumerate(test_cases, 1):
        print(f"\n[Test {i}] {test['name']}")
        print(f"Query: {test['query']}")
        print("-" * 80)

        try:
            result = run_query(query=test["query"])

            print(f"✓ Intent:        {result.get('intent', 'N/A')}")
            print(f"✓ Confidence:    {result.get('confidence', 0.0):.2%}")
            print(f"✓ Tools Used:    {', '.join(result.get('tools_used', []))}")
            print(f"✓ Loop Count:    {result.get('loop_count', 0)}")
            
            answer = result.get("answer", "No answer").strip()
            if len(answer) > 200:
                print(f"\nAnswer:\n{answer[:200]}...\n")
            else:
                print(f"\nAnswer:\n{answer}\n")

            notes = result.get("evaluation_notes", "").strip()
            if notes:
                print(f"Notes: {notes}")

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("All tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    test_queries()
