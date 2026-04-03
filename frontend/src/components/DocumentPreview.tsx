import { useEffect, useRef, useState } from 'react';
import styles from '../styles/MappingReview.module.css';
import type { UploadResponse, FieldName } from '../api';

interface DocumentPreviewProps {
  rawText?: UploadResponse['raw_text'];
  activeSourceText?: string;
  activePage?: number;
  activeFieldName?: FieldName | null;
  fieldValues?: Record<string, { value: string | number | null }>;
}

// Map field names to search patterns in the raw text
const FIELD_SEARCH_PATTERNS: Record<FieldName, RegExp[]> = {
  lot: [/Lot\s*[:\s]+([A-Z0-9\-\.]+)/i, /Batch\s*[:\s]+([A-Z0-9\-\.]+)/i],
  pieces: [/Total\s+(?:No\.?\s*of\s*)?(?:Rolls?|Pieces?|Pcs?)[:\s]+(\d+)/i],
  meters: [/Total\s+(?:Metres?|Meters?|MTR)[:\s]+([,\d\.]+)/i],
  po_number: [/PO\s*(?:No)?\s*[:\s#]+([A-Z0-9\-\/]+)/i, /Contract\s*No\s*[:\s]+([A-Z0-9\-\/]+)/i],
  net_weight: [/Net\s*Weight\s*[:\s]+([,\d\.]+)/i, /N\s*Wt\.\s*\(KGS?\)\s*[:\s]+([,\d\.]+)/i],
  order_number: [/Order\s*No\s*[:\s]+([A-Z0-9\/\-]+)/i, /Delivery\s*No\s*[:\s]+([A-Z0-9\/\-]+)/i],
  invoice_number: [/Invoice\s*No\s*[:\s]+([A-Z0-9\.\-\/]+)/i, /D\/A\s*No\s*[:\s]+([A-Z0-9\.\-\/]+)/i],
  delivered_date: [/Date\s*[:\s]+(\d{2}[-\/]\w{3,}[-\/]\d{2,4})/i],
  quality: [/Quality\s*[:\s]+([^\n\r]+)/i, /Article\s*[:\s]+([^\n\r]+)/i],
  color: [/Color\s*[:\s]+([^\n\r\|]+)/i, /Shade\s*[:\s]+([^\n\r\|]+)/i],
};

export default function DocumentPreview({ 
  rawText, 
  activeSourceText, 
  activePage,
  activeFieldName,
  fieldValues 
}: DocumentPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLSpanElement>(null);
  const [highlightPattern, setHighlightPattern] = useState<string | null>(null);

  useEffect(() => {
    if (highlightRef.current && containerRef.current) {
      // Scroll to highlighted text behavior
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeSourceText, activePage, highlightPattern]);

  // Auto-find text to highlight based on active field
  useEffect(() => {
    if (!activeFieldName || !fieldValues || !rawText) {
      setHighlightPattern(null);
      return;
    }

    const fieldValue = fieldValues[activeFieldName]?.value;
    if (!fieldValue || typeof fieldValue !== 'string') {
      setHighlightPattern(null);
      return;
    }

    // Try to find the field value in the raw text
    const patterns = FIELD_SEARCH_PATTERNS[activeFieldName] || [];
    
    // Combine all pages text for searching
    const fullText = rawText.map(p => p.text).join('\n');
    
    // Try each pattern
    for (const pattern of patterns) {
      const match = pattern.exec(fullText);
      if (match && match[1]) {
        setHighlightPattern(match[1]);
        return;
      }
    }
    
    // Fallback: just highlight the field value itself if found in text
    if (fullText.includes(fieldValue)) {
      setHighlightPattern(fieldValue);
    } else {
      setHighlightPattern(null);
    }
  }, [activeFieldName, fieldValues, rawText]);

  if (!rawText || rawText.length === 0) {
    return (
      <div className={styles.previewPanel}>
        <div className={styles.emptyPreview}>
          No raw text data returned from backend.
        </div>
      </div>
    );
  }

  // Determine what to highlight
  const textToHighlight = activeSourceText || highlightPattern;

  return (
    <div className={styles.previewPanel} ref={containerRef}>
      <div className={styles.previewHeader}>
        <h3>DOCUMENT PREVIEW</h3>
      </div>

      <div className={styles.previewContent}>
        {rawText.map((pageData, index) => {
          let content = <span>{pageData.text}</span>;

          if (textToHighlight && pageData.text.includes(textToHighlight)) {
            // Split text and highlight all occurrences
            const parts = pageData.text.split(new RegExp(`(${textToHighlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
            content = (
              <>
                {parts.map((part, i) => 
                  part.toLowerCase() === textToHighlight.toLowerCase() ? (
                    <span 
                      key={i} 
                      ref={i === parts.findIndex(p => p.toLowerCase() === textToHighlight.toLowerCase()) ? highlightRef : null}
                      className={styles.highlightedText}
                    >
                      {part}
                    </span>
                  ) : (
                    <span key={i}>{part}</span>
                  )
                )}
              </>
            );
          }

          return (
            <div key={index} className={styles.pageBreak}>
              <div className={styles.pageLabel}>PAGE {pageData.page}</div>
              <div className={styles.rawText}>
                {content}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
