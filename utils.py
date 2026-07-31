import re
import os
import time
from typing import Dict, List, Any

# Safe import for Gemini / google generative SDK
# We try to import compatible modules in a forgiving way so the server
# does not crash at import time if the SDK is missing or the API changed.
gemini_client = None
genai_types = None

try:
    # try the modern 'genai' package first (some projects use genai.GenerativeModel)
    import genai as _genai  # type: ignore
    try:
        # prefer the high-level client if available
        if hasattr(_genai, "GenerativeModel"):
            # some code uses: genai.GenerativeModel(api_key=...)
            # create an instance if key provided; otherwise keep module
            api_key = os.getenv("GEMINI_API_KEY")
            try:
                gemini_client = _genai.GenerativeModel(api_key=api_key) if api_key else _genai.GenerativeModel()
            except Exception:
                # fallback to module if instantiation signature differs
                gemini_client = _genai
        else:
            gemini_client = _genai
        # genai may not expose a 'types' object; leave genai_types as None
        genai_types = getattr(_genai, "types", None)
    except Exception:
        gemini_client = _genai
        genai_types = getattr(_genai, "types", None)
except Exception:
    # try the google.generativeai package next
    try:
        import google.generativeai as _gai  # type: ignore
        # Newer google.generativeai may require configure(API_KEY) instead of a Client class
        try:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if hasattr(_gai, "configure"):
                # configure the module (no client instance returned)
                if api_key:
                    try:
                        _gai.configure(api_key=api_key)
                    except Exception:
                        # some versions expect api_key via environment; ignore minor failure
                        pass
                gemini_client = _gai
            elif hasattr(_gai, "Client"):
                # older style with Client class
                try:
                    gemini_client = _gai.Client(api_key=api_key) if api_key else _gai.Client()
                except Exception:
                    # fallback to module object
                    gemini_client = _gai
            else:
                gemini_client = _gai
            genai_types = getattr(_gai, "types", None)
        except Exception:
            gemini_client = _gai
            genai_types = getattr(_gai, "types", None)
    except Exception:
        # No compatible gemini SDK found — continue without crashing
        gemini_client = None
        genai_types = None

# If you previously used `client` and `types` variable names, keep backward-compatible aliases:
client = gemini_client
types = genai_types

# continue with streamlit and other imports
import streamlit as st
from dotenv import load_dotenv
import phonenumbers
import pycountry

load_dotenv()

def get_gemini_response(prompt: str, model: str = "gemini-2.5-flash") -> str:
    """Get response from Gemini AI with error handling"""
    try:
        if not client:
            # Keep existing behavior: use Streamlit to show error; fall back to empty string
            try:
                st.error("Gemini AI client not initialized")
            except Exception:
                print("Gemini AI client not initialized")
            return ""
        
        # Attempt to use the available client API; adapt to common API shapes.
        # We try a few common call patterns and handle failures gracefully.
        try:
            if hasattr(client, "GenerativeModel") and callable(client.GenerativeModel):
                try:
                    _model_instance = client.GenerativeModel(model)
                    response = _model_instance.generate_content(
                        prompt,
                        generation_config={"temperature": 0.7, "max_output_tokens": 4096}
                    )
                    # Extract text safely via candidates path first
                    if hasattr(response, "candidates") and response.candidates:
                        for cand in response.candidates:
                            if hasattr(cand, "content") and cand.content:
                                for part in cand.content.parts:
                                    if hasattr(part, "text") and part.text:
                                        return part.text
                    # Fallback to .text shortcut
                    if hasattr(response, "text") and response.text:
                        return response.text
                    return ""
                except Exception:
                    pass  # Fall through to the other patterns below
            # Pattern 1: google.generativeai or module-style with models.generate_content
            if hasattr(client, "models") and hasattr(client.models, "generate_content"):
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=(types.GenerateContentConfig(max_output_tokens=4096, temperature=0.7) if types else None)
                )
                # In some SDK versions result text is under response.text or response.content[0].text
                if hasattr(response, "text"):
                    return response.text or ""
                if hasattr(response, "content") and isinstance(response.content, (list, tuple)) and len(response.content):
                    first = response.content[0]
                    return getattr(first, "text", "") or getattr(first, "output", "") or ""
                return ""
            
            # Pattern 2: genai.GenerativeModel instance: .generate() or .generate_text(...)
            if hasattr(client, "generate") or hasattr(client, "generate_text"):
                # try generic call
                try:
                    if hasattr(client, "generate"):
                        out = client.generate(model=model, prompt=prompt)
                    else:
                        out = client.generate_text(model=model, prompt=prompt)
                except TypeError:
                    # some signatures differ; try other kw names
                    out = client.generate(model=model, contents=prompt)
                
                # extract text from response
                if isinstance(out, dict):
                    return out.get("text", "") or out.get("output", "") or ""
                if hasattr(out, "text"):
                    return out.text or ""
                # fallback
                return str(out)
            
            # Pattern 3: module object with a top-level generate function
            if hasattr(client, "generate_text") and callable(client.generate_text):
                r = client.generate_text(model=model, input=prompt)
                if isinstance(r, dict):
                    return r.get("candidates", [{}])[0].get("content", "") or r.get("output", "")
                if hasattr(r, "candidates"):
                    c = r.candidates
                    if c and len(c):
                        return getattr(c[0], "content", "") or ""
                return str(r)
            
            # Unknown client object shape: try to call `str()` as fallback
            print("Gemini client present but unknown API shape; returning empty response.")
            return ""
        except Exception as e:
            # Log the inner error but fail gracefully
            try:
                st.error(f"AI processing error: {str(e)}")
            except Exception:
                print("AI processing error:", str(e))
            return ""
    except Exception as e:
        try:
            st.error(f"AI processing error: {str(e)}")
        except Exception:
            print("AI processing error:", str(e))
        return ""

