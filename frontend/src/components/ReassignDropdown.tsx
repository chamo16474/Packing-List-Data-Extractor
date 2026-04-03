import { useEffect, useState, useRef } from 'react';
import { getCandidates } from '../api';
import type { Candidate, FieldName } from '../api';

interface ReassignDropdownProps {
  jobId: string;
  fieldName: FieldName;
  onSelect: (value: string | number) => void;
  onClose: () => void;
}

export default function ReassignDropdown({ jobId, fieldName, onSelect, onClose }: ReassignDropdownProps) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [manualValue, setManualValue] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    getCandidates(jobId, fieldName)
      .then(res => {
        if (active) {
          setCandidates(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(true);
          setLoading(false);
        }
      });
    return () => { active = false; };
  }, [jobId, fieldName]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  return (
    <div 
      ref={dropdownRef}
      style={{
        position: 'absolute',
        top: '100%',
        right: 0,
        zIndex: 10,
        marginTop: '4px',
        backgroundColor: 'var(--bg-color)',
        border: '1px solid var(--border-strong)',
        borderRadius: '2px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        minWidth: '240px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{
        padding: '8px 12px',
        backgroundColor: 'var(--row-hover)',
        borderBottom: '1px solid var(--border-color)',
        fontSize: '11px',
        fontWeight: '600',
        color: 'var(--text-muted)',
        textTransform: 'uppercase'
      }}>
        Top Candidates
      </div>

      <div style={{ padding: '8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {loading ? (
          <div style={{ padding: '8px', fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center' }}>
            Loading...
          </div>
        ) : error || candidates.length === 0 ? (
          <div style={{ padding: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: 'var(--status-flag)' }}>Fallback manual entry:</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                type="text" 
                value={manualValue} 
                onChange={(e) => setManualValue(e.target.value)}
                style={{ flex: 1, padding: '4px 8px', fontSize: '13px' }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && manualValue) onSelect(manualValue);
                }}
              />
              <button 
                onClick={() => manualValue && onSelect(manualValue)}
                style={{
                  backgroundColor: 'var(--primary)',
                  color: 'white',
                  padding: '4px 8px',
                  borderRadius: '2px',
                  fontSize: '12px'
                }}
              >
                Set
              </button>
            </div>
          </div>
        ) : (
          candidates.map((c, i) => (
            <button
              key={i}
              onClick={() => onSelect(c.value)}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '8px 12px',
                textAlign: 'left',
                fontSize: '13px',
                fontFamily: 'var(--font-mono)',
                backgroundColor: 'transparent',
                transition: 'background 0.1s',
                borderRadius: '2px'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--row-hover)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <span>{c.value}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{c.confidence}%</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
