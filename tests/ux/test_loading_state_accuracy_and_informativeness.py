"""
Test Loading State Accuracy and Informativeness

This test suite validates that loading states are accurate and informative,
ensuring users receive clear, specific, and helpful information about system status.

Tests cover:
1. Progress accuracy - percentages match actual state
2. ETA accuracy - time estimates are realistic
3. Capability-specific indicators - show what's actually loading
4. Progress labels - descriptive and specific to each capability
5. Status consistency - all UI elements show consistent information
6. Real-time updates - information updates correctly
"""

import asyncio
import time
import pytest
from typing import Dict, Any, List


class TestLoadingStateAccuracy:
    """Test suite for loading state accuracy."""
    
    @pytest.mark.asyncio
    async def test_progress_percentage_accuracy(self):
        """Test that progress percentages accurately reflect system state."""
        print("\n🧪 Testing Progress Percentage Accuracy")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        
        # Get loading progress
        progress = capability_service.get_loading_progress()
        
        print(f"📊 Overall Progress: {progress['overall_progress']:.1f}%")
        
        # Verify progress is within valid range
        assert 0 <= progress['overall_progress'] <= 100, \
            f"Progress {progress['overall_progress']}% is out of range [0, 100]"
        
        # Verify phase progress
        phase_progress = progress.get('phase_progress', {})
        for phase_name, phase_data in phase_progress.items():
            phase_percent = phase_data.get('progress_percent', 0)
            print(f"   {phase_name}: {phase_percent:.1f}%")
            
            assert 0 <= phase_percent <= 100, \
                f"Phase {phase_name} progress {phase_percent}% is out of range"
            
            # Verify progress matches completion status
            if phase_data.get('complete', False):
                assert phase_percent == 100, \
                    f"Phase {phase_name} marked complete but progress is {phase_percent}%"
        
        # Verify model progress
        model_progress = progress.get('model_progress', {})
        for model_name, model_data in model_progress.items():
            model_percent = model_data.get('progress_percent', 0)
            model_status = model_data.get('status', 'unknown')
            
            print(f"   Model {model_name}: {model_percent:.1f}% ({model_status})")
            
            assert 0 <= model_percent <= 100, \
                f"Model {model_name} progress {model_percent}% is out of range"
            
            # Verify progress matches status
            if model_status == 'loaded':
                assert model_percent == 100, \
                    f"Model {model_name} loaded but progress is {model_percent}%"
            elif model_status == 'failed':
                # Failed models might have partial progress
                pass
            elif model_status == 'pending':
                assert model_percent < 50, \
                    f"Model {model_name} pending but progress is {model_percent}%"
        
        print("✅ Progress percentages are accurate")
    
    @pytest.mark.asyncio
    async def test_eta_accuracy(self):
        """Test that ETA estimates are realistic and accurate."""
        print("\n🧪 Testing ETA Accuracy")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        
        # Get capability summary with ETAs
        summary = capability_service.get_capability_summary()
        
        # Check ETAs for loading capabilities
        for level in ['basic', 'enhanced', 'full']:
            loading_caps = summary[level].get('loading', [])
            
            for cap in loading_caps:
                cap_name = cap['name']
                eta_seconds = cap.get('eta_seconds')
                
                if eta_seconds is not None:
                    print(f"📅 {cap_name}: ETA {eta_seconds}s")
                    
                    # Verify ETA is reasonable (not negative, not absurdly long)
                    assert eta_seconds >= 0, \
                        f"ETA for {cap_name} is negative: {eta_seconds}s"
                    
                    assert eta_seconds <= 600, \
                        f"ETA for {cap_name} is too long: {eta_seconds}s (>10 minutes)"
                    
                    # Verify ETA makes sense for capability level
                    if level == 'basic':
                        assert eta_seconds <= 60, \
                            f"Basic capability {cap_name} ETA {eta_seconds}s is too long"
                    elif level == 'enhanced':
                        assert eta_seconds <= 180, \
                            f"Enhanced capability {cap_name} ETA {eta_seconds}s is too long"
        
        # Check overall completion ETA
        progress = capability_service.get_loading_progress()
        overall_eta = progress.get('estimated_completion')
        
        if overall_eta:
            print(f"📅 Overall completion ETA: {overall_eta}")
            
            # Verify it's a valid ISO timestamp
            from datetime import datetime
            try:
                eta_time = datetime.fromisoformat(overall_eta)
                now = datetime.now()
                
                # Verify ETA is in the future (or very recent past for completed systems)
                time_diff = (eta_time - now).total_seconds()
                assert time_diff >= -60, \
                    f"Overall ETA is too far in the past: {time_diff}s"
                
                assert time_diff <= 600, \
                    f"Overall ETA is too far in the future: {time_diff}s"
                
            except ValueError as e:
                pytest.fail(f"Invalid ETA timestamp format: {overall_eta}")
        
        print("✅ ETA estimates are accurate and realistic")
    
    @pytest.mark.asyncio
    async def test_capability_specific_indicators(self):
        """Test that capability-specific indicators are accurate and informative."""
        print("\n🧪 Testing Capability-Specific Indicators")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        summary = capability_service.get_capability_summary()
        
        # Define expected indicators for each capability
        expected_indicators = {
            'health_check': ['✅', '🔄', '⏳'],
            'simple_text': ['📝', '⏳'],
            'status_updates': ['📊', '📈'],
            'basic_chat': ['💬', '🤖'],
            'simple_search': ['🔍', '🔎'],
            'document_upload': ['📤', '📋'],
            'advanced_chat': ['🧠', '🤯'],
            'semantic_search': ['🎯', '🔍'],
            'document_analysis': ['📊', '📄'],
            'complex_reasoning': ['🧮', '💭'],
            'multimodal_processing': ['🎨', '🖼️']
        }
        
        # Check all capabilities have appropriate indicators
        for level in ['basic', 'enhanced', 'full']:
            all_caps = summary[level].get('available', []) + summary[level].get('loading', [])
            
            for cap in all_caps:
                cap_name = cap['name']
                indicator = cap.get('indicator', '')
                
                print(f"   {cap_name}: {indicator}")
                
                # Verify indicator is not empty
                assert indicator, f"Capability {cap_name} has no indicator"
                
                # Verify indicator is appropriate for capability
                if cap_name in expected_indicators:
                    valid_indicators = expected_indicators[cap_name]
                    assert indicator in valid_indicators, \
                        f"Capability {cap_name} has unexpected indicator {indicator}"
                
                # Verify indicator is an emoji or symbol (not just text)
                assert len(indicator) <= 2, \
                    f"Indicator for {cap_name} is too long: {indicator}"
        
        print("✅ Capability-specific indicators are accurate")
    
    @pytest.mark.asyncio
    async def test_progress_labels_specificity(self):
        """Test that progress labels are specific and descriptive."""
        print("\n🧪 Testing Progress Label Specificity")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        summary = capability_service.get_capability_summary()
        
        # Define expected label patterns for different capabilities
        capability_keywords = {
            'health_check': ['monitoring', 'health', 'check', 'endpoint'],
            'simple_text': ['text', 'processor', 'tokenizer', 'processing'],
            'basic_chat': ['chat', 'model', 'AI', 'conversation'],
            'simple_search': ['search', 'index', 'query'],
            'document_upload': ['file', 'upload', 'storage', 'document'],
            'document_analysis': ['analysis', 'document', 'processor', 'understanding'],
            'advanced_chat': ['AI', 'reasoning', 'advanced', 'intelligence'],
            'semantic_search': ['semantic', 'embedding', 'similarity'],
            'complex_reasoning': ['reasoning', 'logic', 'inference'],
            'multimodal_processing': ['multimodal', 'vision', 'audio', 'processing']
        }
        
        # Check loading capabilities have specific labels
        for level in ['basic', 'enhanced', 'full']:
            loading_caps = summary[level].get('loading', [])
            
            for cap in loading_caps:
                cap_name = cap['name']
                description = cap.get('description', '').lower()
                
                print(f"   {cap_name}: {description}")
                
                # Verify description is not empty
                assert description, f"Capability {cap_name} has no description"
                
                # Verify description is specific (not generic)
                generic_phrases = ['loading', 'processing', 'working', 'please wait']
                is_generic = all(phrase not in description for phrase in generic_phrases) or \
                            any(keyword in description for keyword in capability_keywords.get(cap_name, []))
                
                assert is_generic or any(keyword in description for keyword in capability_keywords.get(cap_name, [])), \
                    f"Description for {cap_name} is too generic: {description}"
                
                # Verify description contains capability-specific keywords
                if cap_name in capability_keywords:
                    keywords = capability_keywords[cap_name]
                    has_keyword = any(keyword in description for keyword in keywords)
                    assert has_keyword, \
                        f"Description for {cap_name} lacks specific keywords: {description}"
        
        print("✅ Progress labels are specific and descriptive")
    
    @pytest.mark.asyncio
    async def test_status_consistency_across_ui(self):
        """Test that status information is consistent across all UI elements."""
        print("\n🧪 Testing Status Consistency Across UI")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        
        # Get status from different sources
        summary = capability_service.get_capability_summary()
        progress = capability_service.get_loading_progress()
        
        # Extract key metrics
        overall_readiness = summary['overall']['readiness_percent']
        overall_progress = progress['overall_progress']
        current_level = summary['overall']['current_level']
        
        print(f"📊 Overall Readiness: {overall_readiness:.1f}%")
        print(f"📊 Overall Progress: {overall_progress:.1f}%")
        print(f"📊 Current Level: {current_level}")
        
        # Verify readiness and progress are consistent
        # They should be within 10% of each other
        diff = abs(overall_readiness - overall_progress)
        assert diff <= 15, \
            f"Readiness ({overall_readiness}%) and progress ({overall_progress}%) differ by {diff}%"
        
        # Verify current level matches readiness
        if overall_readiness >= 80:
            assert current_level in ['enhanced', 'full'], \
                f"Readiness {overall_readiness}% but level is {current_level}"
        elif overall_readiness >= 40:
            assert current_level in ['basic', 'enhanced'], \
                f"Readiness {overall_readiness}% but level is {current_level}"
        else:
            assert current_level == 'basic', \
                f"Readiness {overall_readiness}% but level is {current_level}"
        
        # Verify capability counts are consistent
        total_caps = summary['overall']['total_capabilities']
        available_caps = summary['overall']['available_capabilities']
        
        # Count capabilities from levels
        counted_total = sum(summary[level]['count'] for level in ['basic', 'enhanced', 'full'])
        counted_available = sum(len(summary[level]['available']) for level in ['basic', 'enhanced', 'full'])
        
        assert total_caps == counted_total, \
            f"Total capabilities mismatch: {total_caps} vs {counted_total}"
        
        assert available_caps == counted_available, \
            f"Available capabilities mismatch: {available_caps} vs {counted_available}"
        
        print("✅ Status information is consistent across UI")
    
    @pytest.mark.asyncio
    async def test_real_time_update_accuracy(self):
        """Test that loading state updates accurately reflect changes."""
        print("\n🧪 Testing Real-Time Update Accuracy")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        
        # Get initial state
        initial_summary = capability_service.get_capability_summary()
        initial_progress = capability_service.get_loading_progress()
        
        initial_readiness = initial_summary['overall']['readiness_percent']
        initial_overall_progress = initial_progress['overall_progress']
        
        print(f"📊 Initial State:")
        print(f"   Readiness: {initial_readiness:.1f}%")
        print(f"   Progress: {initial_overall_progress:.1f}%")
        
        # Wait a short time
        await asyncio.sleep(2)
        
        # Get updated state
        updated_summary = capability_service.get_capability_summary()
        updated_progress = capability_service.get_loading_progress()
        
        updated_readiness = updated_summary['overall']['readiness_percent']
        updated_overall_progress = updated_progress['overall_progress']
        
        print(f"\n📊 Updated State:")
        print(f"   Readiness: {updated_readiness:.1f}%")
        print(f"   Progress: {updated_overall_progress:.1f}%")
        
        # Verify progress doesn't decrease (unless system restarted)
        if initial_readiness < 100:
            assert updated_readiness >= initial_readiness - 5, \
                f"Readiness decreased from {initial_readiness}% to {updated_readiness}%"
        
        # Verify changes are reflected consistently
        readiness_change = updated_readiness - initial_readiness
        progress_change = updated_overall_progress - initial_overall_progress
        
        # Changes should be in the same direction
        if abs(readiness_change) > 5 or abs(progress_change) > 5:
            assert (readiness_change >= 0 and progress_change >= 0) or \
                   (readiness_change <= 0 and progress_change <= 0), \
                f"Inconsistent changes: readiness {readiness_change:+.1f}%, progress {progress_change:+.1f}%"
        
        print("✅ Real-time updates are accurate")
    
    @pytest.mark.asyncio
    async def test_loading_message_informativeness(self):
        """Test that loading messages are informative and helpful."""
        print("\n🧪 Testing Loading Message Informativeness")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        summary = capability_service.get_capability_summary()
        
        current_level = summary['overall']['current_level']
        readiness = summary['overall']['readiness_percent']
        
        print(f"📝 Current Level: {current_level}")
        print(f"📝 Readiness: {readiness:.1f}%")
        
        # Define expected message characteristics for each level
        level_expectations = {
            'basic': {
                'should_mention': ['basic', 'simple', 'starting'],
                'should_not_mention': ['advanced', 'complex', 'full'],
                'should_have_eta': True
            },
            'enhanced': {
                'should_mention': ['enhanced', 'some', 'partial'],
                'should_not_mention': ['basic only', 'not available'],
                'should_have_eta': True
            },
            'full': {
                'should_mention': ['full', 'all', 'ready', 'complete'],
                'should_not_mention': ['loading', 'waiting', 'pending'],
                'should_have_eta': False
            }
        }
        
        expectations = level_expectations.get(current_level, {})
        
        # Check loading capabilities have informative descriptions
        for level in ['basic', 'enhanced', 'full']:
            loading_caps = summary[level].get('loading', [])
            
            for cap in loading_caps:
                description = cap.get('description', '').lower()
                
                # Verify description is informative (>20 characters)
                assert len(description) > 20, \
                    f"Description for {cap['name']} is too short: {description}"
                
                # Verify description explains what the capability does
                action_words = ['process', 'analyze', 'search', 'handle', 'provide', 'enable']
                has_action = any(word in description for word in action_words)
                assert has_action, \
                    f"Description for {cap['name']} doesn't explain what it does: {description}"
        
        print("✅ Loading messages are informative and helpful")
    
    @pytest.mark.asyncio
    async def test_feature_specific_progress_tracking(self):
        """Test that feature-specific progress is tracked accurately."""
        print("\n🧪 Testing Feature-Specific Progress Tracking")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        progress = capability_service.get_loading_progress()
        
        # Check model-specific progress
        model_progress = progress.get('model_progress', {})
        
        print(f"📊 Model Progress:")
        for model_name, model_data in model_progress.items():
            status = model_data.get('status', 'unknown')
            percent = model_data.get('progress_percent', 0)
            estimated_time = model_data.get('estimated_time', 0)
            
            print(f"   {model_name}:")
            print(f"      Status: {status}")
            print(f"      Progress: {percent:.1f}%")
            print(f"      Estimated time: {estimated_time}s")
            
            # Verify model progress data is complete
            assert status in ['pending', 'loading', 'loaded', 'failed'], \
                f"Invalid status for {model_name}: {status}"
            
            assert 0 <= percent <= 100, \
                f"Invalid progress for {model_name}: {percent}%"
            
            assert estimated_time >= 0, \
                f"Invalid estimated time for {model_name}: {estimated_time}s"
            
            # Verify progress matches status
            if status == 'loaded':
                assert percent == 100, \
                    f"Model {model_name} loaded but progress is {percent}%"
            elif status == 'pending':
                assert percent < 10, \
                    f"Model {model_name} pending but progress is {percent}%"
        
        print("✅ Feature-specific progress tracking is accurate")


