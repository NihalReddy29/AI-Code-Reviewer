import React from "react";

interface CardProps {
  title?: string;
  subtitle?: string;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Card({ title, subtitle, badge, action, children, className = "" }: CardProps) {
  return (
    <div className={`dashboard-card ${className}`}>
      {(title || subtitle || action || badge) && (
        <div className="card-header">
          <div className="card-title-group">
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          <div className="card-actions">
            {badge}
            {action}
          </div>
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  );
}
