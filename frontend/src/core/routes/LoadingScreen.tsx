import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './LoadingScreen.module.scss';

const TIPS = [
  'Tip: Check in fast at events to earn attendance badges.',
  'Tip: Organizers can post announcements to the whole club.',
  'Tip: Keep an eye on your coin balance in the shop.',
  'Tip: Volunteering hours count toward club recognition.',
];

const STEP_MS = 90;
const STEP_SIZE = 8;

export function LoadingScreen() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(0);
  const [tipIndex] = useState(() => Math.floor(Math.random() * TIPS.length));

  useEffect(() => {
    const interval = setInterval(() => {
      setProgress((p) => Math.min(100, p + STEP_SIZE));
    }, STEP_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (progress >= 100) {
      const timeout = setTimeout(() => navigate('/home', { replace: true }), 200);
      return () => clearTimeout(timeout);
    }
  }, [progress, navigate]);

  return (
    <div className={styles.screen}>
      <div className={styles.content}>
        <h1 className={styles.title}>Loading Campus League…</h1>
        <div className={styles.track} role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className={styles.fill} style={{ width: `${progress}%` }} />
        </div>
        <p className={styles.tip}>{TIPS[tipIndex]}</p>
      </div>
    </div>
  );
}
