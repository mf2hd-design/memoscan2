import { REPORT_TYPES } from '../lib/progressSteps';

interface ReportTypeSelectorProps {
  onSelect: (reportType: string) => void;
}

export default function ReportTypeSelector({ onSelect }: ReportTypeSelectorProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-gray-900">
          Select a Report Type
        </h2>
        <p className="mt-2 text-gray-600">
          Choose the type of strategic analysis you need
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {REPORT_TYPES.map((type) => (
          <button
            key={type.id}
            onClick={() => onSelect(type.id)}
            className={`card hover:shadow-lg transition-shadow text-left ${
              type.featured ? 'ring-2 ring-primary-500' : ''
            }`}
          >
            <div className="text-5xl mb-4">{type.icon}</div>

            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              {type.name}
            </h3>

            <p className="text-gray-600 mb-4 min-h-[48px]">
              {type.description}
            </p>

            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">⏱️ {type.time}</span>
              {type.featured && (
                <span className="text-primary-600 font-semibold">
                  ⭐ Most Comprehensive
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
