#!/usr/bin/env python3
"""
Example demonstrating the Export Engine functionality.

This script shows how to use the ExportEngine to export multimedia responses
to various formats including .txt, .docx, .pdf, .rtf, .pptx, and .xlsx.
"""

import sys
import os
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.components.export_engine import ExportEngine
from multimodal_librarian.models.core import (
    MultimediaResponse, Visualization, AudioFile, VideoFile, 
    KnowledgeCitation, SourceType
)


def create_sample_response():
    """Create a sample multimedia response for testing."""
    # Create sample visualization (fake PNG data)
    viz_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
    visualization = Visualization(
        viz_id="sample_chart",
        viz_type="bar_chart",
        content_data=viz_data,
        caption="Sample Bar Chart showing quarterly sales data",
        alt_text="A bar chart displaying Q1-Q4 sales figures"
    )
    
    # Create sample audio
    audio = AudioFile(
        audio_id="sample_audio",
        content_data=b"fake_audio_data_for_demonstration",
        duration_seconds=45.2,
        format="mp3"
    )
    
    # Create sample video
    video = VideoFile(
        video_id="sample_video",
        content_data=b"fake_video_data_for_demonstration",
        duration_seconds=180.5,
        format="mp4",
        resolution="1920x1080"
    )
    
    # Create sample citations
    citations = [
        KnowledgeCitation(
            source_type=SourceType.BOOK,
            source_title="Advanced Data Analysis Techniques",
            location_reference="Chapter 7, Page 142",
            chunk_id="book_chunk_789",
            relevance_score=0.92
        ),
        KnowledgeCitation(
            source_type=SourceType.CONVERSATION,
            source_title="Discussion on Machine Learning Trends",
            location_reference="2023-12-15 14:30:22",
            chunk_id="conv_chunk_456",
            relevance_score=0.78
        )
    ]
    
    return MultimediaResponse(
        text_content="""
        This is a comprehensive analysis of quarterly sales performance across different product categories. 
        
        The data shows significant growth in Q3 and Q4, with particularly strong performance in the technology 
        and healthcare sectors. Key findings include:
        
        1. Technology sector grew by 23% year-over-year
        2. Healthcare products showed consistent 15% quarterly growth
        3. Consumer goods remained stable with 3% growth
        4. International markets contributed 40% of total revenue
        
        The accompanying visualization demonstrates these trends clearly, while the audio commentary provides 
        additional context from our quarterly review meeting. The video presentation includes detailed 
        breakdowns by region and product line.
        
        These results align with industry trends discussed in recent literature and conversations with 
        domain experts, suggesting continued growth potential in the coming quarters.
        """,
        visualizations=[visualization],
        audio_content=audio,
        video_content=video,
        knowledge_citations=citations
    )


def main():
    """Demonstrate export functionality across all supported formats."""
    print("🚀 Export Engine Demonstration")
    print("=" * 50)
    
    # Initialize export engine
    export_engine = ExportEngine()
    
    # Create sample response
    response = create_sample_response()
    
    # Get supported formats
    formats = export_engine.get_supported_formats()
    print(f"📋 Supported formats: {', '.join(formats)}")
    print()
    
    # Create exports directory
    exports_dir = Path("exports")
    exports_dir.mkdir(exist_ok=True)
    
    # Export to each format
    for format_type in formats:
        try:
            print(f"📄 Exporting to {format_type.upper()}...")
            
            # Export the response
            exported_content = export_engine.export_to_format(response, format_type)
            
            # Save to file
            output_file = exports_dir / f"sample_export.{format_type}"
            with open(output_file, 'wb') as f:
                f.write(exported_content)
            
            # Display results
            file_size = len(exported_content)
            print(f"   ✅ Success! Size: {file_size:,} bytes")
            print(f"   📁 Saved to: {output_file}")
            
            # Show export metadata
            if response.export_metadata:
                print(f"   📊 Metadata: {response.export_metadata.export_format}, "
                      f"includes media: {response.export_metadata.includes_media}")
            
            print()
            
        except Exception as e:
            print(f"   ❌ Failed: {str(e)}")
            print()
    
    print("🎉 Export demonstration completed!")
    print(f"📂 Check the '{exports_dir}' directory for exported files.")
    
    # Display summary
    print("\n📈 Export Summary:")
    print("-" * 30)
    print(f"Text content: {len(response.text_content)} characters")
    print(f"Visualizations: {len(response.visualizations)}")
    print(f"Audio content: {'Yes' if response.audio_content else 'No'}")
    print(f"Video content: {'Yes' if response.video_content else 'No'}")
    print(f"Citations: {len(response.knowledge_citations)}")
    print(f"Has multimedia: {response.has_multimedia()}")


if __name__ == "__main__":
    main()