import React, { useState, useCallback, useRef } from 'react';
import {
  FileText, Users, Building2, Layers, Grid, Target, UserCircle,
  Loader2, CheckCircle, AlertCircle, Download, Copy, RefreshCw
} from 'lucide-react';

// Report type configurations
const REPORT_TYPES = {
  brand_audit: {
    label: 'Brand Audit',
    icon: FileText,
    description: 'Comprehensive brand health analysis',
    fields: [
      { name: 'brand_name', label: 'Brand Name', required: true, placeholder: 'e.g., Nike' },
      { name: 'brand_url', label: 'Brand Website', required: true, placeholder: 'https://nike.com' },
      { name: 'competitors', label: 'Competitors (optional)', required: false, placeholder: 'Adidas, Puma, Under Armour' }
    ]
  },
  meeting_brief: {
    label: 'Meeting Brief',
    icon: Users,
    description: 'Person & company intelligence for meetings',
    fields: [
      { name: 'person_name', label: 'Person Name', required: true, placeholder: 'e.g., Tim Cook' },
      { name: 'person_role', label: 'Role/Title', required: true, placeholder: 'e.g., CEO' },
      { name: 'company_name', label: 'Company', required: true, placeholder: 'e.g., Apple' }
    ]
  },
  industry_profile: {
    label: 'Industry Profile',
    icon: Building2,
    description: 'Market research and trends analysis',
    fields: [
      { name: 'industry_name', label: 'Industry', required: true, placeholder: 'e.g., Electric Vehicles' }
    ]
  },
  brand_house: {
    label: 'Brand House',
    icon: Layers,
    description: 'Strategic brand positioning framework',
    fields: [
      { name: 'brand_name', label: 'Brand Name', required: true, placeholder: 'e.g., Nike' },
      { name: 'brand_url', label: 'Brand Website', required: true, placeholder: 'https://nike.com' }
    ]
  },
  four_cs: {
    label: 'Four C\'s Analysis',
    icon: Grid,
    description: 'Company, Category, Consumer, Culture',
    fields: [
      { name: 'brand_name', label: 'Brand Name', required: true, placeholder: 'e.g., Nike' },
      { name: 'brand_url', label: 'Brand Website', required: true, placeholder: 'https://nike.com' }
    ]
  },
  competitive_landscape: {
    label: 'Competitive Landscape',
    icon: Target,
    description: 'Market positioning and competitor analysis',
    fields: [
      { name: 'brand_name', label: 'Brand Name', required: true, placeholder: 'e.g., Nike' },
      { name: 'brand_url', label: 'Brand Website', required: true, placeholder: 'https://nike.com' }
    ]
  },
  audience_profile: {
    label: 'Audience Profile',
    icon: UserCircle,
    description: 'Demographics, psychographics, and behaviors',
    fields: [
      { name: 'audience_name', label: 'Audience Segment', required: true, placeholder: 'e.g., Gen Z Gamers' }
    ]
  }
};

const GEOGRAPHIES = ['US', 'UK', 'EU', 'APAC', 'Global'];

