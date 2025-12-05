/**
 * Progress step definitions for each report type.
 */

export const PROGRESS_STEPS: Record<string, string[]> = {
  brand_audit: [
    'Initializing workflow',
    'Checking cache',
    'Processing PDFs',
    'Scraping brand website',
    'Collecting social sentiment',
    'Identifying competitors',
    'Scraping competitors',
    'Gathering news mentions',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  meeting_brief: [
    'Initializing workflow',
    'Checking cache',
    'Researching person and company',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  industry_profile: [
    'Initializing workflow',
    'Checking cache',
    'Researching industry',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  brand_house: [
    'Initializing workflow',
    'Checking cache',
    'Researching brand positioning',
    'Identifying competitors',
    'Scraping competitors',
    'Gathering news mentions',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  four_cs: [
    'Initializing workflow',
    'Checking cache',
    'Researching company data',
    'Identifying competitors',
    'Scraping competitors',
    'Collecting social sentiment',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  competitive_landscape: [
    'Initializing workflow',
    'Checking cache',
    'Identifying competitors',
    'Scraping competitors',
    'Researching market analysis',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ],
  audience_profile: [
    'Initializing workflow',
    'Checking cache',
    'Researching audience demographics',
    'Analyzing with GPT-5.1',
    'Formatting report'
  ]
};

export const REPORT_TYPES = [
  {
    id: 'brand_audit',
    name: 'Brand Audit',
    description: 'Comprehensive health check with social sentiment and competitive analysis',
    icon: '🏥',
    time: '8-12 min',
    featured: true,
    inputs: ['brand_name', 'brand_url', 'competitors', 'geography', 'files']
  },
  {
    id: 'meeting_brief',
    name: 'Meeting Brief',
    description: 'Executive dossier with person background and company intelligence',
    icon: '🤝',
    time: '4-6 min',
    featured: false,
    inputs: ['person_name', 'person_role', 'company_name', 'geography']
  },
  {
    id: 'industry_profile',
    name: 'Industry Profile',
    description: 'Market analysis with trends, challenges, and key players',
    icon: '📊',
    time: '5-7 min',
    featured: false,
    inputs: ['industry_name', 'geography']
  },
  {
    id: 'brand_house',
    name: 'Brand House (Rebranding)',
    description: 'Strategic positioning framework with vision, mission, and brand pillars',
    icon: '🏛️',
    time: '6-9 min',
    featured: false,
    inputs: ['brand_name', 'brand_url', 'geography']
  },
  {
    id: 'four_cs',
    name: "Four C's Analysis",
    description: 'Company, Category, Consumer, and Culture strategic framework',
    icon: '🔄',
    time: '7-10 min',
    featured: false,
    inputs: ['brand_name', 'brand_url', 'geography']
  },
  {
    id: 'competitive_landscape',
    name: 'Competitive Landscape',
    description: 'Deep competitive intelligence with market positioning analysis',
    icon: '🗺️',
    time: '5-8 min',
    featured: false,
    inputs: ['brand_name', 'brand_url', 'geography']
  },
  {
    id: 'audience_profile',
    name: 'Audience Profile (Persona)',
    description: 'Target audience analysis with demographics, psychographics, and behavior',
    icon: '👥',
    time: '4-7 min',
    featured: false,
    inputs: ['audience_name', 'geography']
  }
];

export const GEOGRAPHIES = [
  { code: 'US', name: 'United States' },
  { code: 'UK', name: 'United Kingdom' },
  { code: 'DE', name: 'Germany' },
  { code: 'FR', name: 'France' },
  { code: 'ES', name: 'Spain' },
  { code: 'IT', name: 'Italy' },
  { code: 'CA', name: 'Canada' },
  { code: 'AU', name: 'Australia' },
  { code: 'JP', name: 'Japan' },
  { code: 'IN', name: 'India' }
];
