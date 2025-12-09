'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ReportViewProps {
  report: {
    markdown: string;
    chart?: any;
    metadata: {
      workflow_id: string;
      duration_seconds: number;
      report_type: string;
      geography: string;
      subject_name?: string;
    };
  };
  onReset: () => void;
}

export default function ReportView({ report, onReset }: ReportViewProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const formatDuration = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}m ${secs}s`;
  };

  // Format report type for display (convert snake_case to Title Case)
  const formatReportType = (type: string) => {
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-gray-900 mb-1">
              {report.metadata.subject_name || 'Report Complete! 🎉'}
            </h2>
            <p className="text-gray-600 mb-3">
              {formatReportType(report.metadata.report_type)}
            </p>
            <div className="flex flex-wrap gap-4 text-sm text-gray-500">
              <span>
                ⏱️ Generated in {formatDuration(report.metadata.duration_seconds)}
              </span>
              <span>🌍 {report.metadata.geography}</span>
            </div>
          </div>
          <button
            onClick={onReset}
            className="btn btn-secondary"
          >
            Generate Another
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-4">
        <button
          onClick={handleCopy}
          className="btn btn-primary"
        >
          {copied ? '✓ Copied!' : '📋 Copy to Clipboard'}
        </button>
      </div>

      {/* Report Content */}
      <div className="card">
        <div className="prose prose-lg max-w-none prose-a:text-blue-600 prose-a:font-medium prose-a:underline prose-a:decoration-2 prose-a:underline-offset-2 hover:prose-a:text-blue-800 hover:prose-a:decoration-blue-800">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {report.markdown}
          </ReactMarkdown>
        </div>
      </div>

      {/* Chart (if available) */}
      {report.chart && (
        <div className="card">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">
            {report.chart.chart_title}
          </h3>
          <div className="text-gray-600">
            <p>Chart visualization coming soon...</p>
            <pre className="mt-4 p-4 bg-gray-50 rounded-lg overflow-auto text-sm">
              {JSON.stringify(report.chart, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Metadata */}
      <div className="text-center text-sm text-gray-500">
        <p>Workflow ID: {report.metadata.workflow_id}</p>
      </div>
    </div>
  );
}
