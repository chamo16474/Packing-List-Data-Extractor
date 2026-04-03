import { useState, useRef, useEffect } from 'react';
import styles from '../styles/UploadScreen.module.css';
import { uploadFile } from '../api';

interface UploadScreenProps {
  onUploadSuccess: (jobId: string) => void;
}

export default function UploadScreen({ onUploadSuccess }: UploadScreenProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [supplierName, setSupplierName] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [processingJobId, setProcessingJobId] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setIsDragging(true);
    else if (e.type === 'dragleave') setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await processFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      await processFile(e.target.files[0]);
    }
  };

  const processFile = async (file: File) => {
    if (file.type !== 'application/pdf') {
       setError("Only PDF files are supported");
       return;
    }
    
    setError(null);
    setLoading(true);
    
    try {
      setLogs(["Uploading document..."]);
      const res = await uploadFile(file, supplierName);
      
      setProcessingJobId(res.job_id);
      
      const eventSource = new EventSource(`http://localhost:8080/stream/${res.job_id}`);
      
      eventSource.onmessage = (e) => {
        if (e.data === "DONE") {
          eventSource.close();
          setLoading(false);
          setProcessingJobId(null);
          onUploadSuccess(res.job_id);
        } else {
          setLogs((prev) => [...prev, e.data]);
        }
      };
      
      eventSource.onerror = (e) => {
          console.error("SSE Error", e);
          setError("Lost connection or stream ended unexpectedly.");
          eventSource.close();
          setLoading(false);
          setProcessingJobId(null);
      };

    } catch (err: any) {
      setError(file.name + ": " + (err.message || String(err)));
      setLoading(false);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className={styles.uploadContainer}>
      <div className={styles.uploadCard}>
        <div className={styles.header}>
          <h2>Upload Packing List</h2>
          <p>Extract canonical fields via AI and Template matching.</p>
        </div>

        <div className={styles.inputGroup}>
          <label htmlFor="supplier">Supplier Override (Optional)</label>
          <input 
            id="supplier"
            type="text" 
            placeholder="e.g. Acme Corp" 
            value={supplierName}
            onChange={(e) => setSupplierName(e.target.value)}
            disabled={loading}
          />
        </div>

        <div 
          className={`${styles.dropZone} ${isDragging ? styles.dragActive : ''} ${loading ? styles.loading : ''}`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => !loading && fileInputRef.current?.click()}
        >
          <input 
            type="file" 
            accept="application/pdf"
            ref={fileInputRef}
            onChange={handleChange}
            className={styles.hiddenInput}
            disabled={loading}
          />
          
          {processingJobId ? (
            <div className={styles.terminalWindow}>
              <div className={styles.terminalHeader}>
                <div className={styles.dots}>
                  <span className={styles.dotRed}></span>
                  <span className={styles.dotYellow}></span>
                  <span className={styles.dotGreen}></span>
                </div>
                Processing Logs
              </div>
              <div className={styles.terminalBody}>
                {logs.map((log, i) => (
                  <div key={i} className={styles.logLine}>
                    <span className={styles.prompt}>$</span> {log}
                  </div>
                ))}
                <div className={styles.blinkingCursor}>_</div>
                <div ref={logEndRef} />
              </div>
            </div>
          ) : loading ? (
            <div className={styles.spinnerWrapper}>
              <div className={styles.spinner}></div>
              <span>Preparing Upload...</span>
            </div>
          ) : (
            <div className={styles.dropZoneContent}>
              <span className={styles.dropIcon}>📁</span>
              <span className={styles.dropTitle}>Drag & Drop PDF here</span>
              <span className={styles.dropSub}>or click to browse</span>
            </div>
          )}
        </div>

        {error && (
          <div className={styles.errorBanner}>
            <span className={styles.errorIcon}>⚠</span>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