// Simple markdown renderer
function renderMarkdown(text) {
  if (!text) return '';
  
  return text
    // Headers
    .replace(/^### (.*$)/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.*$)/gm, '<h2 class="text-xl font-bold mt-6 mb-3 text-indigo-700">$1</h2>')
    .replace(/^# (.*$)/gm, '<h1 class="text-2xl font-bold mt-6 mb-4 text-indigo-800">$1</h1>')
    // Bold
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Lists
    .replace(/^- (.*$)/gm, '<li class="ml-4">$1</li>')
    .replace(/^(\d+)\. (.*$)/gm, '<li class="ml-4">$1. $2</li>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p class="mb-3">')
    // Line breaks
    .replace(/\n/g, '<br/>');
}

export default function App() {
  const [selectedType, setSelectedType] = useState('brand_audit');
  const [formData, setFormData] = useState({});
  const [geography, setGeography] = useState('US');
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [requestId, setRequestId] = useState(null);
  const abortControllerRef = useRef(null);

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const handleFieldChange = (name, value) => {
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setProgress(0);
    setProgressMessage('Initializing...');
    setResult(null);
    setError(null);

    // Create form data
    const submitData = new FormData();
    submitData.append('report_type', selectedType);
    submitData.append('geography', geography);
    
    REPORT_TYPES[selectedType].fields.forEach(field => {
      if (formData[field.name]) {
        submitData.append(field.name, formData[field.name]);
      }
    });

    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_URL}/api/v1/generate-report`, {
        method: 'POST',
        body: submitData,
        signal: abortControllerRef.current.signal
      });

      setRequestId(response.headers.get('x-request-id'));

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n').filter(line => line.trim());

        for (const line of lines) {
          try {
            const data = JSON.parse(line);

            if (data.type === 'progress') {
              setProgress(data.progress_percent || 0);
              setProgressMessage(data.message || 'Processing...');
            } else if (data.type === 'result') {
              setResult(data);
              setProgress(100);
              setProgressMessage('Complete!');
            } else if (data.type === 'error') {
              setError(data);
              setProgressMessage('Error occurred');
            }
          } catch (parseError) {
            console.warn('Failed to parse line:', line);
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError({ message: 'Connection failed', details: err.message });
      }
    } finally {
      setIsLoading(false);
    }
  }, [selectedType, formData, geography, API_URL]);

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsLoading(false);
    setProgressMessage('Cancelled');
  };

  const handleCopy = () => {
    if (result?.markdown) {
      navigator.clipboard.writeText(result.markdown);
    }
  };

  const handleDownload = () => {
    if (result?.markdown) {
      const blob = new Blob([result.markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selectedType}_report.md`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const config = REPORT_TYPES[selectedType];
  const Icon = config.icon;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">Strategist's Best Friend</h1>
              <p className="text-sm text-slate-500">AI-powered brand research</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Panel - Form */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Generate Report</h2>

              {/* Report Type Selection */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Report Type
                </label>
                <div className="grid grid-cols-1 gap-2">
                  {Object.entries(REPORT_TYPES).map(([key, type]) => {
                    const TypeIcon = type.icon;
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => {
                          setSelectedType(key);
                          setFormData({});
                        }}
                        className={`flex items-center gap-3 p-3 rounded-lg border transition-all text-left ${
                          selectedType === key
                            ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                            : 'border-slate-200 hover:border-slate-300 text-slate-700'
                        }`}
                      >
                        <TypeIcon className="w-5 h-5 flex-shrink-0" />
                        <div>
                          <div className="font-medium text-sm">{type.label}</div>
                          <div className="text-xs text-slate-500">{type.description}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Dynamic Fields */}
              <form onSubmit={handleSubmit}>
                <div className="space-y-4 mb-6">
                  {config.fields.map(field => (
                    <div key={field.name}>
                      <label className="block text-sm font-medium text-slate-700 mb-1">
                        {field.label} {field.required && <span className="text-red-500">*</span>}
                      </label>
                      <input
                        type="text"
                        value={formData[field.name] || ''}
                        onChange={e => handleFieldChange(field.name, e.target.value)}
                        placeholder={field.placeholder}
                        required={field.required}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                      />
                    </div>
                  ))}

                  {/* Geography */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      Geography
                    </label>
                    <select
                      value={geography}
                      onChange={e => setGeography(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    >
                      {GEOGRAPHIES.map(geo => (
                        <option key={geo} value={geo}>{geo}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Icon className="w-5 h-5" />
                      Generate {config.label}
                    </>
                  )}
                </button>

                {isLoading && (
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="w-full mt-2 px-4 py-2 text-slate-600 font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                )}
              </form>
            </div>
          </div>

          {/* Right Panel - Results */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 min-h-[600px]">
              {/* Progress Bar */}
              {isLoading && (
                <div className="p-4 border-b border-slate-200">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-slate-700">{progressMessage}</span>
                    <span className="text-sm text-slate-500">{progress}%</span>
                  </div>
                  <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-indigo-600 transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Error Display */}
              {error && (
                <div className="p-4 m-4 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <h3 className="font-medium text-red-800">{error.message}</h3>
                      {error.details && (
                        <p className="text-sm text-red-600 mt-1">{error.details}</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Result Display */}
              {result && (
                <>
                  {/* Result Header */}
                  <div className="p-4 border-b border-slate-200 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-green-500" />
                      <span className="font-medium text-slate-700">Report Generated</span>
                      {result.metadata?.duration_seconds && (
                        <span className="text-sm text-slate-500">
                          ({result.metadata.duration_seconds.toFixed(1)}s)
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleCopy}
                        className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                        title="Copy to clipboard"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                      <button
                        onClick={handleDownload}
                        className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                        title="Download as Markdown"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Markdown Content */}
                  <div className="p-6 prose prose-slate max-w-none">
                    <div 
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(result.markdown) }}
                    />
                  </div>

                  {/* Chart Data (if present) */}
                  {result.chart && (
                    <div className="p-4 border-t border-slate-200">
                      <h3 className="font-medium text-slate-700 mb-2">Chart Data</h3>
                      <pre className="bg-slate-50 p-4 rounded-lg text-xs overflow-auto">
                        {JSON.stringify(result.chart, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}

              {/* Empty State */}
              {!isLoading && !result && !error && (
                <div className="flex flex-col items-center justify-center h-[500px] text-slate-400">
                  <Icon className="w-16 h-16 mb-4" />
                  <p className="text-lg font-medium">Select a report type and fill in the details</p>
                  <p className="text-sm">Your report will appear here</p>
                </div>
              )}
            </div>

            {/* Request ID */}
            {requestId && (
              <div className="mt-2 text-xs text-slate-400 text-right">
                Request ID: {requestId}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
