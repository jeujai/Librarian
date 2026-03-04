"""
Tests for the Multimedia Generator component.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from src.multimodal_librarian.components.multimedia_generator import MultimediaGenerator
from src.multimodal_librarian.models.core import (
    KnowledgeChunk, SourceType, ContentType, MediaElement, KnowledgeMetadata
)


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def multimedia_generator(temp_output_dir):
    """Create a MultimediaGenerator instance for testing."""
    return MultimediaGenerator(output_dir=temp_output_dir)


@pytest.fixture
def sample_knowledge_chunks():
    """Create sample knowledge chunks for testing."""
    chunks = [
        KnowledgeChunk(
            id="chunk1",
            content="Sales data shows Revenue: $100K, Profit: $25K, Expenses: $75K",
            source_type=SourceType.BOOK,
            source_id="business_report",
            location_reference="page 15",
            content_type=ContentType.TECHNICAL,
            knowledge_metadata=KnowledgeMetadata(complexity_score=0.7)
        ),
        KnowledgeChunk(
            id="chunk2", 
            content="The company grew from 2020: 50 employees to 2021: 75 employees to 2022: 100 employees",
            source_type=SourceType.BOOK,
            source_id="hr_report",
            location_reference="page 8",
            content_type=ContentType.GENERAL,
            knowledge_metadata=KnowledgeMetadata(complexity_score=0.5)
        )
    ]
    return chunks


class TestMultimediaGenerator:
    """Test cases for MultimediaGenerator."""
    
    def test_initialization(self, temp_output_dir):
        """Test MultimediaGenerator initialization."""
        generator = MultimediaGenerator(output_dir=temp_output_dir)
        
        assert generator.output_dir == Path(temp_output_dir)
        assert generator.output_dir.exists()
        assert generator.tts_engine is not None
    
    def test_generate_text_response(self, multimedia_generator, sample_knowledge_chunks):
        """Test text response generation."""
        query = "What are the company financials?"
        
        response = multimedia_generator.generate_text_response(sample_knowledge_chunks, query)
        
        assert isinstance(response, str)
        assert len(response) > 0
        assert "Revenue: $100K" in response
        assert "[book: page 15]" in response
    
    def test_generate_text_response_empty_context(self, multimedia_generator):
        """Test text response generation with empty context."""
        query = "What are the company financials?"
        
        response = multimedia_generator.generate_text_response([], query)
        
        assert response == "I couldn't find relevant information to answer your query."
    
    def test_extract_data_for_visualization(self, multimedia_generator):
        """Test data extraction for visualization."""
        content = "Sales: 100, Marketing: 50, Operations: 75. Also 2020: 200, 2021: 250, 2022: 300"
        
        data_patterns = multimedia_generator.extract_data_for_visualization(content)
        
        assert len(data_patterns) >= 1
        
        # Check for bar chart data
        bar_chart = next((p for p in data_patterns if p['type'] == 'bar_chart'), None)
        if bar_chart:
            assert 'Sales' in bar_chart['labels']
            assert 100.0 in bar_chart['values']
        
        # Check for time series data
        line_chart = next((p for p in data_patterns if p['type'] == 'line_chart'), None)
        if line_chart:
            assert '2020' in line_chart['x_values']
            assert 200.0 in line_chart['y_values']
    
    def test_create_visualizations(self, multimedia_generator):
        """Test visualization creation."""
        data_patterns = [
            {
                'type': 'bar_chart',
                'labels': ['Sales', 'Marketing', 'Operations'],
                'values': [100, 50, 75],
                'title': 'Department Budgets'
            }
        ]
        
        visualizations = multimedia_generator.create_visualizations(data_patterns)
        
        assert len(visualizations) == 1
        viz = visualizations[0]
        assert viz.viz_type == "bar_chart"
        assert len(viz.content_data) > 0
        assert "bar chart" in viz.caption.lower()
    
    def test_process_and_caption_images(self, multimedia_generator):
        """Test image processing and captioning."""
        # Create a simple test image
        from PIL import Image
        import io
        
        test_image = Image.new('RGB', (100, 200), color='red')
        img_bytes = io.BytesIO()
        test_image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        media_element = MediaElement(
            element_id="test_img",
            element_type="image",
            content_data=img_bytes.getvalue()
        )
        
        processed = multimedia_generator.process_and_caption_images([media_element])
        
        assert len(processed) == 1
        processed_element = processed[0]
        assert processed_element.caption is not None
        assert "tall format image" in processed_element.caption
        assert processed_element.metadata.get("processed") is True
    
    @patch('src.multimodal_librarian.components.multimedia_generator.multimedia_generator.gTTS')
    def test_synthesize_audio_gtts(self, mock_gtts, multimedia_generator):
        """Test audio synthesis with gTTS."""
        # Mock gTTS
        mock_tts_instance = Mock()
        mock_gtts.return_value = mock_tts_instance
        
        # Mock the write_to_fp method
        def mock_write_to_fp(buffer):
            buffer.write(b"fake_audio_data")
        
        mock_tts_instance.write_to_fp = mock_write_to_fp
        
        text = "This is a test audio generation."
        audio = multimedia_generator.synthesize_audio(text, use_gtts=True)
        
        assert audio is not None
        assert audio.format == "mp3"
        assert audio.content_data == b"fake_audio_data"
        assert audio.duration_seconds > 0
        assert audio.metadata["engine"] == "gtts"
    
    def test_synthesize_audio_empty_text(self, multimedia_generator):
        """Test audio synthesis with empty text."""
        audio = multimedia_generator.synthesize_audio("")
        assert audio is None
        
        audio = multimedia_generator.synthesize_audio("   ")
        assert audio is None
    
    def test_generate_complete_multimedia_response(self, multimedia_generator, sample_knowledge_chunks):
        """Test complete multimedia response generation."""
        query = "What are the company metrics?"
        
        with patch.object(multimedia_generator, 'synthesize_audio') as mock_audio:
            mock_audio.return_value = None  # Skip audio generation for test
            
            response = multimedia_generator.generate_complete_multimedia_response(
                sample_knowledge_chunks, 
                query,
                include_audio=False,
                include_video=False
            )
        
        assert response is not None
        assert len(response.text_content) > 0
        assert len(response.knowledge_citations) == len(sample_knowledge_chunks)
        
        # Check citations
        for citation in response.knowledge_citations:
            assert citation.source_type in [SourceType.BOOK, SourceType.CONVERSATION]
            assert len(citation.chunk_id) > 0
    
    def test_wrap_text(self, multimedia_generator):
        """Test text wrapping functionality."""
        text = "This is a very long text that should be wrapped to multiple lines when the width limit is reached."
        
        wrapped = multimedia_generator._wrap_text(text, 20)
        
        lines = wrapped.split('\n')
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 20 or ' ' not in line  # Single words can exceed limit