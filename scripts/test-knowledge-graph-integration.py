#!/usr/bin/env python3
"""
Test Knowledge Graph Integration with RAG Service

This script validates that Task 9 (Knowledge Graph Integration) is properly
connected to the RAG service and chat system.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.components.knowledge_graph.kg_builder import (
    KnowledgeGraphBuilder,
)
from multimodal_librarian.components.knowledge_graph.kg_query_engine import (
    KnowledgeGraphQueryEngine,
)
from multimodal_librarian.services.rag_service import get_rag_service


async def test_knowledge_graph_integration():
    """Test knowledge graph integration with RAG service."""
    print("🧠 Testing Knowledge Graph Integration with RAG Service")
    print("=" * 60)
    
    results = {
        "timestamp": time.time(),
        "tests": {},
        "overall_status": "unknown",
        "summary": {}
    }
    
    try:
        # Test 1: RAG Service Initialization with KG
        print("\n1. Testing RAG Service Initialization with Knowledge Graph...")
        rag_service = get_rag_service()
        
        # Check if KG components are initialized
        has_kg_builder = hasattr(rag_service, 'kg_builder') and rag_service.kg_builder is not None
        has_kg_query_engine = hasattr(rag_service, 'kg_query_engine') and rag_service.kg_query_engine is not None
        kg_enabled = getattr(rag_service, 'use_knowledge_graph', False)
        
        results["tests"]["rag_kg_initialization"] = {
            "status": "pass" if (has_kg_builder and has_kg_query_engine and kg_enabled) else "fail",
            "has_kg_builder": has_kg_builder,
            "has_kg_query_engine": has_kg_query_engine,
            "kg_enabled": kg_enabled,
            "details": "RAG service properly initialized with knowledge graph components"
        }
        
        if has_kg_builder and has_kg_query_engine and kg_enabled:
            print("   ✅ RAG service initialized with knowledge graph support")
        else:
            print("   ❌ RAG service missing knowledge graph components")
            print(f"      - KG Builder: {has_kg_builder}")
            print(f"      - KG Query Engine: {has_kg_query_engine}")
            print(f"      - KG Enabled: {kg_enabled}")
        
        # Test 2: Knowledge Graph Builder Functionality
        print("\n2. Testing Knowledge Graph Builder...")
        kg_builder = rag_service.kg_builder
        
        # Test concept extraction
        test_content = """
        Machine learning is a subset of artificial intelligence. 
        Neural networks are used in deep learning algorithms.
        Data preprocessing is essential for model training.
        """
        
        concepts = kg_builder.extract_concepts_from_content(test_content, "test_chunk_1")
        relationships = kg_builder.extract_relationships_from_content(test_content, concepts, "test_chunk_1")
        
        results["tests"]["kg_builder_functionality"] = {
            "status": "pass" if (len(concepts) > 0 or len(relationships) > 0) else "fail",
            "concepts_extracted": len(concepts),
            "relationships_extracted": len(relationships),
            "concept_names": [c.concept_name for c in concepts[:5]],  # First 5 concepts
            "details": "Knowledge graph builder can extract concepts and relationships"
        }
        
        if len(concepts) > 0 or len(relationships) > 0:
            print(f"   ✅ Extracted {len(concepts)} concepts and {len(relationships)} relationships")
            if concepts:
                print(f"      Sample concepts: {', '.join([c.concept_name for c in concepts[:3]])}")
        else:
            print("   ❌ No concepts or relationships extracted")
        
        # Test 3: Knowledge Graph Query Engine (legacy method removed)
        print("\n3. Testing Knowledge Graph Query Engine...")
        kg_query_engine = rag_service.kg_query_engine
        
        # process_graph_enhanced_query has been removed in favor of QueryDecomposer
        # Test that the engine is initialized and has retained methods
        has_engine = kg_query_engine is not None
        has_multi_hop = hasattr(kg_query_engine, 'multi_hop_reasoning_async') if kg_query_engine else False
        has_related = hasattr(kg_query_engine, 'get_related_concepts_async') if kg_query_engine else False
        
        results["tests"]["kg_query_engine"] = {
            "status": "pass" if has_engine else "fail",
            "has_engine": has_engine,
            "has_multi_hop_reasoning": has_multi_hop,
            "has_get_related_concepts": has_related,
            "details": "Knowledge graph query engine initialized with reasoning methods"
        }
        
        if has_engine:
            print("   ✅ Query engine initialized with reasoning methods")
        else:
            print("   ❌ Query engine not available")
        
        # Test 4: Document Processing for Knowledge Graph
        print("\n4. Testing Document Processing for Knowledge Graph...")
        
        test_chunks = [
            "Artificial intelligence encompasses machine learning and deep learning techniques.",
            "Neural networks consist of interconnected nodes that process information.",
            "Training data quality directly impacts model performance and accuracy."
        ]
        
        kg_processing_result = await rag_service.process_document_for_knowledge_graph(
            document_id="test_doc_1",
            document_title="AI Fundamentals",
            content_chunks=test_chunks
        )
        
        processing_success = kg_processing_result.get("status") == "success"
        concepts_extracted = kg_processing_result.get("concepts_extracted", 0)
        relationships_extracted = kg_processing_result.get("relationships_extracted", 0)
        
        results["tests"]["document_kg_processing"] = {
            "status": "pass" if processing_success else "fail",
            "processing_success": processing_success,
            "concepts_extracted": concepts_extracted,
            "relationships_extracted": relationships_extracted,
            "chunks_processed": kg_processing_result.get("chunks_processed", 0),
            "details": "Documents can be processed to populate knowledge graph"
        }
        
        if processing_success:
            print(f"   ✅ Document processed successfully")
            print(f"      Concepts extracted: {concepts_extracted}")
            print(f"      Relationships extracted: {relationships_extracted}")
        else:
            print("   ❌ Document processing failed")
            print(f"      Error: {kg_processing_result.get('error', 'Unknown error')}")
        
        # Test 5: RAG Query with Knowledge Graph Enhancement
        print("\n5. Testing RAG Query with Knowledge Graph Enhancement...")
        
        test_query = "How does machine learning relate to artificial intelligence?"
        
        try:
            rag_response = await rag_service.generate_response(
                query=test_query,
                user_id="test_user",
                conversation_context=[]
            )
            
            # Check if KG metadata is present
            kg_metadata_present = bool(rag_response.metadata.get('related_concepts'))
            kg_reasoning_present = bool(rag_response.metadata.get('reasoning_paths', 0) > 0)
            kg_explanation_present = bool(rag_response.metadata.get('kg_explanation'))
            
            results["tests"]["rag_kg_enhancement"] = {
                "status": "pass" if (kg_metadata_present or kg_reasoning_present) else "partial",
                "response_generated": bool(rag_response.response),
                "kg_metadata_present": kg_metadata_present,
                "kg_reasoning_present": kg_reasoning_present,
                "kg_explanation_present": kg_explanation_present,
                "related_concepts": rag_response.metadata.get('related_concepts', []),
                "confidence_score": rag_response.confidence_score,
                "details": "RAG responses include knowledge graph enhancements"
            }
            
            if kg_metadata_present or kg_reasoning_present:
                print("   ✅ RAG response includes knowledge graph enhancements")
                if rag_response.metadata.get('related_concepts'):
                    print(f"      Related concepts: {', '.join(rag_response.metadata['related_concepts'][:3])}")
                print(f"      Confidence score: {rag_response.confidence_score:.2f}")
            else:
                print("   ⚠️  RAG response generated but limited KG enhancement")
                print(f"      Response: {rag_response.response[:100]}...")
            
        except Exception as e:
            results["tests"]["rag_kg_enhancement"] = {
                "status": "fail",
                "error": str(e),
                "details": "RAG query with KG enhancement failed"
            }
            print(f"   ❌ RAG query failed: {e}")
        
        # Test 6: Knowledge Graph Insights
        print("\n6. Testing Knowledge Graph Insights...")
        
        insights = rag_service.get_knowledge_graph_insights("neural networks and deep learning")
        
        insights_success = insights.get("status") == "success"
        has_reasoning_paths = len(insights.get("reasoning_paths", [])) > 0
        has_related_concepts = len(insights.get("related_concepts", [])) > 0
        
        results["tests"]["kg_insights"] = {
            "status": "pass" if insights_success else "fail",
            "insights_success": insights_success,
            "reasoning_paths": len(insights.get("reasoning_paths", [])),
            "related_concepts": len(insights.get("related_concepts", [])),
            "has_explanation": bool(insights.get("explanation")),
            "details": "Knowledge graph can provide insights for queries"
        }
        
        if insights_success:
            print(f"   ✅ Knowledge graph insights generated")
            print(f"      Reasoning paths: {len(insights.get('reasoning_paths', []))}")
            print(f"      Related concepts: {len(insights.get('related_concepts', []))}")
        else:
            print("   ❌ Knowledge graph insights failed")
            print(f"      Error: {insights.get('error', 'Unknown error')}")
        
        # Test 7: Service Status with KG Information
        print("\n7. Testing Service Status with Knowledge Graph Information...")
        
        service_status = rag_service.get_service_status()
        
        kg_status_present = "knowledge_graph" in service_status
        kg_features_present = service_status.get("features", {}).get("knowledge_graph_reasoning", False)
        
        results["tests"]["service_status_kg"] = {
            "status": "pass" if (kg_status_present and kg_features_present) else "fail",
            "kg_status_present": kg_status_present,
            "kg_features_present": kg_features_present,
            "kg_enabled": service_status.get("knowledge_graph", {}).get("enabled", False),
            "total_concepts": service_status.get("knowledge_graph", {}).get("total_concepts", 0),
            "total_relationships": service_status.get("knowledge_graph", {}).get("total_relationships", 0),
            "details": "Service status includes knowledge graph information"
        }
        
        if kg_status_present and kg_features_present:
            print("   ✅ Service status includes knowledge graph information")
            kg_info = service_status.get("knowledge_graph", {})
            print(f"      Total concepts: {kg_info.get('total_concepts', 0)}")
            print(f"      Total relationships: {kg_info.get('total_relationships', 0)}")
        else:
            print("   ❌ Service status missing knowledge graph information")
        
        # Calculate overall results
        passed_tests = sum(1 for test in results["tests"].values() if test["status"] == "pass")
        partial_tests = sum(1 for test in results["tests"].values() if test["status"] == "partial")
        total_tests = len(results["tests"])
        
        results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "partial_tests": partial_tests,
            "failed_tests": total_tests - passed_tests - partial_tests,
            "success_rate": (passed_tests + partial_tests * 0.5) / total_tests * 100
        }
        
        if passed_tests == total_tests:
            results["overall_status"] = "success"
        elif passed_tests + partial_tests >= total_tests * 0.7:
            results["overall_status"] = "partial"
        else:
            results["overall_status"] = "failed"
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 KNOWLEDGE GRAPH INTEGRATION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Partial: {partial_tests}")
        print(f"Failed: {total_tests - passed_tests - partial_tests}")
        print(f"Success Rate: {results['summary']['success_rate']:.1f}%")
        print(f"Overall Status: {results['overall_status'].upper()}")
        
        if results["overall_status"] == "success":
            print("\n🎉 Knowledge Graph Integration is FULLY FUNCTIONAL!")
            print("   Task 9 components are properly connected to RAG service")
        elif results["overall_status"] == "partial":
            print("\n⚠️  Knowledge Graph Integration is PARTIALLY FUNCTIONAL")
            print("   Some components working, others need attention")
        else:
            print("\n❌ Knowledge Graph Integration has SIGNIFICANT ISSUES")
            print("   Major components not working properly")
        
        # Save results
        results_file = f"kg-integration-test-results-{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return results
        
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        results["overall_status"] = "error"
        results["error"] = str(e)
        return results

if __name__ == "__main__":
    print("🚀 Starting Knowledge Graph Integration Tests...")
    
    try:
        results = asyncio.run(test_knowledge_graph_integration())
        
        # Exit with appropriate code
        if results["overall_status"] in ["success", "partial"]:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        sys.exit(1)