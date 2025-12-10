#!/bin/bash

# Backup the original
cp prompts.py prompts.py.backup

# Create a Python script to properly inject length limits into ALL 7 prompts
python3 << 'PYEOF'
import re

with open('prompts.py', 'r') as f:
    content = f.read()

# Define the length constraint that will be added to EVERY prompt
length_limit = '''
**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total (approximately 1,000-1,300 words)
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently
'''

# Find all prompt methods and add length limit after the opening "Act as..." sentence
# Pattern: finds return f"""Act as [role]... Then looks for the first newline after period
methods = [
    'brand_audit',
    'meeting_brief', 
    'industry_profile',
    'brand_house',
    'four_cs_analysis',
    'competitive_landscape',
    'audience_profile'
]

for method in methods:
    # Find the method definition
    pattern = rf'def {method}\([^)]+\) -> str:.*?return f"""(.*?)"""'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        prompt_content = match.group(1)
        
        # Check if length limit already exists
        if 'CRITICAL LENGTH REQUIREMENT' in prompt_content:
            print(f"⚠️  {method} already has length limit")
            continue
            
        # Find the first newline after "Act as..." sentence
        first_line_end = prompt_content.find('\n', 0)
        
        if first_line_end != -1:
            # Insert length limit after first line
            new_prompt = prompt_content[:first_line_end+1] + length_limit + prompt_content[first_line_end+1:]
            
            # Replace in content
            old_full = f'return f"""{prompt_content}"""'
            new_full = f'return f"""{new_prompt}"""'
            content = content.replace(old_full, new_full)
            print(f"✅ Added length limit to {method}")
        else:
            print(f"❌ Could not process {method}")
    else:
        print(f"❌ Could not find {method}")

# Write updated content
with open('prompts.py', 'w') as f:
    f.write(content)

print("\n✅ All prompts updated!")
PYEOF

echo "Done! Check prompts.py"