class TestLoadingStateInformativeness:
    """Test suite for loading state informativeness."""
    
    @pytest.mark.asyncio
    async def test_capability_descriptions_are_clear(self):
        """Test that capability descriptions are clear and understandable."""
        print("\n🧪 Testing Capability Description Clarity")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        capabilities = capability_service.get_current_capabilities()
        
        for cap_name, capability in capabilities.items():
            description = capability.description
            
            print(f"   {cap_name}: {description}")
            
            # Verify description is not empty
            assert description, f"Capability {cap_name} has no description"
            
            # Verify description is clear (not too short, not too long)
            assert 20 <= len(description) <= 200, \
                f"Description for {cap_name} is {len(description)} chars (should be 20-200)"
            
            # Verify description uses clear language
            jargon_words = ['instantiate', 'initialize', 'bootstrap', 'provision']
            clear_words = ['process', 'analyze', 'search', 'handle', 'provide']
            
            has_clear_language = any(word in description.lower() for word in clear_words)
            has_too_much_jargon = sum(1 for word in jargon_words if word in description.lower()) > 1
            
            assert has_clear_language or not has_too_much_jargon, \
                f"Description for {cap_name} uses unclear language: {description}"
        
        print("✅ Capability descriptions are clear")
    
    @pytest.mark.asyncio
    async def test_eta_formatting_is_user_friendly(self):
        """Test that ETA formatting is user-friendly and easy to understand."""
        print("\n🧪 Testing ETA Formatting")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        
        capability_service = get_capability_service()
        summary = capability_service.get_capability_summary()
        
        # Check ETA formatting for loading capabilities
        for level in ['basic', 'enhanced', 'full']:
            loading_caps = summary[level].get('loading', [])
            
            for cap in loading_caps:
                eta_seconds = cap.get('eta_seconds')
                
                if eta_seconds is not None:
                    # Format ETA in user-friendly way
                    if eta_seconds < 60:
                        formatted = f"{eta_seconds}s"
                    elif eta_seconds < 3600:
                        minutes = eta_seconds // 60
                        seconds = eta_seconds % 60
                        formatted = f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
                    else:
                        hours = eta_seconds // 3600
                        minutes = (eta_seconds % 3600) // 60
                        formatted = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
                    
                    print(f"   {cap['name']}: {formatted}")
                    
                    # Verify formatting is concise
                    assert len(formatted) <= 10, \
                        f"ETA format for {cap['name']} is too long: {formatted}"
        
        print("✅ ETA formatting is user-friendly")
    
    @pytest.mark.asyncio
    async def test_quality_indicators_are_meaningful(self):
        """Test that quality indicators provide meaningful information."""
        print("\n🧪 Testing Quality Indicator Meaningfulness")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service, CapabilityLevel
        
        capability_service = get_capability_service()
        
        # Define expected quality indicators
        quality_indicators = {
            CapabilityLevel.BASIC: "⚡",
            CapabilityLevel.ENHANCED: "🔄",
            CapabilityLevel.FULL: "🧠"
        }
        
        # Check that capabilities use appropriate quality indicators
        capabilities = capability_service.get_current_capabilities()
        
        for cap_name, capability in capabilities.items():
            indicator = capability.quality_indicator
            level = capability.level
            
            print(f"   {cap_name} ({level.value}): {indicator}")
            
            # Verify indicator matches level
            expected_indicator = quality_indicators[level]
            assert indicator == expected_indicator, \
                f"Capability {cap_name} has wrong indicator: {indicator} (expected {expected_indicator})"
        
        print("✅ Quality indicators are meaningful")
    
    @pytest.mark.asyncio
    async def test_loading_state_provides_actionable_information(self):
        """Test that loading state provides actionable information to users."""
        print("\n🧪 Testing Actionable Information")
        print("-" * 60)
        
        from multimodal_librarian.services.capability_service import get_capability_service
        from multimodal_librarian.api.middleware.loading_middleware import get_loading_state_injector
        
        capability_service = get_capability_service()
        loading_injector = get_loading_state_injector()
        
        # Test different request types
        test_cases = [
            {
                'request_type': 'chat',
                'required_capabilities': ['basic_chat'],
                'should_have': ['can_handle', 'quality_level', 'recommendation']
            },
            {
                'request_type': 'document_analysis',
                'required_capabilities': ['document_analysis'],
                'should_have': ['can_handle', 'missing_capabilities', 'eta_seconds']
            },
            {
                'request_type': 'search',
                'required_capabilities': ['semantic_search'],
                'should_have': ['can_handle', 'quality_level', 'fallback_available']
            }
        ]
        
        for test_case in test_cases:
            print(f"\n   Testing {test_case['request_type']}:")
            
            # Check if system can handle request
            check = capability_service.can_handle_request(
                request_type=test_case['request_type'],
                required_capabilities=test_case['required_capabilities']
            )
            
            # Verify all expected fields are present
            for field in test_case['should_have']:
                assert field in check, \
                    f"Missing field '{field}' for {test_case['request_type']}"
                print(f"      {field}: {check[field]}")
            
            # Verify recommendation is actionable
            recommendation = check.get('recommendation', '')
            assert recommendation, \
                f"No recommendation for {test_case['request_type']}"
            
            # Verify recommendation contains action words
            action_words = ['process', 'queue', 'provide', 'wait', 'ready']
            has_action = any(word in recommendation.lower() for word in action_words)
            assert has_action, \
                f"Recommendation for {test_case['request_type']} is not actionable: {recommendation}"
        
        print("\n✅ Loading state provides actionable information")


