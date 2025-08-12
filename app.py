from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import requests
import re
import json
import os
import codecs
import time
import random
from urllib.parse import urlparse, parse_qs
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def clean_description(raw_description):
    """
    Clean and format the YouTube description text for better readability
    """
    try:
        description = raw_description
        
        # Handle JSON-escaped unicode sequences first
        try:
            # Decode JSON escape sequences like \u0000
            description = codecs.decode(description, 'unicode_escape')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        
        # Handle common escape sequences
        description = description.replace('\\n', '\n')
        description = description.replace('\\r', '\r')
        description = description.replace('\\t', '\t')
        description = description.replace('\\"', '"')
        description = description.replace("\\'", "'")
        description = description.replace('\\\\', '\\')
        
        # Try to fix garbled Unicode characters
        # This handles cases where UTF-8 was incorrectly decoded as Latin-1
        try:
            # If the string contains the garbled pattern, try to fix it
            if 'ð' in description or any(ord(c) > 255 for c in description if isinstance(c, str)):
                # Try to encode as latin-1 and decode as utf-8
                description = description.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
            # If that doesn't work, try other approaches
            try:
                # Remove or replace problematic characters
                description = description.encode('utf-8', errors='ignore').decode('utf-8')
            except (UnicodeDecodeError, UnicodeEncodeError):
                # As a last resort, remove non-ASCII characters
                description = ''.join(char for char in description if ord(char) < 128)
        
        # Clean up whitespace while preserving intentional formatting
        lines = description.split('\n')
        cleaned_lines = []
        
        for line in lines:
            cleaned_line = line.strip()
            cleaned_lines.append(cleaned_line)
        
        description = '\n'.join(cleaned_lines)
        
        # Remove excessive consecutive newlines (more than 2)
        description = re.sub(r'\n{3,}', '\n\n', description)
        
        # Final cleanup - ensure it's valid UTF-8
        try:
            description = description.encode('utf-8').decode('utf-8')
        except UnicodeError:
            description = description.encode('utf-8', errors='replace').decode('utf-8')
        
        # Trim if too long
        if len(description) > 2000:
            description = description[:2000] + "..."
        
        return description.strip()
        
    except Exception as e:
        print(f"Error in clean_description: {str(e)}")
        return f"Error cleaning description: {str(e)}"

def get_youtube_info(url):
    """
    Get YouTube video title and description from any YouTube URL
    Enhanced version with better detection and alternative methods
    """
    try:
        # Try multiple approaches in order
        methods = [
            lambda: get_youtube_info_method1(url),
            lambda: get_youtube_info_method2(url),
            lambda: get_youtube_info_method3(url)
        ]
        
        for i, method in enumerate(methods):
            try:
                result = method()
                if (result['title'] not in ['Title not found', 'Error'] and 
                    result['description'] not in ['Description not found', 'Error']):
                    print(f"Success with method {i+1}")
                    return result
                elif result['title'] not in ['Title not found', 'Error']:
                    print(f"Partial success with method {i+1} (title only)")
                    # Keep trying for description
                    for j, method2 in enumerate(methods[i+1:], i+1):
                        try:
                            result2 = method2()
                            if result2['description'] not in ['Description not found', 'Error']:
                                return {
                                    'title': result['title'],
                                    'description': result2['description']
                                }
                        except:
                            continue
                    return result
            except Exception as e:
                print(f"Method {i+1} failed: {str(e)}")
                continue
        
        # If all methods fail, return error
        return {
            'title': "All extraction methods failed",
            'description': "Could not extract video information"
        }
        
    except Exception as e:
        print(f"Error in get_youtube_info: {str(e)}")
        return {
            'title': f"Error: {str(e)}",
            'description': f"Error: {str(e)}"
        }

