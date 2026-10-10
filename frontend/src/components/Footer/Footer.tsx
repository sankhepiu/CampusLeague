import styles from './Footer.module.scss';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <span className={styles.brand}>Campus League</span>
      <span>Built for student orgs, one quest at a time.</span>
    </footer>
  );
}
