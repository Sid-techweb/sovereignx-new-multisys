import React from 'react';

export default function PageHeader({ title, description, actions }) {
  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-console-line pb-4 mb-4">
      <div>
        <h1 className="text-[26px] font-semibold tracking-tight text-console-text leading-tight">{title}</h1>
        {description && (
          <p className="text-sm text-console-text2 mt-1">{description}</p>
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