def get_youtube_info_method1(url):
    """Method 1: Standard web scraping with enhanced patterns"""
    time.sleep(random.uniform(0.5, 2))
    
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'DNT': '1'
    }
    
    response = session.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    content = response.text
    print(f"Method 1 - Content length: {len(content)}")
    
    # Check for blocking
    if "unusual traffic" in content.lower() or len(content) < 1000:
        raise Exception("Request appears to be blocked")
    
    # Extract title
    title_patterns = [
        r'"videoDetails":\s*{[^}]*?"title":"((?:[^"\\]|\\.)*)(?<!\\)"',
        r'<title[^>]*>([^<]+?)\s*-\s*YouTube</title>',
        r'<meta property="og:title" content="([^"]*)"',
        r'"title":"((?:[^"\\]|\\.)*?)(?<!\\)"[^}]*?"lengthSeconds"',
    ]
    
    title = "Title not found"
    for pattern in title_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            title = clean_description(match.group(1))
            if len(title.strip()) > 0:
                break
    
    # Extract description
    desc_patterns = [
        r'"videoDetails":\s*{[^}]*?"shortDescription":"((?:[^"\\]|\\.)*)(?<!\\)"',
        r'"shortDescription":"((?:[^"\\]|\\.)*)(?<!\\)"',
        r'<meta property="og:description" content="([^"]*)"',
        r'"description":\s*{"simpleText":"((?:[^"\\]|\\.)*)(?<!\\)"}',
    ]
    
    description = "Description not found"
    for pattern in desc_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            description = clean_description(match.group(1))
            if len(description.strip()) > 0:
                break
    
    return {'title': title, 'description': description}

def get_youtube_info_method2(url):
    """Method 2: Mobile YouTube approach"""
    time.sleep(random.uniform(0.5, 2))
    
    # Convert to mobile URL
    mobile_url = url.replace('www.youtube.com', 'm.youtube.com')
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
    }
    
    response = requests.get(mobile_url, headers=headers, timeout=15)
    response.raise_for_status()
    
    content = response.text
    print(f"Method 2 - Mobile content length: {len(content)}")
    
    # Mobile-specific patterns
    title_patterns = [
        r'<title[^>]*>([^<]+)</title>',
        r'"title":"([^"]*)"',
        r'<meta property="og:title" content="([^"]*)"'
    ]
    
    title = "Title not found"
    for pattern in title_patterns:
        match = re.search(pattern, content)
        if match:
            raw_title = match.group(1)
            title = clean_description(raw_title.replace(' - YouTube', ''))
            if len(title.strip()) > 0:
                break
    
    desc_patterns = [
        r'<meta property="og:description" content="([^"]*)"',
        r'"description":"([^"]*)"',
        r'<meta name="description" content="([^"]*)"'
    ]
    
    description = "Description not found"
    for pattern in desc_patterns:
        match = re.search(pattern, content)
        if match:
            description = clean_description(match.group(1))
            if len(description.strip()) > 0:
                break
    
    return {'title': title, 'description': description}

def get_youtube_info_method3(url):
    """Method 3: Alternative approach using different endpoints"""
    try:
        # Extract video ID
        video_id = get_video_id_from_url(url)
        if not video_id:
            raise Exception("Could not extract video ID")
        
        time.sleep(random.uniform(0.5, 2))
        
        # Try oembed endpoint first
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; YTInfoExtractor/1.0)'
        }
        
        try:
            response = requests.get(oembed_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                title = data.get('title', 'Title not found')
                # oEmbed doesn't provide description, so get it from main page
                
                # Get description from main page with minimal request
                main_response = requests.get(url, headers=headers, timeout=10)
                desc_match = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)(?<!\\)"', main_response.text)
                description = "Description not found"
                if desc_match:
                    description = clean_description(desc_match.group(1))
                
                print(f"Method 3 - oEmbed success")
                return {'title': title, 'description': description}
        except:
            pass
        
        # Fallback: Try a simple approach with minimal headers
        simple_headers = {'User-Agent': 'curl/7.68.0'}
        response = requests.get(url, headers=simple_headers, timeout=15)
        content = response.text
        
        # Simple extraction
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', content)
        title = "Title not found"
        if title_match:
            title = clean_description(title_match.group(1).replace(' - YouTube', ''))
        
        desc_match = re.search(r'<meta property="og:description" content="([^"]*)"', content)
        description = "Description not found"
        if desc_match:
            description = clean_description(desc_match.group(1))
        
        print(f"Method 3 - Simple extraction")
        return {'title': title, 'description': description}
        
    except Exception as e:
        print(f"Method 3 error: {str(e)}")
        return {'title': "Title not found", 'description': "Description not found"}

