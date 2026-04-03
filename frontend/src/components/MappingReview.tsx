import { useEffect, useState, useCallback, useRef } from 'react';
import styles from '../styles/MappingReview.module.css';
import { getResult, getAllCandidates, submitAction } from '../api';
import type { UploadResponse, FieldName, MappedItem } from '../api';
import FieldRow from './FieldRow';
import DocumentPreview from './DocumentPreview';
import AllMappedFields from './AllMappedFields';

interface MappingReviewProps {
  jobId: string;
  onReviewComplete: () => void;
}

const FIELD_ORDER: FieldName[] = [
  "lot", "pieces", "meters", "po_number", "net_weight",
  "order_number", "invoice_number", "delivered_date", "quality", "color"
];

function deriveStatus(confidence: number): 'auto' | 'review' | 'flag' {
  if (confidence >= 85) return 'auto';
  if (confidence >= 60) return 'review';
  return 'flag';
}

export default function MappingReview({ jobId, onReviewComplete }: MappingReviewProps) {
  const [data, setData] = useState<UploadResponse | null>(null);
  const [allItems, setAllItems] = useState<MappedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draggingItem, setDraggingItem] = useState<MappedItem | null>(null);
  const [focusedFieldIndex, setFocusedFieldIndex] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    Promise.all([getResult(jobId), getAllCandidates(jobId)])
      .then(([res, candidates]) => {
        // Hydrate statuses
        const fields = { ...res.fields };
        FIELD_ORDER.forEach(f => {
          if (fields[f]) {
            fields[f] = {
              ...fields[f],
              status: deriveStatus(fields[f].confidence),
              actioned: fields[f].confidence >= 85, // auto-confirm high confidence
            };
          }
        });
        res.fields = fields;
        setData(res);
        setAllItems(candidates);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || String(err));
        setLoading(false);
      });
  }, [jobId]);

  // Focus input when navigating with arrow keys
  useEffect(() => {
    if (inputRefs.current[focusedFieldIndex]) {
      inputRefs.current[focusedFieldIndex]?.focus();
      inputRefs.current[focusedFieldIndex]?.select();
    }
  }, [focusedFieldIndex]);

  const handleAction = useCallback(async (
    fieldName: FieldName,
    value: string | number | null,
    action: 'CONFIRM' | 'REASSIGN' | 'NA'
  ) => {
    try {
      await submitAction(jobId, fieldName, value, action);
      setData(prev => {
        if (!prev) return prev;
        const newFields = { ...prev.fields };
        newFields[fieldName] = {
          ...newFields[fieldName],
          value: action === 'NA' ? null : value,
          actioned: true,
          confidence: action === 'REASSIGN' ? 100 : newFields[fieldName].confidence,
          status: action === 'NA' ? 'auto' : newFields[fieldName].status,
        };
        return { ...prev, fields: newFields };
      });
    } catch (err: any) {
      alert("Failed to submit: " + (err.message || String(err)));
    }
  }, [jobId]);

  const handleDrop = useCallback(async (fieldName: FieldName, item: MappedItem) => {
    await handleAction(fieldName, item.value, 'REASSIGN');
  }, [handleAction]);

  // Keyboard navigation handler
  const handleKeyDown = useCallback((e: React.KeyboardEvent, fieldName: FieldName) => {
    const currentIndex = FIELD_ORDER.indexOf(fieldName);
    
    switch (e.key) {
      case 'Enter':
        // Confirm current field
        e.preventDefault();
        const field = data?.fields[fieldName];
        if (field) {
          handleAction(fieldName, field.value, 'CONFIRM');
          // Move to next field
          if (currentIndex < FIELD_ORDER.length - 1) {
            setFocusedFieldIndex(currentIndex + 1);
          }
        }
        break;
      
      case 'ArrowDown':
        e.preventDefault();
        if (currentIndex < FIELD_ORDER.length - 1) {
          setFocusedFieldIndex(currentIndex + 1);
        }
        break;
      
      case 'ArrowUp':
        e.preventDefault();
        if (currentIndex > 0) {
          setFocusedFieldIndex(currentIndex - 1);
        }
        break;
      
      case 'n':
      case 'N':
        // Mark as N/A
        e.preventDefault();
        handleAction(fieldName, null, 'NA');
        if (currentIndex < FIELD_ORDER.length - 1) {
          setFocusedFieldIndex(currentIndex + 1);
        }
        break;
      
      case 'r':
      case 'R':
        // Focus the input for reassign (already focused by default)
        e.preventDefault();
        inputRefs.current[currentIndex]?.select();
        break;
      
      case 'Escape':
        // Clear selection
        e.preventDefault();
        if (data?.fields[fieldName]) {
          inputRefs.current[currentIndex]?.blur();
        }
        break;
    }
  }, [data, handleAction]);

  if (loading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.spinner} />
        <p>Extracting and mapping fields…</p>
        <p className={styles.hint}>Tip: Use ↑↓ arrows to navigate, Enter to confirm, N for N/A</p>
      </div>
    );
  }

  if (error || !data) {
    return <div className={styles.errorScreen}>Error: {error}</div>;
  }

  const canSubmit = FIELD_ORDER.every(f => {
    const field = data.fields[f];
    if (field?.status === 'flag' && !field.actioned) return false;
    return true;
  });

  const flaggedCount = FIELD_ORDER.filter(f => data.fields[f]?.status === 'flag' && !data.fields[f]?.actioned).length;
  const confirmedCount = FIELD_ORDER.filter(f => data.fields[f]?.actioned).length;

  return (
    <div className={styles.reviewLayout}>
      {/* ── LEFT: PDF Preview with auto-highlighting ──────────────────────────────── */}
      <div className={styles.leftPanel}>
        <DocumentPreview 
          rawText={data.raw_text} 
          activeFieldName={FIELD_ORDER[focusedFieldIndex]}
          fieldValues={data.fields as Record<string, { value: string | number | null }>}
        />
      </div>

      {/* ── CENTER: Field mapping table ────────────────────── */}
      <div className={styles.centerPanel}>
        <div className={styles.centerHeader}>
          <div className={styles.centerTitle}>HUMAN VERIFICATION</div>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${(confirmedCount / FIELD_ORDER.length) * 100}%` }}
            />
          </div>
          <div className={styles.progressLabel}>
            {confirmedCount} / {FIELD_ORDER.length} confirmed
            {flaggedCount > 0 && <span className={styles.flagBadge}>{flaggedCount} flagged</span>}
          </div>
        </div>

        <div className={styles.keyboardHints}>
          <span>⌨️ <strong>Shortcuts:</strong> Enter = Confirm | ↑↓ = Navigate | N = N/A | R = Reassign</span>
        </div>

        <div className={styles.tableHead}>
          <div className={styles.thField}>Output Field</div>
          <div className={styles.thMapped}>Mapped Value from Packing List</div>
          <div className={styles.thConf}>Confident</div>
          <div className={styles.thAction}>Action</div>
        </div>

        <div className={styles.tableBody}>
          {FIELD_ORDER.map((fieldName, index) => {
            const fieldData = data.fields[fieldName];
            if (!fieldData) return null;
            return (
              <FieldRow
                key={fieldName}
                jobId={jobId}
                fieldName={fieldName}
                fieldData={fieldData}
                onAction={handleAction}
                onDrop={handleDrop}
                draggingItem={draggingItem}
                inputRef={(el) => { inputRefs.current[index] = el; }}
                onKeyDown={(e) => handleKeyDown(e, fieldName)}
                isFocused={index === focusedFieldIndex}
              />
            );
          })}
        </div>

        <div className={styles.submitArea}>
          {!canSubmit && (
            <div className={styles.submitWarning}>
              <span>⚠</span> Please action all flagged fields before submitting
            </div>
          )}
          <button
            className={styles.submitBtn}
            disabled={!canSubmit}
            onClick={onReviewComplete}
          >
            Submit All & Generate Excel →
          </button>
        </div>
      </div>

      {/* ── RIGHT: All Mapped Fields (drag-drop source) ────── */}
      <div className={styles.rightPanel}>
        <AllMappedFields
          items={allItems}
          onDragStart={setDraggingItem}
        />
      </div>
    </div>
  );
}