# ---------------------------
# Rest of your original utils.py follows unchanged
# (from filter_keywords onward). I paste the rest verbatim to keep file self-contained.
# ---------------------------

def filter_keywords(keywords):
    """Remove generic and stop words from keyword list"""
    stop_words = {
        "the", "and", "is", "in", "of", "for", "to", "with", "on", "at", "by", "an", "be",
        "from", "that", "this", "it", "as", "are", "or", "have", "has", "was", "were", "will",
        "a", "i", "you", "your", "we", "our", "can", "able", "achieve", "achieved", "aptitude",
        "attitude", "dynamic", "motivated", "strong", "great", "success", "successful", "capable",
        "good", "proficient", "hardworking", "dedicated", "excellent", "team", "communication", "passion"
    }
    return [kw for kw in keywords if kw not in stop_words and len(kw) > 2]

def optimize_keywords(cv_content: str, job_description: str = None, target_match: int = None) -> Dict[str, Any]:
    """Improved ATS score checker with domain/title alignment"""

    if not job_description:
        return get_default_analysis()

    # Normalize & extract keyword sets
    jd_keywords = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9\-]+\b', job_description.lower()))
    cv_keywords = set(re.findall(r'\b[a-zA-Z][a-zA-Z0-9\-]+\b', cv_content.lower()))

    common_keywords = jd_keywords.intersection(cv_keywords)
    keyword_match_pct = round(len(common_keywords) / len(jd_keywords) * 100) if jd_keywords else 0
    keyword_score = min(40, keyword_match_pct)  # Cap at 40

    # Quantification score
    quantitative_pct = calculate_quantitative_percentage(cv_content)
    quantitative_score = min(int(quantitative_pct / 5), 20)  # Max 20 pts

    # Formatting score
    validation = validate_cv_format(cv_content)
    format_score = 10 if validation["valid"] else 5

    # ==== NEW: Domain & Job Title Matching ====
    title_match = 0
    domain_score = 0
    missing_keywords = list(jd_keywords - cv_keywords)

    # Job title extraction
    job_title_match = re.search(r'(?i)(applying for|job title|position:?)\s*([\w\s]+)', job_description)
    if job_title_match:
        title = job_title_match.group(2).strip().lower()
        if title in cv_content.lower():
            title_match = 10
        else:
            title_match = 0

    # Domain relevance: if more than 70% of domain terms are missing, penalize
    domain_terms = extract_domain_keywords(job_description)
    domain_overlap = set(domain_terms).intersection(cv_keywords)
    if len(domain_overlap) < max(1, len(domain_terms) * 0.3):
        domain_score = 0
    else:
        domain_score = 20

    # Total ATS Score
    ats_score = keyword_score + quantitative_score + format_score + title_match + domain_score
    ats_score = min(100, ats_score)

    # Final suggestion block
    suggestions = []
    if quantitative_pct < 50:
        suggestions.append("Add more quantifiable achievements with specific numbers and percentages")
    if not validation["valid"]:
        suggestions.append("Fix formatting issues and add missing sections")
    if title_match == 0:
        suggestions.append("Ensure your resume reflects the job title from the JD")
    if domain_score == 0:
        suggestions.append("Align your resume to the domain-specific keywords in the JD")

    missing_keywords = list(jd_keywords - cv_keywords)
    filtered_missing_keywords = filter_keywords(missing_keywords)

    return {
        "score": ats_score,
        "keyword_match": keyword_match_pct,
        "suggestions": suggestions,
        "missing_keywords": filtered_missing_keywords[:10],
        "strengths": validation.get("strengths", ["Good structure", "Relevant experience"])
    }

