import type { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  message?: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({ title, message, description, action, icon }: EmptyStateProps) {
  const displayMsg = description ?? message;
  return (
    <div className="empty-state-card" role="status">
      <div className="empty-state-icon" aria-hidden="true">
        {icon || (
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="4" width="20" height="16" rx="3" />
            <path d="M8 10h8M8 14h4" />
          </svg>
        )}
      </div>
      <h4 className="empty-state-title">{title}</h4>
      {displayMsg && <p className="empty-state-message">{displayMsg}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}