def get_youtube_tags(video_url):
    """
    Extract YouTube video tags from the video page
    """
    try:
        time.sleep(random.uniform(0.5, 1.5))  # Rate limiting
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(video_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Look for keywords/tags in the page with multiple patterns
        tag_patterns = [
            r'"keywords":\s*\[(.*?)\]',
            r'"tags":\s*\[(.*?)\]',
            r'"hashtags":\s*\[(.*?)\]'
        ]
        
        all_tags = []
        
        for pattern in tag_patterns:
            keywords_match = re.search(pattern, response.text)
            if keywords_match:
                keywords_str = keywords_match.group(1)
                # Extract individual tags
                tags = re.findall(r'"([^"]*)"', keywords_str)
                all_tags.extend(tags)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in all_tags:
            if tag not in seen and len(tag.strip()) > 0:
                seen.add(tag)
                unique_tags.append(tag.strip())
        
        return unique_tags[:20]  # Limit to 20 tags
        
    except Exception as e:
        print(f"Error extracting tags: {str(e)}")
        return []

def get_video_id_from_url(video_url):
    """Extract video ID from YouTube URL"""
    try:
        parsed = urlparse(video_url)
        video_id = None

        if parsed.hostname in ("youtu.be",):
            video_id = parsed.path[1:]
        elif parsed.hostname in ("www.youtube.com", "youtube.com"):
            if "/watch" in parsed.path:
                qs = parse_qs(parsed.query)
                video_id = qs.get("v", [None])[0]
            elif "/embed/" in parsed.path:
                video_id = parsed.path.split("/embed/")[1].split("?")[0]
            elif "/v/" in parsed.path:
                video_id = parsed.path.split("/v/")[1].split("?")[0]

        # Clean video ID (remove any extra parameters)
        if video_id:
            video_id = video_id.split("&")[0].split("?")[0]
            
        return video_id
    except Exception as e:
        print(f"Error extracting video ID: {str(e)}")
        return None

@app.route('/')
def index():
    """Serve the main HTML page"""
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>YouTube Info Extractor</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 800px; margin: 0 auto; }
                input[type="url"] { width: 70%; padding: 10px; margin: 10px; }
                button { padding: 10px 20px; background: #ff0000; color: white; border: none; cursor: pointer; }
                .result { margin: 20px 0; padding: 20px; border: 1px solid #ddd; }
                .description { white-space: pre-wrap; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>YouTube Video Info Extractor</h1>
                <input type="url" id="videoUrl" placeholder="Enter YouTube URL">
                <button onclick="extractInfo()">Extract Info</button>
                <div id="result"></div>
            </div>
            
            <script>
                async function extractInfo() {
                    const url = document.getElementById('videoUrl').value;
                    if (!url) return;
                    
                    const result = document.getElementById('result');
                    result.innerHTML = 'Loading...';
                    
                    try {
                        const response = await fetch('/api/extract', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ url: url })
                        });
                        
                        const data = await response.json();
                        
                        if (data.error) {
                            result.innerHTML = `<div class="result">Error: ${data.error}</div>`;
                        } else {
                            result.innerHTML = `
                                <div class="result">
                                    <h3>Title:</h3>
                                    <p>${data.title}</p>
                                    <h3>Description:</h3>
                                    <p class="description">${data.description}</p>
                                    <h3>Tags:</h3>
                                    <p>${data.tags.join(', ')}</p>
                                    ${data.thumbnail ? `<h3>Thumbnail:</h3><img src="${data.thumbnail}" style="max-width: 300px;">` : ''}
                                </div>
                            `;
                        }
                    } catch (error) {
                        result.innerHTML = `<div class="result">Error: ${error.message}</div>`;
                    }
                }
            </script>
        </body>
        </html>
        """

@app.route('/api/extract', methods=['POST'])
def extract_video_info():
    """API endpoint to extract YouTube video information"""
    try:
        data = request.get_json()
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'error': 'No URL provided'}), 400
        
        if not ('youtube.com' in video_url or 'youtu.be' in video_url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        print(f"Extracting info for URL: {video_url}")
        
        # Get video information
        info = get_youtube_info(video_url)
        tags = get_youtube_tags(video_url)
        
        # Get video ID for thumbnail
        video_id = get_video_id_from_url(video_url)
        
        # Build thumbnail URLs
        thumbnail_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/default.jpg"
        ] if video_id else []
        
        # Find working thumbnail URL
        thumbnail_url = None
        for url in thumbnail_urls:
            try:
                response = requests.head(url, timeout=5)
                if response.status_code == 200:
                    thumbnail_url = url
                    break
            except:
                continue
        
        result = {
            'title': info['title'],
            'description': info['description'],
            'tags': tags,
            'thumbnail': thumbnail_url,
            'video_id': video_id
        }
        
        print(f"Extraction completed. Title: {info['title'][:50]}...")
        return jsonify(result)
        
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-thumbnail/<video_id>')
def download_thumbnail(video_id):
    """API endpoint to download thumbnail"""
    try:
        thumbnail_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/default.jpg"
        ]
        
        for thumbnail_url in thumbnail_urls:
            try:
                response = requests.get(thumbnail_url, timeout=10)
                if response.status_code == 200:
                    # Create a temporary file
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    temp_file.write(response.content)
                    temp_file.close()
                    
                    return send_file(
                        temp_file.name,
                        as_attachment=True,
                        download_name=f'{video_id}_thumbnail.jpg',
                        mimetype='image/jpeg'
                    )
            except Exception as e:
                print(f"Error downloading thumbnail from {thumbnail_url}: {str(e)}")
                continue
        
        return jsonify({'error': 'Thumbnail not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug', methods=['POST'])
def debug_extraction():
    """Debug endpoint to see what's happening during extraction"""
    try:
        data = request.get_json()
        video_url = data.get('url')
        
        if not video_url:
            return jsonify({'error': 'No URL provided'}), 400
        
        print(f"DEBUG: Extracting info for URL: {video_url}")
        
        # Try to get basic page content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(video_url, headers=headers, timeout=15)
        content = response.text
        
        # Check if we're being blocked
        is_blocked = (
            "unusual traffic" in content.lower() or 
            "captcha" in content.lower() or
            len(content) < 1000 or
            "blocked" in content.lower()
        )
        
        # Look for key indicators
        has_video_details = '"videoDetails"' in content
        has_title_tag = '<title>' in content
        has_og_tags = 'og:title' in content
        
        # Find potential title matches
        title_samples = []
        patterns = [
            r'<title[^>]*>([^<]+)</title>',
            r'"title":"([^"]*)"',
            r'<meta property="og:title" content="([^"]*)"'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            title_samples.extend(matches[:3])  # Get first 3 matches
        
        # Find potential description matches
        desc_samples = []
        desc_patterns = [
            r'"shortDescription":"([^"]{0,200})',
            r'<meta property="og:description" content="([^"]*)"'
        ]
        
        for pattern in desc_patterns:
            matches = re.findall(pattern, content)
            desc_samples.extend(matches[:3])
        
        debug_info = {
            'url': video_url,
            'response_status': response.status_code,
            'content_length': len(content),
            'is_likely_blocked': is_blocked,
            'has_video_details_json': has_video_details,
            'has_title_tag': has_title_tag,
            'has_og_tags': has_og_tags,
            'title_samples': title_samples,
            'description_samples': desc_samples,
            'content_preview': content[:1000] if len(content) > 1000 else content
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e), 'debug': 'Exception in debug endpoint'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'message': 'YouTube Info Extractor is running'})

if __name__ == '__main__':
    print("Starting YouTube Info Extractor...")
    print("Available endpoints:")
    print("  GET  / - Main interface")
    print("  POST /api/extract - Extract video info")
    print("  GET  /api/download-thumbnail/<video_id> - Download thumbnail")
    print("  GET  /health - Health check")
    
    app.run(debug=True, host='0.0.0.0', port=5000)