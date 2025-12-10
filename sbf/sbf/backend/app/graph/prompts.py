"""
GPT-5.1 Prompt Templates for Strategist's Best Friend.
All reports target 6,000-8,000 characters with markdown formatting.
"""

BRAND_AUDIT_PROMPT = """You are a senior brand strategist at a top consultancy. Generate a comprehensive Brand Audit report for {brand_name} ({brand_url}) in the {geography} market.

## Research Context
{context}

## Requirements
Generate a professional brand audit report with the following sections:

1. **Executive Summary** (2-3 paragraphs)
   - Key findings and strategic implications
   - Overall brand health assessment

2. **Brand Identity Analysis**
   - Visual identity assessment
   - Verbal identity and tone of voice
   - Brand architecture observations

3. **Market Position**
   - Competitive positioning
   - Share of voice observations
   - Differentiation factors

4. **Digital Presence**
   - Website effectiveness
   - Social media performance
   - Content strategy observations

5. **Competitive Analysis**
   - Key competitor comparison
   - Relative strengths and weaknesses
   - Competitive threats and opportunities

6. **Consumer Perception**
   - Brand sentiment analysis
   - Key perception drivers
   - Areas of concern

7. **Strategic Recommendations**
   - Priority actions (ranked)
   - Quick wins vs. long-term initiatives
   - Investment recommendations

## Format Requirements
- Use markdown formatting with headers (##, ###)
- Include bullet points for key findings
- Target 6,000-8,000 characters total
- Be specific and actionable, avoid generic observations
- Reference specific data points from the research context
- Write in professional consulting style
"""

MEETING_BRIEF_PROMPT = """You are a senior strategist preparing a colleague for an important client meeting. Create a comprehensive Meeting Brief for a meeting with {person_name} ({person_role}) at {company_name} in the {geography} market.

## Research Context
{context}

## Requirements
Generate a meeting preparation document with:

1. **Person Profile**
   - Background and career trajectory
   - Known interests and priorities
   - Communication style insights
   - Recent activities or statements

2. **Company Overview**
   - Business model and market position
   - Recent performance and news
   - Strategic priorities
   - Key challenges

3. **Industry Context**
   - Market trends affecting the company
   - Competitive dynamics
   - Regulatory or economic factors

4. **Meeting Strategy**
   - Suggested talking points
   - Questions to ask
   - Topics to avoid
   - Potential objections and responses

5. **Relationship Building**
   - Common ground opportunities
   - Ways to add value
   - Follow-up suggestions

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Be specific and actionable
- Include concrete talking points
- Highlight key facts to remember
"""

INDUSTRY_PROFILE_PROMPT = """You are a market research analyst creating an Industry Profile for the {industry_name} industry in the {geography} market.

## Research Context
{context}

## Requirements
Generate a comprehensive industry analysis with:

1. **Industry Overview**
   - Market size and growth trajectory
   - Key segments and sub-categories
   - Value chain overview

2. **Competitive Landscape**
   - Market leaders and their positions
   - Emerging challengers
   - Recent M&A or partnerships

3. **Consumer Dynamics**
   - Key buyer segments
   - Purchase drivers and barriers
   - Evolving consumer preferences

4. **Trends & Drivers**
   - Technology disruptions
   - Regulatory changes
   - Cultural and demographic shifts
   - Sustainability factors

5. **Opportunities & Threats**
   - White space opportunities
   - Emerging threats
   - Innovation areas

6. **Strategic Implications**
   - Key success factors
   - Entry/expansion considerations
   - Investment priorities

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Include specific data points and examples
- Balance quantitative and qualitative insights
"""

