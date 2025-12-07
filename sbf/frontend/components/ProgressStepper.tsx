import { useState, useEffect } from 'react';
import { PROGRESS_STEPS, REPORT_TYPES } from '../lib/progressSteps';
import { StreamEvent } from '../lib/api';

interface ProgressStepperProps {
  reportType: string;
  events: StreamEvent[];
}

export default function ProgressStepper({ reportType, events }: ProgressStepperProps) {
  const steps = PROGRESS_STEPS[reportType] || [];
  const reportTypeInfo = REPORT_TYPES.find(r => r.id === reportType);
  const latestProgress = events[events.length - 1];
  const progressPercent = latestProgress && 'progress_percent' in latestProgress
    ? latestProgress.progress_percent || 0
    : 0;

  // Calculate which step we're on based on progress percentage
  const currentStepIndex = Math.floor((progressPercent / 100) * steps.length);

  // Elapsed timer
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [startTime] = useState(Date.now());

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);

  // Format elapsed time as MM:SS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Parse estimated time range (e.g., "4-6 min" -> {min: 4, max: 6})
  const parseTimeEstimate = (timeStr: string) => {
    const match = timeStr.match(/(\d+)-(\d+)/);
    if (match) {
      return { min: parseInt(match[1]), max: parseInt(match[2]) };
    }
    return { min: 5, max: 8 }; // Default fallback
  };

  const timeEstimate = reportTypeInfo ? parseTimeEstimate(reportTypeInfo.time) : { min: 5, max: 8 };
  const avgEstimateSeconds = ((timeEstimate.min + timeEstimate.max) / 2) * 60;
  const remainingSeconds = Math.max(0, Math.floor(avgEstimateSeconds - elapsedSeconds));

  return (
    <div className="card max-w-3xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2 flex items-center gap-3">
          <span>{reportTypeInfo?.icon || '📄'}</span>
          <span>Generating {reportTypeInfo?.name || 'Report'}...</span>
        </h2>
        <div className="flex items-center justify-between text-gray-600">
          <p>This may take several minutes. Please don't close this window.</p>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-semibold">Elapsed:</span>
              <span className="font-mono bg-gray-100 px-2 py-1 rounded">{formatTime(elapsedSeconds)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold">Remaining:</span>
              <span className="font-mono bg-blue-50 text-blue-700 px-2 py-1 rounded">~{formatTime(remainingSeconds)}</span>
            </div>
          </div>
        </div>
        <div className="mt-2 text-sm text-gray-500">
          Estimated total time: {timeEstimate.min}-{timeEstimate.max} minutes
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-8">
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-primary-600 h-3 rounded-full transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-sm text-gray-600">
          <span>{progressPercent}% Complete</span>
          <span className="animate-pulse">Processing...</span>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-4">
        {steps.map((step, idx) => {
          const isCompleted = idx < currentStepIndex;
          const isActive = idx === currentStepIndex;
          const isPending = idx > currentStepIndex;

          return (
            <div key={idx} className="flex items-center gap-4">
              {/* Status Icon */}
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold ${
                  isCompleted
                    ? 'bg-green-500 text-white'
                    : isActive
                    ? 'bg-primary-600 text-white animate-pulse'
                    : 'bg-gray-200 text-gray-600'
                }`}
              >
                {isCompleted && '✓'}
                {isActive && '⋯'}
                {isPending && idx + 1}
              </div>

              {/* Step Label */}
              <div className="flex-1">
                <div
                  className={`font-medium ${
                    isActive
                      ? 'text-primary-700'
                      : isCompleted
                      ? 'text-green-700'
                      : 'text-gray-500'
                  }`}
                >
                  {step}
                </div>
                {isActive && latestProgress && 'message' in latestProgress && (
                  <div className="text-sm text-gray-600 mt-1">
                    {latestProgress.message}
                  </div>
                )}
              </div>

              {/* Status Badge */}
              {isCompleted && (
                <span className="text-xs text-green-600 font-medium">Done</span>
              )}
              {isActive && (
                <span className="text-xs text-primary-600 font-medium animate-pulse">
                  In Progress
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Latest Message */}
      {latestProgress && 'message' in latestProgress && (
        <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-900">{latestProgress.message}</p>
        </div>
      )}
    </div>
  );
}
