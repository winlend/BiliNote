import { FC } from 'react'
import { Check, X } from 'lucide-react'

interface Step {
  label: string
  key: string
  Icon?: React.ReactNode
}

interface StepBarProps {
  steps: Step[]
  currentStep: string
  /** 失败时所在步骤 key，该步及之后不再标为已完成 */
  failedStep?: string
}

const StepBar: FC<StepBarProps> = ({ steps, currentStep, failedStep }) => {
  const currentIndex = steps.findIndex(step => step.key === currentStep)
  const failedIndex = failedStep ? steps.findIndex(step => step.key === failedStep) : -1
  const effectiveIndex =
    failedIndex >= 0 ? failedIndex : currentIndex >= 0 ? currentIndex : 0

  return (
    <div className="flex w-full items-center justify-between">
      {steps.map((step, index) => {
        const isFailedHere = failedIndex >= 0 && index === failedIndex
        const isDone = failedIndex >= 0 ? index < failedIndex : index < effectiveIndex
        const isCurrent = failedIndex < 0 && index === effectiveIndex
        const isActive = isDone || isCurrent || isFailedHere

        return (
          <div key={step.key} className="relative flex flex-1 flex-col items-center">
            <div className="relative flex flex-col items-center justify-center">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${
                  isFailedHere
                    ? 'bg-red-500 text-white'
                    : isDone
                      ? 'bg-primary text-white'
                      : isCurrent
                        ? 'bg-primary text-white'
                        : 'bg-gray-300 text-gray-600'
                }`}
              >
                {isFailedHere ? (
                  <X className="h-4 w-4" />
                ) : isDone ? (
                  <Check className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </div>
              {isCurrent && step.Icon && (
                <div className="absolute top-10 h-16 w-16">{step.Icon}</div>
              )}
            </div>

            <div
              className={`mt-4 text-center text-xs ${
                isFailedHere ? 'font-semibold text-red-500' : 'text-gray-700'
              }`}
            >
              {step.label}
            </div>

            <div
              className={`mt-1 h-1 w-full ${
                isFailedHere ? 'bg-red-400' : isActive ? 'bg-primary' : 'bg-gray-300'
              }`}
            />
          </div>
        )
      })}
    </div>
  )
}

export default StepBar