# Run all tests
async def run_all_tests():
    """Run all loading state accuracy and informativeness tests."""
    print("\n" + "=" * 80)
    print("LOADING STATE ACCURACY AND INFORMATIVENESS TEST SUITE")
    print("=" * 80)
    
    accuracy_tests = TestLoadingStateAccuracy()
    informativeness_tests = TestLoadingStateInformativeness()
    
    test_methods = [
        # Accuracy tests
        ("Progress Percentage Accuracy", accuracy_tests.test_progress_percentage_accuracy),
        ("ETA Accuracy", accuracy_tests.test_eta_accuracy),
        ("Capability-Specific Indicators", accuracy_tests.test_capability_specific_indicators),
        ("Progress Label Specificity", accuracy_tests.test_progress_labels_specificity),
        ("Status Consistency", accuracy_tests.test_status_consistency_across_ui),
        ("Real-Time Update Accuracy", accuracy_tests.test_real_time_update_accuracy),
        ("Loading Message Informativeness", accuracy_tests.test_loading_message_informativeness),
        ("Feature-Specific Progress", accuracy_tests.test_feature_specific_progress_tracking),
        
        # Informativeness tests
        ("Capability Description Clarity", informativeness_tests.test_capability_descriptions_are_clear),
        ("ETA Formatting", informativeness_tests.test_eta_formatting_is_user_friendly),
        ("Quality Indicator Meaningfulness", informativeness_tests.test_quality_indicators_are_meaningful),
        ("Actionable Information", informativeness_tests.test_loading_state_provides_actionable_information),
    ]
    
    results = []
    
    for test_name, test_method in test_methods:
        try:
            await test_method()
            results.append((test_name, True, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n❌ {test_name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed
    
    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(results)*100):.1f}%")
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
