"""
Discovery Mode Prompts - GPT-5 Optimized
Version: 1.0.0
Date: August 2025

These prompts are specifically crafted for GPT-5's enhanced reasoning capabilities,
emphasizing chain-of-thought analysis and strict JSON output requirements.
"""

# Programmatic version tag for logs/metrics
PROMPT_VERSION = "1.0.0"

# Discovery Mode prompt dictionary - GPT-5 optimized
DECONSTRUCTION_KEYS_PROMPTS = {
    "positioning_themes": {
        "name": "Positioning Themes",
        "prompt": """You are a senior market strategist. Your task is to analyze the provided website text to synthesize the brand's core **Positioning Themes**. A theme is a high-level concept the brand is trying to own (e.g., "Effortless Simplicity," "Rugged Durability," "Pioneering Innovation").

Follow this four-step process:
1. **Step 1 (Concept Extraction):** Read through all the content and identify the most repeated concepts, keywords, and value propositions.
2. **Step 2 (Theme Synthesis):** Group the extracted concepts into 3-5 high-level strategic themes. For example, "fast," "easy," and "intuitive" might synthesize into a theme of "Effortless Simplicity."
3. **Step 3 (Evidence Gathering):** For each synthesized theme, find two distinct, direct quotes from the text that serve as the strongest evidence.
4. **Step 4 (Final Output):** Assemble the results into the required JSON format.

Your final output MUST be a JSON object containing a list of the top 3-5 themes, structured as follows:
{{
  "themes": [
    {{
      "theme": "Effortless Simplicity",
      "description": "A one-sentence explanation of what this theme means for the brand",
      "evidence_quotes": [
        "Direct quote 1 supporting the theme",
        "Direct quote 2 supporting the theme"
      ],
      "confidence": 85
    }}
  ]
}}

TEXT CONTENT:
{text_content}

Analyze the content and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["themes"],
            "properties": {
                "themes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["theme", "description", "evidence_quotes", "confidence"],
                        "properties": {
                            "theme": {"type": "string", "minLength": 1, "maxLength": 50},
                            "description": {"type": "string", "minLength": 1, "maxLength": 200},
                            "evidence_quotes": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "minItems": 1,
                                "maxItems": 3
                            },
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                        }
                    },
                    "minItems": 1,
                    "maxItems": 5
                }
            }
        }
    },
    
    "key_messages": {
        "name": "Key Messages",
        "prompt": """You are a senior copywriter and brand messaging analyst. Your task is to identify the most prominent and strategically important **Key Messages** from the provided website text.

For each message you identify, you must perform two distinct tasks:
1. **Extract the Core Message:** Isolate the exact tagline, slogan, or value proposition statement. **Keep it under 200 characters and as concise as possible.**
2. **Extract the Strategic Context:** Provide the surrounding sentence or short paragraph that gives the message its meaning. **Crucially, the context must NOT contain the core message itself.**

Classify each message as either a "Tagline" (a short, memorable slogan) or a "Value Proposition" (a statement of benefit).

Your final output MUST be a JSON object structured as follows:
{{
  "key_messages": [
    {{
      "message": "Reinventing essentials for sustainable living",
      "context": "To meet the challenges of tomorrow, we are transforming our portfolio, our operations, and our mindset.",
      "type": "Tagline",
      "confidence": 90
    }}
  ]
}}

TEXT CONTENT:
{text_content}

Analyze the content and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["key_messages"],
            "properties": {
                "key_messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["message", "context", "type", "confidence"],
                        "properties": {
                            "message": {"type": "string", "minLength": 1, "maxLength": 200},
                            "context": {"type": "string", "minLength": 1, "maxLength": 300},
                            "type": {"type": "string", "enum": ["Tagline", "Value Proposition"]},
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
                        }
                    },
                    "minItems": 1,
                    "maxItems": 5
                }
            }
        }
    },
    
    "tone_of_voice": {
        "name": "Tone of Voice",
        "prompt": """You are an expert in brand voice and communication strategy. Your task is to analyze the provided website text to define the brand's **Tone of Voice**.

Follow this step-by-step analysis:
1. **Identify the Primary Tone:** Determine the single, most dominant personality trait of the communication (e.g., "Authoritative," "Playful," "Empathetic").
2. **Identify the Secondary Tone:** Determine a complementary trait that adds nuance (e.g., "Optimistic," "Witty," "Reassuring").
3. **Find Evidence:** For both the primary and secondary tones, find the single best direct quote from the text that exemplifies it.
4. **Check for Contradictions:** Scan the text for any moments where the tone feels inconsistent with the primary/secondary traits you identified.

Your final output MUST be a JSON object structured as follows:
{{
  "primary_tone": {{
    "tone": "Authoritative",
    "justification": "Why you chose this tone",
    "evidence_quote": "A direct quote that perfectly exemplifies this tone"
  }},
  "secondary_tone": {{
    "tone": "Optimistic",
    "justification": "Why you chose this tone",
    "evidence_quote": "A direct quote that perfectly exemplifies this tone"
  }},
  "contradictions": [
    {{
      "contradiction": "Describe a moment where the tone felt inconsistent",
      "evidence_quote": "A direct quote showing the inconsistency"
    }}
  ],
  "confidence": 85
}}

TEXT CONTENT:
{text_content}

Analyze the content and output ONLY the JSON structure above.

IMPORTANT:
- Always include an `evidence_quote` of **5–25 words**, **copied verbatim** from the provided snippets for BOTH primary and secondary tones. If no short quote fits, choose the shortest complete sentence from the snippets. Do **not** leave it blank.
""",
        "schema": {
            "type": "object",
            "required": ["primary_tone", "secondary_tone", "confidence"],
            "properties": {
                "primary_tone": {
                    "type": "object",
                    "required": ["tone", "justification", "evidence_quote"],
                    "properties": {
                        "tone": {"type": "string", "minLength": 1, "maxLength": 30},
                        "justification": {"type": "string", "minLength": 1, "maxLength": 200},
                        "evidence_quote": {"type": "string", "minLength": 1}
                    }
                },
                "secondary_tone": {
                    "type": "object",
                    "required": ["tone", "justification", "evidence_quote"],
                    "properties": {
                        "tone": {"type": "string", "minLength": 1, "maxLength": 30},
                        "justification": {"type": "string", "minLength": 1, "maxLength": 200},
                        "evidence_quote": {"type": "string", "minLength": 1}
                    }
                },
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["contradiction", "evidence_quote"],
                        "properties": {
                            "contradiction": {"type": "string", "minLength": 1, "maxLength": 200},
                            "evidence_quote": {"type": "string", "minLength": 1}
                        }
                    },
                    "maxItems": 3
                },
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
            }
        }
    },
    
    "brand_elements": {
        "name": "Brand Elements",
        "prompt": """You are a world-class brand identity consultant. Your goal is to conduct a holistic audit of the brand's identity, synthesizing insights from the provided **website screenshots** and **text corpus**. Your focus is on **coherence and strategic alignment**.

Follow this three-step reasoning process:
1. **Step 1 (Visual Hypothesis):** Analyze the screenshots *first*. Form a preliminary hypothesis about the brand's personality, tone, and values based only on the visual evidence (colors, fonts, imagery).
2. **Step 2 (Verbal Analysis):** Analyze the text corpus to understand the brand's explicitly stated values, tone, and key messages.
3. **Step 3 (Synthesize & Critique):** Compare your visual hypothesis from Step 1 with your verbal analysis from Step 2. Identify points of **harmony** (where the visuals perfectly support the text) and **dissonance** (where they contradict or miss an opportunity).

Based on this synthesis, your final output MUST be a JSON object with the following structure. **IMPORTANT: coherence_score must be 1-5 only:**
{{
  "overall_impression": {{
    "summary": "A brief summary of the visual feel and personality",
    "keywords": ["Keyword1", "Keyword2", "Keyword3"]
  }},
  "coherence_score": 4,
  "visual_identity": {{
    "color_palette": {{ "description": "Describe the primary/secondary colors and their psychological impact", "consistency_notes": "Are they used consistently?" }},
    "typography": {{ "description": "Describe the font styles and their personality", "consistency_notes": "Is the hierarchy clear and consistent?" }},
    "imagery_style": {{ "description": "Describe the dominant style of photos/illustrations", "consistency_notes": "Is the style consistent across pages?" }}
  }},
  "strategic_alignment": {{
    "harmony": "Describe one key way the visual and verbal identities work together perfectly, citing evidence from both the image and text.",
    "dissonance": "Describe one key area where the visuals and verbals seem to contradict each other. State 'None observed' if no significant contradictions exist."
  }},
  "confidence": 75
}}

SCREENSHOTS AND TEXT:
{screenshot_context}

Analyze the visual identity and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["overall_impression", "coherence_score", "visual_identity", "strategic_alignment", "confidence"],
            "properties": {
                "overall_impression": {
                    "type": "object",
                    "required": ["summary", "keywords"],
                    "properties": {
                        "summary": {"type": "string", "minLength": 1, "maxLength": 300},
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 5
                        }
                    }
                },
                "coherence_score": {"type": "integer", "minimum": 1, "maximum": 5},
                "visual_identity": {
                    "type": "object",
                    "required": ["color_palette", "typography", "imagery_style"],
                    "properties": {
                        "color_palette": {
                            "type": "object",
                            "required": ["description", "consistency_notes"],
                            "properties": {
                                "description": {"type": "string", "minLength": 1, "maxLength": 300},
                                "consistency_notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        },
                        "typography": {
                            "type": "object",
                            "required": ["description", "consistency_notes"],
                            "properties": {
                                "description": {"type": "string", "minLength": 1, "maxLength": 300},
                                "consistency_notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        },
                        "imagery_style": {
                            "type": "object",
                            "required": ["description", "consistency_notes"],
                            "properties": {
                                "description": {"type": "string", "minLength": 1, "maxLength": 300},
                                "consistency_notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        }
                    }
                },
                "strategic_alignment": {
                    "type": "object",
                    "required": ["harmony", "dissonance"],
                    "properties": {
                        "harmony": {"type": "string", "minLength": 1, "maxLength": 400},
                        "dissonance": {"type": "string", "minLength": 1, "maxLength": 400}
                    }
                },
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
            }
        }
    },
    
    "visual_text_alignment": {
        "name": "Visual-Text Alignment",
        "prompt": """You are a senior brand strategist evaluating brand consistency.

CONTEXT: You've completed analysis of a brand's text-based positioning themes and visual brand elements. Now assess whether they align strategically.

PROVIDED ANALYSIS:
Positioning Themes: {positioning_themes}
Brand Elements: {brand_elements}

TASK: Determine if the visual identity supports and reinforces the strategic positioning.

REQUIREMENTS:
- Answer "Yes" if visuals and messaging are strategically aligned
- Answer "No" if there's a significant disconnect
- Provide a brief (1-2 sentence) strategic justification

OUTPUT FORMAT (JSON only, no other text):
{{
  "alignment": "Yes",
  "justification": "The minimalist visual design directly reinforces the innovation and simplicity themes found in the messaging"
}}

Analyze the alignment and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["alignment", "justification"],
            "properties": {
                "alignment": {"type": "string", "enum": ["Yes", "No"]},
                "justification": {"type": "string", "minLength": 1, "maxLength": 1000}
            }
        }
    }
}

