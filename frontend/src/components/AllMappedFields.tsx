import styles from '../styles/AllMappedFields.module.css';
import type { MappedItem } from '../api';

interface AllMappedFieldsProps {
  items: MappedItem[];
  onDragStart: (item: MappedItem) => void;
}

const CANONICAL_LABELS: Record<string, string> = {
  lot: "Lot / Batch",
  pieces: "Pieces / Rolls",
  meters: "Meters",
  po_number: "PO Number",
  net_weight: "Net Weight",
  order_number: "Order Number",
  invoice_number: "Invoice Number",
  delivered_date: "Delivered Date",
  quality: "Quality",
  color: "Color",
};

export default function AllMappedFields({ items, onDragStart }: AllMappedFieldsProps) {
  const canonical = items.filter(i => i.is_canonical);
  const unidentified = items.filter(i => !i.is_canonical);

  const handleDragStart = (e: React.DragEvent, item: MappedItem) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('application/json', JSON.stringify(item));
    onDragStart(item);
  };

  const renderChip = (item: MappedItem, idx: number) => (
    <div
      key={`${item.field}-${idx}`}
      className={`${styles.chip} ${item.is_confirmed ? styles.chipConfirmed : ''} ${!item.is_canonical ? styles.chipUnidentified : ''}`}
      draggable
      onDragStart={(e) => handleDragStart(e, item)}
      title={`Drag to assign to a field\nSource field: ${item.field}`}
    >
      <span className={styles.chipLabel}>
        {CANONICAL_LABELS[item.field] ?? item.label}
      </span>
      <span className={styles.chipValue}>{item.value || '—'}</span>
      <span className={styles.dragHandle}>⠿</span>
    </div>
  );

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>ALL MAPPED FIELDS</span>
        <span className={styles.panelCount}>{items.length} values</span>
      </div>
      <p className={styles.hint}>Drag any chip onto a field row to assign that value.</p>

      {canonical.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Identified Fields</div>
          {canonical.map(renderChip)}
        </div>
      )}

      {unidentified.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Unidentified / Extra</div>
          {unidentified.map(renderChip)}
        </div>
      )}

      {items.length === 0 && (
        <div className={styles.empty}>No extracted values available.</div>
      )}
    </div>
  );
}
