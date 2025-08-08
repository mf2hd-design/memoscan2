"""
Discovery Mode Prompts - GPT-5 Optimized
Version: 1.0.0
Date: August 2025

These prompts are specifically crafted for GPT-5's enhanced reasoning capabilities,
emphasizing chain-of-thought analysis and strict JSON output requirements.
"""

# Discovery Mode prompt dictionary - GPT-5 optimized
DECONSTRUCTION_KEYS_PROMPTS = {
    "positioning_themes": {
        "name": "Positioning Themes",
        "prompt": """You are a senior brand strategist analyzing a website's strategic positioning.

CONTEXT: You've been provided with text content from a brand's website. Your task is to identify the core positioning themes - the fundamental strategic pillars that define what this brand stands for.

PROCESS:
1. Read through all content carefully
2. Identify recurring strategic themes and messages
3. Select the 3-5 most prominent and important themes
4. For each theme, find the strongest verbatim evidence from the text

REQUIREMENTS:
- Each theme should be a short, descriptive phrase (2-5 words)
- Confidence scores must reflect the strength and frequency of evidence (0-100)
- Evidence MUST be exact quotes from the provided text - no paraphrasing
- Think strategically - look for themes that define the brand's market position

OUTPUT FORMAT (JSON only, no other text):
{
  "themes": [
    {
      "theme": "Innovation Leadership",
      "confidence": 85,
      "evidence": "We pioneer breakthrough technologies that reshape industries"
    }
  ]
}

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
                        "required": ["theme", "confidence", "evidence"],
                        "properties": {
                            "theme": {"type": "string", "minLength": 1, "maxLength": 50},
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                            "evidence": {"type": "string", "minLength": 1}
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
        "prompt": """You are a senior brand strategist analyzing a website's core messaging.

CONTEXT: You've been provided with text content from a brand's website. Your task is to extract the key messages - the primary value propositions and taglines that the brand repeatedly emphasizes.

PROCESS:
1. Scan for prominent headlines, taglines, and repeated phrases
2. Identify value propositions that appear multiple times or in prominent positions
3. Select the 3-5 most important and frequently communicated messages
4. Find the clearest instance of each message in the text

REQUIREMENTS:
- Messages should be actual taglines or value propositions (not generic descriptions)
- Confidence reflects how prominently and frequently the message appears (0-100)
- Evidence MUST be verbatim quotes - the exact wording as it appears
- Focus on messages that communicate specific value or differentiation

OUTPUT FORMAT (JSON only, no other text):
{
  "messages": [
    {
      "message": "Trusted by millions worldwide",
      "confidence": 90,
      "evidence": "Join the 50 million users who trust us with their data every day"
    }
  ]
}

TEXT CONTENT:
{text_content}

Analyze the content and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["messages"],
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["message", "confidence", "evidence"],
                        "properties": {
                            "message": {"type": "string", "minLength": 1, "maxLength": 100},
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                            "evidence": {"type": "string", "minLength": 1}
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
        "prompt": """You are a senior brand strategist analyzing a website's tone of voice.

CONTEXT: You've been provided with text content from a brand's website. Your task is to identify the key characteristics of how this brand communicates - its tone of voice.

PROCESS:
1. Analyze the language style, word choices, and communication patterns
2. Identify 3-4 adjectives that best describe the brand's tone
3. For each adjective, explain why it applies
4. Find specific textual evidence that demonstrates this tone

REQUIREMENTS:
- Use single, precise adjectives (e.g., "Authoritative", "Playful", "Empathetic")
- Justifications should be brief (1-2 sentences) but insightful
- Confidence reflects how consistently this tone appears (0-100)
- Evidence MUST be exact quotes that exemplify the tone

OUTPUT FORMAT (JSON only, no other text):
{
  "tone_descriptors": [
    {
      "adjective": "Confident",
      "justification": "The brand uses definitive statements and positions itself as a leader",
      "confidence": 85,
      "evidence": "We don't just follow trends, we set them"
    }
  ]
}

TEXT CONTENT:
{text_content}

Analyze the content and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["tone_descriptors"],
            "properties": {
                "tone_descriptors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["adjective", "justification", "confidence", "evidence"],
                        "properties": {
                            "adjective": {"type": "string", "minLength": 1, "maxLength": 30},
                            "justification": {"type": "string", "minLength": 1, "maxLength": 200},
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                            "evidence": {"type": "string", "minLength": 1}
                        }
                    },
                    "minItems": 1,
                    "maxItems": 4
                }
            }
        }
    },
    
    "brand_elements": {
        "name": "Brand Elements",
        "prompt": """You are a senior brand strategist with expertise in visual identity systems.

CONTEXT: You've been provided with screenshots and text from a brand's website. Your task is to analyze the coherence and effectiveness of the brand's visual identity.

PROCESS:
1. Review all screenshots to form an overall visual impression
2. Analyze color consistency, typography, imagery style, and brand architecture
3. Evaluate how well these elements work together (coherence score)
4. Assess strategic alignment with the brand's messaging
5. Identify specific visual evidence

REQUIREMENTS:
- Overall impression should capture the visual essence in 2-3 sentences
- Coherence score: 1 (very inconsistent) to 5 (perfectly cohesive)
- Consistency ratings: "High", "Medium", or "Low" for each element
- Notes should be specific observations, not generic comments
- Evidence should reference specific visual elements you can see

OUTPUT FORMAT (JSON only, no other text):
{
  "overall_impression": {
    "summary": "A modern, minimalist visual identity with strong tech sector positioning",
    "keywords": ["Modern", "Minimalist", "Tech-forward"]
  },
  "coherence_score": 4,
  "detailed_analysis": {
    "color_palette": {
      "consistency": "High",
      "notes": "Consistent use of deep blue (#003366) with orange accents throughout"
    },
    "typography": {
      "consistency": "Medium",
      "notes": "Sans-serif headers consistent, but body text varies between pages"
    },
    "imagery": {
      "consistency": "High",
      "notes": "Cohesive use of abstract geometric patterns and professional photography"
    },
    "brand_architecture": {
      "consistency": "High",
      "notes": "Clear visual hierarchy with consistent logo placement and navigation structure"
    }
  },
  "strategic_alignment": "Visual identity strongly reinforces the innovation and trust positioning through clean, professional design",
  "confidence": 75,
  "evidence": "Homepage hero uses the primary blue (#003366) with geometric patterns visible in screenshots 1-3"
}

SCREENSHOTS AND TEXT:
{screenshot_context}

Analyze the visual identity and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["overall_impression", "coherence_score", "detailed_analysis", "strategic_alignment", "confidence", "evidence"],
            "properties": {
                "overall_impression": {
                    "type": "object",
                    "required": ["summary", "keywords"],
                    "properties": {
                        "summary": {"type": "string", "minLength": 1, "maxLength": 200},
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 5
                        }
                    }
                },
                "coherence_score": {"type": "integer", "minimum": 1, "maximum": 5},
                "detailed_analysis": {
                    "type": "object",
                    "required": ["color_palette", "typography", "imagery", "brand_architecture"],
                    "properties": {
                        "color_palette": {
                            "type": "object",
                            "required": ["consistency", "notes"],
                            "properties": {
                                "consistency": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                "notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        },
                        "typography": {
                            "type": "object",
                            "required": ["consistency", "notes"],
                            "properties": {
                                "consistency": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                "notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        },
                        "imagery": {
                            "type": "object",
                            "required": ["consistency", "notes"],
                            "properties": {
                                "consistency": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                "notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        },
                        "brand_architecture": {
                            "type": "object",
                            "required": ["consistency", "notes"],
                            "properties": {
                                "consistency": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                "notes": {"type": "string", "minLength": 1, "maxLength": 200}
                            }
                        }
                    }
                },
                "strategic_alignment": {"type": "string", "minLength": 1, "maxLength": 300},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "evidence": {"type": "string", "minLength": 1}
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
{
  "alignment": "Yes",
  "justification": "The minimalist visual design directly reinforces the innovation and simplicity themes found in the messaging"
}

Analyze the alignment and output ONLY the JSON structure above.""",
        "schema": {
            "type": "object",
            "required": ["alignment", "justification"],
            "properties": {
                "alignment": {"type": "string", "enum": ["Yes", "No"]},
                "justification": {"type": "string", "minLength": 1, "maxLength": 200}
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
            
            # Log performance metrics
            log("info", f"Discovery key '{key_name}' completed", {
                "key_name": key_name,
                "latency_ms": latency_ms,
                "model": "gpt-5",
                "tokens": result.get("token_usage", 0) if isinstance(result, dict) else 0
            })
            
            return result
        return wrapper
    return decorator