# Performance monitoring decorator for GPT-5 calls
def track_discovery_performance(key_name):
    """Decorator to track token usage and latency for each Discovery key."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()
            
            result = func(*args, **kwargs)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract token usage from tuple return format (analysis_result, metrics)
            token_usage = 0
            if isinstance(result, tuple) and len(result) == 2:
                analysis_result, metrics = result
                token_usage = metrics.get("token_usage", 0)
            elif isinstance(result, dict):
                token_usage = result.get("token_usage", 0)
            
            # Log performance metrics (use print if log not available)
            try:
                from scanner import log
                log("info", f"Discovery key '{key_name}' completed")
                print(f"[INFO] ✅ Configuration validation passed")
                print(f"[INFO] Discovery key '{key_name}' completed")
                print(f"[DETAILS] {{")
                print(f'  "key_name": "{key_name}",')
                print(f'  "latency_ms": {latency_ms},')
                print(f'  "model": "gpt-5",')
                print(f'  "tokens": {token_usage}')
                print(f"}}")
            except ImportError:
                print(f"[INFO] Discovery key '{key_name}' completed")
                print(f"[DETAILS] {{")
                print(f'  "key_name": "{key_name}",')
                print(f'  "latency_ms": {latency_ms},')
                print(f'  "model": "gpt-5",')
                print(f'  "tokens": {token_usage}')
                print(f"}}")
            
            return result
        return wrapper
    return decorator