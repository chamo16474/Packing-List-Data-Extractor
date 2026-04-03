import { useState, useEffect, forwardRef } from 'react';
import styles from '../styles/MappingReview.module.css';
import type { ExtractedField, FieldName, MappedItem } from '../api';

interface FieldRowProps {
  jobId?: string;
  fieldName: FieldName;
  fieldData: ExtractedField;
  onAction: (fieldName: FieldName, value: string | number | null, action: 'CONFIRM' | 'REASSIGN' | 'NA') => Promise<void>;
  onDrop: (fieldName: FieldName, item: MappedItem) => Promise<void>;
  draggingItem: MappedItem | null;
  inputRef?: (el: HTMLInputElement | null) => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  isFocused?: boolean;
}

const FIELD_LABELS: Record<string, string> = {
  lot: "LOT",
  pieces: "PIECES",
  meters: "METERS",
  po_number: "PO NUMBER",
  net_weight: "NET WEIGHT",
  order_number: "ORDER NUMBER",
  invoice_number: "INVOICE NUMBER",
  delivered_date: "DELIVERED DATE",
  quality: "QUALITY",
  color: "COLOR",
};

const FieldRow = forwardRef<HTMLInputElement, FieldRowProps>(function FieldRow(
  { fieldName, fieldData, onAction, onDrop, draggingItem, inputRef, onKeyDown, isFocused },
  ref
) {
  const [editingValue, setEditingValue] = useState<string>(
    fieldData.value !== null && fieldData.value !== undefined ? String(fieldData.value) : ""
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  // Keep local input in sync when parent updates value (e.g. after drag-drop reassign)
  useEffect(() => {
    setEditingValue(fieldData.value !== null && fieldData.value !== undefined ? String(fieldData.value) : "");
  }, [fieldData.value]);

  const handleConfirm = async () => {
    setIsSubmitting(true);
    try {
      await onAction(fieldName, editingValue || null, 'CONFIRM');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (onKeyDown) {
      onKeyDown(e);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      handleConfirm();
    }
  };

  // ── Drag-drop handlers ─────────────────────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    // Only clear if leaving the row entirely (not entering a child)
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    try {
      const raw = e.dataTransfer.getData('application/json');
      if (!raw) return;
      const item: MappedItem = JSON.parse(raw);
      setEditingValue(item.value);
      await onDrop(fieldName, item);
    } catch {
      // Ignore malformed drops
    }
  };

  // ── Derived state ─────────────────────────────────────────────────────
  const isConfirmed = !!fieldData.actioned && fieldData.value !== null && fieldData.value !== undefined;
  const isNA = !!fieldData.actioned && (fieldData.value === null || fieldData.value === undefined);
  const isFlagged = fieldData.status === 'flag' && !fieldData.actioned;

  const conf = fieldData.confidence ?? 0;
  const confPct = Math.round(conf);
  const confClass =
    conf >= 85 ? styles.confHigh :
    conf >= 60 ? styles.confMid :
    styles.confLow;

  let rowClass = styles.fieldRow;
  if (isConfirmed) rowClass += ` ${styles.rowConfirmed}`;
  else if (isNA)   rowClass += ` ${styles.rowNA}`;
  else if (isFlagged) rowClass += ` ${styles.rowFlagged}`;
  if (isDragOver)  rowClass += ` ${styles.rowDragOver}`;
  if (isFocused)   rowClass += ` ${styles.rowFocused}`;

  return (
    <div
      className={rowClass}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Col 1: Output field label */}
      <div className={styles.colField}>
        <span className={styles.fieldLabel}>{FIELD_LABELS[fieldName] ?? fieldName.toUpperCase()}</span>
        {isFlagged && <span className={styles.flagDot} title="Needs review">●</span>}
        {isConfirmed && <span className={styles.confirmDot} title="Confirmed">✓</span>}
      </div>

      {/* Col 2: Mapped value input + drop zone */}
      <div className={`${styles.colMapped} ${isDragOver ? styles.dropZoneActive : ''}`}>
        {isDragOver && draggingItem && (
          <div className={styles.dropHint}>Drop "{draggingItem.value}"</div>
        )}
        <input
          ref={inputRef || ref}
          className={`${styles.mappedInput} ${isConfirmed ? styles.inputConfirmed : ''}`}
          type="text"
          value={editingValue}
          onChange={e => setEditingValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isSubmitting}
          placeholder={isNA ? "N/A — not present" : "Enter or drop a value..."}
        />
      </div>

      {/* Col 3: Confidence badge */}
      <div className={styles.colConf}>
        <div className={`${styles.confBadge} ${confClass}`}>
          {isNA ? '—' : `${confPct}%`}
        </div>
      </div>

      {/* Col 4: Confirm button */}
      <div className={styles.colAction}>
        <button
          className={`${styles.confirmBtn} ${isConfirmed ? styles.confirmedBtn : ''}`}
          onClick={handleConfirm}
          disabled={isSubmitting}
          title="Press Enter to confirm"
        >
          {isConfirmed ? '✓ Confirmed' : 'confirm'}
        </button>
      </div>
    </div>
  );
});

export default FieldRow;