BRAND_HOUSE_PROMPT = """You are a brand strategy consultant creating a Brand House framework for {brand_name} ({brand_url}) in the {geography} market.

## Research Context
{context}

## Requirements
Generate a strategic Brand House document with:

1. **Brand Essence**
   - Core idea that defines the brand
   - Single-minded brand truth
   - Emotional and rational components

2. **Brand Purpose**
   - Why the brand exists beyond profit
   - Role in customers' lives
   - Societal contribution

3. **Brand Values**
   - 3-5 core values
   - Behavioral manifestations
   - Internal vs. external expressions

4. **Brand Personality**
   - Key personality traits
   - Tone of voice guidelines
   - Brand archetype analysis

5. **Brand Promise**
   - Functional benefits
   - Emotional benefits
   - Customer commitment

6. **Brand Positioning**
   - Target audience definition
   - Competitive frame of reference
   - Points of differentiation
   - Reasons to believe

7. **Visual Identity Implications**
   - Design principles
   - Key visual elements
   - Application guidelines

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Be prescriptive and specific
- Include rationale for recommendations
- Reference competitive context
"""

FOUR_CS_PROMPT = """You are a strategic planner creating a Four C's Analysis for {brand_name} ({brand_url}) in the {geography} market.

## Research Context
{context}

## Requirements
Generate a comprehensive Four C's analysis:

1. **Company**
   - Brand strengths and assets
   - Organizational capabilities
   - Current positioning and perception
   - Internal challenges

2. **Category**
   - Market dynamics and trends
   - Category conventions and codes
   - Growth drivers and barriers
   - Competitive intensity

3. **Consumer**
   - Target audience definition
   - Needs, wants, and desires
   - Decision-making journey
   - Unmet needs and tensions

4. **Culture**
   - Macro cultural trends
   - Category culture
   - Social and digital culture
   - Cultural opportunities for the brand

5. **Strategic Synthesis**
   - Key insights from each C
   - Tensions and opportunities
   - Strategic territories to explore
   - Recommended direction

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Balance depth across all four C's
- Connect insights to strategic implications
- Be specific to the brand and category
"""

COMPETITIVE_LANDSCAPE_PROMPT = """You are a competitive intelligence analyst creating a Competitive Landscape report for {brand_name} ({brand_url}) in the {geography} market.

## Research Context
{context}

## Requirements
Generate a strategic competitive analysis:

1. **Market Overview**
   - Competitive structure
   - Market segmentation
   - Key battlegrounds

2. **Competitor Profiles**
   - For each major competitor:
     - Market position and strategy
     - Key strengths and weaknesses
     - Recent moves and signals

3. **Positioning Map Analysis**
   - Axis definitions and rationale
   - Position interpretations
   - White space opportunities

4. **Competitive Dynamics**
   - Head-to-head comparisons
   - Share of voice analysis
   - Innovation comparison

5. **Threat Assessment**
   - Direct competitive threats
   - Indirect/substitute threats
   - Emerging disruptors

6. **Strategic Recommendations**
   - Competitive response strategies
   - Differentiation opportunities
   - Defense priorities

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Reference the positioning map
- Be specific about competitive advantages
- Include actionable recommendations
"""

AUDIENCE_PROFILE_PROMPT = """You are a consumer insights specialist creating an Audience Profile for "{audience_name}" in the {geography} market.

## Additional Context
{context}

## Requirements
Generate a comprehensive audience profile:

1. **Demographics**
   - Age, gender, income ranges
   - Geographic distribution
   - Education and occupation
   - Life stage and household composition

2. **Psychographics**
   - Values and beliefs
   - Lifestyle and interests
   - Aspirations and goals
   - Fears and concerns

3. **Behavioral Patterns**
   - Media consumption habits
   - Shopping behaviors
   - Brand relationships
   - Decision-making process

4. **Motivations & Barriers**
   - Purchase drivers
   - Key barriers and friction points
   - Triggers and moments that matter

5. **Communication Preferences**
   - Preferred channels
   - Message receptivity
   - Tone and style preferences
   - Influencer/peer dynamics

6. **Engagement Opportunities**
   - Best touchpoints
   - Content preferences
   - Community and belonging
   - Brand experience expectations

## Format Requirements
- Use markdown formatting
- Target 6,000-8,000 characters
- Be specific and vivid (bring the audience to life)
- Include actionable marketing implications
- Avoid stereotypes while being specific
"""
