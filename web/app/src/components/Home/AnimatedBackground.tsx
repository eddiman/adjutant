import styles from './AnimatedBackground.module.css';

export function AnimatedBackground() {
  return (
    <div className={styles.background}>
      {/* Base gradient */}
      <div className={styles.gradient} />
      
      {/* Dot pattern */}
      <div className={styles.dots} />
      
      {/* Floating blobs */}
      <div className={styles.blobContainer}>
        <div className={`${styles.blob} ${styles.blob1}`} />
        <div className={`${styles.blob} ${styles.blob2}`} />
        <div className={`${styles.blob} ${styles.blob3}`} />
        <div className={`${styles.blob} ${styles.blob4}`} />
        <div className={`${styles.blob} ${styles.blob5}`} />
      </div>
      
    </div>
  );
}