def get_default_analysis():
    """Return default analysis when AI fails"""
    return {
        'score': 70,
        'keyword_match': 65,
        'suggestions': ['Enhance technical skills section', 'Add more quantifiable results'],
        'missing_keywords': ['industry-specific terms'],
        'strengths': ['Good structure', 'Clear formatting']
    }

def extract_keywords_from_text(text: str) -> List[str]:
    """Extract potential keywords from text"""
    # Remove common words and extract meaningful terms
    words = re.findall(r'\b[A-Za-z]{3,}\b', text.lower())
    
    # Filter out common words
    common_words = {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'was', 'were', 'been', 'are', 'will', 'would', 'could', 'should'}
    keywords = [word for word in set(words) if word not in common_words]
    
    return keywords[:20]  # Return top 20 keywords

def keyword_overlap_score(resume_text: str, jd_text: str) -> int:
    """Local resume↔job match score (0–100). Zero LLM calls.

    Percentage of *meaningful* job-description keywords (stop-words removed via
    filter_keywords) that also appear in the resume. Deterministic — same inputs
    always yield the same score. Used by the job aggregator (Phase 1).
    """
    if not resume_text or not jd_text:
        return 0

    token = r'\b[a-zA-Z][a-zA-Z0-9\-]+\b'
    jd_keywords = set(filter_keywords(re.findall(token, jd_text.lower())))
    if not jd_keywords:
        return 0

    cv_keywords = set(re.findall(token, resume_text.lower()))
    overlap = jd_keywords & cv_keywords
    return round(len(overlap) / len(jd_keywords) * 100)

def enforce_page_limit(content: str, max_pages: int = 2) -> str:
    """Enforce page limit by trimming content intelligently"""
    
    if not content:
        return "Error: No content to limit"
    
    lines = content.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    
    # Estimate lines per page (approximately 50 lines per page)
    lines_per_page = 50
    max_lines = max_pages * lines_per_page
    
    if len(non_empty_lines) <= max_lines:
        return content
    
    # Parse into sections
    sections = parse_content_sections(content)
    
    # Priority order for sections
    priority_sections = [
        'professional summary',
        'key skills',
        'work experience',
        'education',
        'certifications',
        'projects',
        'awards',
        'languages',
        'hobbies'
    ]
    
    # Rebuild content with priority
    rebuilt_lines = []
    current_line_count = 0
    
    # Add name/header first
    name_section = get_name_section(sections)
    if name_section:
        rebuilt_lines.extend(name_section)
        current_line_count += len(name_section)
    
    # Add sections by priority
    for priority in priority_sections:
        if current_line_count >= max_lines:
            break
            
        section_content = get_section_by_priority(sections, priority)
        if section_content:
            available_lines = max_lines - current_line_count
            if available_lines > 0:
                # Trim section if necessary
                trimmed_section = trim_section_content(section_content, available_lines)
                rebuilt_lines.extend(trimmed_section)
                current_line_count += len(trimmed_section)
    
    return '\n'.join(rebuilt_lines)

