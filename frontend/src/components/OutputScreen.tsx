import { useEffect, useState } from 'react';
import styles from '../styles/OutputScreen.module.css';
import { getResult, downloadExcel } from '../api';
import type { UploadResponse } from '../api';

interface OutputScreenProps {
  jobId: string;
  onReset: () => void;
}

export default function OutputScreen({ jobId, onReset }: OutputScreenProps) {
  const [data, setData] = useState<UploadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    getResult(jobId)
      .then(res => {
        setData(res);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || String(err));
        setLoading(false);
      });
  }, [jobId]);

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      await downloadExcel(jobId);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return <div className={styles.centerMessage}>Loading final results...</div>;
  }

  if (error || !data) {
    return <div className={styles.centerMessage}>Error: {error}</div>;
  }

  return (
    <div className={styles.outputContainer}>
      <div className={styles.headerRow}>
        <h2>Extraction Complete</h2>
        <div className={styles.headerDetails}>
          <span>Job ID: {jobId}</span>
        </div>
      </div>

      <div className={styles.summaryTable}>
        <div className={styles.tableHeader}>
          <div className={styles.colField}>Field</div>
          <div className={styles.colValue}>Confirmed Value</div>
          <div className={styles.colSource}>Source</div>
        </div>
        
        {Object.entries(data.fields).map(([fieldName, fieldData]) => (
          <div key={fieldName} className={styles.tableRow}>
            <div className={styles.colField}>{fieldName.replace('_', ' ').toUpperCase()}</div>
            <div className={styles.colValue}>
              {fieldData.value !== null ? fieldData.value : <span className={styles.noValue}>N/A</span>}
            </div>
            <div className={styles.colSource}>
              {fieldData.mapping_source}
            </div>
          </div>
        ))}
      </div>

      <div className={styles.actionFooter}>
        <button className={styles.secondaryBtn} onClick={onReset}>
          Process another file
        </button>
        <button 
          className={styles.primaryBtn} 
          onClick={handleDownload}
          disabled={downloading}
        >
          {downloading ? "Downloading..." : "Download Excel (.xlsx)"}
        </button>
      </div>
    </div>
  );
}
