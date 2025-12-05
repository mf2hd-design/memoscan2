"""
GPT-5.1 prompt templates for all report types.
These templates follow the exact structures provided by the user.
"""


class PromptTemplates:
    """Collection of prompt templates for different report types."""

    @staticmethod
    def brand_audit(
        brand_name: str,
        brand_site_content: str,
        twitter_sentiment: str,
        reddit_sentiment: str,
        instagram_sentiment: str,
        facebook_sentiment: str,
        competitor_data: str,
        news_mentions: str,
        pdf_context: str = ""
    ) -> str:
        """Brand Audit prompt template."""
        return f"""Act as a Senior Strategy Consultant. Perform a comprehensive Brand Audit for {brand_name}.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently


CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN section headers: Executive Summary, Owned Space, Recent Developments, Product Portfolio, Brand Social Sentiment, Brand Website & Creative, Competitor & Industry Audit, Audience Identification, Audience Competitor Interactions, Messaging & Engagement
- Use ## (H2) for subsection headers: Strategic Tensions, Positive Themes, Negative Themes, Key Emotions, Tone of Voice, Key Messages, Industry Trends, Category Social Trends, Competitive Positioning, Current Audiences, Aspirational Audiences, etc.
- Use bullet points (-) for all lists
- Use **bold** for emphasis on key terms, brand names, and important findings
- Use tables for competitive comparisons and messaging frameworks
- Add blank lines between sections for readability
- Keep paragraphs concise (2-3 sentences max)
- For citations, use markdown link syntax: [Source](URL) to make them clickable
- Use > blockquotes for key insights or strategic recommendations

REQUIRED SECTIONS (in this exact order):

# Executive Summary

## Strategic Tensions

[Identify 3 key strategic tensions facing the brand:]

### Tension 1: [Name] (e.g., Innovation vs. Transparency)
- **Consumer Truth:** [What consumers want/expect]
- **Brand Truth:** [Current brand reality/position]
- **Manifestation:** [Strategic recommendation to resolve this tension]

### Tension 2: [Name]
- **Consumer Truth:** [What consumers want/expect]
- **Brand Truth:** [Current brand reality/position]
- **Manifestation:** [Strategic recommendation to resolve this tension]

### Tension 3: [Name]
- **Consumer Truth:** [What consumers want/expect]
- **Brand Truth:** [Current brand reality/position]
- **Manifestation:** [Strategic recommendation to resolve this tension]

---

# Owned Space

[What is the brand currently doing well?]
- **[Strength Area]:** [Description and evidence]
- **[Strength Area]:** [Description and evidence]

Examples: Global Reach, Employee Satisfaction, Market Leadership, Innovation Reputation

---

# Recent Developments

[New deals, acquisitions, partnerships, or strategic initiatives:]
- **[Date/Timeframe]:** [Development description] [Citation]
- **[Date/Timeframe]:** [Development description] [Citation]

---

# Product Portfolio

## Core Products & Services

[List main products/services with proof points:]
- **[Product/Service Name]:** [Key features, market position, differentiators]
- **[Product/Service Name]:** [Key features, market position, differentiators]

---

# Brand Social Sentiment

## Positive Themes
[Key positive themes from social media across platforms:]
- **[Theme]:** [Description and examples from Twitter, Reddit, Instagram, Facebook]
- **[Theme]:** [Description and examples]

## Negative Themes
[Key criticism or concerns from social media:]
- **[Theme]:** [Description and examples from Twitter, Reddit, Instagram, Facebook]
- **[Theme]:** [Description and examples]

## Key Emotions
[Dominant emotional responses to the brand:]
- **[Emotion]:** [Context and prevalence]
- **[Emotion]:** [Context and prevalence]

Examples: Trust, Skepticism, Excitement, Frustration, Loyalty

---

# Brand Website & Creative

## Tone of Voice
[Analysis of brand communication style:]
- [Characteristic 1]
- [Characteristic 2]

## Key Messages
[Primary messages the brand communicates:]
- **[Message Theme]:** [Description and examples]
- **[Message Theme]:** [Description and examples]

## Emotional Appeal
[Emotions the brand evokes through creative:]
- [Emotion 1 and how it's conveyed]
- [Emotion 2 and how it's conveyed]

---

# Competitor & Industry Audit

## Industry Trends
[Major trends shaping the vertical:]
- **[Trend]:** [Description and implications for {brand_name}]
- **[Trend]:** [Description and implications for {brand_name}]

Examples: Gen AI Adoption, Nearshoring, Sustainability Demands, Digital Transformation

## Category Social Trends
[What consumers are saying about the industry in general:]
- **[Trend/Topic]:** [Consumer sentiment and discussion themes]
- **[Trend/Topic]:** [Consumer sentiment and discussion themes]

## Competitive Positioning

| Brand | Market Position | Key Strengths | Differentiation |
|-------|----------------|---------------|-----------------|
| **{brand_name}** | [Leading/Emergent/Challenger] | [List 2-3 strengths] | [Primary differentiator] |
| **[Competitor 1]** | [Leading/Emergent/Challenger] | [List 2-3 strengths] | [Primary differentiator] |
| **[Competitor 2]** | [Leading/Emergent/Challenger] | [List 2-3 strengths] | [Primary differentiator] |
| **[Competitor 3]** | [Leading/Emergent/Challenger] | [List 2-3 strengths] | [Primary differentiator] |

---

# Audience Identification

## Current Target Audiences
[Who the brand currently serves:]
- **[Audience Segment]:** [Demographics, psychographics, needs]
- **[Audience Segment]:** [Demographics, psychographics, needs]

## Aspirational Audiences
[Who the brand should target:]
- **[Audience Segment]:** [Why this audience matters, opportunity size]
- **[Audience Segment]:** [Why this audience matters, opportunity size]

---

# Audience Competitor Interactions

[Where and how competitors win against this brand:]
- **[Competitor] wins with [Audience]:** [Reason and evidence]
- **[Competitor] wins with [Audience]:** [Reason and evidence]

---

# Messaging & Engagement

## Recommended Messaging Framework

| Audience Segment | Key Message | Engagement Tactics | Content Types |
|------------------|-------------|-------------------|---------------|
| [Segment 1] | [Tailored message] | [e.g., Webinars, LinkedIn] | [e.g., Whitepapers, Case Studies] |
| [Segment 2] | [Tailored message] | [e.g., Events, Podcasts] | [e.g., Videos, Infographics] |
| [Segment 3] | [Tailored message] | [e.g., Social ads, Email] | [e.g., eBooks, Templates] |

---

**Strategic Recommendations:** [1-2 sentence summary of top priority actions]

--- RESEARCH CONTEXT ---

## Brand Website Content
{brand_site_content}

## Social Media Sentiment

### Twitter
{twitter_sentiment}

### Reddit
{reddit_sentiment}

### Instagram
{instagram_sentiment}

### Facebook
{facebook_sentiment}

## Competitor Analysis
{competitor_data}

## Recent News
{news_mentions}

{f"## Uploaded Documents Context\\n{pdf_context}" if pdf_context else ""}

---

Now generate the comprehensive Brand Audit report following the exact structure and formatting requirements above. Use high-level consultancy language - strategic, critical, and actionable. Ensure every section has proper markdown formatting with clear visual hierarchy using H1 (#) for main sections and H2 (##) for subsections.
"""

    @staticmethod
    def meeting_brief(
        person_name: str,
        person_role: str,
        company_name: str,
        person_profile: str,
        company_data: str,
        recent_news: str,
        competitors: str,
        industry_trends: str
    ) -> str:
        """Meeting Brief prompt template."""
        return f"""Act as a Chief of Staff. Prepare a professional Meeting Brief for a meeting with {person_name}, {person_role} at {company_name}.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total (approximately 1,000-1,300 words)
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently

CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN section headers: About {person_name}, About {company_name}, Recent News & Developments, Competitive Landscape, Industry Trends, Strategic Talking Points
- Use ## (H2) for subsection headers: Current Role, Career Journey, Key Achievements, Personal Interests, Company Overview, Core Business, Innovation & Strategy, Top 5 Competitors, Icebreakers, Strategic Questions
- Use bullet points (-) for all lists
- Use **bold** for emphasis on key terms and labels
- Add blank lines between sections for readability
- Keep paragraphs concise (2-3 sentences max)
- CRITICAL: For ALL citations and sources, you MUST use the ACTUAL URLs provided in the research data below. Use markdown link syntax: [Article title](actual-url-from-data) to make links clickable. DO NOT use placeholder URLs like "#" or "URL" - use the real URLs from the research context.
- IMPORTANT: Today's date is December 2025. Only include news from 2024-2025 in the "Recent News & Developments" section. Ignore any news from 2023 or earlier as it is NOT recent.

REQUIRED SECTIONS (in this exact order):

# About {person_name}

## Current Role
- [Describe their current position, responsibilities, and focus areas]

## Career Journey
- [List previous companies and key leadership roles in reverse chronological order]

## Key Achievements
- [Specific wins, frameworks implemented, growth delivered, awards, recognition]

## Personal Interests
- [Hobbies, passions, causes they support - useful for icebreakers]

---

# About {company_name}

## Company Overview
- **Global Presence:** [Geographic footprint and scale]
- **Leadership:** [Key executives and organizational structure]
- **Revenue/Scale:** [Financial metrics if available]

## Core Business
- [Primary services, products, and capabilities]
- [Target markets and customer segments]

## Innovation & Strategy
- [Brand promise, strategic initiatives, differentiators]
- [Technology investments, R&D focus]

---

# Recent News & Developments

[List 3-5 RECENT newsworthy items from 2024-2025 ONLY. Use the news titles and URLs from the "Recent News Data" section below. Format as:]
- **[Month Year]:** [Brief summary of what happened] [Read more](actual-news-url-from-data)

CRITICAL: Use the ACTUAL URLs from the Recent News Data provided below. Do NOT make up or use placeholder URLs.

---

# Competitive Landscape

## Top 5 Competitors
1. **[Competitor Name]** - [Brief description of competitive positioning] [Source](URL)
2. **[Competitor Name]** - [Brief description of competitive positioning] [Source](URL)
3. **[Competitor Name]** - [Brief description of competitive positioning] [Source](URL)
4. **[Competitor Name]** - [Brief description of competitive positioning] [Source](URL)
5. **[Competitor Name]** - [Brief description of competitive positioning] [Source](URL)

---

# Industry Trends

[Highlight 3-4 key trends relevant to their business from 2024-2025:]
- **[Trend Name]:** [Impact and relevance to {company_name}] [Source](URL)
- **[Trend Name]:** [Impact and relevance to {company_name}] [Source](URL)
- **[Trend Name]:** [Impact and relevance to {company_name}] [Source](URL)

---

# Strategic Talking Points

## Icebreakers
1. [Personalized question based on their interests or recent achievements]
2. [Observation about company news or industry trend they care about]

## Strategic Questions
1. [Thoughtful question about their business strategy or challenges]
2. [Question connecting industry trends to their specific context]

---

**Goal:** Make the reader look smart, prepared, and genuinely interested in this meeting.

--- RESEARCH CONTEXT ---

## Person Profile Data
{person_profile}

## Company Data
{company_data}

## Recent News Data
{recent_news}

## Competitor Data
{competitors}

## Industry Trends Data
{industry_trends}

---

CRITICAL INSTRUCTIONS FOR USING URLS:
1. The "Recent News Data" section above contains news items with titles and URLs
2. You MUST extract the actual URLs from that data and use them in your citations
3. Format news items as: **[Date]:** [Summary] [Read more](actual-url-from-above)
4. Example of CORRECT formatting: **November 2024:** Company announces new product [Read more](https://example.com/article)
5. DO NOT use placeholder URLs like "#" or "(URL)" - extract and use the REAL URLs from the Recent News Data above
6. If a news item doesn't have a URL, skip the citation link entirely

Now generate the Meeting Brief following the exact structure and formatting requirements above. Use professional language, be concise, and ensure every section has proper markdown formatting with clear visual hierarchy and REAL clickable URLs from the research data.
"""

    @staticmethod
    def industry_profile(
        industry_name: str,
        geography: str,
        market_reports: str,
        trend_data: str,
        top_brands: str,
        emerging_brands: str,
        news_articles: str
    ) -> str:
        """Industry Profile prompt template."""
        return f"""Act as a Senior Market Research Analyst. Create a comprehensive Industry & Market Profile for {industry_name} in {geography}.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total (approximately 1,000-1,300 words)
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently

CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN section headers: Macro Trends, Market Challenges & Threats, Growth Opportunities, Industry Drivers, Consumer Mindset, Leading Brands, Emerging Brands, Sources
- Use ## (H2) for subsection headers when breaking down complex sections
- Use bullet points (-) for all lists
- Use **bold** for emphasis on key terms, brand names, and trend names
- Add blank lines between sections for readability
- Keep paragraphs concise (2-3 sentences max)
- For citations, use markdown link syntax: [Source name](URL) to make them clickable
- Use > blockquotes for notable statistics or quotes

REQUIRED SECTIONS (in this exact order):

# Macro Trends

[Identify 5-6 major industry shifts. For each trend:]
- **[Trend Name]:** [Description of the trend and its impact] [Citation if available]

Examples: Digital Transformation, AI Integration, Sustainability Focus, Remote Work Adoption

---

# Market Challenges & Threats

[List structural, economic, regulatory, or competitive challenges:]
- **[Challenge Name]:** [Description and potential impact] [Citation]

---

# Growth Opportunities

[Highlight areas where growth and innovation are possible:]
- **[Opportunity Area]:** [Description of the opportunity and potential] [Citation]

Examples: SME Growth, Emerging Markets, New Technologies, Underserved Segments

---

# Industry Drivers

[What is fueling growth in this industry?]
- **[Driver Name]:** [Explanation of how this drives the industry] [Citation]

Examples: Consumer Expectations, Technology Advancement, Regulatory Changes, Economic Factors

---

# Consumer Mindset

[Current consumer preferences and behaviors in this industry:]
- **[Preference/Behavior]:** [Description and implications] [Citation]

Examples: Digital-First Preference, Sustainability Focus, Price Sensitivity, Experience Over Products

---

# Leading Brands

## Top Market Players

[List 5-7 leading brands with their key strengths:]

1. **[Brand Name]** - [Brief description of market position and key strengths] [Citation]
2. **[Brand Name]** - [Brief description of market position and key strengths] [Citation]
3. **[Brand Name]** - [Brief description of market position and key strengths] [Citation]

---

# Emerging Brands

## Rising Stars & Disruptors

[List 3-5 emerging brands/startups making an impact:]

1. **[Brand Name]** - [Unique value proposition and innovation] [Citation]
2. **[Brand Name]** - [Unique value proposition and innovation] [Citation]
3. **[Brand Name]** - [Unique value proposition and innovation] [Citation]

---

# Sources

[List all citations and sources used in this report:]
- [Source name with link if available]
- [Source name with link if available]

---

**Analysis Quality:** Ensure all insights are data-driven, factual, and based on the research context provided below.

--- RESEARCH CONTEXT ---

## Market Reports and Analysis
{market_reports}

## Industry Trends Data
{trend_data}

## Leading Brands Data
{top_brands}

## Emerging Brands Data
{emerging_brands}

## Recent News Data
{news_articles}

---

Now generate the Industry & Market Profile report following the exact structure and formatting requirements above. Use professional language, be concise, and ensure every section has proper markdown formatting with clear visual hierarchy using H1 (#) for main sections.
"""

    @staticmethod
    def brand_house(
        brand_name: str,
        brand_site_content: str,
        current_positioning: str,
        competitor_data: str,
        news_mentions: str
    ) -> str:
        """Brand House prompt template."""
        return f"""Act as a Brand Strategist. Create a Brand House Strategy for {brand_name}. The goal is to analyze their current positioning and recommend a strategic rebrand/refresh.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently


CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN section headers: Current Positioning, Reason To Be (Recommendation), Vision & Mission Updates, Brand Pillars Updates, Brand Personality, Updated Positioning Statements
- Use ## (H2) for subsection headers: Brand Tone and Voice, Key Messages & Reasons to Believe, Value Proposition, Primary Customers, Current Competitive Landscape, One-Liner, Positioning Statement, Elevator Pitch
- Use bullet points (-) for all lists
- Use **bold** for emphasis on key terms and recommendations
- Add blank lines between sections for readability
- Keep paragraphs concise (2-3 sentences max)
- For citations, use markdown link syntax: [Source](URL) to make them clickable

REQUIRED SECTIONS (in this exact order):

# Current Positioning

## Brand Tone and Voice
[Describe the current tone: e.g., Professional, innovative, technical]

## Key Messages & Reasons to Believe
[List the primary messages the brand communicates and what backs them up:]
- **[Message 1]:** [Supporting evidence or proof point]
- **[Message 2]:** [Supporting evidence or proof point]

## Value Proposition
[The current promise to the customer - what value does the brand deliver?]

## Primary Customers
[Who they currently serve - describe target segments]

## Current Competitive Landscape
[Brief overview of their market position and key competitors]

---

# Reason To Be (Recommendation)

[Propose an updated "Reason to Be" that differentiates {brand_name} in the market]

**Rationale:** [Explain why this new positioning makes strategic sense]

---

# Vision & Mission Updates

## Current Focus
[Describe the current vision/mission]

## Suggested Update
[Propose a more aspirational vision/mission that aligns with the recommended positioning]

**Why this matters:** [Brief explanation of the strategic benefit]

---

# Brand Pillars Updates

[Recommend 3 core pillars that support the brand positioning:]

## Pillar 1: [Name] (e.g., Sustainability Leadership)
**Reasons to Believe:**
- [Proof point 1]
- [Proof point 2]
- [Proof point 3]

## Pillar 2: [Name] (e.g., AI Innovation)
**Reasons to Believe:**
- [Proof point 1]
- [Proof point 2]
- [Proof point 3]

## Pillar 3: [Name] (e.g., Customer Centricity)
**Reasons to Believe:**
- [Proof point 1]
- [Proof point 2]
- [Proof point 3]

---

# Brand Personality

## Defining Qualities
[List 4-6 personality traits that should define the brand:]
- **[Trait 1]:** [Brief description]
- **[Trait 2]:** [Brief description]
- **[Trait 3]:** [Brief description]

## Visual Identity Implications
[How these qualities should manifest in design, color, typography, imagery]

---

# Updated Positioning Statements

## One-Liner
[A punchy, memorable tagline that captures the essence]

## Positioning Statement
[Internal strategic statement: For [target], {brand_name} is the [category] that [benefit] because [reason to believe]]

## Elevator Pitch
[A short external summary (2-3 sentences) that explains who you are, what you do, and why it matters]

---

**Strategic Recommendation:** [1-2 sentence summary of the recommended brand evolution]

--- RESEARCH CONTEXT ---

## Brand Website Content
{brand_site_content}

## Current Positioning Analysis
{current_positioning}

## Competitor Analysis
{competitor_data}

## Recent News
{news_mentions}

---

Now generate the Brand House Strategy following the exact structure and formatting requirements above. Use strategic, forward-looking language that is persuasive and actionable.
"""

    @staticmethod
    def four_cs_analysis(
        brand_name: str,
        brand_site_content: str,
        news_mentions: str,
        competitor_data: str,
        social_sentiment: str,
        industry_trends: str
    ) -> str:
        """Four C's Analysis prompt template."""
        return f"""Act as a Strategic Planner. Conduct a deep-dive "Four C's" Analysis for {brand_name}. Analyze the brand through the lens of Company, Category, Consumer, and Culture.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently


CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for the FOUR MAIN sections: COMPANY, CATEGORY, CONSUMER, CULTURE
- Use ## (H2) for subsections within each C
- Use bullet points (-) for all lists
- Use **bold** for emphasis on key terms
- Add blank lines between sections for readability
- For citations, use markdown link syntax: [Source](URL) to make them clickable

REQUIRED SECTIONS (in this exact order):

# 1. COMPANY

## Origin Story
[When was {brand_name} founded? What were the founders' values and original vision?]

## Recent News
[Bullet points of the last 6 months of key developments:]
- **[Date]:** [News item - M&A, new products, stock performance, leadership changes] [Citation]
- **[Date]:** [News item] [Citation]
- **[Date]:** [News item] [Citation]

## Market Share
[Revenue, growth trends, global ranking, market capitalization if public]

## Employee / Consumer Satisfaction
- **Employee Sentiment:** [Glassdoor ratings, retention rates, culture feedback]
- **Consumer Perception:** [NPS scores, brand loyalty metrics, general public perception]

## Expert Opinion
[What do industry analysts say about their innovation, growth potential, and competitive positioning?]

## Reasons to Believe
[What gives {brand_name} credibility?]
- **Heritage:** [Years in business, track record]
- **Expertise:** [Unique capabilities or domain knowledge]
- **Strategic Assets:** [Locations, partnerships, IP]

---

# 2. CATEGORY

## Advertising Clichés
[What are the overused tropes in this industry? What does everyone say?]
- [Cliché 1]
- [Cliché 2]
- [Cliché 3]

## Positioning Among Peers
[Use a metaphor: If this category were a classroom, who would {brand_name} be?]
- **{brand_name}:** [e.g., "The diligent student who always delivers"]
- **[Competitor 1]:** [e.g., "The popular kid everyone knows"]
- **[Competitor 2]:** [e.g., "The disruptive newcomer"]

## Category Issues & Opportunities
**Challenges:**
- [Supply chain pressures, regulatory hurdles, cost inflation]

**Opportunities:**
- [Emerging markets, technology adoption, sustainability demands]

## Category Evolution
[How is the industry shifting?]
- **[Trend 1]:** [e.g., AI Integration] - [Description]
- **[Trend 2]:** [e.g., Sustainability Focus] - [Description]
- **[Trend 3]:** [e.g., Consolidation] - [Description]

---

# 3. CONSUMER

## Demographics
[B2B or B2C? Who are the actual buyers and users?]
- **Primary Audience:** [Description]
- **Secondary Audience:** [Description]

## Consumer Problem & Goal
**Functional Problem:** [What specific pain point does {brand_name} solve?]

**Higher-Order Goal:** [What deeper need or aspiration does it fulfill?]

## Consumer Mindset
**Positive Perceptions:**
- [What consumers appreciate or trust about {brand_name}]
- [Common praise themes from social/reviews]

**Negative Perceptions:**
- [Common criticisms or concerns]
- [Barriers to adoption or loyalty]

---

# 4. CULTURE

## Audience Focus
[Who are they fighting to reach? Which segment is the priority?]

## Macro Forces
[What external forces are shaping this audience?]
- **Economic:** [Inflation, interest rates, employment]
- **Technological:** [AI, automation, digital transformation]
- **Social:** [Remote work, sustainability values, health consciousness]
- **Political:** [Regulations, trade policies, geopolitics]

## Muses
[What inspires this audience? What do they look up to?]
- [Thought leaders, movements, cultural phenomena]

## Subcultures
[What specific niche groups or values does the brand align with?]
- **[Subculture 1]:** [e.g., Green Transformation advocates] - [Why relevant]
- **[Subculture 2]:** [e.g., Digital Natives] - [Why relevant]

---

**Strategic Synthesis:** [2-3 sentences summarizing the key insights from this 4C analysis and their strategic implications for {brand_name}]

--- RESEARCH CONTEXT ---

## Brand Website Content
{brand_site_content}

## Recent News
{news_mentions}

## Competitor Analysis
{competitor_data}

## Social Sentiment
{social_sentiment}

## Industry Trends
{industry_trends}

---

Now generate the Four C's Analysis following the exact structure above. Use analytical, comprehensive language that is culturally aware and strategically insightful.
"""

    @staticmethod
    def competitive_landscape(
        brand_name: str,
        industry_name: str,
        competitor_data: str,
        market_analysis: str
    ) -> str:
        """Competitive Landscape prompt template."""
        return f"""Act as a Market Analyst. Build a Competitive Landscape Map for {brand_name} in the {industry_name} industry.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total (approximately 1,000-1,300 words)
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently

CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN sections: Competitor Overview Table, Deep Dives by Category, Sources
- Use ## (H2) for category names in Deep Dives
- Use tables for the Competitor Overview
- Use bullet points (-) for lists
- Use **bold** for company names and emphasis
- For citations, use markdown link syntax: [Source](URL)

REQUIRED SECTIONS (in this exact order):

# Competitor Overview Table

| Company | One-Line Description | Category | Key Differentiator |
|---------|---------------------|----------|-------------------|
| **{brand_name}** | [Brief summary of offering] | [Niche/segment] | [Primary competitive advantage] |
| **[Competitor 1]** | [Brief summary] | [Niche/segment] | [Advantage] |
| **[Competitor 2]** | [Brief summary] | [Niche/segment] | [Advantage] |
| **[Competitor 3]** | [Brief summary] | [Niche/segment] | [Advantage] |
| **[Competitor 4]** | [Brief summary] | [Niche/segment] | [Advantage] |
| **[Competitor 5]** | [Brief summary] | [Niche/segment] | [Advantage] |
| **[Competitor 6]** | [Brief summary] | [Niche/segment] | [Advantage] |

---

# Deep Dives by Category

[Group competitors into 3-4 distinct categories based on their strategic focus. Examples: Premium/Luxury, Mass Market, Technology-Focused, Emerging/Disruptors]

## Category 1: [Category Name] (e.g., Premium Leaders)

**Category Focus:** [What defines this category]

**Major Players:**

### {brand_name}
[Detailed paragraph covering: competitive advantage, flagship products/services, market positioning, strategic partnerships, unique capabilities, and recent developments] [Citation]

### [Competitor A]
[Detailed paragraph with same structure] [Citation]

### [Competitor B]
[Detailed paragraph with same structure] [Citation]

---

## Category 2: [Category Name] (e.g., Tech Innovators)

**Category Focus:** [What defines this category]

**Major Players:**

### [Competitor C]
[Detailed paragraph] [Citation]

### [Competitor D]
[Detailed paragraph] [Citation]

---

## Category 3: [Category Name] (e.g., Emerging Disruptors)

**Category Focus:** [What defines this category]

**Major Players:**

### [Competitor E]
[Detailed paragraph] [Citation]

### [Competitor F]
[Detailed paragraph] [Citation]

---

# Competitive Positioning Analysis

## {brand_name}'s Competitive Position

**Strengths:**
- [Key strength 1]
- [Key strength 2]
- [Key strength 3]

**Weaknesses:**
- [Gap or challenge 1]
- [Gap or challenge 2]

**Opportunities:**
- [Market whitespace or growth area]
- [Strategic opportunity]

**Threats:**
- [Competitive pressure]
- [Market risk]

---

# Sources

[List all sources used in this analysis:]
- [Source with link]
- [Source with link]

---

--- RESEARCH CONTEXT ---

## Brand Data ({brand_name})
{brand_name} - analyze their position in the landscape

## Competitor Intelligence
{competitor_data}

## Market Analysis
{market_analysis}

---

Now generate the Competitive Landscape Map following the exact structure above. Be specific about competitive advantages and use real data from the research context.
"""

    @staticmethod
    def audience_profile(
        audience_name: str,
        geography: str,
        demographic_data: str,
        psychographic_data: str,
        media_consumption: str,
        brand_preferences: str
    ) -> str:
        """Audience Profile prompt template."""
        return f"""Act as a Consumer Insights Researcher. Create a comprehensive Audience Profile for {audience_name} in {geography}.

**CRITICAL LENGTH REQUIREMENT:**
- Your response MUST be between 6,000-8,000 characters total (approximately 1,000-1,300 words)
- This is a HARD LIMIT - responses over 8,000 characters will be rejected
- Be comprehensive but concise - prioritize quality over quantity
- Use bullet points and tables to convey information efficiently

CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax with STRONG visual hierarchy
- Use # (H1) for MAIN section headers
- Use ## (H2) for subsections
- Use bullet points (-) for all lists
- Use **bold** for emphasis
- Use > blockquotes for notable statistics
- For citations, use markdown link syntax: [Source](URL)

REQUIRED SECTIONS (in this exact order):

# How Many Are There?

[Provide statistics on the size and scale of this audience:]
- **Local Market:** [Number/percentage in {geography}]
- **Global Reach:** [If applicable]
- **Digital Adoption:** [Online penetration, app usage]
- **Segmentation:** [Key sub-segments within this audience]

---

# Demographics

[Provide detailed demographic breakdown:]
- **Age Range:** [Primary age groups]
- **Gender Distribution:** [If relevant]
- **Income Levels:** [Economic segments]
- **Education:** [Typical education levels]
- **Geographic Distribution:** [Urban vs. rural, regional differences]
- **Life Stage:** [e.g., Young professionals, families, retirees]

---

# Media Consumption

## How Much Media Do They Consume?
[Daily/weekly media consumption habits:]
- **TV:** [Hours per day, preferred times]
- **Digital:** [Screen time, device preferences]
- **Social Media:** [Platform usage statistics]
- **Traditional Media:** [Print, radio usage]

## Where Do They Consume Media?
[Specific platforms and channels:]
- **Primary Platforms:** [e.g., Instagram, TikTok, YouTube]
- **Emerging Platforms:** [New channels gaining traction]
- **Content Preferences:** [Video, articles, podcasts, etc.]

---

# Brand Preferences

## What Brands Do They Prefer?
[List top brands in the category and why they resonate:]
1. **[Brand 1]:** [Why this audience loves them]
2. **[Brand 2]:** [Why this audience loves them]
3. **[Brand 3]:** [Why this audience loves them]

## What Brand Affinities Do They Have?
**Loyalty Drivers:**
- [What builds lasting relationships]
- [What creates advocacy]

**Key Factors:**
- **Price Sensitivity:** [High/Medium/Low and context]
- **Sustainability Focus:** [Importance level and manifestation]
- **Innovation Appetite:** [Early adopters vs. mainstream]
- **Trust & Transparency:** [What earns credibility]

---

# What's Most Important to This Audience?

## Factors
[Rank the key decision factors:]
1. **[Factor 1]:** [e.g., Convenience] - [Why it matters]
2. **[Factor 2]:** [e.g., Trust] - [Why it matters]
3. **[Factor 3]:** [e.g., Value] - [Why it matters]

## Motivations
**Goals:**
- [What they're trying to achieve]
- [Higher-order aspirations]

**Costs/Barriers:**
- [What holds them back]
- [Pain points and frustrations]

---

# Who Influences Them?

[Identify key influencers and influence channels:]
- **Family & Friends:** [Role in decision-making]
- **Experts & Advisors:** [Professional influences]
- **Social Media Influencers:** [Types and reach]
- **Regulatory/Institutional:** [Policy or organizational influence]
- **Community & Peers:** [Social proof and word-of-mouth]

---

# What Lights Them Up and Shuts Them Down?

## Lights Up
[What excites, delights, or activates this audience:]
- **[Trigger 1]:** [e.g., Personalization] - [Why it works]
- **[Trigger 2]:** [e.g., Innovation] - [Why it works]
- **[Trigger 3]:** [e.g., Community] - [Why it works]

## Shuts Down
[What turns them off or creates resistance:]
- **[Barrier 1]:** [e.g., Hidden fees] - [Why it fails]
- **[Barrier 2]:** [e.g., Poor support] - [Why it fails]
- **[Barrier 3]:** [e.g., Inauthenticity] - [Why it fails]

---

**Strategic Summary:** [2-3 sentences synthesizing the key insights about this audience and how brands should approach them]

--- RESEARCH CONTEXT ---

## Demographic Data
{demographic_data}

## Psychographic Data
{psychographic_data}

## Media Consumption Data
{media_consumption}

## Brand Preference Data
{brand_preferences}

---

Now generate the Audience Profile following the exact structure above. Use ethnographic, statistical language that is empathetic to the user and grounded in real behavioral insights.
"""