def parse_content_sections(content: str) -> Dict[str, List[str]]:
    """Parse content into sections"""
    sections = {}
    current_section = None
    current_content = []
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this is a section header
        if line.endswith(':') and len(line) > 1 and line.isupper():
            # Save previous section
            if current_section:
                sections[current_section.lower()] = current_content
            
            # Start new section
            current_section = line[:-1]  # Remove colon
            current_content = []
        elif ':' in line and len(line.split(':')) == 2:
            # Alternative section header format
            if current_section:
                sections[current_section.lower()] = current_content
            
            current_section = line.split(':')[0].strip()
            current_content = [line.split(':')[1].strip()] if line.split(':')[1].strip() else []
        else:
            if current_section:
                current_content.append(line)
            else:
                # This might be the name or first line
                sections['header'] = sections.get('header', []) + [line]
    
    # Save last section
    if current_section:
        sections[current_section.lower()] = current_content
    
    return sections

def get_name_section(sections: Dict[str, List[str]]) -> List[str]:
    """Get name/header section"""
    if 'header' in sections:
        return sections['header']
    return []

def get_section_by_priority(sections: Dict[str, List[str]], priority: str) -> List[str]:
    """Get section content by priority keyword"""
    for section_name, content in sections.items():
        if priority in section_name.lower():
            return [f"{section_name.upper()}:"] + content
    return []

def trim_section_content(section_content: List[str], max_lines: int) -> List[str]:
    """Trim section content to fit within line limit"""
    if len(section_content) <= max_lines:
        return section_content
    
    # Keep header and trim content
    if section_content and section_content[0].endswith(':'):
        header = [section_content[0]]
        content = section_content[1:max_lines-1]
        return header + content
    else:
        return section_content[:max_lines]

def calculate_quantitative_percentage(content: str) -> float:
    """Calculate percentage of quantitative content"""
    lines = content.split('\n')
    quantitative_lines = 0
    total_content_lines = 0
    
    # Pattern to match numbers, percentages, and quantifiable metrics
    quantitative_pattern = r'(\d+(?:\.\d+)?(?:%|K|M|B|k|m|b|\+|,\d+)*|\$\d+|increased?|decreased?|improved?|reduced?|saved?|generated?|achieved?)'
    
    for line in lines:
        line = line.strip()
        if line and not line.endswith(':'):  # Skip empty lines and headers
            total_content_lines += 1
            if re.search(quantitative_pattern, line, re.IGNORECASE):
                quantitative_lines += 1
    
    if total_content_lines == 0:
        return 0.0
    
    return (quantitative_lines / total_content_lines) * 100

def enhance_with_action_verbs(content: str, intensity: str = "High") -> str:
    """Enhance content with action verbs"""
    
    action_verbs = {
        "Moderate": [
            "managed", "developed", "created", "implemented", "led", "coordinated",
            "designed", "analyzed", "improved", "organized", "planned", "supervised"
        ],
        "High": [
            "spearheaded", "orchestrated", "revolutionized", "transformed", "pioneered",
            "architected", "optimized", "streamlined", "accelerated", "amplified",
            "executed", "delivered", "achieved", "established", "initiated"
        ],
        "Very High": [
            "masterminded", "propelled", "catapulted", "dominated", "commanded",
            "conquered", "devastated", "obliterated", "revolutionized", "transformed",
            "pioneered", "trailblazed", "championed", "galvanized", "maximized"
        ]
    }
    
    # This is a simplified implementation
    # In practice, you'd use more sophisticated NLP to replace verbs contextually
    weak_verbs = ["worked", "did", "made", "helped", "was responsible for", "handled"]
    replacement_verbs = action_verbs.get(intensity, action_verbs["High"])
    
    enhanced_content = content
    for i, weak_verb in enumerate(weak_verbs):
        if i < len(replacement_verbs):
            enhanced_content = re.sub(
                r'\b' + weak_verb + r'\b',
                replacement_verbs[i],
                enhanced_content,
                flags=re.IGNORECASE
            )
    
    return enhanced_content

def validate_cv_format(content: str) -> Dict[str, Any]:
    """Validate CV format and structure"""
    issues = []
    suggestions = []
    
    # Check for essential sections
    essential_sections = ['professional summary', 'experience', 'skills', 'education']
    content_lower = content.lower()
    
    for section in essential_sections:
        if section not in content_lower:
            issues.append(f"Missing {section} section")
    
    # Check for contact information
    if not re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content):
        issues.append("Missing email address")
    
    # Check for phone number
    if not re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', content):
        issues.append("Missing phone number")
    
    # Check for quantifiable achievements
    quantitative_percent = calculate_quantitative_percentage(content)
    if quantitative_percent < 30:
        suggestions.append("Add more quantifiable achievements with numbers and percentages")
    
    # Check content length
    word_count = len(content.split())
    if word_count < 200:
        issues.append("CV content is too short")
    elif word_count > 800:
        suggestions.append("Consider condensing content for better readability")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'suggestions': suggestions,
        'quantitative_percentage': quantitative_percent,
        'word_count': word_count
    }

