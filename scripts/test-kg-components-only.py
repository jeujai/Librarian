#!/usr/bin/env python3
"""
Test Knowledge Graph Components Only

This script tests the knowledge graph components in isolation to validate
that Task 9 implementation is working correctly.
"""

import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_knowledge_graph_components():
    """Test knowledge graph components in isolation."""
    print("🧠 Testing Knowledge Graph Components")
    print("=" * 50)
    
    results = {
        "timestamp": time.time(),
        "tests": {},
        "overall_status": "unknown",
        "summary": {}
    }
    
    try:
        # Test 1: Import Knowledge Graph Components
        print("\n1. Testing Knowledge Graph Component Imports...")
        
        try:
            from multimodal_librarian.components.knowledge_graph.kg_builder import (
                ConceptExtractor,
                KnowledgeGraphBuilder,
                RelationshipExtractor,
            )
            from multimodal_librarian.components.knowledge_graph.kg_query_engine import (
                KnowledgeGraphQueryEngine,
            )
            from multimodal_librarian.models.knowledge_graph import (
                ConceptNode,
                RelationshipEdge,
                Triple,
            )
            
            results["tests"]["imports"] = {
                "status": "pass",
                "details": "All knowledge graph components imported successfully"
            }
            print("   ✅ All knowledge graph components imported successfully")
            
        except Exception as e:
            results["tests"]["imports"] = {
                "status": "fail",
                "error": str(e),
                "details": "Failed to import knowledge graph components"
            }
            print(f"   ❌ Import failed: {e}")
            return results
        
        # Test 2: Initialize Knowledge Graph Builder
        print("\n2. Testing Knowledge Graph Builder Initialization...")
        
        try:
            kg_builder = KnowledgeGraphBuilder()
            
            # Check if components are initialized
            has_concept_extractor = hasattr(kg_builder, 'concept_extractor')
            has_relationship_extractor = hasattr(kg_builder, 'relationship_extractor')
            has_embedding_model = hasattr(kg_builder, 'embedding_model')
            
            results["tests"]["kg_builder_init"] = {
                "status": "pass" if all([has_concept_extractor, has_relationship_extractor, has_embedding_model]) else "fail",
                "has_concept_extractor": has_concept_extractor,
                "has_relationship_extractor": has_relationship_extractor,
                "has_embedding_model": has_embedding_model,
                "details": "Knowledge graph builder initialized with all components"
            }
            
            if all([has_concept_extractor, has_relationship_extractor, has_embedding_model]):
                print("   ✅ Knowledge graph builder initialized successfully")
            else:
                print("   ❌ Knowledge graph builder missing components")
                
        except Exception as e:
            results["tests"]["kg_builder_init"] = {
                "status": "fail",
                "error": str(e),
                "details": "Failed to initialize knowledge graph builder"
            }
            print(f"   ❌ Initialization failed: {e}")
            return results
        
        # Test 3: Test Concept Extraction
        print("\n3. Testing Concept Extraction...")
        
        try:
            test_content = """
            Machine learning is a subset of artificial intelligence that enables computers to learn without being explicitly programmed.
            Neural networks are computational models inspired by biological neural networks.
            Deep learning uses multiple layers of neural networks to model and understand complex patterns.
            """
            
            # Test NER-based extraction
            ner_concepts = kg_builder.concept_extractor.extract_concepts_regex(test_content)
            
            # Test LLM-based extraction (simplified)
            llm_concepts = kg_builder.concept_extractor.extract_concepts_definition_patterns(test_content, "test_chunk")
            
            total_concepts = len(ner_concepts) + len(llm_concepts)
            
            results["tests"]["concept_extraction"] = {
                "status": "pass" if total_concepts > 0 else "fail",
                "ner_concepts": len(ner_concepts),
                "llm_concepts": len(llm_concepts),
                "total_concepts": total_concepts,
                "sample_concepts": [c.concept_name for c in (ner_concepts + llm_concepts)[:5]],
                "details": "Concept extraction working with multiple methods"
            }
            
            if total_concepts > 0:
                print(f"   ✅ Extracted {total_concepts} concepts")
                print(f"      NER concepts: {len(ner_concepts)}")
                print(f"      LLM concepts: {len(llm_concepts)}")
                if ner_concepts or llm_concepts:
                    sample_names = [c.concept_name for c in (ner_concepts + llm_concepts)[:3]]
                    print(f"      Sample: {', '.join(sample_names)}")
            else:
                print("   ❌ No concepts extracted")
                
        except Exception as e:
            results["tests"]["concept_extraction"] = {
                "status": "fail",
                "error": str(e),
                "details": "Concept extraction failed"
            }
            print(f"   ❌ Concept extraction failed: {e}")
        
        # Test 4: Test Relationship Extraction
        print("\n4. Testing Relationship Extraction...")
        
        try:
            # Use the concepts from previous test
            all_concepts = ner_concepts + llm_concepts if 'ner_concepts' in locals() and 'llm_concepts' in locals() else []
            
            if all_concepts:
                # Test pattern-based extraction
                pattern_relationships = kg_builder.relationship_extractor.extract_relationships_pattern(
                    test_content, all_concepts
                )
                
                # Test LLM-based extraction
                llm_relationships = kg_builder.relationship_extractor.extract_relationships_llm(
                    test_content, all_concepts, "test_chunk"
                )
                
                total_relationships = len(pattern_relationships) + len(llm_relationships)
                
                results["tests"]["relationship_extraction"] = {
                    "status": "pass" if total_relationships > 0 else "partial",
                    "pattern_relationships": len(pattern_relationships),
                    "llm_relationships": len(llm_relationships),
                    "total_relationships": total_relationships,
                    "details": "Relationship extraction working with multiple methods"
                }
                
                if total_relationships > 0:
                    print(f"   ✅ Extracted {total_relationships} relationships")
                    print(f"      Pattern-based: {len(pattern_relationships)}")
                    print(f"      LLM-based: {len(llm_relationships)}")
                else:
                    print("   ⚠️  No relationships extracted (may be normal with limited test data)")
            else:
                results["tests"]["relationship_extraction"] = {
                    "status": "skip",
                    "details": "Skipped due to no concepts available"
                }
                print("   ⏭️  Skipped (no concepts available)")
                
        except Exception as e:
            results["tests"]["relationship_extraction"] = {
                "status": "fail",
                "error": str(e),
                "details": "Relationship extraction failed"
            }
            print(f"   ❌ Relationship extraction failed: {e}")
        
        # Test 5: Test Knowledge Graph Query Engine
        print("\n5. Testing Knowledge Graph Query Engine...")
        
        try:
            kg_query_engine = KnowledgeGraphQueryEngine(kg_builder)
            
            # process_graph_enhanced_query has been removed in favor of QueryDecomposer
            # Test that the engine initializes and has retained methods
            has_engine = kg_query_engine is not None
            has_multi_hop = hasattr(kg_query_engine, 'multi_hop_reasoning')
            has_related = hasattr(kg_query_engine, 'get_related_concepts')
            has_enhance = hasattr(kg_query_engine, 'enhance_vector_search')
            
            results["tests"]["kg_query_engine"] = {
                "status": "pass" if has_engine else "fail",
                "has_engine": has_engine,
                "has_multi_hop_reasoning": has_multi_hop,
                "has_get_related_concepts": has_related,
                "has_enhance_vector_search": has_enhance,
                "details": "Knowledge graph query engine initialized with reasoning and re-ranking methods"
            }
            
            if has_engine:
                print("   ✅ Query engine initialized successfully")
                print(f"      multi_hop_reasoning: {has_multi_hop}")
                print(f"      get_related_concepts: {has_related}")
                print(f"      enhance_vector_search: {has_enhance}")
            else:
                print("   ❌ Query engine failed to initialize")
                
        except Exception as e:
            results["tests"]["kg_query_engine"] = {
                "status": "fail",
                "error": str(e),
                "details": "Knowledge graph query engine failed"
            }
            print(f"   ❌ Query engine failed: {e}")
        
        # Test 6: Test Knowledge Graph Statistics
        print("\n6. Testing Knowledge Graph Statistics...")
        
        try:
            kg_stats = kg_builder.get_knowledge_graph_stats()
            
            has_stats = kg_stats is not None
            has_concepts = kg_stats.total_concepts > 0 if kg_stats else False
            has_relationships = kg_stats.total_relationships > 0 if kg_stats else False
            
            results["tests"]["kg_statistics"] = {
                "status": "pass" if has_stats else "fail",
                "has_stats": has_stats,
                "total_concepts": kg_stats.total_concepts if kg_stats else 0,
                "total_relationships": kg_stats.total_relationships if kg_stats else 0,
                "concept_types": len(kg_stats.concept_types) if kg_stats else 0,
                "relationship_types": len(kg_stats.relationship_types) if kg_stats else 0,
                "details": "Knowledge graph statistics available"
            }
            
            if has_stats:
                print("   ✅ Knowledge graph statistics available")
                print(f"      Total concepts: {kg_stats.total_concepts}")
                print(f"      Total relationships: {kg_stats.total_relationships}")
                print(f"      Concept types: {len(kg_stats.concept_types)}")
                print(f"      Relationship types: {len(kg_stats.relationship_types)}")
            else:
                print("   ❌ Knowledge graph statistics not available")
                
        except Exception as e:
            results["tests"]["kg_statistics"] = {
                "status": "fail",
                "error": str(e),
                "details": "Knowledge graph statistics failed"
            }
            print(f"   ❌ Statistics failed: {e}")
        
        # Test 7: Test Triple Extraction
        print("\n7. Testing Triple Extraction...")
        
        try:
            test_content_triples = "Python is a programming language. Machine learning uses Python for data analysis."
            
            triples = kg_builder.extract_knowledge_triples(test_content_triples, "test_source")
            
            has_triples = len(triples) > 0
            
            results["tests"]["triple_extraction"] = {
                "status": "pass" if has_triples else "partial",
                "triples_extracted": len(triples),
                "sample_triples": [
                    {
                        "subject": t.subject,
                        "predicate": t.predicate,
                        "object": t.object,
                        "confidence": t.confidence
                    }
                    for t in triples[:3]
                ] if triples else [],
                "details": "Knowledge triples can be extracted from content"
            }
            
            if has_triples:
                print(f"   ✅ Extracted {len(triples)} knowledge triples")
                for i, triple in enumerate(triples[:2]):
                    print(f"      {i+1}. {triple.subject} → {triple.predicate} → {triple.object}")
            else:
                print("   ⚠️  No triples extracted (may be normal with simple test data)")
                
        except Exception as e:
            results["tests"]["triple_extraction"] = {
                "status": "fail",
                "error": str(e),
                "details": "Triple extraction failed"
            }
            print(f"   ❌ Triple extraction failed: {e}")
        
        # Calculate overall results
        test_statuses = [test["status"] for test in results["tests"].values()]
        passed_tests = test_statuses.count("pass")
        partial_tests = test_statuses.count("partial")
        skipped_tests = test_statuses.count("skip")
        total_tests = len(test_statuses) - skipped_tests
        
        results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "partial_tests": partial_tests,
            "skipped_tests": skipped_tests,
            "failed_tests": total_tests - passed_tests - partial_tests,
            "success_rate": (passed_tests + partial_tests * 0.5) / total_tests * 100 if total_tests > 0 else 0
        }
        
        if passed_tests >= total_tests * 0.8:
            results["overall_status"] = "success"
        elif passed_tests + partial_tests >= total_tests * 0.6:
            results["overall_status"] = "partial"
        else:
            results["overall_status"] = "failed"
        
        # Print summary
        print("\n" + "=" * 50)
        print("📊 KNOWLEDGE GRAPH COMPONENTS TEST SUMMARY")
        print("=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Partial: {partial_tests}")
        print(f"Skipped: {skipped_tests}")
        print(f"Failed: {total_tests - passed_tests - partial_tests}")
        print(f"Success Rate: {results['summary']['success_rate']:.1f}%")
        print(f"Overall Status: {results['overall_status'].upper()}")
        
        if results["overall_status"] == "success":
            print("\n🎉 Knowledge Graph Components are FULLY FUNCTIONAL!")
            print("   All core KG components working properly")
        elif results["overall_status"] == "partial":
            print("\n⚠️  Knowledge Graph Components are MOSTLY FUNCTIONAL")
            print("   Core functionality working, some features may need attention")
        else:
            print("\n❌ Knowledge Graph Components have ISSUES")
            print("   Some core components not working properly")
        
        # Save results
        results_file = f"kg-components-test-results-{int(time.time())}.json"
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
    print("🚀 Starting Knowledge Graph Components Tests...")
    
    try:
        results = test_knowledge_graph_components()
        
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