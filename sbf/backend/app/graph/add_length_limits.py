"""
Script to add 8K character length limits to all 7 report prompts
"""

length_constraint = """
**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently

"""

# Read the prompts file
with open('prompts.py', 'r') as f:
    content = f.read()

# Add length constraint after each "Act as" opening line for all 7 reports
prompts_to_fix = [
    ('Act as a Senior Strategy Consultant. Perform a comprehensive Brand Audit', 'brand_audit'),
    ('Act as an Executive Briefing Specialist. Create a comprehensive Meeting Brief', 'meeting_brief'),
    ('Act as an Industry Analyst. Create a comprehensive Industry Profile', 'industry_profile'),
    ('Act as a Brand Strategist. Create a Brand House Strategy', 'brand_house'),
    ('Act as a Strategic Planner. Conduct a deep-dive "Four C\'s" Analysis', 'four_cs'),
    ('Act as a Competitive Intelligence Analyst. Create a Competitive Landscape Map', 'competitive_landscape'),
    ('Act as a Consumer Insights Analyst. Create a comprehensive Audience Profile', 'audience_profile')
]

for search_text, report_name in prompts_to_fix:
    if search_text in content:
        # Find the position after the opening sentence
        pos = content.find(search_text)
        if pos != -1:
            # Find the end of the sentence (period followed by newline)
            end_pos = content.find('.', pos) + 1
            # Find the next newline
            newline_pos = content.find('\n', end_pos)
            
            # Insert the length constraint
            before = content[:newline_pos + 1]
            after = content[newline_pos + 1:]
            content = before + length_constraint + after
            print(f"✓ Added length limit to {report_name}")
    else:
        print(f"✗ Could not find {report_name}")

# Write the updated content
with open('prompts.py', 'w') as f:
    f.write(content)

print("\n✅ All 7 prompts updated with 8K character limits")
