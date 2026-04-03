import { useState } from 'react';
import styles from './styles/App.module.css';
import UploadScreen from './components/UploadScreen';
import MappingReview from './components/MappingReview';
import OutputScreen from './components/OutputScreen';

export type ScreenState = 'UPLOAD' | 'REVIEW' | 'OUTPUT';

function App() {
  const [currentScreen, setCurrentScreen] = useState<ScreenState>('UPLOAD');
  const [jobId, setJobId] = useState<string | null>(null);

  const resetFlow = () => {
    setJobId(null);
    setCurrentScreen('UPLOAD');
  };

  return (
    <div className={styles.appContainer}>
      <header className={styles.appHeader}>
        <div className={styles.brand}>
          <h1>Extraction Platform</h1>
          <span className={styles.versionBadge}>v2.0</span>
        </div>
      </header>
      
      <main className={styles.mainContent}>
        {currentScreen === 'UPLOAD' && (
          <UploadScreen 
            onUploadSuccess={(id) => {
              setJobId(id);
              setCurrentScreen('REVIEW');
            }} 
          />
        )}
        
        {currentScreen === 'REVIEW' && jobId && (
          <MappingReview 
            jobId={jobId} 
            onReviewComplete={() => setCurrentScreen('OUTPUT')} 
          />
        )}
        
        {currentScreen === 'OUTPUT' && jobId && (
          <OutputScreen 
            jobId={jobId} 
            onReset={resetFlow} 
          />
        )}
      </main>
    </div>
  );
}

export default App;
