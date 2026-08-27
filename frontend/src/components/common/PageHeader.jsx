import React from 'react';

export default function PageHeader({ title, description, actions }) {
  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-slate-900 pb-5 mb-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">{title}</h1>
        {description && (
          <p className="text-sm text-slate-500 mt-1 font-sans">{description}</p>
        )}
      </div>
      {actions && (
        <div className="mt-4 md:mt-0 flex items-center gap-3">
          {actions}
        </div>
      )}
    </div>
  );
}
