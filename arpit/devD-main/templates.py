from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import black, darkblue, gray
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from io import BytesIO
import re
from reportlab.platypus import HRFlowable


def apply_template(cv_content, template_name):
    """Apply selected template to CV content"""
    
    if template_name == "professional":
        return create_professional_template(cv_content)
    else:
        return create_professional_template(cv_content)

def create_professional_template(cv_content):
    """Create professional template PDF"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=darkblue
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=6,
        spaceBefore=12,
        textColor=darkblue
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,                 # Slightly smaller font
        spaceAfter=2,               # ↓ Reduce spacing between lines
        leading=11,                 # ↓ Tighten line height
        alignment=TA_JUSTIFY        # ✅ Justify text
    )
    
    # Parse CV content into sections
    sections = parse_cv_sections(cv_content)
    # ✅ Enforce 2-page line budget
    sections = trim_sections_to_fit(sections, max_lines=100)
    
    # Build story
    story = []
    
    # Add header section (Name + Contact Info)
    if 'HEADER' in sections:
        for line in sections['HEADER']:
            story.append(Paragraph(line, title_style))
        story.append(Spacer(1, 12))
    
    # Add sections
    for section_name, section_content in sections.items():
        if section_name.endswith(':'):
            # This is a section header
            story.append(Paragraph(section_name, heading_style))
            story.append(HRFlowable(width="100%", thickness=1.5, color=darkblue, spaceBefore=3, spaceAfter=6))

            
            for i, line in enumerate(section_content):
                if not line.strip():
                    continue

                is_bold_line = False
                add_top_space = False  # <-- Flag to trigger spacing

                if section_name.strip().upper() == "WORK EXPERIENCE:" and "|" in line and not line.strip().startswith("•"):
                    is_bold_line = True
                    add_top_space = True  # <-- Trigger small space before company line

                if section_name.strip().upper() == "PROJECTS:" and not line.strip().startswith("•"):
                    is_bold_line = True

                # 🔵 Add small space before each company line
                if add_top_space:
                    story.append(Spacer(1, 6))  # ~6 points (~0.08 inch)

                if is_bold_line:
                    formatted = f"<b>{line.strip()}</b>"
                else:
                    formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line.strip())

                story.append(Paragraph(formatted, body_style))


            
            story.append(Spacer(1, 12))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def parse_cv_sections(cv_content):
    sections = {}
    current_section = None
    current_content = []

    lines = cv_content.split('\n')

    header_block = []
    section_started = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r'^[A-Z][A-Za-z ]{2,}:\s*$', line):
            section_started = True
            if current_section:
                sections[current_section] = current_content
            current_section = line if line.endswith(':') else f"{line}:"
            current_content = []
        else:
            if not section_started:
                header_block.append(line)
            elif current_section:
                current_content.append(line)

    if current_section:
        sections[current_section] = current_content

    if header_block:
        sections["HEADER"] = header_block

    return sections

def estimate_page_count(content):
    """Estimate page count for content"""
    # Rough estimation: 50 lines per page
    lines = content.split('\n')
    return max(1, len([line for line in lines if line.strip()]) // 50)

def trim_content_to_pages(content, max_pages=2):
    """Trim content to fit within page limit"""
    if estimate_page_count(content) <= max_pages:
        return content
    
    # Split into sections and prioritize
    sections = parse_cv_sections(content)
    
    # Priority order for sections
    priority_order = [
        "Professional Summary",
        "Key Skills",
        "Work Experience",
        "Education",
        "Certifications",
        "Projects",
        "Awards",
        "Languages",
        "Hobbies"
    ]
    
    # Rebuild content with priority sections
    rebuilt_content = []
    
    for section_name in priority_order:
        for key, value in sections.items():
            if section_name.lower() in key.lower():
                rebuilt_content.append(key)
                rebuilt_content.extend(value)
                break
    
    return '\n'.join(rebuilt_content)

def estimate_total_lines(sections):
    """Estimate total rendered lines based on content length"""
    total_lines = 0
    for section_content in sections.values():
        total_lines += len([line for line in section_content if line.strip()])
    return total_lines

def trim_sections_to_fit(sections, max_lines=100):
    """Trim content from long sections (like Projects or Work Experience) to fit page limit"""
    total_lines = estimate_total_lines(sections)

    if total_lines <= max_lines:
        return sections  # Already within limit

    # Priority list for trimming (most trim first)
    trim_order = ["Projects", "Work Experience", "Certifications", "Awards", "Languages", "Hobbies"]
    
    for section_key in trim_order:
        for key in list(sections.keys()):
            if section_key.lower() in key.lower():
                original = sections[key]
                if len(original) > 4:  # Only trim if content is long enough
                    trimmed = original[:len(original) - 2]  # Trim 2 lines
                    sections[key] = trimmed
                    total_lines = estimate_total_lines(sections)
                    if total_lines <= max_lines:
                        return sections  # Trimmed enough
    
    return sections  # Return best possible under max_lines