def format_processing_time(seconds: float) -> str:
    """Format processing time for display"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.1f}s"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for download"""
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized

def estimate_reading_time(content: str) -> int:
    """Estimate reading time in seconds"""
    words = len(content.split())
    # Average reading speed: 200-250 words per minute
    reading_speed = 225  # words per minute
    return int((words / reading_speed) * 60)

def extract_contact_info(content: str) -> Dict[str, str]:
    """Extract contact information from CV"""
    contact_info = {}
    
    # Extract email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content)
    if email_match:
        contact_info['email'] = email_match.group()
    
    # Extract phone
    phone_match = re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', content)
    if phone_match:
        contact_info['phone'] = phone_match.group()
    
    # Extract LinkedIn
    linkedin_match = re.search(r'linkedin\.com/in/[\w-]+', content, re.IGNORECASE)
    if linkedin_match:
        contact_info['linkedin'] = linkedin_match.group()
    
    return contact_info

def calculate_ats_score(cv_content: str, job_description: str) -> int:
    """Calculate ATS compatibility score"""
    try:
        # Use keyword analysis
        analysis = optimize_keywords(cv_content, job_description)
        return analysis.get('score', 75)
    except:
        # Fallback calculation
        jd_words = set(job_description.lower().split())
        cv_words = set(cv_content.lower().split())
        
        common_words = jd_words.intersection(cv_words)
        if len(jd_words) > 0:
            match_ratio = len(common_words) / len(jd_words)
            return min(100, int(match_ratio * 100) + 30)  # Add base score
        
        return 75  # Default score

def get_improvement_suggestions(cv_content: str, job_description: str) -> List[str]:
    """Get specific improvement suggestions"""
    suggestions = []
    
    # Check quantitative content
    quant_percent = calculate_quantitative_percentage(cv_content)
    if quant_percent < 50:
        suggestions.append("Add more quantifiable achievements with specific numbers and percentages")
    
    # Check for action verbs
    weak_verbs = ["worked", "did", "made", "helped", "was responsible for"]
    for verb in weak_verbs:
        if verb in cv_content.lower():
            suggestions.append(f"Replace weak verbs like '{verb}' with stronger action verbs")
            break
    
    # Check for job-specific keywords
    if job_description:
        analysis = optimize_keywords(cv_content, job_description)
        missing_keywords = analysis.get('missing_keywords', [])
        if missing_keywords:
            suggestions.append(f"Include these important keywords: {', '.join(missing_keywords[:3])}")
    
    # Check formatting
    validation = validate_cv_format(cv_content)
    suggestions.extend(validation['suggestions'])
    
    return suggestions[:5]  # Return top 5 suggestions

def extract_domain_keywords(job_description: str) -> List[str]:
    """Extract domain-relevant keywords from JD"""
    clinical_terms = ['clinic', 'dental', 'oral', 'patient', 'surgery', 'anesthesia', 'teeth', 'hygiene', 'prosthodontics', 'radiographs']
    tech_terms = ['sql', 'python', 'tableau', 'pipeline', 'dashboard', 'kafka', 'data engineering']

    # You can expand this logic to classify JD domain more smartly
    if any(word in job_description.lower() for word in clinical_terms):
        return clinical_terms
    elif any(word in job_description.lower() for word in tech_terms):
        return tech_terms
    return []

def get_all_country_dial_codes(default_region="IN"):
    """Return (label, region, dial_code) tuples for all supported regions."""
    items = []
    for region in sorted(phonenumbers.SUPPORTED_REGIONS):
        try:
            code = phonenumbers.country_code_for_region(region)
            country = pycountry.countries.get(alpha_2=region)
            name = getattr(country, "name", region)
            label = f"{name} (+{code})"
            items.append((label, region, f"+{code}"))
        except Exception:
            continue
    # Put default region (e.g., India) at the top
    items.sort(key=lambda x: (x[1] != default_region, x[0]))
    return items