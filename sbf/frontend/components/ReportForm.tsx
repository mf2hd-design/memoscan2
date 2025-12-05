'use client';

import { useState } from 'react';
import { GEOGRAPHIES, REPORT_TYPES } from '../lib/progressSteps';

interface ReportFormProps {
  reportType: string;
  onSubmit: (formData: FormData) => void;
}

export default function ReportForm({ reportType, onSubmit }: ReportFormProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [files, setFiles] = useState<File[]>([]);

  const reportConfig = REPORT_TYPES.find(r => r.id === reportType);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsSubmitting(true);

    const formData = new FormData(e.currentTarget);
    formData.append('report_type', reportType);

    // Add files for brand audit
    if (reportType === 'brand_audit') {
      files.forEach(file => {
        formData.append('files', file);
      });
    }

    try {
      await onSubmit(formData);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  return (
    <div className="card max-w-2xl mx-auto">
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <span className="text-4xl">{reportConfig?.icon}</span>
          <div>
            <h2 className="text-2xl font-semibold text-gray-900">
              {reportConfig?.name}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              {reportConfig?.description}
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Brand Audit Fields */}
        {reportType === 'brand_audit' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Name *
              </label>
              <input
                type="text"
                name="brand_name"
                required
                className="input"
                placeholder="e.g., Tesla"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Website URL *
              </label>
              <input
                type="url"
                name="brand_url"
                required
                className="input"
                placeholder="https://tesla.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Competitors (Optional)
              </label>
              <input
                type="text"
                name="competitors"
                className="input"
                placeholder="e.g., Ford, GM, Rivian (comma-separated)"
              />
              <p className="mt-1 text-sm text-gray-500">
                Leave blank to auto-detect competitors
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Upload PDFs (Optional)
              </label>
              <input
                type="file"
                multiple
                accept=".pdf"
                onChange={handleFileChange}
                className="input"
              />
              {files.length > 0 && (
                <p className="mt-2 text-sm text-gray-600">
                  {files.length} file(s) selected
                </p>
              )}
            </div>
          </>
        )}

        {/* Meeting Brief Fields */}
        {reportType === 'meeting_brief' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Person Name *
              </label>
              <input
                type="text"
                name="person_name"
                required
                className="input"
                placeholder="e.g., Tim Cook"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Person Role *
              </label>
              <input
                type="text"
                name="person_role"
                required
                className="input"
                placeholder="e.g., CEO"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Company Name *
              </label>
              <input
                type="text"
                name="company_name"
                required
                className="input"
                placeholder="e.g., Apple Inc"
              />
            </div>
          </>
        )}

        {/* Industry Profile Fields */}
        {reportType === 'industry_profile' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Industry Name *
            </label>
            <input
              type="text"
              name="industry_name"
              required
              className="input"
              placeholder="e.g., Electric Vehicles"
            />
          </div>
        )}

        {/* Brand House Fields */}
        {reportType === 'brand_house' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Name *
              </label>
              <input
                type="text"
                name="brand_name"
                required
                className="input"
                placeholder="e.g., Nike"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Website URL *
              </label>
              <input
                type="url"
                name="brand_url"
                required
                className="input"
                placeholder="https://nike.com"
              />
            </div>
          </>
        )}

        {/* Four C's Analysis Fields */}
        {reportType === 'four_cs' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Name *
              </label>
              <input
                type="text"
                name="brand_name"
                required
                className="input"
                placeholder="e.g., Tesla"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Website URL *
              </label>
              <input
                type="url"
                name="brand_url"
                required
                className="input"
                placeholder="https://tesla.com"
              />
            </div>
          </>
        )}

        {/* Competitive Landscape Fields */}
        {reportType === 'competitive_landscape' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Name *
              </label>
              <input
                type="text"
                name="brand_name"
                required
                className="input"
                placeholder="e.g., Spotify"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brand Website URL *
              </label>
              <input
                type="url"
                name="brand_url"
                required
                className="input"
                placeholder="https://spotify.com"
              />
            </div>
          </>
        )}

        {/* Audience Profile Fields */}
        {reportType === 'audience_profile' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Audience Name *
            </label>
            <input
              type="text"
              name="audience_name"
              required
              className="input"
              placeholder="e.g., Gen Z Consumers"
            />
            <p className="mt-1 text-sm text-gray-500">
              Describe the target audience segment you want to profile
            </p>
          </div>
        )}

        {/* Geography (All Reports) */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Geography *
          </label>
          <select name="geography" className="input" defaultValue="US">
            {GEOGRAPHIES.map((geo) => (
              <option key={geo.code} value={geo.code}>
                {geo.name}
              </option>
            ))}
          </select>
        </div>

        {/* Submit Button */}
        <div className="flex gap-4 pt-4">
          <button
            type="submit"
            disabled={isSubmitting}
            className="btn btn-primary flex-1"
          >
            {isSubmitting ? 'Generating...' : `Generate ${reportConfig?.name}`}
          </button>
        </div>

        <div className="text-sm text-gray-500 text-center">
          <p>Estimated time: {reportConfig?.time}</p>
        </div>
      </form>
    </div>
  );
}
