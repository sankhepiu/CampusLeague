import { useEffect, useState } from 'react';
import QRCodeLib from 'qrcode';
import { Spinner } from '../Spinner/Spinner';
import styles from './QRCode.module.scss';

interface QRCodeProps {
  /** The opaque token to encode. Never interpreted or parsed client-side —
   * it's rendered exactly as given, the same way a check-in scanner reads it. */
  value: string;
  size?: number;
}

export function QRCode({ value, size = 180 }: QRCodeProps) {
  const [result, setResult] = useState<{ forValue: string; dataUrl: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    QRCodeLib.toDataURL(value, {
      width: size,
      margin: 1,
      color: { dark: '#0b0a1a', light: '#f2efff' },
    })
      .then((dataUrl) => {
        if (!cancelled) setResult({ forValue: value, dataUrl });
      })
      .catch(() => {
        if (!cancelled) setResult(null);
      });
    return () => {
      cancelled = true;
    };
  }, [value, size]);

  // Derived rather than reset via setState: a stale result (still showing
  // the previous value's QR while the new one loads) is simply not "current".
  const dataUrl = result?.forValue === value ? result.dataUrl : null;

  if (!dataUrl) {
    return (
      <div className={styles.frame} style={{ width: size, height: size }}>
        <Spinner label="Generating QR code" />
      </div>
    );
  }

  return (
    <div className={styles.frame} style={{ width: size, height: size }}>
      <img src={dataUrl} alt="Membership check-in QR code" width={size} height={size} />
    </div>
  );
}
