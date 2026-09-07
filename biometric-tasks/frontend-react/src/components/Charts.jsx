import React from 'react';

export const TrendChart = ({ labels, vals, color }) => {
  const maxVal = Math.max(...vals, 1);
  return (
    <>
      <div className="trend-dots">
        {vals.map((v, idx) => (
          <div 
            key={idx} 
            className="trend-bar" 
            style={{ 
              height: `${Math.round((v / maxVal) * 52)}px`, 
              background: color, 
              opacity: v === 0 ? 0.2 : 0.8 
            }} 
          />
        ))}
      </div>
      <div className="trend-labels">
        {labels.map((l, idx) => (
          <div key={idx} className="trend-label">{l}</div>
        ))}
      </div>
    </>
  );
};

export const BarChart = ({ labels, colors, vals }) => {
  const maxVal = Math.max(...vals, 1);
  return (
    <>
      {labels.map((l, idx) => (
        <div key={idx} className="chart-row">
          <div className="chart-label">{l.length > 8 ? l.substring(0, 7) + '…' : l}</div>
          <div className="chart-bar-bg">
            <div 
              className="chart-bar" 
              style={{ 
                width: `${Math.round((vals[idx] / maxVal) * 100)}%`, 
                background: colors[idx] || colors[0], 
                opacity: 0.7 
              }}
            >
              <span style={{ color: 'rgba(255,255,255,0.9)' }}>{vals[idx]}</span>
            </div>
          </div>
        </div>
      ))}
    </>
  );
};
