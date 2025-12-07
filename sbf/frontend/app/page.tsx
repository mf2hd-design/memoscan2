'use client';

import { useState } from 'react';
import ReportTypeSelector from '../components/ReportTypeSelector';
import ReportForm from '../components/ReportForm';
import ProgressStepper from '../components/ProgressStepper';
import ReportView from '../components/ReportView';
import { streamReport, StreamEvent } from '../lib/api';

export default function Home() {
  const [reportType, setReportType] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [progressEvents, setProgressEvents] = useState<StreamEvent[]>([]);
  const [report, setReport] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async (formData: FormData) => {
    setIsGenerating(true);
    setProgressEvents([]);
    setReport(null);
    setError(null);

    try {
      for await (const event of streamReport(formData)) {
        if (event.type === 'progress') {
          setProgressEvents(prev => [...prev, event]);
        } else if (event.type === 'result') {
          setReport(event);
          setIsGenerating(false);
        } else if (event.type === 'error') {
          setError(event.message);
          setIsGenerating(false);
        }
      }
    } catch (err: any) {
      console.error('Stream error:', err);
      setError(err.message || 'An error occurred while generating the report');
      setIsGenerating(false);
    }
  };

  const handleReset = () => {
    setReportType(null);
    setReport(null);
    setProgressEvents([]);
    setError(null);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold text-gray-900">
            Strategist's Best Friend
          </h1>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-8">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <span className="text-2xl">⚠️</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Error</h3>
                <div className="mt-2 text-sm text-red-700">{error}</div>
                <button
                  onClick={handleReset}
                  className="mt-3 btn btn-secondary text-sm"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        )}

        {!reportType && !isGenerating && !report && (
          <ReportTypeSelector onSelect={setReportType} />
        )}

        {reportType && !isGenerating && !report && (
          <div>
            <button
              onClick={() => setReportType(null)}
              className="mb-4 text-primary-600 hover:text-primary-700 flex items-center"
            >
              ← Back to report types
            </button>
            <ReportForm
              reportType={reportType}
              onSubmit={handleGenerate}
            />
          </div>
        )}

        {isGenerating && (
          <div>
            <ProgressStepper
              reportType={reportType!}
              events={progressEvents}
            />
          </div>
        )}

        {report && (
          <ReportView
            report={report}
            onReset={handleReset}
          />
        )}
      </div>

      {/* Footer */}
      <footer className="mt-16 border-t border-gray-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 py-6 text-center text-sm text-gray-500">
          <p>© 2025 Saffron Brand Consultants</p>
        </div>
      </footer>
    </main>
  );
}
