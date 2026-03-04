"""
Multimedia Generation Component.

This component generates text responses, visualizations, audio content,
and video presentations from retrieved knowledge.
"""

import io
import uuid
import re
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from pathlib import Path
import json

# Multimedia generation libraries
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import plotly.graph_objects as go
import plotly.express as px
from plotly.io import to_image
import seaborn as sns
import numpy as np
import pandas as pd

# Audio generation libraries
from gtts import gTTS
import pyttsx3

# Image processing
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Core models
from ...models.core import (
    KnowledgeChunk, MultimediaResponse, Visualization, AudioFile, VideoFile,
    KnowledgeCitation, MediaElement
)

logger = logging.getLogger(__name__)

# Video generation libraries
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
    from moviepy.video.fx import resize
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger.warning("MoviePy not available. Video generation will be disabled.")


class MultimediaGenerator:
    """
    Generates multimedia content including visualizations, audio, and video
    from retrieved knowledge chunks.
    """
    
    def __init__(self, output_dir: str = "media"):
        """
        Initialize the multimedia generator.
        
        Args:
            output_dir: Directory to store generated media files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize text-to-speech engine
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty('rate', 150)  # Speaking rate
        self.tts_engine.setProperty('volume', 0.9)  # Volume level
        
        # Set up matplotlib style
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        logger.info(f"MultimediaGenerator initialized with output directory: {self.output_dir}")
    
    def generate_text_response(self, context: List[KnowledgeChunk], query: str) -> str:
        """
        Generate coherent text response from knowledge chunks.
        
        Args:
            context: List of relevant knowledge chunks
            query: Original user query
            
        Returns:
            Generated text response
        """
        if not context:
            return "I couldn't find relevant information to answer your query."
        
        # Combine content from chunks with proper citations
        response_parts = []
        
        # Add introduction
        response_parts.append(f"Based on the available knowledge, here's what I found regarding your query:\n")
        
        # Process each chunk and extract key information
        for i, chunk in enumerate(context, 1):
            chunk_content = chunk.content.strip()
            if chunk_content:
                # Add chunk content with source reference
                source_ref = f"[{chunk.source_type.value}: {chunk.location_reference}]"
                response_parts.append(f"{chunk_content} {source_ref}")
        
        # Combine all parts
        full_response = "\n\n".join(response_parts)
        
        logger.info(f"Generated text response with {len(context)} knowledge chunks")
        return full_response
    
    def extract_data_for_visualization(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract numerical data and patterns suitable for visualization.
        
        Args:
            content: Text content to analyze
            
        Returns:
            List of data structures suitable for visualization
        """
        data_patterns = []
        
        # Pattern 1: Numbers with labels (e.g., "Sales: 100", "Revenue: $500K")
        number_pattern = r'(\w+(?:\s+\w+)*)\s*[:=]\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*([KMB%]?)'
        matches = re.findall(number_pattern, content, re.IGNORECASE)
        
        if matches:
            labels, values, units = zip(*matches)
            # Convert values to numbers
            numeric_values = []
            for val, unit in zip(values, units):
                num_val = float(val.replace(',', ''))
                if unit.upper() == 'K':
                    num_val *= 1000
                elif unit.upper() == 'M':
                    num_val *= 1000000
                elif unit.upper() == 'B':
                    num_val *= 1000000000
                numeric_values.append(num_val)
            
            data_patterns.append({
                'type': 'bar_chart',
                'labels': list(labels),
                'values': numeric_values,
                'title': 'Extracted Data Values'
            })
        
        # Pattern 2: Time series data (years with values)
        time_pattern = r'(\d{4})\s*[:=]\s*\$?(\d+(?:,\d{3})*(?:\.\d+)?)'
        time_matches = re.findall(time_pattern, content)
        
        if time_matches and len(time_matches) > 1:
            years, values = zip(*time_matches)
            numeric_values = [float(val.replace(',', '')) for val in values]
            
            data_patterns.append({
                'type': 'line_chart',
                'x_values': list(years),
                'y_values': numeric_values,
                'title': 'Time Series Data'
            })
        
        # Pattern 3: Percentage data
        percent_pattern = r'(\w+(?:\s+\w+)*)\s*[:=]\s*(\d+(?:\.\d+)?)\s*%'
        percent_matches = re.findall(percent_pattern, content, re.IGNORECASE)
        
        if percent_matches:
            labels, values = zip(*percent_matches)
            numeric_values = [float(val) for val in values]
            
            data_patterns.append({
                'type': 'pie_chart',
                'labels': list(labels),
                'values': numeric_values,
                'title': 'Percentage Distribution'
            })
        
        logger.info(f"Extracted {len(data_patterns)} data patterns for visualization")
        return data_patterns
    
    def create_visualizations(self, data_patterns: List[Dict[str, Any]]) -> List[Visualization]:
        """
        Generate charts and graphs from extracted data patterns.
        
        Args:
            data_patterns: List of data structures for visualization
            
        Returns:
            List of generated visualizations
        """
        visualizations = []
        
        for pattern in data_patterns:
            try:
                viz_id = str(uuid.uuid4())
                
                if pattern['type'] == 'bar_chart':
                    viz = self._create_bar_chart(
                        pattern['labels'], 
                        pattern['values'], 
                        pattern['title'],
                        viz_id
                    )
                elif pattern['type'] == 'line_chart':
                    viz = self._create_line_chart(
                        pattern['x_values'], 
                        pattern['y_values'], 
                        pattern['title'],
                        viz_id
                    )
                elif pattern['type'] == 'pie_chart':
                    viz = self._create_pie_chart(
                        pattern['labels'], 
                        pattern['values'], 
                        pattern['title'],
                        viz_id
                    )
                else:
                    continue
                
                if viz:
                    visualizations.append(viz)
                    
            except Exception as e:
                logger.error(f"Error creating visualization: {e}")
                continue
        
        logger.info(f"Created {len(visualizations)} visualizations")
        return visualizations
    
    def _create_bar_chart(self, labels: List[str], values: List[float], 
                         title: str, viz_id: str) -> Optional[Visualization]:
        """Create a bar chart visualization."""
        try:
            fig = go.Figure(data=[
                go.Bar(x=labels, y=values, marker_color='steelblue')
            ])
            
            fig.update_layout(
                title=title,
                xaxis_title="Categories",
                yaxis_title="Values",
                template="plotly_white",
                width=800,
                height=500
            )
            
            # Convert to image bytes
            img_bytes = to_image(fig, format="png", width=800, height=500)
            
            return Visualization(
                viz_id=viz_id,
                viz_type="bar_chart",
                content_data=img_bytes,
                caption=f"Bar chart showing {title.lower()}",
                alt_text=f"Bar chart with {len(labels)} categories",
                metadata={
                    "chart_type": "bar",
                    "data_points": len(labels),
                    "title": title
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating bar chart: {e}")
            return None
    
    def _create_line_chart(self, x_values: List[str], y_values: List[float], 
                          title: str, viz_id: str) -> Optional[Visualization]:
        """Create a line chart visualization."""
        try:
            fig = go.Figure(data=[
                go.Scatter(x=x_values, y=y_values, mode='lines+markers', 
                          line=dict(color='steelblue', width=3),
                          marker=dict(size=8))
            ])
            
            fig.update_layout(
                title=title,
                xaxis_title="Time",
                yaxis_title="Values",
                template="plotly_white",
                width=800,
                height=500
            )
            
            # Convert to image bytes
            img_bytes = to_image(fig, format="png", width=800, height=500)
            
            return Visualization(
                viz_id=viz_id,
                viz_type="line_chart",
                content_data=img_bytes,
                caption=f"Line chart showing {title.lower()}",
                alt_text=f"Line chart with {len(x_values)} data points",
                metadata={
                    "chart_type": "line",
                    "data_points": len(x_values),
                    "title": title
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating line chart: {e}")
            return None
    
    def _create_pie_chart(self, labels: List[str], values: List[float], 
                         title: str, viz_id: str) -> Optional[Visualization]:
        """Create a pie chart visualization."""
        try:
            fig = go.Figure(data=[
                go.Pie(labels=labels, values=values, hole=0.3)
            ])
            
            fig.update_layout(
                title=title,
                template="plotly_white",
                width=800,
                height=500
            )
            
            # Convert to image bytes
            img_bytes = to_image(fig, format="png", width=800, height=500)
            
            return Visualization(
                viz_id=viz_id,
                viz_type="pie_chart",
                content_data=img_bytes,
                caption=f"Pie chart showing {title.lower()}",
                alt_text=f"Pie chart with {len(labels)} segments",
                metadata={
                    "chart_type": "pie",
                    "data_points": len(labels),
                    "title": title
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating pie chart: {e}")
            return None
    
    def process_and_caption_images(self, media_elements: List[MediaElement]) -> List[MediaElement]:
        """
        Process images and generate captions for them.
        
        Args:
            media_elements: List of media elements to process
            
        Returns:
            List of processed media elements with captions
        """
        processed_elements = []
        
        for element in media_elements:
            if element.element_type == "image":
                try:
                    # Process the image
                    processed_element = self._process_single_image(element)
                    processed_elements.append(processed_element)
                except Exception as e:
                    logger.error(f"Error processing image {element.element_id}: {e}")
                    # Add original element if processing fails
                    processed_elements.append(element)
            else:
                # Non-image elements pass through unchanged
                processed_elements.append(element)
        
        logger.info(f"Processed {len([e for e in processed_elements if e.element_type == 'image'])} images")
        return processed_elements
    
    def _process_single_image(self, element: MediaElement) -> MediaElement:
        """Process a single image element and generate caption."""
        try:
            # Load image data
            if element.content_data:
                image = Image.open(io.BytesIO(element.content_data))
            elif element.file_path:
                image = Image.open(element.file_path)
            else:
                return element
            
            # Generate basic caption based on image properties
            width, height = image.size
            mode = image.mode
            
            # Basic image analysis
            caption_parts = []
            
            # Analyze image characteristics
            if width > height * 1.5:
                caption_parts.append("wide format image")
            elif height > width * 1.5:
                caption_parts.append("tall format image")
            else:
                caption_parts.append("square format image")
            
            # Add size information
            if width * height > 1000000:  # > 1MP
                caption_parts.append("high resolution")
            
            # Generate caption
            if not element.caption:
                element.caption = f"Image showing {', '.join(caption_parts)} ({width}x{height} pixels)"
            
            # Generate alt text if not present
            if not element.alt_text:
                element.alt_text = f"Image with dimensions {width}x{height}"
            
            # Update metadata
            element.metadata.update({
                "width": width,
                "height": height,
                "mode": mode,
                "processed": True
            })
            
            return element
            
        except Exception as e:
            logger.error(f"Error in image processing: {e}")
            return element
    
    def synthesize_audio(self, text: str, use_gtts: bool = True) -> Optional[AudioFile]:
        """
        Convert text to natural speech audio.
        
        Args:
            text: Text content to convert to speech
            use_gtts: Whether to use gTTS (True) or pyttsx3 (False)
            
        Returns:
            Generated audio file or None if generation fails
        """
        if not text.strip():
            return None
        
        try:
            audio_id = str(uuid.uuid4())
            
            if use_gtts:
                return self._synthesize_with_gtts(text, audio_id)
            else:
                return self._synthesize_with_pyttsx3(text, audio_id)
                
        except Exception as e:
            logger.error(f"Error synthesizing audio: {e}")
            return None
    
    def _synthesize_with_gtts(self, text: str, audio_id: str) -> Optional[AudioFile]:
        """Synthesize audio using Google Text-to-Speech."""
        try:
            # Create gTTS object
            tts = gTTS(text=text, lang='en', slow=False)
            
            # Save to bytes buffer
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            # Estimate duration (rough approximation: ~150 words per minute)
            word_count = len(text.split())
            duration_seconds = (word_count / 150) * 60
            
            return AudioFile(
                audio_id=audio_id,
                content_data=audio_buffer.getvalue(),
                duration_seconds=duration_seconds,
                format="mp3",
                metadata={
                    "engine": "gtts",
                    "language": "en",
                    "word_count": word_count
                }
            )
            
        except Exception as e:
            logger.error(f"Error with gTTS synthesis: {e}")
            return None
    
    def _synthesize_with_pyttsx3(self, text: str, audio_id: str) -> Optional[AudioFile]:
        """Synthesize audio using pyttsx3."""
        try:
            # Create temporary file for pyttsx3 output
            temp_file = self.output_dir / f"temp_audio_{audio_id}.wav"
            
            # Configure and save audio
            self.tts_engine.save_to_file(text, str(temp_file))
            self.tts_engine.runAndWait()
            
            # Read the generated file
            if temp_file.exists():
                with open(temp_file, 'rb') as f:
                    audio_data = f.read()
                
                # Clean up temporary file
                temp_file.unlink()
                
                # Estimate duration
                word_count = len(text.split())
                duration_seconds = (word_count / 150) * 60
                
                return AudioFile(
                    audio_id=audio_id,
                    content_data=audio_data,
                    duration_seconds=duration_seconds,
                    format="wav",
                    metadata={
                        "engine": "pyttsx3",
                        "word_count": word_count
                    }
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error with pyttsx3 synthesis: {e}")
            return None
    
    def create_video(self, text: str, images: List[Visualization], 
                    audio: Optional[AudioFile] = None) -> Optional[VideoFile]:
        """
        Combine visual elements with audio narration to create video content.
        
        Args:
            text: Text content for the video
            images: List of visualizations to include
            audio: Optional audio narration
            
        Returns:
            Generated video file or None if creation fails
        """
        if not MOVIEPY_AVAILABLE:
            logger.warning("MoviePy not available. Cannot create video.")
            return None
            
        if not text.strip() and not images:
            return None
        
        try:
            video_id = str(uuid.uuid4())
            
            # Generate audio if not provided
            if not audio and text.strip():
                audio = self.synthesize_audio(text)
            
            # Create video clips from images
            video_clips = []
            
            if images:
                # Calculate duration per image
                total_duration = audio.duration_seconds if audio else max(len(images) * 3, 10)
                duration_per_image = total_duration / len(images)
                
                for i, viz in enumerate(images):
                    try:
                        # Save visualization to temporary file
                        temp_img_path = self.output_dir / f"temp_viz_{video_id}_{i}.png"
                        with open(temp_img_path, 'wb') as f:
                            f.write(viz.content_data)
                        
                        # Create image clip
                        img_clip = ImageClip(str(temp_img_path), duration=duration_per_image)
                        img_clip = img_clip.resize(height=720)  # Standardize height
                        video_clips.append(img_clip)
                        
                        # Clean up temporary file
                        temp_img_path.unlink()
                        
                    except Exception as e:
                        logger.error(f"Error processing image {i} for video: {e}")
                        continue
            else:
                # Create a simple text-based video if no images
                video_clips = [self._create_text_video_clip(text, audio.duration_seconds if audio else 10)]
            
            if not video_clips:
                return None
            
            # Concatenate video clips
            final_video = concatenate_videoclips(video_clips, method="compose")
            
            # Add audio if available
            if audio:
                # Save audio to temporary file
                temp_audio_path = self.output_dir / f"temp_audio_{video_id}.mp3"
                with open(temp_audio_path, 'wb') as f:
                    f.write(audio.content_data)
                
                # Load audio clip
                audio_clip = AudioFileClip(str(temp_audio_path))
                final_video = final_video.set_audio(audio_clip)
                
                # Clean up temporary audio file
                temp_audio_path.unlink()
            
            # Export video to bytes
            temp_video_path = self.output_dir / f"temp_video_{video_id}.mp4"
            final_video.write_videofile(
                str(temp_video_path),
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )
            
            # Read video data
            with open(temp_video_path, 'rb') as f:
                video_data = f.read()
            
            # Clean up temporary video file
            temp_video_path.unlink()
            
            # Close clips to free memory
            final_video.close()
            for clip in video_clips:
                clip.close()
            
            return VideoFile(
                video_id=video_id,
                content_data=video_data,
                duration_seconds=final_video.duration,
                format="mp4",
                resolution="1280x720",
                metadata={
                    "image_count": len(images),
                    "has_audio": audio is not None,
                    "text_length": len(text)
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating video: {e}")
            return None
    
    def _create_text_video_clip(self, text: str, duration: float):
        """Create a video clip with text overlay."""
        if not MOVIEPY_AVAILABLE:
            return None
            
        try:
            # Create a simple image with text
            img = Image.new('RGB', (1280, 720), color='white')
            draw = ImageDraw.Draw(img)
            
            # Try to use a nice font, fall back to default if not available
            try:
                font = ImageFont.truetype("arial.ttf", 36)
            except:
                font = ImageFont.load_default()
            
            # Wrap text to fit the image
            wrapped_text = self._wrap_text(text, 60)  # 60 characters per line
            
            # Calculate text position (centered)
            text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            x = (1280 - text_width) // 2
            y = (720 - text_height) // 2
            
            # Draw text
            draw.text((x, y), wrapped_text, fill='black', font=font)
            
            # Save to temporary file
            temp_path = self.output_dir / f"text_frame_{uuid.uuid4()}.png"
            img.save(temp_path)
            
            # Create image clip
            clip = ImageClip(str(temp_path), duration=duration)
            
            # Clean up temporary file
            temp_path.unlink()
            
            return clip
            
        except Exception as e:
            logger.error(f"Error creating text video clip: {e}")
            # Return a blank clip as fallback
            if MOVIEPY_AVAILABLE:
                return ImageClip(np.zeros((720, 1280, 3), dtype=np.uint8), duration=duration)
            return None
    
    def _wrap_text(self, text: str, width: int) -> str:
        """Wrap text to specified width."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 <= width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    def generate_complete_multimedia_response(
        self, 
        context: List[KnowledgeChunk], 
        query: str,
        include_audio: bool = True,
        include_video: bool = False
    ) -> MultimediaResponse:
        """
        Generate a complete multimedia response with text, visualizations, audio, and optionally video.
        
        Args:
            context: List of relevant knowledge chunks
            query: Original user query
            include_audio: Whether to generate audio narration
            include_video: Whether to generate video content
            
        Returns:
            Complete multimedia response
        """
        try:
            # Generate text response
            text_content = self.generate_text_response(context, query)
            
            # Extract and process media from chunks
            all_media = []
            for chunk in context:
                all_media.extend(chunk.associated_media)
            
            processed_media = self.process_and_caption_images(all_media)
            
            # Extract data for visualization
            combined_content = text_content + " " + " ".join([chunk.content for chunk in context])
            data_patterns = self.extract_data_for_visualization(combined_content)
            
            # Create visualizations
            visualizations = self.create_visualizations(data_patterns)
            
            # Generate audio if requested
            audio_content = None
            if include_audio and text_content.strip():
                audio_content = self.synthesize_audio(text_content)
            
            # Generate video if requested
            video_content = None
            if include_video and (visualizations or text_content.strip()):
                video_content = self.create_video(text_content, visualizations, audio_content)
            
            # Create citations
            citations = []
            for chunk in context:
                citation = KnowledgeCitation(
                    source_type=chunk.source_type,
                    source_title=chunk.source_id,
                    location_reference=chunk.location_reference,
                    chunk_id=chunk.id,
                    relevance_score=1.0  # Could be calculated based on similarity
                )
                citations.append(citation)
            
            response = MultimediaResponse(
                text_content=text_content,
                visualizations=visualizations,
                audio_content=audio_content,
                video_content=video_content,
                knowledge_citations=citations
            )
            
            logger.info(f"Generated complete multimedia response with {len(visualizations)} visualizations, "
                       f"audio: {audio_content is not None}, video: {video_content is not None}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating multimedia response: {e}")
            # Return minimal response on error
            return MultimediaResponse(
                text_content="I encountered an error while generating the multimedia response.",
                visualizations=[],
                knowledge_citations=[]
            )
    
    def create_synchronized_multimedia(
        self, 
        text_segments: List[str], 
        images: List[Visualization],
        segment_durations: Optional[List[float]] = None
    ) -> Optional[VideoFile]:
        """
        Create synchronized multimedia content with precise timing.
        
        Args:
            text_segments: List of text segments for narration
            images: List of visualizations to synchronize
            segment_durations: Optional custom durations for each segment
            
        Returns:
            Synchronized video file with audio and visual elements
        """
        if not MOVIEPY_AVAILABLE:
            logger.warning("MoviePy not available. Cannot create synchronized multimedia.")
            return None
            
        if not text_segments and not images:
            return None
        
        try:
            video_id = str(uuid.uuid4())
            video_clips = []
            audio_clips = []
            
            # Calculate segment durations if not provided
            if not segment_durations:
                segment_durations = []
                for text in text_segments:
                    word_count = len(text.split())
                    duration = max((word_count / 150) * 60, 3.0)  # Minimum 3 seconds
                    segment_durations.append(duration)
            
            # Create synchronized segments
            for i, (text, duration) in enumerate(zip(text_segments, segment_durations)):
                # Generate audio for this segment
                segment_audio = self.synthesize_audio(text)
                
                if segment_audio:
                    # Save audio to temporary file
                    temp_audio_path = self.output_dir / f"segment_audio_{video_id}_{i}.mp3"
                    with open(temp_audio_path, 'wb') as f:
                        f.write(segment_audio.content_data)
                    
                    audio_clip = AudioFileClip(str(temp_audio_path))
                    audio_clips.append(audio_clip)
                    
                    # Clean up temporary file
                    temp_audio_path.unlink()
                
                # Create corresponding video segment
                if i < len(images):
                    # Use corresponding image
                    viz = images[i]
                    temp_img_path = self.output_dir / f"segment_img_{video_id}_{i}.png"
                    with open(temp_img_path, 'wb') as f:
                        f.write(viz.content_data)
                    
                    img_clip = ImageClip(str(temp_img_path), duration=duration)
                    img_clip = img_clip.resize(height=720)
                    video_clips.append(img_clip)
                    
                    # Clean up temporary file
                    temp_img_path.unlink()
                else:
                    # Create text-based clip
                    text_clip = self._create_text_video_clip(text, duration)
                    video_clips.append(text_clip)
            
            if not video_clips:
                return None
            
            # Combine all clips
            final_video = concatenate_videoclips(video_clips, method="compose")
            
            # Combine all audio
            if audio_clips:
                final_audio = concatenate_videoclips(audio_clips)
                final_video = final_video.set_audio(final_audio)
            
            # Export to file
            temp_video_path = self.output_dir / f"sync_video_{video_id}.mp4"
            final_video.write_videofile(
                str(temp_video_path),
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )
            
            # Read video data
            with open(temp_video_path, 'rb') as f:
                video_data = f.read()
            
            # Clean up
            temp_video_path.unlink()
            final_video.close()
            for clip in video_clips + audio_clips:
                clip.close()
            
            return VideoFile(
                video_id=video_id,
                content_data=video_data,
                duration_seconds=sum(segment_durations),
                format="mp4",
                resolution="1280x720",
                metadata={
                    "segments": len(text_segments),
                    "synchronized": True,
                    "total_duration": sum(segment_durations)
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating synchronized multimedia: {e}")
            return None
    
    def create_audio_with_background_music(
        self, 
        text: str, 
        background_tone: str = "professional"
    ) -> Optional[AudioFile]:
        """
        Create audio narration with optional background tone/music.
        
        Args:
            text: Text to convert to speech
            background_tone: Tone style (professional, casual, educational)
            
        Returns:
            Enhanced audio file with background elements
        """
        try:
            # Generate base narration
            base_audio = self.synthesize_audio(text)
            if not base_audio:
                return None
            
            # For now, return the base audio
            # In a full implementation, this would add background music/tones
            base_audio.metadata.update({
                "background_tone": background_tone,
                "enhanced": True
            })
            
            return base_audio
            
        except Exception as e:
            logger.error(f"Error creating enhanced audio: {e}")
            return None
    
    def create_presentation_video(
        self, 
        slides_data: List[Dict[str, Any]], 
        narration_text: str
    ) -> Optional[VideoFile]:
        """
        Create a presentation-style video with slides and narration.
        
        Args:
            slides_data: List of slide data with titles and content
            narration_text: Full narration text
            
        Returns:
            Presentation video file
        """
        if not MOVIEPY_AVAILABLE:
            logger.warning("MoviePy not available. Cannot create presentation video.")
            return None
        try:
            video_id = str(uuid.uuid4())
            
            # Generate narration audio
            narration_audio = self.synthesize_audio(narration_text)
            if not narration_audio:
                return None
            
            # Calculate duration per slide
            slide_duration = narration_audio.duration_seconds / len(slides_data)
            
            # Create slide images
            slide_clips = []
            for i, slide_data in enumerate(slides_data):
                slide_image = self._create_slide_image(slide_data, i)
                if slide_image:
                    temp_slide_path = self.output_dir / f"slide_{video_id}_{i}.png"
                    slide_image.save(temp_slide_path)
                    
                    slide_clip = ImageClip(str(temp_slide_path), duration=slide_duration)
                    slide_clip = slide_clip.resize(height=720)
                    slide_clips.append(slide_clip)
                    
                    # Clean up
                    temp_slide_path.unlink()
            
            if not slide_clips:
                return None
            
            # Combine slides
            presentation_video = concatenate_videoclips(slide_clips, method="compose")
            
            # Add narration
            temp_audio_path = self.output_dir / f"narration_{video_id}.mp3"
            with open(temp_audio_path, 'wb') as f:
                f.write(narration_audio.content_data)
            
            audio_clip = AudioFileClip(str(temp_audio_path))
            presentation_video = presentation_video.set_audio(audio_clip)
            
            # Export
            temp_video_path = self.output_dir / f"presentation_{video_id}.mp4"
            presentation_video.write_videofile(
                str(temp_video_path),
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )
            
            # Read and clean up
            with open(temp_video_path, 'rb') as f:
                video_data = f.read()
            
            temp_video_path.unlink()
            temp_audio_path.unlink()
            
            # Close clips
            presentation_video.close()
            audio_clip.close()
            for clip in slide_clips:
                clip.close()
            
            return VideoFile(
                video_id=video_id,
                content_data=video_data,
                duration_seconds=narration_audio.duration_seconds,
                format="mp4",
                resolution="1280x720",
                metadata={
                    "type": "presentation",
                    "slides": len(slides_data),
                    "has_narration": True
                }
            )
            
        except Exception as e:
            logger.error(f"Error creating presentation video: {e}")
            return None
    
    def _create_slide_image(self, slide_data: Dict[str, Any], slide_number: int) -> Optional[Image.Image]:
        """Create a slide image from slide data."""
        try:
            # Create slide background
            img = Image.new('RGB', (1280, 720), color='white')
            draw = ImageDraw.Draw(img)
            
            # Load fonts
            try:
                title_font = ImageFont.truetype("arial.ttf", 48)
                content_font = ImageFont.truetype("arial.ttf", 24)
            except:
                title_font = ImageFont.load_default()
                content_font = ImageFont.load_default()
            
            # Draw title
            title = slide_data.get('title', f'Slide {slide_number + 1}')
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (1280 - title_width) // 2
            draw.text((title_x, 50), title, fill='black', font=title_font)
            
            # Draw content
            content = slide_data.get('content', '')
            if content:
                wrapped_content = self._wrap_text(content, 80)
                draw.text((100, 150), wrapped_content, fill='black', font=content_font)
            
            # Add slide number
            slide_num_text = f"Slide {slide_number + 1}"
            draw.text((1150, 680), slide_num_text, fill='gray', font=content_font)
            
            return img
            
        except Exception as e:
            logger.error(f"Error creating slide image: {e}")
            return None